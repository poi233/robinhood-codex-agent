#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading_agent.data.market_context import collect_market_context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--timeframes", default="1w,1d,1h,15m")
    parser.add_argument("--news-limit", type=int, default=5)
    parser.add_argument("--mock", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = collect_market_context(
        universe_file=Path(args.universe_file),
        output_dir=Path(args.output_dir),
        run_date=args.date,
        timeframes=[value.strip() for value in args.timeframes.split(",") if value.strip()],
        news_limit=args.news_limit,
        mock=args.mock,
    )
    print(json.dumps({"output_dir": args.output_dir, "data_status": payload["data_status"]}))
    return 0 if payload["data_status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
