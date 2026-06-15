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
    assert score["diagnostics"]["technical"]["raw_action"] == "buy_bias"
    assert score["diagnostics"]["technical"]["normalized_action"] == "buy_bias"
    assert score["diagnostics"]["technical"]["component_score"] == 82
    assert score["diagnostics"]["technical"]["component_weight"] == 0.3
    assert score["diagnostics"]["technical"]["weighted_contribution"] == 24.6
    assert score["score_status"] == "scored"
    assert score["coverage"] > 0.5


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
    assert score["score_status"] == "blocked"


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


def test_score_candidate_normalizes_promote_to_high_technical_score() -> None:
    score = score_candidate(
        symbol="AVGO",
        dsa={"selected_candidates": [{"symbol": "AVGO", "score": 70}]},
        kronos={"symbols": {"AVGO": {"signal": "neutral", "confidence": 0.5}}},
        technical={"symbols": {"AVGO": {"technical_action": "promote"}}},
        quote={"symbols": {"AVGO": {"change_pct": 1.0}}},
        catalyst={"symbols": {"AVGO": {"catalyst_score": 50}}},
    )

    assert score["components"]["technical"] == 82
    assert score["diagnostics"]["technical"]["raw_action"] == "promote"
    assert score["diagnostics"]["technical"]["normalized_action"] == "promote"
    assert score["diagnostics"]["technical"]["component_score"] == 82
    assert score["diagnostics"]["technical"]["weighted_contribution"] == 24.6


def test_score_candidate_normalizes_reduce_to_low_technical_score() -> None:
    score = score_candidate(
        symbol="AMD",
        dsa={"selected_candidates": [{"symbol": "AMD", "score": 70}]},
        kronos={"symbols": {"AMD": {"signal": "neutral", "confidence": 0.5}}},
        technical={"symbols": {"AMD": {"action": "reduce"}}},
        quote={"symbols": {"AMD": {"change_pct": 1.0}}},
        catalyst={"symbols": {"AMD": {"catalyst_score": 50}}},
    )

    assert score["components"]["technical"] == 30
    assert score["diagnostics"]["technical"]["raw_action"] == "reduce"
    assert score["diagnostics"]["technical"]["normalized_action"] == "reduce"


def test_score_candidate_maps_observe_to_neutral_technical_score() -> None:
    score = score_candidate(
        symbol="SMCI",
        dsa={"selected_candidates": [{"symbol": "SMCI", "score": 70}]},
        kronos={"symbols": {"SMCI": {"signal": "neutral", "confidence": 0.5}}},
        technical={"symbols": {"SMCI": {"recommendation": "observe"}}},
        quote={"symbols": {"SMCI": {"change_pct": 1.0}}},
        catalyst={"symbols": {"SMCI": {"catalyst_score": 50}}},
    )

    assert score["components"]["technical"] == 50
    assert score["diagnostics"]["technical"]["raw_action"] == "observe"
    assert score["diagnostics"]["technical"]["normalized_action"] == "observe"


def test_score_candidate_unknown_technical_action_warns_and_stays_neutral() -> None:
    score = score_candidate(
        symbol="ANET",
        dsa={"selected_candidates": [{"symbol": "ANET", "score": 70}]},
        kronos={"symbols": {"ANET": {"signal": "neutral", "confidence": 0.5}}},
        technical={"symbols": {"ANET": {"bias": "moonshot"}}},
        quote={"symbols": {"ANET": {"change_pct": 1.0}}},
        catalyst={"symbols": {"ANET": {"catalyst_score": 50}}},
    )

    assert score["components"]["technical"] == 50
    assert score["diagnostics"]["technical"]["raw_action"] == "moonshot"
    assert score["diagnostics"]["technical"]["normalized_action"] == "observe"
    assert score["diagnostics"]["technical"]["warning"] == "unmapped_technical_action:moonshot"
    assert "unmapped_technical_action:moonshot" in score["warnings"]


def test_score_candidate_completed_catalyst_without_numeric_score_stays_neutral() -> None:
    score = score_candidate(
        symbol="AVGO",
        dsa={"selected_candidates": [{"symbol": "AVGO", "score": 70}]},
        kronos={"symbols": {"AVGO": {"signal": "neutral", "confidence": 0.5}}},
        technical={"symbols": {"AVGO": {"technical_action": "promote"}}},
        quote={"symbols": {"AVGO": {"score": 65}}},
        catalyst={"symbols": {"AVGO": {"status": "completed"}}},
    )

    assert score["components"]["catalyst"] == 50
    assert score["score"] > 50
    assert score["diagnostics"]["catalyst"]["reason"] == "completed_without_numeric_score"
    assert score["diagnostics"]["catalyst"]["confidence"] == 0.5


def test_score_candidate_partial_catalyst_without_numeric_score_stays_neutral() -> None:
    score = score_candidate(
        symbol="NVDA",
        dsa={"selected_candidates": [{"symbol": "NVDA", "score": 70}]},
        kronos={"symbols": {"NVDA": {"signal": "neutral", "confidence": 0.5}}},
        technical={"symbols": {"NVDA": {"technical_action": "promote"}}},
        quote={"symbols": {"NVDA": {"change_pct": 3.0}}},
        catalyst={"symbols": {"NVDA": {"status": "partial"}}},
    )

    assert score["components"]["catalyst"] == 50
    assert score["diagnostics"]["catalyst"]["reason"] == "partial_without_numeric_score"
    assert score["diagnostics"]["catalyst"]["confidence"] == 0.25


def test_score_candidate_negative_catalyst_can_reduce_score() -> None:
    score = score_candidate(
        symbol="MRVL",
        dsa={"selected_candidates": [{"symbol": "MRVL", "score": 70}]},
        kronos={"symbols": {"MRVL": {"signal": "neutral", "confidence": 0.5}}},
        technical={"symbols": {"MRVL": {"technical_action": "observe"}}},
        quote={"symbols": {"MRVL": {"change_pct": 0.0}}},
        catalyst={"symbols": {"MRVL": {"catalyst_bias": "negative", "confidence": 0.8}}},
    )

    assert score["components"]["catalyst"] < 50
    assert score["diagnostics"]["catalyst"]["reason"] == "explicit_negative_catalyst"


def test_score_candidate_missing_catalyst_is_neutral_not_bearish() -> None:
    score = score_candidate(
        symbol="SMH",
        dsa={"selected_candidates": [{"symbol": "SMH", "score": 70}]},
        kronos={"symbols": {"SMH": {"signal": "neutral", "confidence": 0.5}}},
        technical={"symbols": {"SMH": {"technical_action": "observe"}}},
        quote={"symbols": {"SMH": {"change_pct": 1.0}}},
        catalyst={"symbols": {}},
    )

    assert score["components"]["catalyst"] == 50
    assert score["missing_components"] == ["catalyst"]
    assert "missing_component:catalyst" in score["warnings"]


def test_score_candidate_avgo_regression_clears_old_broken_threshold() -> None:
    score = score_candidate(
        symbol="AVGO",
        dsa={"selected_candidates": [{"symbol": "AVGO", "score": 70}]},
        kronos={"symbols": {"AVGO": {"signal": "neutral", "confidence": 0.5}}},
        technical={"symbols": {"AVGO": {"technical_action": "promote"}}},
        quote={"symbols": {"AVGO": {"score": 64.77}}},
        catalyst={"symbols": {"AVGO": {"status": "completed"}}},
    )

    assert score["components"]["technical"] == 82
    assert score["components"]["catalyst"] == 50
    assert score["score"] > 50


def test_score_candidate_low_confidence_component_reduces_effective_weight() -> None:
    score = score_candidate(
        symbol="NBIS",
        dsa={"selected_candidates": [{"symbol": "NBIS", "score": 80}]},
        kronos={"symbols": {"NBIS": {"signal": "neutral", "confidence": 0.2}}},
        technical={"symbols": {"NBIS": {"technical_action": "promote"}}},
        quote={"symbols": {"NBIS": {"change_pct": 2.0}}},
        catalyst={"symbols": {"NBIS": {"status": "partial"}}},
    )

    assert score["diagnostics"]["kronos"]["effective_weight"] == 0.03
    assert score["diagnostics"]["catalyst"]["effective_weight"] == 0.05


def test_score_candidate_blocked_component_blocks_candidate() -> None:
    score = score_candidate(
        symbol="TSLA",
        dsa={"selected_candidates": [{"symbol": "TSLA", "score": 70}]},
        kronos={"symbols": {"TSLA": {"signal": "neutral", "confidence": 0.5}}},
        technical={"symbols": {"TSLA": {"technical_action": "promote"}}},
        quote={"symbols": {"TSLA": {"change_pct": 1.0}}},
        catalyst={"symbols": {"TSLA": {"catalyst_bias": "block", "block_reasons": ["event_risk"]}}},
    )

    assert score["blocked"] is True
    assert "catalyst:catalyst_blocked" in score["block_reasons"]
    assert score["diagnostics"]["catalyst"]["blocked"] is True


def test_score_candidate_marks_insufficient_data_when_effective_coverage_is_low() -> None:
    score = score_candidate(
        symbol="QQQ",
        dsa={},
        kronos={},
        technical={},
        quote={"symbols": {"QQQ": {"change_pct": 1.0}}},
        catalyst={},
    )

    assert score["score_status"] == "insufficient_data"
    assert score["coverage"] < 0.5
    assert "missing_component:dsa" in score["warnings"]
    assert "missing_component:technical" in score["warnings"]
    assert "missing_component:kronos" in score["warnings"]
    assert "missing_component:catalyst" in score["warnings"]
