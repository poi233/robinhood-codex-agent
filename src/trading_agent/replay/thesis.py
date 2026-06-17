from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json
from trading_agent.portfolio.target import load_theme_map
from trading_agent.replay.forward_returns import (
    DEFAULT_HORIZONS,
    PriceLoader,
    compute_forward_return_records,
    default_price_loader,
)

# K3 — Thesis Tracker. Answers "which theses actually make money", not just "which ticker did". For
# each scored candidate it derives a set of thesis tags (universe_meta theme + the DSA primary_theme
# + DSA strategy_matches), joins them to E1 forward returns, and aggregates win rate / mean return
# per thesis. Read-only; tags are derived from already-persisted artifacts (no new capture needed).


def _norm(tag: Any) -> str | None:
    s = str(tag or "").strip().upper().replace(" ", "_")
    return s or None


def thesis_tags_for(symbol: str, dsa_signal: dict[str, Any], theme_map: dict[str, str]) -> list[str]:
    """Thesis tags for one symbol: universe_meta theme + DSA primary_theme + DSA strategy_matches."""
    tags: list[str] = []
    meta_theme = _norm(theme_map.get(symbol.upper()))
    if meta_theme:
        tags.append(meta_theme)
    if isinstance(dsa_signal, dict):
        pt = _norm(dsa_signal.get("primary_theme"))
        if pt:
            tags.append(pt)
        for m in dsa_signal.get("strategy_matches") or []:
            nm = _norm(m)
            if nm:
                tags.append(nm)
    # de-dup, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _dsa_signals_for(agent_root: Path, run_date: str) -> dict[str, Any]:
    path = build_runtime_paths(agent_root, run_date=run_date).dsa_signals_path
    if not path.exists():
        return {}
    payload = read_json(path)
    block = payload.get("symbol_signals") if isinstance(payload, dict) else None
    return block if isinstance(block, dict) else {}


def thesis_attribution(
    agent_root: Path,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    since: str | None = None,
    until: str | None = None,
    price_loader: PriceLoader = default_price_loader,
    min_count: int = 3,
) -> dict[str, Any]:
    """Per-thesis forward-return win rate + mean at the primary horizon. Read-only."""
    records = compute_forward_return_records(agent_root, horizons=horizons, since=since, until=until, price_loader=price_loader)
    theme_map = load_theme_map(build_runtime_paths(agent_root).config_dir)
    primary_h = horizons[0] if horizons else 1

    # cache DSA signals per run date
    dsa_cache: dict[str, dict[str, Any]] = {}
    by_thesis: dict[str, list[float]] = defaultdict(list)
    for rec in records:
        ret = rec.returns.get(primary_h)
        if ret is None:
            continue
        dsa = dsa_cache.setdefault(rec.run_date, _dsa_signals_for(agent_root, rec.run_date))
        tags = thesis_tags_for(rec.symbol, dsa.get(rec.symbol.upper()) or dsa.get(rec.symbol) or {}, theme_map)
        for tag in tags:
            by_thesis[tag].append(ret)

    rows = []
    for thesis, rets in by_thesis.items():
        if len(rets) < min_count:
            continue
        rows.append({
            "thesis": thesis,
            "count": len(rets),
            "win_rate": round(sum(1 for r in rets if r > 0) / len(rets), 4),
            "mean_return": round(sum(rets) / len(rets), 6),
        })
    rows.sort(key=lambda r: (r["win_rate"], r["mean_return"]), reverse=True)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "primary_horizon": primary_h,
        "sample_size": len([r for r in records if r.returns.get(primary_h) is not None]),
        "min_count": min_count,
        "theses": rows,
        "note": "Read-only thesis win-rate attribution. Small samples are noisy — wait for 15-30 run dates.",
    }


def default_thesis_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "thesis_attribution.json"


def default_thesis_md_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "thesis_attribution.md"


def format_thesis_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Thesis Attribution (K3)",
        "",
        f"_Generated {report['generated_at']}._ horizon: {report['primary_horizon']}d · "
        f"samples: {report['sample_size']} · min count: {report['min_count']}",
        "",
        "> Which theses actually make money (not just which ticker). Read-only; small samples noisy.",
        "",
    ]
    if not report["theses"]:
        lines.append("_No thesis has enough samples yet._")
        return "\n".join(lines) + "\n"
    for r in report["theses"]:
        lines.append(f"- **{r['thesis']}**: win {r['win_rate'] * 100:.0f}%  ·  mean "
                     f"{r['mean_return'] * 100:+.2f}%  ·  n={r['count']}")
    return "\n".join(lines) + "\n"


def write_thesis_attribution(
    agent_root: Path,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    since: str | None = None,
    until: str | None = None,
    price_loader: PriceLoader = default_price_loader,
) -> tuple[Path, Path]:
    report = thesis_attribution(agent_root, horizons=horizons, since=since, until=until, price_loader=price_loader)
    json_path = default_thesis_path(agent_root)
    md_path = default_thesis_md_path(agent_root)
    write_json(json_path, report)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(format_thesis_markdown(report), encoding="utf-8")
    return json_path, md_path
