from __future__ import annotations

import json
from pathlib import Path

from trading_agent.planner.quote_snapshot import build_candidate_quote_snapshot


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_candidate_quote_snapshot_uses_market_feed_daily_rows(tmp_path: Path) -> None:
    market_feed = tmp_path / "market_feed"
    _write_json(
        market_feed / "ohlcv" / "SMH" / "daily.json",
        [
            {"timestamp": "2026-06-12T00:00:00-04:00", "close": 600.0},
            {"timestamp": "2026-06-13T00:00:00-04:00", "close": 619.96},
        ],
    )
    candidate_snapshot = {"selected_symbols": ["SMH"]}

    payload = build_candidate_quote_snapshot(
        run_date="2026-06-14",
        candidate_snapshot=candidate_snapshot,
        market_feed_dir=market_feed,
    )

    assert payload["data_status"] == "ok"
    assert payload["symbols"]["SMH"]["last_price"] == 619.96
    assert payload["symbols"]["SMH"]["previous_close"] == 600.0
    assert payload["symbols"]["SMH"]["source"] == "market_feed:daily"


def test_build_candidate_quote_snapshot_marks_missing_symbols_partial(tmp_path: Path) -> None:
    payload = build_candidate_quote_snapshot(
        run_date="2026-06-14",
        candidate_snapshot={"selected_symbols": ["MISSING"]},
        market_feed_dir=tmp_path / "market_feed",
    )

    assert payload["data_status"] == "failed"
    assert payload["symbols"] == {}
    assert payload["missing_symbols"] == ["MISSING"]
