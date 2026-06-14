#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading_agent.signals.kronos import (
    build_failed_kronos_payload,
    build_live_kronos_payload,
    build_mock_kronos_payload,
    validate_signal_symbols,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe-file", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--mock", action="store_true")
    return parser.parse_args()


def load_universe(path: Path) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip().upper()
        if not line or line in seen:
            continue
        seen.add(line)
        symbols.append(line)
    if not symbols:
        raise ValueError("universe file produced zero symbols")
    return symbols


build_failed_payload = build_failed_kronos_payload
build_mock_payload = build_mock_kronos_payload
build_live_payload = build_live_kronos_payload


def main() -> int:
    args = parse_args()
    universe_file = Path(args.universe_file)
    output_file = Path(args.output_file)
    try:
        symbols = load_universe(universe_file)
        payload = (
            build_mock_payload(symbols, args.date, str(universe_file))
            if args.mock
            else build_live_payload(symbols, args.date, str(universe_file))
        )
        exit_code = 0
    except Exception as exc:
        if args.mock:
            raise
        payload = build_failed_kronos_payload(
            args.date,
            str(universe_file),
            f"live Kronos generation failed: {exc}",
            "inference_only",
        )
        print(f"kronos signal generation failed: {exc}", file=sys.stderr)
        exit_code = 1
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"kronos signals written: {output_file}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
