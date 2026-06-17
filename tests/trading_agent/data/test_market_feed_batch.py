from __future__ import annotations

import pandas as pd

from trading_agent.data.market_context import _frame_to_rows, _rows_from_download_frame


def _single_frame() -> pd.DataFrame:
    idx = pd.to_datetime(["2026-06-15", "2026-06-16"])
    return pd.DataFrame(
        {"Open": [10.0, 11.0], "High": [10.5, 11.5], "Low": [9.5, 10.5], "Close": [10.2, 11.2], "Volume": [1000, 1100]},
        index=idx,
    )


def test_frame_to_rows_converts_and_rounds():
    rows = _frame_to_rows(_single_frame())
    assert len(rows) == 2
    assert rows[0]["close"] == 10.2
    assert rows[0]["volume"] == 1000
    assert rows[1]["timestamp"].startswith("2026-06-16")


def test_frame_to_rows_skips_nan_rows():
    df = _single_frame()
    df.loc[df.index[1], "Close"] = float("nan")  # gap for this symbol/bar
    rows = _frame_to_rows(df)
    assert len(rows) == 1  # the NaN bar is dropped


def test_rows_from_download_frame_multi_ticker():
    idx = pd.to_datetime(["2026-06-15", "2026-06-16"])
    cols = pd.MultiIndex.from_product([["NVDA", "AMD"], ["Open", "High", "Low", "Close", "Volume"]])
    data = {
        ("NVDA", "Open"): [10.0, 11.0], ("NVDA", "High"): [10.5, 11.5], ("NVDA", "Low"): [9.5, 10.5],
        ("NVDA", "Close"): [10.2, 11.2], ("NVDA", "Volume"): [1000, 1100],
        ("AMD", "Open"): [5.0, 5.2], ("AMD", "High"): [5.3, 5.5], ("AMD", "Low"): [4.8, 5.0],
        ("AMD", "Close"): [5.1, 5.4], ("AMD", "Volume"): [2000, 2100],
    }
    frame = pd.DataFrame(data, index=idx)
    frame.columns = cols

    out = _rows_from_download_frame(frame, ["NVDA", "AMD"])
    assert set(out) == {"NVDA", "AMD"}
    assert len(out["NVDA"]) == 2 and out["NVDA"][0]["close"] == 10.2
    assert len(out["AMD"]) == 2 and out["AMD"][1]["close"] == 5.4


def test_rows_from_download_frame_missing_symbol_and_empty():
    assert _rows_from_download_frame(pd.DataFrame(), ["NVDA"]) == {"NVDA": []}
    out = _rows_from_download_frame(_single_frame(), ["NVDA"])  # flat (single-ticker) frame
    assert len(out["NVDA"]) == 2
