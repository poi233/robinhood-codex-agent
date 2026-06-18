from __future__ import annotations

from trading_agent.planner.scoring import (
    rescore_candidate,
    rescore_candidate_scores,
    score_candidate,
)


def _scored(symbol: str = "NVDA") -> dict:
    """A real champion scoring result to re-aggregate under challenger configs."""
    return score_candidate(
        symbol=symbol,
        dsa={"selected_candidates": [{"symbol": symbol, "score": 86, "action": "strong_candidate"}]},
        kronos={"symbols": {symbol: {"signal": "bullish", "confidence": 0.8, "setup_bias": "buy"}}},
        technical={"symbols": {symbol: {"technical_action": "buy_bias", "priority_score": 82}}},
        quote={"symbols": {symbol: {"last_price": 100.0, "change_pct": 1.0}}},
        catalyst={"symbols": {symbol: {"catalyst_score": 60}}},
    )


def test_rescore_no_changes_preserves_score() -> None:
    scored = _scored()
    re = rescore_candidate(scored)
    # Re-aggregating with default weights reproduces the champion score (within rounding).
    assert abs(re["score"] - scored["score"]) < 0.5


def test_rescore_disabling_kronos_drops_its_contribution() -> None:
    scored = _scored()
    re = rescore_candidate(scored, disabled_components={"kronos"})
    assert re["diagnostics"]["kronos"]["effective_weight"] == 0.0
    assert re["diagnostics"]["kronos"]["contribution"] == 0.0
    # kronos was bullish (high), removing it should not raise the score.
    assert re["score"] <= scored["score"] + 0.01


def test_rescore_reweighting_changes_score() -> None:
    scored = _scored()
    # Heavily up-weight technical, down-weight everything else.
    re = rescore_candidate(scored, component_weights={
        "technical": 0.80, "dsa": 0.05, "kronos": 0.05, "quote": 0.05, "catalyst": 0.05,
    })
    # technical raw score is 82; with dominant weight the aggregate should move toward it.
    assert re["score"] != scored["score"]


def test_rescore_folds_in_factor_alpha_component() -> None:
    scored = _scored()
    re = rescore_candidate(scored, factor_alpha_score=90.0, factor_alpha_weight=0.20)
    assert "factor_alpha" in re["diagnostics"]
    assert re["diagnostics"]["factor_alpha"]["score"] == 90.0
    assert re["diagnostics"]["factor_alpha"]["effective_weight"] == 0.20
    assert re["components"]["factor_alpha"] == 90.0


def test_rescore_factor_alpha_ignored_when_weight_zero() -> None:
    scored = _scored()
    re = rescore_candidate(scored, factor_alpha_score=90.0, factor_alpha_weight=0.0)
    assert "factor_alpha" not in re["diagnostics"]


def test_rescore_candidate_scores_reaggregates_all_and_reranks() -> None:
    champion = {
        "date": "2026-06-18",
        "symbols": {
            "NVDA": _scored("NVDA"),
            "SMH": _scored("SMH"),
        },
        "ranked_symbols": ["NVDA", "SMH"],
    }
    re = rescore_candidate_scores(
        champion,
        factor_alpha={"symbols": {"SMH": {"factor_alpha_score": 95.0}, "NVDA": {"factor_alpha_score": 20.0}}},
        factor_alpha_weight=0.40,
    )
    assert re["rescored"] is True
    # SMH gets a strong factor boost, NVDA a weak one → SMH should now outrank NVDA.
    assert re["ranked_symbols"][0] == "SMH"
    assert "factor_alpha" in re["symbols"]["SMH"]["diagnostics"]


def test_rescore_does_not_mutate_champion() -> None:
    champion = {"symbols": {"NVDA": _scored("NVDA")}, "ranked_symbols": ["NVDA"]}
    original_score = champion["symbols"]["NVDA"]["score"]
    rescore_candidate_scores(champion, disabled_components={"kronos"})
    assert champion["symbols"]["NVDA"]["score"] == original_score
    assert "rescored" not in champion
