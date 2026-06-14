from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trading_agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("premarket", "intraday", "postmarket"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--dry-run", action="store_true")

    return parser


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
    return 0
