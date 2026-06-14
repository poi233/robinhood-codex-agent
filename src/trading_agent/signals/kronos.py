from __future__ import annotations

import os
import sys
from datetime import datetime


def validate_signal_symbols(universe_symbols: set[str], signal_map: dict[str, object]) -> None:
    extra = set(signal_map) - universe_symbols
    if extra:
        raise ValueError(f"signals contained symbols outside universe: {sorted(extra)}")


def build_failed_kronos_payload(run_date: str, source_universe: str, note: str, mode: str) -> dict[str, object]:
    return {
        "date": run_date,
        "generated_at": datetime.now().astimezone().isoformat(),
        "timeframe": os.environ.get("KRONOS_TIMEFRAME", "30m"),
        "horizon_bars": int(os.environ.get("KRONOS_HORIZON_BARS", "8")),
        "source_universe": source_universe,
        "model": {
            "name": os.environ.get("KRONOS_MODEL_NAME", "NeoQuasar/Kronos-small"),
            "tokenizer": os.environ.get("KRONOS_TOKENIZER_NAME", "NeoQuasar/Kronos-Tokenizer-base"),
            "mode": mode,
        },
        "data_status": "failed",
        "symbols": {},
        "notes": note,
    }


def build_mock_kronos_payload(symbols: list[str], run_date: str, source_universe: str) -> dict[str, object]:
    signal_map: dict[str, dict[str, object]] = {}
    for index, symbol in enumerate(symbols):
        signal_map[symbol] = {
            "direction_bias": "bullish" if index == 0 else "neutral",
            "confidence": 0.72 if index == 0 else 0.61,
            "predicted_return_bps": 180 - (index * 25),
            "predicted_volatility_bps": 220 + (index * 10),
            "path_summary": "up_then_consolidate" if index == 0 else "mixed_range",
            "setup_bias": "breakout" if index == 0 else "chop",
            "risk_flags": [],
            "reason": f"mock Kronos signal for {symbol}",
        }
    validate_signal_symbols(set(symbols), signal_map)
    return {
        "date": run_date,
        "generated_at": datetime.now().astimezone().isoformat(),
        "timeframe": os.environ.get("KRONOS_TIMEFRAME", "30m"),
        "horizon_bars": int(os.environ.get("KRONOS_HORIZON_BARS", "8")),
        "source_universe": source_universe,
        "model": {
            "name": os.environ.get("KRONOS_MODEL_NAME", "NeoQuasar/Kronos-small"),
            "tokenizer": os.environ.get("KRONOS_TOKENIZER_NAME", "NeoQuasar/Kronos-Tokenizer-base"),
            "mode": "inference_only_mock",
        },
        "data_status": "ok",
        "symbols": signal_map,
        "notes": "mock output for portable setup validation",
    }


def build_live_kronos_payload(symbols: list[str], run_date: str, source_universe: str) -> dict[str, object]:
    import pandas as pd
    import yfinance as yf

    sys.path.insert(0, os.environ["KRONOS_PROJECT_ROOT"])
    from model import Kronos, KronosPredictor, KronosTokenizer

    model_name = os.environ.get("KRONOS_MODEL_NAME", "NeoQuasar/Kronos-small")
    tokenizer_name = os.environ.get("KRONOS_TOKENIZER_NAME", "NeoQuasar/Kronos-Tokenizer-base")
    timeframe = os.environ.get("KRONOS_TIMEFRAME", "30m")
    lookback = int(os.environ.get("KRONOS_LOOKBACK_BARS", "400"))
    pred_len = int(os.environ.get("KRONOS_HORIZON_BARS", "8"))
    tokenizer = KronosTokenizer.from_pretrained(tokenizer_name)
    model = Kronos.from_pretrained(model_name)
    predictor = KronosPredictor(model, tokenizer, max_context=512)

    interval_map = {
        "30m": ("30m", "60d", "30min"),
        "1h": ("60m", "730d", "60min"),
        "1d": ("1d", "5y", "1D"),
    }
    interval, period, future_freq = interval_map[timeframe]
    signals: dict[str, dict[str, object]] = {}
    failures: list[str] = []

    for symbol in symbols:
        try:
            history = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False)
            if history.empty:
                raise ValueError("no market data returned")
            if isinstance(history.columns, pd.MultiIndex):
                history = history.copy()
                history.columns = history.columns.get_level_values(0)
            history = history.rename(columns=str.lower).reset_index()
            history = history.rename(columns={history.columns[0]: "timestamps"})
            for column in ["open", "high", "low", "close"]:
                if column not in history.columns:
                    raise ValueError(f"missing column {column}")
            if "volume" not in history.columns:
                history["volume"] = 0
            if "amount" not in history.columns:
                history["amount"] = 0

            window = history.tail(lookback).reset_index(drop=True)
            x_df = window[["open", "high", "low", "close", "volume", "amount"]]
            x_timestamp = pd.Series(pd.to_datetime(window["timestamps"]), name="timestamps")
            last_ts = pd.to_datetime(x_timestamp.iloc[-1])
            y_timestamp = pd.Series(pd.date_range(last_ts, periods=pred_len + 1, freq=future_freq)[1:], name="timestamps")
            pred_df = predictor.predict(
                df=x_df,
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=pred_len,
                T=float(os.environ.get("KRONOS_TEMPERATURE", "1.0")),
                top_p=float(os.environ.get("KRONOS_TOP_P", "0.9")),
                sample_count=int(os.environ.get("KRONOS_SAMPLE_COUNT", "1")),
            )

            last_close = float(x_df["close"].iloc[-1])
            forecast_close = float(pred_df["close"].iloc[-1])
            return_bps = int(round(((forecast_close - last_close) / last_close) * 10000))
            vol_bps = max(1, int(round(pred_df["close"].pct_change().fillna(0).std() * 10000)))
            confidence = round(min(0.95, max(0.05, abs(return_bps) / max(vol_bps, 50))), 2)

            if return_bps >= 75:
                direction_bias = "bullish"
                setup_bias = "breakout"
                path_summary = "up_then_consolidate"
            elif return_bps <= -75:
                direction_bias = "bearish"
                setup_bias = "avoid"
                path_summary = "downside_extension"
            else:
                direction_bias = "neutral"
                setup_bias = "chop"
                path_summary = "mixed_range"

            signals[symbol] = {
                "direction_bias": direction_bias,
                "confidence": confidence,
                "predicted_return_bps": return_bps,
                "predicted_volatility_bps": vol_bps,
                "path_summary": path_summary,
                "setup_bias": setup_bias,
                "risk_flags": [] if vol_bps < 300 else ["high_forecast_volatility"],
                "reason": f"Kronos forecast from {timeframe} data",
            }
        except Exception as exc:
            failures.append(f"{symbol}: {exc}")

    validate_signal_symbols(set(symbols), signals)
    return {
        "date": run_date,
        "generated_at": datetime.now().astimezone().isoformat(),
        "timeframe": timeframe,
        "horizon_bars": pred_len,
        "source_universe": source_universe,
        "model": {
            "name": model_name,
            "tokenizer": tokenizer_name,
            "mode": "inference_only",
        },
        "data_status": "ok" if signals and not failures else "partial" if signals else "failed",
        "symbols": signals,
        "notes": "; ".join(failures[:5]) if failures else "live Kronos output",
    }
