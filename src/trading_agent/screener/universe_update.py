from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.io import read_json, write_json
from trading_agent.data.universe import parse_universe
from trading_agent.screener.factor_gate import CandidateEvaluation


def _tier_of(meta: dict[str, dict], symbol: str) -> str:
    entry = meta.get(symbol) or {}
    return str(entry.get("tier") or "watch")


def _assign_ranks(score_map: dict[str, float | None]) -> dict[str, int]:
    """Rank 1 = highest factor_score. Symbols with no score are ranked last (worst)."""
    scored = sorted(
        [(s, sc) for s, sc in score_map.items() if sc is not None],
        key=lambda item: item[1],
        reverse=True,
    )
    ranks: dict[str, int] = {s: i for i, (s, _sc) in enumerate(scored, start=1)}
    next_rank = len(scored) + 1
    for symbol, score in score_map.items():
        if score is None:
            ranks[symbol] = next_rank
            next_rank += 1
    return ranks


@dataclass(frozen=True)
class UniverseUpdatePlan:
    added: list[dict[str, Any]] = field(default_factory=list)          # new symbols to append
    meta_score_updates: dict[str, dict[str, Any]] = field(default_factory=dict)  # screen_score/rank for all
    demoted: list[str] = field(default_factory=list)                   # symbols → tier passive
    skipped: list[dict[str, Any]] = field(default_factory=list)        # discovered not added (audit)
    effective_count_before: int = 0
    effective_count_after: int = 0

    @property
    def added_symbols(self) -> list[str]:
        return [r["symbol"] for r in self.added]


def plan_universe_update(
    *,
    existing_symbols: list[str],
    existing_meta: dict[str, dict],
    evaluations: dict[str, CandidateEvaluation],
    discovered: list[dict[str, Any]],
    max_adds_per_week: int,
    universe_max: int,
    protected: set[str],
) -> UniverseUpdatePlan:
    """Pure planner for the weekly universe update (add-only + rate-limit + cap-demote + re-rank).

    - **Add-only, rate-limited**: only *new* discovered symbols that pass the factor gate are
      eligible; the top ``max_adds_per_week`` by ``factor_score`` are added, the rest skipped.
    - **Re-rank (meta only)**: every existing + added symbol with a score gets a ``screen_score`` /
      ``screen_rank`` written to ``universe_meta.json``. ``universe.txt`` is never reordered here.
    - **Cap-demote**: the *effective* research set = symbols whose tier is not ``passive``. When it
      exceeds ``universe_max``, the lowest-ranked, **non-protected, currently-watch** symbols are
      demoted to ``tier:passive`` (excluded from AI layers but kept in the file — never deleted).
      Protected anchors (pins/benchmarks) and freshly added names are never demoted.
    """
    existing_set = set(existing_symbols)
    score_map: dict[str, float | None] = {}
    for symbol in existing_symbols:
        ev = evaluations.get(symbol)
        score_map[symbol] = ev.factor_score if ev else None

    # --- adds: new + gate-passed, ranked by score, capped per week ---
    discovered_by_symbol = {str(r.get("symbol") or "").upper(): r for r in discovered}
    eligible: list[tuple[str, float]] = []
    skipped: list[dict[str, Any]] = []
    for symbol, rec in discovered_by_symbol.items():
        if not symbol:
            continue
        if symbol in existing_set:
            skipped.append({"symbol": symbol, "reason": "already_in_universe"})
            continue
        ev = evaluations.get(symbol)
        if ev is None or not ev.passed_gate:
            skipped.append({"symbol": symbol, "reason": ev.reject_reason if ev else "not_evaluated"})
            continue
        eligible.append((symbol, ev.factor_score if ev.factor_score is not None else float("-inf")))

    eligible.sort(key=lambda item: item[1], reverse=True)
    added: list[dict[str, Any]] = []
    for rank_pos, (symbol, score) in enumerate(eligible):
        if rank_pos >= max(0, max_adds_per_week):
            skipped.append({"symbol": symbol, "reason": "rate_limited"})
            continue
        rec = discovered_by_symbol[symbol]
        ev = evaluations[symbol]
        added.append(
            {
                "symbol": symbol,
                "factor_score": ev.factor_score,
                "theme": rec.get("theme", "unknown"),
                "thesis": rec.get("thesis"),
                "conviction": rec.get("conviction"),
            }
        )
        score_map[symbol] = ev.factor_score

    added_set = {r["symbol"] for r in added}

    # --- re-rank: screen_score/screen_rank for everyone scored ---
    ranks = _assign_ranks(score_map)
    meta_score_updates: dict[str, dict[str, Any]] = {
        symbol: {"screen_score": score_map[symbol], "screen_rank": ranks[symbol]}
        for symbol in score_map
    }

    # --- cap-demote: bound the effective (non-passive) research set ---
    effective_before = [s for s in existing_symbols if _tier_of(existing_meta, s) != "passive"]
    effective_after = list(effective_before) + list(added_set)
    demoted: list[str] = []
    overflow = len(effective_after) - universe_max
    if overflow > 0:
        demotion_pool = [
            s
            for s in effective_before
            if s not in protected
            and s not in added_set
            and _tier_of(existing_meta, s) == "watch"
        ]
        # sorted ascending by rank (1 = best); the worst are at the end → demote those.
        demotion_pool.sort(key=lambda s: (ranks.get(s, 1_000_000), s))
        demoted = demotion_pool[-overflow:]

    return UniverseUpdatePlan(
        added=added,
        meta_score_updates=meta_score_updates,
        demoted=demoted,
        skipped=skipped,
        effective_count_before=len(effective_before),
        effective_count_after=len(effective_after) - len(demoted),
    )


def _backup(run_dir: Path, universe_path: Path, meta_path: Path) -> None:
    backup_dir = run_dir / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    if universe_path.exists():
        (backup_dir / "universe.txt").write_text(universe_path.read_text(encoding="utf-8"), encoding="utf-8")
    if meta_path.exists():
        (backup_dir / "universe_meta.json").write_text(meta_path.read_text(encoding="utf-8"), encoding="utf-8")


def apply_universe_update(
    *,
    config_dir: Path,
    run_dir: Path,
    run_date: str,
    plan: UniverseUpdatePlan,
) -> dict[str, Any]:
    """Write the plan to ``universe.txt`` (append-only) + ``universe_meta.json``, after backing up.

    Never deletes a line from ``universe.txt`` and never reorders it — only appends the new symbols
    under a dated header. ``universe_meta.json`` gets screen_score/rank for everyone, new entries for
    adds, and ``tier:passive`` for demotions.
    """
    universe_path = config_dir / "universe.txt"
    meta_path = config_dir / "universe_meta.json"
    run_dir.mkdir(parents=True, exist_ok=True)
    _backup(run_dir, universe_path, meta_path)

    # --- universe.txt: append-only ---
    if plan.added:
        existing_text = universe_path.read_text(encoding="utf-8") if universe_path.exists() else ""
        if existing_text and not existing_text.endswith("\n"):
            existing_text += "\n"
        block = f"\n# --- Added by weekly screener {run_date} ---\n" + "".join(
            f"{r['symbol']}\n" for r in plan.added
        )
        universe_path.write_text(existing_text + block, encoding="utf-8")

    # --- universe_meta.json: re-rank + new entries + demotions ---
    meta: dict[str, Any] = {}
    if meta_path.exists():
        try:
            loaded = read_json(meta_path)
            if isinstance(loaded, dict):
                meta = loaded
        except Exception:
            meta = {}

    for rec in plan.added:
        symbol = rec["symbol"]
        entry = dict(meta.get(symbol) or {})
        entry.update(
            {
                "tier": "watch",
                "theme": rec.get("theme", "unknown"),
                "source": "serenity_screen",
                "added_date": run_date,
            }
        )
        meta[symbol] = entry

    for symbol, scores in plan.meta_score_updates.items():
        if symbol.startswith("_"):
            continue
        entry = dict(meta.get(symbol) or {})
        entry["screen_score"] = scores.get("screen_score")
        entry["screen_rank"] = scores.get("screen_rank")
        meta[symbol] = entry

    for symbol in plan.demoted:
        entry = dict(meta.get(symbol) or {})
        entry["tier"] = "passive"
        entry["demoted_date"] = run_date
        entry["demoted_by"] = "weekly_screener_cap"
        meta[symbol] = entry

    write_json(meta_path, meta)

    return {
        "added": plan.added_symbols,
        "demoted": plan.demoted,
        "backup_dir": str(run_dir / "backup"),
    }


def write_audit(
    *,
    run_dir: Path,
    run_date: str,
    plan: UniverseUpdatePlan,
    applied: bool,
) -> tuple[Path, Path]:
    """Write ``universe_change.{json,md}`` — who/why/score/who-was-demoted."""
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "applied": applied,
        "added": plan.added,
        "demoted": plan.demoted,
        "skipped": plan.skipped,
        "effective_count_before": plan.effective_count_before,
        "effective_count_after": plan.effective_count_after,
    }
    json_path = run_dir / "universe_change.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        f"# Weekly universe change — {run_date}",
        "",
        f"- mode: {'APPLIED' if applied else 'report-only (dry-run)'}",
        f"- effective set: {plan.effective_count_before} → {plan.effective_count_after}",
        "",
        "## Added",
    ]
    if plan.added:
        lines.append("| symbol | factor_score | theme | thesis |")
        lines.append("|---|---:|---|---|")
        for r in plan.added:
            lines.append(
                f"| {r['symbol']} | {r.get('factor_score')} | {r.get('theme','')} | {str(r.get('thesis') or '').replace('|','/')} |"
            )
    else:
        lines.append("_(none this week)_")
    lines += ["", "## Demoted to passive (cap)"]
    lines.append(", ".join(plan.demoted) if plan.demoted else "_(none)_")
    lines += ["", "## Skipped discoveries"]
    if plan.skipped:
        for s in plan.skipped:
            lines.append(f"- {s.get('symbol')}: {s.get('reason')}")
    else:
        lines.append("_(none)_")
    md_path = run_dir / "universe_change.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path
