from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from trading_agent.core.config import load_env_files
from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import write_json
from trading_agent.screener.config import load_screener_config
from trading_agent.screener.paths import screener_run_dir


def _resolve_will_apply(*, enabled: bool, dry_run: bool, apply: bool | None) -> bool:
    """Effective write mode.

    ``--dry-run`` forces report-only (wins over everything); ``--apply`` forces writing;
    otherwise follow the ``ENABLE_WEEKLY_SCREENER`` flag.
    """
    if dry_run:
        return False
    if apply is not None:
        return apply
    return enabled


def run_screen(agent_root: Path, *, dry_run: bool = False, apply: bool | None = None) -> int:
    """Weekly Serenity screener (O1).

    **Step 1 skeleton**: load env, resolve config, prepare the dated screener run dir, and
    write ``status.json`` describing what the later steps will do. No discovery, factor
    validation, or universe mutation happens yet — those land in O1 steps 2–4. Always safe to
    run regardless of the flag; nothing outside ``runtime/screener/<date>/`` is touched.
    """
    load_env_files(agent_root)
    cfg = load_screener_config()
    paths = build_runtime_paths(agent_root)
    run_dir = screener_run_dir(agent_root)
    run_dir.mkdir(parents=True, exist_ok=True)

    will_apply = _resolve_will_apply(enabled=cfg.enabled, dry_run=dry_run, apply=apply)

    status = {
        "run_date": paths.run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stage": "skeleton",
        "enabled_flag": cfg.enabled,
        "will_apply": will_apply,
        "config": {
            "max_adds_per_week": cfg.max_adds_per_week,
            "universe_max": cfg.universe_max,
            "min_dollar_volume": cfg.min_dollar_volume,
            "require_uptrend": cfg.require_uptrend,
        },
        "pending_steps": [
            "discover (Codex + serenity-supply-chain skill)",
            "factor validation (strict liquidity/data/trend gate)",
            "auto-apply writer (add-only + rate-limit + cap-demote, meta re-rank)",
        ],
        "note": (
            "O1 step-1 skeleton: discovery / factor validation / universe mutation not "
            "implemented yet. Running this never modifies universe.txt or universe_meta.json."
        ),
    }
    write_json(run_dir / "status.json", status)

    mode = "apply" if will_apply else "report-only"
    print(f"screener skeleton ready ({mode}); wrote {run_dir / 'status.json'}")
    print(
        f"  ENABLE_WEEKLY_SCREENER={'1' if cfg.enabled else '0'}  "
        f"max_adds/week={cfg.max_adds_per_week}  universe_max={cfg.universe_max}"
    )
    return 0
