from __future__ import annotations

import json
from pathlib import Path

from trading_agent.replay.fill_quality import (
    Fill,
    fill_quality_report,
    format_fill_quality_markdown,
    load_fills,
)


def _write_orders(agent_root: Path, run_date: str, orders: list[dict]) -> None:
    path = agent_root / "runtime" / "state" / "runs" / run_date / "paper" / "orders.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(o) for o in orders) + "\n", encoding="utf-8")


def test_realized_slippage_sign_is_cost_oriented():
    # Buy filled above reference -> positive cost.
    buy = Fill("d", "NVDA", "buy", 1.0, reference_price=100.0, fill_price=100.5, notional=100.5, spread_bps=None)
    assert round(buy.realized_slippage_bps, 1) == 50.0
    # Sell filled below reference -> positive cost (still bad for us).
    sell = Fill("d", "NVDA", "sell", 1.0, reference_price=100.0, fill_price=99.5, notional=99.5, spread_bps=None)
    assert round(sell.realized_slippage_bps, 1) == 50.0


def test_load_fills_skips_unfilled_and_missing_prices(tmp_path):
    _write_orders(tmp_path, "2026-06-15", [
        {"order_id": "a", "symbol": "NVDA", "side": "buy", "status": "filled",
         "current_price_at_submit": 100.0, "fill_price": 100.5, "quantity": 2.0, "spread_bps": 12.0},
        {"order_id": "b", "symbol": "AMD", "side": "buy", "status": "pending",
         "current_price_at_submit": 100.0, "fill_price": None, "quantity": 1.0},
        {"order_id": "c", "symbol": "MSFT", "side": "sell", "status": "filled",
         "current_price_at_submit": None, "fill_price": 50.0, "quantity": 1.0},
    ])
    fills = load_fills(tmp_path)
    assert len(fills) == 1
    assert fills[0].symbol == "NVDA"
    assert fills[0].spread_bps == 12.0


def test_fill_quality_report_scenarios_and_buckets(tmp_path):
    _write_orders(tmp_path, "2026-06-15", [
        {"order_id": "a", "symbol": "NVDA", "side": "buy", "status": "filled",
         "current_price_at_submit": 100.0, "fill_price": 100.1, "quantity": 10.0, "spread_bps": None},
        {"order_id": "b", "symbol": "AMD", "side": "sell", "status": "filled",
         "current_price_at_submit": 50.0, "fill_price": 49.9, "quantity": 10.0, "spread_bps": None},
    ])
    report = fill_quality_report(tmp_path, spread_scenarios_bps=(10.0, 50.0))
    assert report["fill_count"] == 2
    assert report["mean_realized_slippage_bps"] is not None
    # 50bps scenario -> 50bps round-trip haircut; drag on total notional (1001 + 499 = 1500).
    s50 = next(s for s in report["scenarios"] if s["assumed_spread_bps"] == 50.0)
    assert s50["roundtrip_edge_haircut_bps"] == 50.0
    assert s50["dollar_drag_on_filled_notional"] == round(report["total_filled_notional"] * 0.005, 2)
    assert report["bucket_basis"] == "realized_slippage_proxy"
    assert sum(b["count"] for b in report["buckets"]) == 2


def test_fill_quality_report_uses_captured_spread_buckets_when_present(tmp_path):
    _write_orders(tmp_path, "2026-06-15", [
        {"order_id": f"o{i}", "symbol": "NVDA", "side": "buy", "status": "filled",
         "current_price_at_submit": 100.0, "fill_price": 100.05, "quantity": 1.0, "spread_bps": 5.0 + i}
        for i in range(4)
    ])
    report = fill_quality_report(tmp_path)
    assert report["bucket_basis"] == "captured_spread"
    assert report["mean_captured_spread_bps"] is not None


def test_fill_quality_report_empty(tmp_path):
    report = fill_quality_report(tmp_path)
    assert report["fill_count"] == 0
    md = format_fill_quality_markdown(report)
    assert "Fill Quality Report" in md


def test_markdown_renders_scenarios(tmp_path):
    _write_orders(tmp_path, "2026-06-15", [
        {"order_id": "a", "symbol": "NVDA", "side": "buy", "status": "filled",
         "current_price_at_submit": 100.0, "fill_price": 100.1, "quantity": 10.0, "spread_bps": None},
    ])
    report = fill_quality_report(tmp_path)
    md = format_fill_quality_markdown(report)
    assert "Conservative-fill sensitivity" in md
    assert "round-trip haircut" in md
