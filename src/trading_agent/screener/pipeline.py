from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from trading_agent.core.config import load_env_files
from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json
from trading_agent.data.universe import parse_active_watchlist, parse_universe
from trading_agent.features.factor_store import BENCHMARK_SYMBOLS
from trading_agent.screener.config import load_screener_config
from trading_agent.screener.discover import run_discovery
from trading_agent.screener.factor_gate import validate_candidates
from trading_agent.screener.paths import screener_run_dir
from trading_agent.screener.universe_update import (
    apply_universe_update,
    plan_universe_update,
    write_audit,
)


def _resolve_will_apply(*, enabled: bool, dry_run: bool, apply: bool | None) -> bool:
    """Effective write mode. ``--dry-run`` wins; else ``--apply``; else follow the flag."""
    if dry_run:
        return False
    if apply is not None:
        return apply
    return enabled


def _read_existing(config_dir: Path) -> tuple[list[str], dict[str, dict]]:
    universe_path = config_dir / "universe.txt"
    meta_path = config_dir / "universe_meta.json"
    symbols = parse_universe(universe_path) if universe_path.exists() else []
    meta: dict[str, dict] = {}
    if meta_path.exists():
        try:
            loaded = read_json(meta_path)
            if isinstance(loaded, dict):
                meta = {k: v for k, v in loaded.items() if isinstance(v, dict)}
        except Exception:
            meta = {}
    return symbols, meta


def _protected_symbols(config_dir: Path) -> set[str]:
    """Never demote pins (the active_watchlist anchors) or benchmark symbols."""
    protected = {s.upper() for s in BENCHMARK_SYMBOLS}
    try:
        protected |= {s.upper() for s in parse_active_watchlist(config_dir)}
    except Exception:
        pass
    return protected


def run_screen(agent_root: Path, *, dry_run: bool = False, apply: bool | None = None) -> int:
    """Weekly Serenity screener (O1).

    Discover pool-external bottleneck stocks (Codex + serenity-supply-chain skill) → strict factor
    gate → plan an **add-only + rate-limited + cap-demote + meta re-rank** universe update → apply it
    (only when the flag/--apply says so) or just report it. Fail-closed throughout: no discoveries or
    no network simply means no change this week. Selection layer only — never touches sizing/risk.
    """
    load_env_files(agent_root)
    cfg = load_screener_config()
    paths = build_runtime_paths(agent_root)
    run_date = paths.run_date
    config_dir = paths.config_dir
    run_dir = screener_run_dir(agent_root)
    run_dir.mkdir(parents=True, exist_ok=True)

    will_apply = _resolve_will_apply(enabled=cfg.enabled, dry_run=dry_run, apply=apply)

    # 1) discover pool-external candidates (fail-closed → empty when offline / no codex)
    discovery = run_discovery(agent_root)
    discovered = discovery["discovered"]

    existing_symbols, existing_meta = _read_existing(config_dir)

    # 2) factor-validate the union (existing for re-rank scoring; discovered for add eligibility)
    union = list(dict.fromkeys([*existing_symbols, *[r["symbol"] for r in discovered]]))
    evaluations = {
        ev.symbol: ev
        for ev in validate_candidates(union, config=cfg, run_date=run_date)
    } if union else {}

    # 3) plan the update (pure)
    plan = plan_universe_update(
        existing_symbols=existing_symbols,
        existing_meta=existing_meta,
        evaluations=evaluations,
        discovered=discovered,
        max_adds_per_week=cfg.max_adds_per_week,
        universe_max=cfg.universe_max,
        protected=_protected_symbols(config_dir),
    )

    # 4) apply or report
    applied = False
    apply_result: dict | None = None
    if will_apply and (plan.added or plan.demoted or plan.meta_score_updates):
        apply_result = apply_universe_update(
            config_dir=config_dir, run_dir=run_dir, run_date=run_date, plan=plan
        )
        applied = True

    write_audit(run_dir=run_dir, run_date=run_date, plan=plan, applied=applied)

    status = {
        "run_date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stage": "complete",
        "enabled_flag": cfg.enabled,
        "will_apply": will_apply,
        "applied": applied,
        "discovery_status": discovery["status"],
        "discovered_count": len(discovered),
        "added": plan.added_symbols,
        "demoted": plan.demoted,
        "skipped_count": len(plan.skipped),
        "effective_count_before": plan.effective_count_before,
        "effective_count_after": plan.effective_count_after,
        "config": {
            "max_adds_per_week": cfg.max_adds_per_week,
            "universe_max": cfg.universe_max,
            "min_dollar_volume": cfg.min_dollar_volume,
            "require_uptrend": cfg.require_uptrend,
        },
    }
    write_json(run_dir / "status.json", status)

    mode = "APPLIED" if applied else ("would-apply" if will_apply else "report-only")
    print(
        f"screener {mode}: discovered={len(discovered)} added={plan.added_symbols} "
        f"demoted={plan.demoted} (effective {plan.effective_count_before}→{plan.effective_count_after})"
    )
    print(f"  audit: {run_dir / 'universe_change.md'}")
    return 0
