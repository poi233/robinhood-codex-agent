from __future__ import annotations

import json
from pathlib import Path

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import write_json
from trading_agent.portfolio.target import build_and_write_portfolio_target, build_portfolio_target


_AI_THEME = {"NVDA": "ai_semiconductor", "AVGO": "ai_semiconductor", "ANET": "ai_semiconductor",
             "MRVL": "ai_semiconductor", "VRT": "ai_data_center"}


def _pos(qty: float, price: float) -> dict:
    return {"quantity": qty, "market_price": price}


def test_concentrated_ai_book_flags_breaches():
    # 5 names, each 18% of a 100k book, mostly one theme; cash 10%.
    positions = {s: _pos(1, 18000.0) for s in ("NVDA", "AVGO", "ANET", "MRVL", "VRT")}
    target = build_portfolio_target(positions, cash=10000.0, theme_map=_AI_THEME)

    assert target["total_equity"] == 100000.0
    assert target["cash_weight"] == 0.10
    # every position is over the 8% single-name cap
    assert set(target["breaches"]["oversize_positions"]) == {"NVDA", "AVGO", "ANET", "MRVL", "VRT"}
    # ai_semiconductor (4 x 18% = 72%) is over the 35% theme cap
    assert "ai_semiconductor" in target["breaches"]["overexposed_themes"]
    assert target["theme_exposure"]["ai_semiconductor"] == 0.72
    assert target["breaches"]["below_cash_target"] is True  # 10% < 20%


def test_diversified_book_no_breaches():
    positions = {"NVDA": _pos(1, 5000.0), "JPM": _pos(1, 5000.0)}
    theme = {"NVDA": "ai_semiconductor", "JPM": "financials"}
    target = build_portfolio_target(positions, cash=90000.0, theme_map=theme)
    assert target["breaches"]["oversize_positions"] == []
    assert target["breaches"]["overexposed_themes"] == []
    assert target["breaches"]["below_cash_target"] is False  # 90% cash


def test_empty_book_is_all_cash():
    target = build_portfolio_target({}, cash=400000.0, theme_map={})
    assert target["cash_weight"] == 1.0
    assert target["theme_exposure"] == {}
    assert target["breaches"]["oversize_positions"] == []
    assert "never a buy signal" in target["notes"].lower()  # red-line disclaimer present


def test_unknown_theme_bucket():
    target = build_portfolio_target({"XYZ": _pos(1, 1000.0)}, cash=0.0, theme_map={})
    assert "unknown" in target["theme_exposure"]


def test_build_and_write_reads_paper_ledger(tmp_path):
    paths = build_runtime_paths(tmp_path, run_date="2026-06-17")
    write_json(paths.paper_positions_path, {"NVDA": _pos(1, 50000.0), "AVGO": _pos(1, 50000.0)})
    write_json(paths.paper_account_path, {"cash": 0.0})
    (tmp_path / "src" / "config").mkdir(parents=True, exist_ok=True)
    write_json(tmp_path / "src" / "config" / "universe_meta.json",
               {"NVDA": {"theme": "ai_semiconductor"}, "AVGO": {"theme": "ai_semiconductor"}})

    out = build_and_write_portfolio_target(tmp_path, "2026-06-17")
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["theme_exposure"]["ai_semiconductor"] == 1.0  # 100% one theme
    assert "ai_semiconductor" in payload["breaches"]["overexposed_themes"]
