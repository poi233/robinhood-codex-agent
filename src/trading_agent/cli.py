from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trading_agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("premarket", "intraday", "postmarket", "dsa"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--dry-run", action="store_true")

    subparsers.add_parser("doctor", help="Print effective runtime configuration and exit.")

    replay_parser = subparsers.add_parser("replay", help="Print local fill-rate and blocked-reason replay report.")
    replay_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None, help="Only include run dates on or after this date.")
    replay_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None, help="Only include run dates on or before this date.")
    replay_parser.add_argument("--output", metavar="PATH", default=None, help="Write JSON report to this path instead of printing text.")

    analytics_parser = subparsers.add_parser("analytics", help="Build the local analytics.db from runtime/state/runs/*.")
    analytics_subparsers = analytics_parser.add_subparsers(dest="analytics_command", required=True)
    analytics_build_parser = analytics_subparsers.add_parser("build", help="(Re)build runtime/analytics/analytics.db.")
    analytics_build_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None, help="Only include run dates on or after this date.")
    analytics_build_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None, help="Only include run dates on or before this date.")

    subparsers.add_parser("dashboard", help="Launch the read-only Streamlit dashboard at http://localhost:8501.")

    growth_parser = subparsers.add_parser("growth", help="Self-growth diagnostics (paper-only, read-only).")
    growth_subparsers = growth_parser.add_subparsers(dest="growth_command", required=True)
    growth_observe_parser = growth_subparsers.add_parser("observe", help="Write runtime/analytics/growth_observations.json.")
    growth_observe_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None)
    growth_observe_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None)

    return parser


def _run_doctor(agent_root: Path) -> int:
    from trading_agent.core.config import TierMisconfigurationError, load_runtime_config
    from trading_agent.strategy.registry import load_active_strategy

    config = load_runtime_config(agent_root)
    env = os.environ
    active_strategy = load_active_strategy(agent_root)

    tier_misconfigured = False
    try:
        effective_tier_line = (
            f"  effective_risk_tier now   = {config.effective_risk_tier}  (based on TRADING_MODE)"
        )
    except TierMisconfigurationError as exc:
        tier_misconfigured = True
        effective_tier_line = f"  effective_risk_tier now   = FAIL-CLOSED: {exc}"

    risk_tiers_path = agent_root / "src" / "config" / "risk_tiers.json"
    risk_tiers: dict = {}
    if risk_tiers_path.exists():
        risk_tiers = json.loads(risk_tiers_path.read_text(encoding="utf-8"))

    def tier_caps(tier: int) -> str:
        caps = risk_tiers.get(str(tier), {})
        single = caps.get("max_single_order_notional", "?")
        daily = caps.get("max_daily_notional", "?")
        name = caps.get("name", "unknown")
        return f"tier {tier} ({name}): max_single=${single}  max_daily=${daily}"

    kill_switch = (agent_root / "KILL_SWITCH").exists()

    lines = [
        "=== Trading Agent — Effective Configuration ===",
        "",
        f"  TRADING_MODE              = {config.trading_mode}",
        f"  KILL_SWITCH               = {'ACTIVE (file present)' if kill_switch else 'inactive'}",
        "",
        "  --- Strategy ---",
        f"  active_strategy            = {active_strategy['strategy_id']}  [{active_strategy['status']}]",
        f"  change_reason              = {active_strategy['change_reason']}",
        "",
        "  --- Risk Tiers ---",
        f"  RISK_TIER (live/review)   = {config.risk_tier}  [{tier_caps(config.risk_tier)}]",
        f"  PAPER_RISK_TIER           = {config.paper_risk_tier}  [{tier_caps(config.paper_risk_tier)}]",
        effective_tier_line,
        "",
        "  --- Codex ---",
        f"  CODEX_MODEL               = {env.get('CODEX_MODEL', 'gpt-5.4-mini')}",
        f"  CODEX_BIN                 = {env.get('CODEX_BIN', 'codex')}",
        f"  CODEX_EXEC_TIMEOUT_SEC    = {env.get('CODEX_EXEC_TIMEOUT_SEC', '3600')}",
        f"  CODEX_EXEC_DRY_RUN        = {env.get('CODEX_EXEC_DRY_RUN', '0')}",
        "",
        "  --- Signal Layers ---",
        f"  ENABLE_DSA_SIGNAL_LAYER   = {env.get('ENABLE_DSA_SIGNAL_LAYER', '1')}",
        f"  DSA_MAX_SUBAGENTS         = {env.get('DSA_MAX_SUBAGENTS', '3')}",
        f"  ENABLE_DSA_METRICS_PRECOMPUTE = {env.get('ENABLE_DSA_METRICS_PRECOMPUTE', '1')}",
        f"  DSA_METRICS_LOOKBACK_DAYS = {env.get('DSA_METRICS_LOOKBACK_DAYS', '180')}",
        f"  ENABLE_KRONOS_SIGNAL_LAYER= {env.get('ENABLE_KRONOS_SIGNAL_LAYER', '1')}",
        f"  ENABLE_MARKET_FEED_LAYER  = {env.get('ENABLE_MARKET_FEED_LAYER', '1')}",
        f"  MARKET_FEED_TIMEFRAMES    = {config.market_feed_timeframes}",
        f"  ENABLE_OHLCV_CACHE        = {env.get('ENABLE_OHLCV_CACHE', '1')}",
        f"  ENABLE_TECHNICAL_SIGNAL   = {env.get('ENABLE_TECHNICAL_SIGNAL_LAYER', '1')}",
        f"  TECHNICAL_MAX_SUBAGENTS   = {env.get('TECHNICAL_MAX_SUBAGENTS', '3')}",
        f"  ENABLE_TECHNICAL_FEATURES_PRECOMPUTE = {env.get('ENABLE_TECHNICAL_FEATURES_PRECOMPUTE', '1')}",
        f"  TECHNICAL_RECENT_BARS     = {env.get('TECHNICAL_RECENT_BARS', '30')}",
        "",
        "  --- Paper ---",
        f"  PAPER_STARTING_CASH       = {env.get('PAPER_STARTING_CASH', '400000')}",
        f"  PAPER_FILL_MODEL          = {env.get('PAPER_FILL_MODEL', 'conservative')}",
        f"  PAPER_PARTIAL_FILL        = {env.get('PAPER_PARTIAL_FILL', '0')}",
        f"  PAPER_PARTIAL_FILL_MIN_RATIO     = {env.get('PAPER_PARTIAL_FILL_MIN_RATIO', '0.3')}",
        f"  PAPER_PARTIAL_FILL_THRESHOLD_BPS = {env.get('PAPER_PARTIAL_FILL_THRESHOLD_BPS', '20')}",
        "",
        "  --- Notifications ---",
        f"  ENABLE_TRADE_EMAIL        = {env.get('ENABLE_TRADE_EMAIL_NOTIFICATIONS', '1')}",
    ]

    print("\n".join(lines))
    return 2 if tier_misconfigured else 0


def _run_replay(agent_root: Path, *, since: str | None, until: str | None, output: str | None) -> int:
    from trading_agent.replay.analysis import build_replay_report, format_replay_report

    report = build_replay_report(agent_root, since_date=since, until_date=until)
    if output:
        Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Replay report written to {output}")
    else:
        print(format_replay_report(report))
    return 0


def _run_analytics_build(agent_root: Path, *, since: str | None, until: str | None) -> int:
    from trading_agent.analytics.build_db import build_analytics_db, default_analytics_db_path

    row_counts = build_analytics_db(agent_root, since_date=since, until_date=until)
    print(f"Wrote {default_analytics_db_path(agent_root)}")
    for table_name, count in row_counts.items():
        print(f"  {table_name:<15} {count} rows")
    return 0


def _run_growth_observe(agent_root: Path, *, since: str | None, until: str | None) -> int:
    from trading_agent.growth.observations import write_growth_observations

    path = write_growth_observations(agent_root, since=since, until=until)
    print(f"Wrote {path}")
    return 0


def _run_dashboard(agent_root: Path) -> int:
    import subprocess
    import sys

    app_path = Path(__file__).resolve().parent / "dashboard" / "app.py"
    env = {**os.environ, "PYTHONPATH": f"{agent_root / 'src'}:{os.environ.get('PYTHONPATH', '')}"}
    return subprocess.call(
        [sys.executable, "-m", "streamlit", "run", str(app_path)],
        cwd=agent_root,
        env=env,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "premarket":
        from trading_agent.orchestration.premarket import run_premarket_pipeline

        return run_premarket_pipeline(dry_run=args.dry_run)
    if args.command == "intraday":
        from trading_agent.orchestration.intraday import run_intraday_pipeline

        return run_intraday_pipeline(dry_run=args.dry_run)
    if args.command == "postmarket":
        from trading_agent.orchestration.postmarket import run_postmarket_pipeline

        return run_postmarket_pipeline(dry_run=args.dry_run)
    if args.command == "dsa":
        from trading_agent.signals.dsa import run_dsa_scan

        if args.dry_run:
            os.environ["CODEX_EXEC_DRY_RUN"] = "1"
        run_dsa_scan(Path.cwd())
        return 0
    if args.command == "doctor":
        return _run_doctor(Path.cwd())
    if args.command == "replay":
        return _run_replay(Path.cwd(), since=args.since, until=args.until, output=args.output)
    if args.command == "analytics" and args.analytics_command == "build":
        return _run_analytics_build(Path.cwd(), since=args.since, until=args.until)
    if args.command == "dashboard":
        return _run_dashboard(Path.cwd())
    if args.command == "growth" and args.growth_command == "observe":
        return _run_growth_observe(Path.cwd(), since=args.since, until=args.until)
    return 0
