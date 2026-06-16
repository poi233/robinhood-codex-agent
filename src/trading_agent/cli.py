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

    return parser


def _run_doctor(agent_root: Path) -> int:
    from trading_agent.core.config import load_runtime_config

    config = load_runtime_config(agent_root)
    env = os.environ

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
        "  --- Risk Tiers ---",
        f"  RISK_TIER (live/review)   = {config.risk_tier}  [{tier_caps(config.risk_tier)}]",
        f"  PAPER_RISK_TIER           = {config.paper_risk_tier}  [{tier_caps(config.paper_risk_tier)}]",
        f"  effective_risk_tier now   = {config.effective_risk_tier}  (based on TRADING_MODE)",
        "",
        "  --- Codex ---",
        f"  CODEX_MODEL               = {env.get('CODEX_MODEL', 'gpt-5.4-mini')}",
        f"  CODEX_BIN                 = {env.get('CODEX_BIN', 'codex')}",
        f"  CODEX_EXEC_TIMEOUT_SEC    = {env.get('CODEX_EXEC_TIMEOUT_SEC', '3600')}",
        f"  CODEX_EXEC_DRY_RUN        = {env.get('CODEX_EXEC_DRY_RUN', '0')}",
        "",
        "  --- Signal Layers ---",
        f"  ENABLE_DSA_SIGNAL_LAYER   = {env.get('ENABLE_DSA_SIGNAL_LAYER', '1')}",
        f"  DSA_MAX_SUBAGENTS         = {env.get('DSA_MAX_SUBAGENTS', '10')}",
        f"  ENABLE_KRONOS_SIGNAL_LAYER= {env.get('ENABLE_KRONOS_SIGNAL_LAYER', '1')}",
        f"  ENABLE_MARKET_FEED_LAYER  = {env.get('ENABLE_MARKET_FEED_LAYER', '1')}",
        f"  MARKET_FEED_TIMEFRAMES    = {config.market_feed_timeframes}",
        f"  ENABLE_TECHNICAL_SIGNAL   = {env.get('ENABLE_TECHNICAL_SIGNAL_LAYER', '1')}",
        f"  TECHNICAL_MAX_SUBAGENTS   = {env.get('TECHNICAL_MAX_SUBAGENTS', '10')}",
        "",
        "  --- Paper ---",
        f"  PAPER_STARTING_CASH       = {env.get('PAPER_STARTING_CASH', '400000')}",
        f"  PAPER_FILL_MODEL          = {env.get('PAPER_FILL_MODEL', 'conservative')}",
        "",
        "  --- Notifications ---",
        f"  ENABLE_TRADE_EMAIL        = {env.get('ENABLE_TRADE_EMAIL_NOTIFICATIONS', '1')}",
    ]

    print("\n".join(lines))
    return 0


def _run_replay(agent_root: Path, *, since: str | None, until: str | None, output: str | None) -> int:
    from trading_agent.replay.analysis import build_replay_report, format_replay_report

    report = build_replay_report(agent_root, since_date=since, until_date=until)
    if output:
        Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Replay report written to {output}")
    else:
        print(format_replay_report(report))
    return 0


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
    return 0
