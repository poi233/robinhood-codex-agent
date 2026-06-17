from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json
from trading_agent.replay.analysis import discover_run_dates
from trading_agent.replay.component_attribution import _spearman_ic
from trading_agent.replay.forward_returns import (
    DEFAULT_HORIZONS,
    PriceLoader,
    compute_forward_return_records,
    default_price_loader,
)

# Layers whose standardized envelopes we study. Quote/technical are deterministic, not AI, and stay
# in component_attribution; this module is specifically the ChatGPT Phase-3 "AI signal study".
AI_LAYERS = ("dsa", "kronos", "catalyst")


def load_ai_signals(agent_root: Path, *, since: str | None = None, until: str | None = None) -> list[dict[str, Any]]:
    """Flatten every run's `ai_signals.json` into a list of envelopes, each tagged with its run_date.
    Missing files are skipped (the layer only starts emitting once H3 step 1 has run on that date)."""
    out: list[dict[str, Any]] = []
    for run_date in discover_run_dates(agent_root, since_date=since, until_date=until):
        path = build_runtime_paths(agent_root, run_date=run_date).ai_signals_path
        if not path.exists():
            continue
        payload = read_json(path)
        layers = payload.get("layers") if isinstance(payload, dict) else None
        if not isinstance(layers, dict):
            continue
        for layer_name, envelopes in layers.items():
            if not isinstance(envelopes, list):
                continue
            for env in envelopes:
                if not isinstance(env, dict):
                    continue
                row = dict(env)
                row["run_date"] = run_date
                row.setdefault("layer", layer_name)
                out.append(row)
    return out


def _hit(direction: str, ret: float) -> bool | None:
    """Did the signal's directional call match the realized move? Neutral has no directional claim."""
    if direction == "long":
        return ret > 0
    if direction == "short":
        return ret < 0
    return None


def _confidence_buckets(pairs: list[tuple[float, float]], *, n_buckets: int) -> list[dict[str, Any]]:
    """Bucket (confidence, return) pairs by confidence quantile; report mean return + hit rate."""
    if not pairs:
        return []
    pairs = sorted(pairs, key=lambda p: p[0])
    n = len(pairs)
    n_buckets = max(1, min(n_buckets, n))
    buckets: list[dict[str, Any]] = []
    for b in range(n_buckets):
        lo = b * n // n_buckets
        hi = (b + 1) * n // n_buckets if b < n_buckets - 1 else n
        chunk = pairs[lo:hi]
        if not chunk:
            continue
        confs = [c for c, _ in chunk]
        rets = [r for _, r in chunk]
        buckets.append({
            "bucket": b + 1,
            "count": len(chunk),
            "confidence_min": round(min(confs), 3),
            "confidence_max": round(max(confs), 3),
            "mean_return": round(sum(rets) / len(rets), 6),
            "hit_rate": round(sum(1 for r in rets if r > 0) / len(rets), 4),
        })
    return buckets


def _code_effectiveness(
    rows: list[dict[str, Any]], *, field: str, horizon: int
) -> list[dict[str, Any]]:
    """For each reason/warning code, mean forward return of signals carrying it vs not carrying it.
    A positive gap means the code marks better-performing signals (for warnings, ideally negative)."""
    all_returns = [r["_returns"].get(horizon) for r in rows if r["_returns"].get(horizon) is not None]
    if not all_returns:
        return []
    carriers: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        ret = row["_returns"].get(horizon)
        if ret is None:
            continue
        for code in row.get(field) or []:
            carriers[str(code)].append(ret)
    baseline = sum(all_returns) / len(all_returns)
    out: list[dict[str, Any]] = []
    for code, rets in carriers.items():
        if len(rets) < 2:
            continue
        mean_with = sum(rets) / len(rets)
        out.append({
            "code": code,
            "count": len(rets),
            "mean_return_with": round(mean_with, 6),
            "lift_vs_baseline": round(mean_with - baseline, 6),
        })
    out.sort(key=lambda r: abs(r["lift_vs_baseline"]), reverse=True)
    return out


def ai_signal_study_report(
    agent_root: Path,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    since: str | None = None,
    until: str | None = None,
    price_loader: PriceLoader = default_price_loader,
    n_buckets: int = 4,
) -> dict[str, Any]:
    """H3 step 2 — AI-signal study. Joins standardized AI envelopes to candidate forward returns and
    reports, per layer: confidence calibration (does higher confidence earn higher returns?),
    directional accuracy (did long/short calls match the move?), confidence→return rank IC, and
    reason/warning-code lift. Read-only; injectable loader for offline tests."""
    records = compute_forward_return_records(agent_root, horizons=horizons, since=since, until=until, price_loader=price_loader)
    ret_index: dict[tuple[str, str], dict[int, float | None]] = {(r.run_date, r.symbol): r.returns for r in records}

    signals = load_ai_signals(agent_root, since=since, until=until)
    # Attach forward returns; keep only signals whose (run_date, symbol) has a scored candidate.
    matched: list[dict[str, Any]] = []
    for sig in signals:
        key = (sig.get("run_date"), str(sig.get("symbol") or "").upper())
        returns = ret_index.get(key)
        if returns is None:
            continue
        sig["_returns"] = returns
        matched.append(sig)

    primary_h = horizons[0] if horizons else 1
    generated_at = datetime.now(timezone.utc).isoformat()
    by_layer: dict[str, dict[str, Any]] = {}
    for layer in AI_LAYERS:
        rows = [s for s in matched if s.get("layer") == layer]
        if not rows:
            by_layer[layer] = {"signal_count": 0}
            continue
        # Confidence calibration + IC per horizon.
        calibration: dict[str, Any] = {}
        confidence_ic: dict[str, float | None] = {}
        for h in horizons:
            pairs = [(float(s["confidence"]), s["_returns"][h]) for s in rows
                     if s.get("confidence") is not None and s["_returns"].get(h) is not None]
            calibration[str(h)] = _confidence_buckets(pairs, n_buckets=n_buckets)
            confidence_ic[str(h)] = round(_spearman_ic(pairs), 4) if _spearman_ic(pairs) is not None else None
        # Directional accuracy at the primary horizon.
        dir_hits = [(_hit(str(s.get("direction")), s["_returns"][primary_h])) for s in rows
                    if s["_returns"].get(primary_h) is not None]
        directional = [h for h in dir_hits if h is not None]
        by_layer[layer] = {
            "signal_count": len(rows),
            "confidence_calibration": calibration,
            "confidence_ic": confidence_ic,
            "directional_accuracy": round(sum(1 for h in directional if h) / len(directional), 4) if directional else None,
            "directional_count": len(directional),
            "reason_code_lift": _code_effectiveness(rows, field="reason_codes", horizon=primary_h),
            "warning_code_lift": _code_effectiveness(rows, field="warning_codes", horizon=primary_h),
        }

    return {
        "generated_at": generated_at,
        "horizons": list(horizons),
        "primary_horizon": primary_h,
        "ai_signal_count": len(signals),
        "matched_count": len(matched),
        "layers": by_layer,
        "note": "Read-only AI-signal study. Small samples are noisy — wait for 15-30 run dates.",
    }


def default_ai_signal_study_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "ai_signal_study.json"


def default_ai_signal_study_md_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "ai_signal_study.md"


def _fmt_pct(value: Any) -> str:
    return f"{value * 100:+.2f}%" if isinstance(value, (int, float)) else "—"


def format_ai_signal_study_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AI Signal Study (H3 step 2)",
        "",
        f"_Generated {report['generated_at']}._ AI signals: {report['ai_signal_count']} · "
        f"matched to forward returns: {report['matched_count']} · primary horizon: {report['primary_horizon']}d",
        "",
        "> Read-only. Joins standardized AI envelopes to candidate forward returns. Does not change any "
        "strategy parameter. Small samples are noisy — wait for 15-30 run dates.",
        "",
    ]
    if report["matched_count"] == 0:
        lines.append("_No AI signals matched to forward returns yet (need run dates with ai_signals.json + future bars)._")
        return "\n".join(lines) + "\n"

    for layer, data in report["layers"].items():
        if not data.get("signal_count"):
            continue
        lines.append(f"## {layer} ({data['signal_count']} signals)")
        lines.append("")
        acc = data.get("directional_accuracy")
        acc_str = f"{acc * 100:.0f}% (n={data['directional_count']})" if acc is not None else "—"
        ic_primary = (data.get("confidence_ic") or {}).get(str(report["primary_horizon"]))
        ic_str = f"{ic_primary:+.2f}" if isinstance(ic_primary, (int, float)) else "—"
        lines.append(f"- directional accuracy ({report['primary_horizon']}d): {acc_str}  ·  confidence IC: {ic_str}")
        primary_buckets = (data.get("confidence_calibration") or {}).get(str(report["primary_horizon"])) or []
        if primary_buckets:
            lines.append(f"- confidence calibration ({report['primary_horizon']}d, low→high):")
            for b in primary_buckets:
                lines.append(f"  - bucket {b['bucket']} [{b['confidence_min']}–{b['confidence_max']}]  "
                             f"n={b['count']}  mean={_fmt_pct(b['mean_return'])}  hit={b['hit_rate'] * 100:.0f}%")
        for label, key in (("reason codes", "reason_code_lift"), ("warning codes", "warning_code_lift")):
            codes = data.get(key) or []
            if codes:
                top = ", ".join(f"{c['code']}={_fmt_pct(c['lift_vs_baseline'])}(n{c['count']})" for c in codes[:5])
                lines.append(f"- {label} lift vs baseline: {top}")
        lines.append("")
    return "\n".join(lines) + "\n"


def write_ai_signal_study_report(
    agent_root: Path,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    since: str | None = None,
    until: str | None = None,
    price_loader: PriceLoader = default_price_loader,
) -> tuple[Path, Path]:
    report = ai_signal_study_report(agent_root, horizons=horizons, since=since, until=until, price_loader=price_loader)
    json_path = default_ai_signal_study_path(agent_root)
    md_path = default_ai_signal_study_md_path(agent_root)
    write_json(json_path, report)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(format_ai_signal_study_markdown(report), encoding="utf-8")
    return json_path, md_path
