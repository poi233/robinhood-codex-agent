from trading_agent.signals.technical_fallback import merge_technical_signals


def test_merge_prefers_live_per_symbol_and_preserves_snapshot_only_symbols():
    full = {"date": "2026-06-16", "analysis_status": "ok", "symbols": {
        "MRVL": {"confidence": 0.7}, "MU": {"confidence": 0.6}, "EOSE": {"confidence": 0.1}}}
    live = {"date": "2026-06-16", "analysis_status": "ok", "symbols": {
        "EOSE": {"confidence": 0.9}}}  # ad hoc fresh EOSE analysis

    merged = merge_technical_signals(full, live)

    assert set(merged["symbols"]) == {"MRVL", "MU", "EOSE"}
    assert merged["symbols"]["EOSE"]["confidence"] == 0.9  # live wins for EOSE
    assert merged["symbols"]["MRVL"]["confidence"] == 0.7  # snapshot preserved


def test_merge_returns_live_when_no_snapshot():
    live = {"symbols": {"NVDA": {"confidence": 0.5}}}
    assert merge_technical_signals({}, live) == live


def test_merge_returns_snapshot_when_live_empty():
    full = {"symbols": {"NVDA": {"confidence": 0.5}}}
    assert merge_technical_signals(full, {}) == full


def test_merge_live_top_level_metadata_wins():
    full = {"generated_at": "old", "analysis_status": "ok", "symbols": {"A": {}}}
    live = {"generated_at": "new", "analysis_status": "failed", "symbols": {"B": {}}}
    merged = merge_technical_signals(full, live)
    assert merged["generated_at"] == "new"
    assert merged["analysis_status"] == "failed"
    assert set(merged["symbols"]) == {"A", "B"}


def test_merge_handles_missing_symbols_key():
    assert merge_technical_signals({"date": "x"}, {"date": "y"})["symbols"] == {}
