from __future__ import annotations

from trading_agent.planner.scoring import score_candidate


def test_score_candidate_combines_signal_layers_with_transparent_weights() -> None:
    score = score_candidate(
        symbol="SMH",
        dsa={"selected_candidates": [{"symbol": "SMH", "score": 86, "action": "strong_candidate"}]},
        kronos={"symbols": {"SMH": {"signal": "bearish", "confidence": 0.6, "setup_bias": "avoid"}}},
        technical={"symbols": {"SMH": {"technical_action": "buy_bias", "priority_score": 82}}},
        quote={"symbols": {"SMH": {"last_price": 619.96, "change_pct": 2.0}}},
        catalyst={"symbols": {"SMH": {"catalyst_score": 55}}},
    )

    assert score["symbol"] == "SMH"
    assert score["score"] > 0
    assert score["components"]["dsa"] == 86
    assert score["components"]["technical"] == 82
    assert score["components"]["kronos"] < 50
    assert score["weights"] == {
        "dsa": 0.25,
        "technical": 0.3,
        "kronos": 0.15,
        "quote": 0.1,
        "catalyst": 0.2,
    }
    assert "dsa_mentions_technical_trend" not in score["overlap_flags"]


def test_score_candidate_marks_dsa_blocks_without_replacing_reasoning() -> None:
    score = score_candidate(
        symbol="NVDA",
        dsa={"blocked_symbols": ["NVDA"]},
        kronos={"symbols": {"NVDA": {"signal": "bullish", "confidence": 0.9}}},
        technical={"symbols": {"NVDA": {"technical_action": "buy_bias", "priority_score": 90}}},
        quote={"symbols": {"NVDA": {"change_pct": 4.0}}},
        catalyst={"symbols": {"NVDA": {"catalyst_score": 80}}},
    )

    assert score["blocked"] is True
    assert "dsa_block" in score["block_reasons"]


def test_score_candidate_marks_dsa_overlap_flags_for_technical_and_event_signals() -> None:
    score = score_candidate(
        symbol="NVDA",
        dsa={
            "symbol_signals": {
                "NVDA": {
                    "dsa_score": 78,
                    "setup": "relative_strength",
                    "strategy_matches": ["bull_trend", "event_driven"],
                    "evidence_summary": "News catalyst remains active ahead of earnings.",
                    "risk_flags": [],
                    "reject_reasons": [],
                }
            }
        },
        kronos={"symbols": {}},
        technical={"symbols": {}},
        quote={"symbols": {}},
        catalyst={"symbols": {}},
    )

    assert "dsa_mentions_technical_trend" in score["overlap_flags"]
    assert "dsa_mentions_news_catalyst" in score["overlap_flags"]
