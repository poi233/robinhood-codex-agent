from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Mapping, Sequence

from trading_agent.contracts.dsa import validate_dsa_payload
from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import ensure_dir, read_json, write_json
from trading_agent.core.run_history import append_prompt_progress_log
from trading_agent.core.time import PT, pt_now
from trading_agent.data.universe import parse_universe
from trading_agent.prompts.codex import run_codex_prompt

PromptRunner = Callable[..., int]

THEME_SCORE_KEYS = (
    "ai_semiconductors",
    "ai_data_center_infrastructure",
    "cpo_photonics_interconnect",
    "space_defense_autonomy",
    "nuclear_power_grid",
    "broad_beta",
)


def _positive_int_from_env(name: str, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    raw = os.environ.get(name)
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def chunk_symbols(symbols: Sequence[str], batch_size: int) -> list[list[str]]:
    size = max(1, batch_size)
    return [list(symbols[index : index + size]) for index in range(0, len(symbols), size)]


def _ordered_unique(values: Sequence[str], universe: Sequence[str]) -> list[str]:
    requested = {str(value).upper() for value in values}
    return [symbol for symbol in universe if symbol.upper() in requested]


def _downgrade_ok_to_partial(status: str, *, failed_count: int) -> str:
    if failed_count > 0 and status == "ok":
        return "partial"
    return status


def _candidate_sort_key(symbol: str, signal: Mapping[str, object], universe_index: Mapping[str, int]) -> tuple[float, int]:
    return (-_score(signal), universe_index.get(symbol, len(universe_index)))


def _failed_symbol_signal(symbol: str, reason: str) -> dict[str, object]:
    return {
        "dsa_score": 0,
        "bias": "blocked",
        "primary_theme": "unknown",
        "strategy_matches": [],
        "setup": "blocked",
        "evidence_summary": reason,
        "risk_flags": [reason],
        "reject_reasons": [reason],
        "confidence": "low",
        "data_quality": "failed",
        "suggested_premarket_use": "block",
    }


def _normalize_symbol_signal(value: object, symbol: str) -> dict[str, object]:
    if not isinstance(value, dict):
        return _failed_symbol_signal(symbol, "batch returned invalid symbol signal")
    signal = dict(value)
    signal.setdefault("dsa_score", 0)
    signal.setdefault("bias", "watch_only")
    signal.setdefault("primary_theme", "unknown")
    signal.setdefault("strategy_matches", [])
    signal.setdefault("setup", "watch_only")
    signal.setdefault("evidence_summary", "batch returned limited evidence")
    signal.setdefault("risk_flags", [])
    signal.setdefault("reject_reasons", [])
    signal.setdefault("confidence", "low")
    signal.setdefault("data_quality", "partial")
    signal.setdefault("suggested_premarket_use", "neutral")
    return signal


def _score(signal: Mapping[str, object]) -> float:
    try:
        return float(signal.get("dsa_score") or 0)
    except (TypeError, ValueError):
        return 0.0


def _rollup_data_status(payloads: Sequence[Mapping[str, object]], key: str, *, default: str = "failed") -> str:
    values: list[str] = []
    for payload in payloads:
        data_status = payload.get("data_status")
        if isinstance(data_status, dict):
            value = data_status.get(key)
            if isinstance(value, str):
                values.append(value)
    if not values:
        return default
    if all(value == "ok" for value in values):
        return "ok"
    if all(value == "failed" for value in values):
        return "failed"
    return "partial"


def _rollup_wash_sale_status(payloads: Sequence[Mapping[str, object]]) -> str:
    values: list[str] = []
    for payload in payloads:
        data_status = payload.get("data_status")
        if isinstance(data_status, dict):
            value = data_status.get("wash_sale_blocks")
            if isinstance(value, str):
                values.append(value)
    if "ok" in values:
        return "ok"
    if "missing" in values:
        return "missing"
    return "not_applicable"


def _rollup_market_phase(payloads: Sequence[Mapping[str, object]]) -> str:
    phases = [payload.get("market_phase") for payload in payloads if payload.get("market_phase") != "unknown"]
    normalized = [phase for phase in phases if phase in {"risk_on", "mixed", "risk_off"}]
    if not normalized:
        return "unknown"
    if len(set(normalized)) == 1:
        return str(normalized[0])
    return "mixed"


def _rollup_theme_scores(payloads: Sequence[Mapping[str, object]]) -> dict[str, int]:
    scores = {key: 0 for key in THEME_SCORE_KEYS}
    for payload in payloads:
        theme_scores = payload.get("theme_scores")
        if not isinstance(theme_scores, dict):
            continue
        for key in THEME_SCORE_KEYS:
            try:
                scores[key] = max(scores[key], int(theme_scores.get(key) or 0))
            except (TypeError, ValueError):
                continue
    return scores


def _expires_at_for_run() -> str:
    now = pt_now()
    return now.replace(hour=16, minute=0, second=0, microsecond=0, tzinfo=PT).isoformat()


def merge_dsa_batch_payloads(
    *,
    run_date: str,
    universe: Sequence[str],
    batch_payloads: Sequence[Mapping[str, object]],
    failed_symbols: Mapping[str, str],
) -> dict[str, object]:
    symbol_signals: dict[str, dict[str, object]] = {}
    blocked: list[str] = []

    for payload in batch_payloads:
        payload_signals = payload.get("symbol_signals")
        if isinstance(payload_signals, dict):
            for symbol, signal in payload_signals.items():
                normalized = str(symbol).upper()
                if normalized in {item.upper() for item in universe}:
                    symbol_signals[normalized] = _normalize_symbol_signal(signal, normalized)
        blocked.extend(str(symbol).upper() for symbol in payload.get("blocked_symbols") or [])

    for symbol in universe:
        if symbol not in symbol_signals:
            reason = failed_symbols.get(symbol, "missing DSA batch output for symbol")
            symbol_signals[symbol] = _failed_symbol_signal(symbol, reason)
            blocked.append(symbol)

    for symbol, signal in symbol_signals.items():
        if signal.get("bias") == "blocked" or signal.get("suggested_premarket_use") == "block":
            blocked.append(symbol)

    blocked_symbols = _ordered_unique(blocked, universe)
    blocked_set = set(blocked_symbols)
    universe_index = {symbol: index for index, symbol in enumerate(universe)}
    selected_candidates = [
        symbol
        for symbol, signal in sorted(
            symbol_signals.items(),
            key=lambda item: _candidate_sort_key(item[0], item[1], universe_index),
        )
        if symbol not in blocked_set
        and signal.get("bias") in {"strong_candidate", "candidate"}
        and signal.get("suggested_premarket_use") in {"promote", "neutral"}
    ][:10]

    failed_count = len({symbol for symbol in failed_symbols if symbol in universe})
    data_default = "failed" if not batch_payloads else "partial"
    quotes_status = _rollup_data_status(batch_payloads, "quotes", default=data_default)
    news_status = _rollup_data_status(batch_payloads, "news", default=data_default)
    historicals_status = _rollup_data_status(batch_payloads, "historicals", default=data_default)
    payload: dict[str, object] = {
        "date": run_date,
        "generated_at": pt_now().isoformat(),
        "expires_at": _expires_at_for_run(),
        "source": {
            "name": "codex_dsa_signal_layer",
            "inspired_by": "https://github.com/ZhuLinsen/daily_stock_analysis",
            "mode": "strategy_signal_layer_only",
            "execution": "parallel_batch_merge",
        },
        "data_status": {
            "quotes": _downgrade_ok_to_partial(quotes_status, failed_count=failed_count),
            "news": _downgrade_ok_to_partial(news_status, failed_count=failed_count),
            "historicals": _downgrade_ok_to_partial(historicals_status, failed_count=failed_count),
            "wash_sale_blocks": _rollup_wash_sale_status(batch_payloads),
        },
        "market_phase": _rollup_market_phase(batch_payloads),
        "theme_scores": _rollup_theme_scores(batch_payloads),
        "selected_candidates": selected_candidates,
        "blocked_symbols": blocked_symbols,
        "symbol_signals": symbol_signals,
        "notes": (
            f"Merged {len(batch_payloads)} DSA batch output(s); "
            f"{failed_count} symbol(s) failed or were missing from batch output."
        ),
    }
    validate_dsa_payload(payload)
    return payload


def _append_dsa_decision(
    *,
    decisions_log_path: Path,
    trading_mode: str,
    checked_symbols: Sequence[str],
    selected_candidates: Sequence[str],
    blocked_symbols: Sequence[str],
    failed_symbol_count: int,
) -> None:
    if failed_symbol_count == 0:
        decision = "dsa_signals_generated"
        reason = "parallel DSA batches completed"
    elif failed_symbol_count < len(checked_symbols):
        decision = "dsa_signals_partial"
        reason = f"parallel DSA batches completed with {failed_symbol_count} failed or missing symbol(s)"
    else:
        decision = "dsa_signals_failed"
        reason = "all DSA batch symbols failed or were missing"
    ensure_dir(decisions_log_path.parent)
    with decisions_log_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "timestamp": pt_now().isoformat(),
                    "run_kind": "dsa_premarket_scan",
                    "trading_mode": trading_mode,
                    "decision": decision,
                    "action_taken": "none",
                    "checked_symbols": list(checked_symbols),
                    "selected_candidates": list(selected_candidates),
                    "blocked_symbols": list(blocked_symbols),
                    "reason": reason,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )


def _read_batch_payload(output_path: Path, symbols: Sequence[str]) -> tuple[dict[str, object] | None, dict[str, str]]:
    if not output_path.exists():
        return None, {symbol: "DSA batch output missing" for symbol in symbols}
    try:
        payload = read_json(output_path)
    except Exception as exc:
        return None, {symbol: f"DSA batch output was not valid JSON: {exc}" for symbol in symbols}
    if not isinstance(payload, dict):
        return None, {symbol: "DSA batch output root was not an object" for symbol in symbols}
    return payload, {}


def run_parallel_dsa_scan(
    agent_root: Path,
    *,
    prompt_runner: PromptRunner = run_codex_prompt,
) -> None:
    paths = build_runtime_paths(agent_root)
    prompt_file = paths.prompts_dir / "signals" / "dsa_scan_batch.txt"
    fallback_prompt_file = paths.prompts_dir / "signals" / "dsa_scan.txt"
    if os.environ.get("CODEX_EXEC_DRY_RUN", "0") == "1":
        status = prompt_runner("dsa_premarket_scan", agent_root, fallback_prompt_file)
        if status != 0:
            raise RuntimeError("dsa dry-run prompt failed")
        return

    universe_file = paths.config_dir / "universe.txt"
    symbols = parse_universe(universe_file)
    batch_size = _positive_int_from_env("DSA_BATCH_SIZE", 8, minimum=1, maximum=50)
    max_workers = _positive_int_from_env("DSA_MAX_WORKERS", 4, minimum=1, maximum=12)
    batches = chunk_symbols(symbols, batch_size)
    batch_output_dir = paths.signals_dir / "dsa_batches"
    ensure_dir(batch_output_dir)
    for stale in batch_output_dir.glob("dsa_batch_*.json"):
        stale.unlink()

    append_prompt_progress_log(
        agent_root,
        paths.run_date,
        "dsa_premarket_scan",
        "started",
        "parallel DSA scan started",
        details={"batch_count": len(batches), "batch_size": batch_size, "max_workers": max_workers},
    )

    def run_batch(index: int, batch_symbols: list[str]) -> tuple[int, list[str], Path, int]:
        batch_id = f"{index:03d}"
        output_path = batch_output_dir / f"dsa_batch_{batch_id}.json"
        run_kind = f"dsa_premarket_scan_batch_{batch_id}"
        overrides = {
            "DSA_BATCH_ID": batch_id,
            "DSA_BATCH_INDEX": str(index),
            "DSA_BATCH_COUNT": str(len(batches)),
            "DSA_BATCH_SYMBOLS": ",".join(batch_symbols),
            "DSA_BATCH_OUTPUT_PATH": str(output_path),
            "DSA_FINAL_SIGNALS_PATH": str(paths.dsa_signals_path),
            "DSA_MAX_SELECTED_CANDIDATES": "10",
        }
        status = prompt_runner(run_kind, agent_root, prompt_file, runtime_overrides=overrides)
        return index, batch_symbols, output_path, status

    batch_payloads: list[Mapping[str, object]] = []
    failed_symbols: dict[str, str] = {}
    max_parallel = min(max_workers, max(1, len(batches)))
    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        futures = [executor.submit(run_batch, index, batch_symbols) for index, batch_symbols in enumerate(batches, start=1)]
        for future in as_completed(futures):
            index, batch_symbols, output_path, status = future.result()
            if status != 0:
                failed_symbols.update({symbol: f"DSA batch {index:03d} prompt exited with status {status}" for symbol in batch_symbols})
                continue
            payload, failures = _read_batch_payload(output_path, batch_symbols)
            failed_symbols.update(failures)
            if payload is not None:
                batch_payloads.append(payload)

    final_payload = merge_dsa_batch_payloads(
        run_date=paths.run_date,
        universe=symbols,
        batch_payloads=batch_payloads,
        failed_symbols=failed_symbols,
    )
    write_json(paths.dsa_signals_path, final_payload)
    _append_dsa_decision(
        decisions_log_path=paths.decisions_log_path,
        trading_mode=os.environ.get("TRADING_MODE", "paper"),
        checked_symbols=symbols,
        selected_candidates=final_payload["selected_candidates"],
        blocked_symbols=final_payload["blocked_symbols"],
        failed_symbol_count=len({symbol for symbol in failed_symbols if symbol in symbols}),
    )
    append_prompt_progress_log(
        agent_root,
        paths.run_date,
        "dsa_premarket_scan",
        "completed",
        "parallel DSA scan completed",
        details={"batch_count": len(batches), "failed_symbol_count": len(failed_symbols)},
    )
    if symbols and len({symbol for symbol in failed_symbols if symbol in symbols}) == len(symbols):
        raise RuntimeError("all DSA batch prompts failed")
