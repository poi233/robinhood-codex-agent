from __future__ import annotations

from trading_agent.policy.loaders import _parse_quote
from trading_agent.policy.models import Quote


def test_quote_mid_and_spread_with_book():
    q = Quote(symbol="NVDA", price=100.0, bid=99.8, ask=100.2)
    assert q.mid == 100.0
    assert q.spread == 100.2 - 99.8
    assert q.spread_bps == round((100.2 - 99.8) / 100.0 * 10000.0, 4)


def test_quote_falls_back_to_last_price_without_book():
    q = Quote(symbol="NVDA", price=100.0)
    assert q.mid == 100.0
    assert q.spread is None
    assert q.spread_bps is None


def test_quote_ignores_crossed_or_nonpositive_book():
    crossed = Quote(symbol="NVDA", price=100.0, bid=100.5, ask=100.1)  # bid > ask
    assert crossed.spread is None
    assert crossed.spread_bps is None
    zero = Quote(symbol="NVDA", price=100.0, bid=0.0, ask=100.1)
    assert zero.spread is None


def test_parse_quote_captures_bid_ask():
    q = _parse_quote({"symbol": "NVDA", "price": 100.0, "bid": 99.9, "ask": 100.1})
    assert q is not None
    assert q.bid == 99.9
    assert q.ask == 100.1
    assert q.spread_bps == round(0.2 / 100.0 * 10000.0, 4)


def test_parse_quote_without_book_leaves_none():
    q = _parse_quote({"symbol": "NVDA", "price": 100.0})
    assert q is not None
    assert q.bid is None
    assert q.ask is None
