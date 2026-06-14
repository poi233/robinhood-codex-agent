from __future__ import annotations

from trading_agent.reporting.trader_watch_levels import build_trader_watch_levels


def test_build_trader_watch_levels_flattens_nested_technical_payload() -> None:
    payload = {
        "date": "2026-06-14",
        "symbols": {
            "SMH": {
                "technical_action": "buy_bias",
                "confidence": 0.72,
                "key_levels": {
                    "reference_price": 619.96,
                    "supports": [527.87, 554.66, 590.82],
                    "resistances": [624.62, 642.77],
                    "range_low": 527.87,
                    "range_high": 642.77,
                },
                "long_setup": {
                    "trigger_above": 642.77,
                    "entry_zone": {"low": 590.82, "high": 619.96},
                    "invalidation_below": 590.82,
                    "target_1": 661.99,
                    "target_2": 681.2,
                    "do_not_chase_above": 674.8,
                    "status": "watch",
                },
                "short_setup": {
                    "trigger_below": 554.66,
                    "entry_zone": {"low": 541.85, "high": 554.66},
                    "invalidation_above": 624.62,
                    "target_1": 527.87,
                    "target_2": 378.0,
                    "status": "watch",
                    "notes": "Existing-long risk management only.",
                },
                "no_trade_zone": {
                    "low": 590.82,
                    "high": 642.77,
                    "reason": "Noisy upper-range area.",
                },
            }
        },
    }

    result = build_trader_watch_levels(payload)

    smh = result["symbols"]["SMH"]
    assert result["schema_version"] == 1
    assert smh["current_context"] == "buy_bias"
    assert smh["confidence"] == 0.72
    assert smh["reference_price"] == 619.96
    assert smh["supports"] == [527.87, 554.66, 590.82]
    assert smh["resistances"] == [624.62, 642.77]
    assert smh["buy_trigger_above"] == 642.77
    assert smh["entry_low"] == 590.82
    assert smh["entry_high"] == 619.96
    assert smh["invalidation_below"] == 590.82
    assert smh["target_1"] == 661.99
    assert smh["target_2"] == 681.2
    assert smh["do_not_chase_above"] == 674.8
    assert smh["no_trade_low"] == 590.82
    assert smh["no_trade_high"] == 642.77
    assert smh["risk_reduction_trigger_below"] == 554.66
    assert smh["risk_reduction_only"] is True


def test_build_trader_watch_levels_omits_malformed_symbol_payloads() -> None:
    payload = {"symbols": {"BROKEN": "not a dict"}}

    result = build_trader_watch_levels(payload)

    assert result == {"schema_version": 1, "symbols": {}}
