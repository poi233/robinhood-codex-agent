from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.io import write_json
from trading_agent.replay.ai_signal_study import AI_LAYERS, load_ai_signals
from trading_agent.replay.component_attribution import _spearman_ic
from trading_agent.replay.forward_returns import (
    DEFAULT_HORIZONS,
    PriceLoader,
    compute_forward_return_records,
    default_price_loader,
)

# Directional conviction sign: a long call adds +confidence, a short call -confidence, neutral 0.
_DIR_SIGN = {"long": 1.0, "short": -1.0, "neutral": 0.0}


def _composite_ai_score(envelopes: list[dict[str, Any]]) -> float:
    """Sum of direction_sign x confidence across a symbol's AI envelopes. This is the simple combined
    'conviction' the ablation perturbs: dropping a layer drops that layer's envelopes from the sum."""
    total = 0.0
    for env in envelopes:
        sign = _DIR_SIGN.get(str(env.get("direction")), 0.0)
        try:
            total += sign * float(env.get("confidence") or 0.0)
        except (TypeError, ValueError):
            continue
    return total


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    for rank, idx in enumerate(order):
        ranks[idx] = float(rank)
    return ranks


def ai_ablation_report(
    agent_root: Path,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    since: str | None = None,
    until: str | None = None,
    price_loader: PriceLoader = default_price_loader,
) -> dict[str, Any]:
    """H3 step 3 — AI-layer ablation. Builds a combined AI conviction score per (run_date, symbol),
    then recomputes its forward-return rank IC with each layer dropped, so the *marginal* IC
    contribution of each layer is visible (full IC - leave-one-out IC). Also reports factor-only and
    AI+factor IC so the AI layers can be weighed against the H2 price-factor score. First version uses
    already-persisted signals (no historical AI re-run). Read-only; injectable loader for tests."""
    records = compute_forward_return_records(agent_root, horizons=horizons, since=since, until=until, price_loader=price_loader)
    ret_index: dict[tuple[str, str], dict[int, float | None]] = {(r.run_date, r.symbol): r.returns for r in records}
    # factor_alpha is folded into each record's components by the H1 calibration pickup.
    factor_index: dict[tuple[str, str], float] = {}
    for r in records:
        fa = r.components.get("factor_alpha")
        if fa is not None:
            factor_index[(r.run_date, r.symbol)] = float(fa)

    signals = load_ai_signals(agent_root, since=since, until=until)
    # Group envelopes by (run_date, symbol), keeping only keys that have a forward return.
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for sig in signals:
        key = (sig.get("run_date"), str(sig.get("symbol") or "").upper())
        if key in ret_index:
            grouped[key].append(sig)

    primary_h = horizons[0] if horizons else 1

    def _ic_for(score_fn, keys: list[tuple[str, str]], horizon: int) -> tuple[float | None, int]:
        pairs: list[tuple[float, float]] = []
        for key in keys:
            ret = ret_index[key].get(horizon)
            if ret is None:
                continue
            score = score_fn(key)
            if score is None:
                continue
            pairs.append((float(score), float(ret)))
        ic = _spearman_ic(pairs)
        return (round(ic, 4) if ic is not None else None, len(pairs))

    ai_keys = list(grouped.keys())

    def _composite_excluding(exclude: str | None):
        def fn(key: tuple[str, str]) -> float:
            envs = [e for e in grouped[key] if e.get("layer") != exclude] if exclude else grouped[key]
            return _composite_ai_score(envs)
        return fn

    variants: dict[str, Any] = {}
    full_ic, full_n = _ic_for(_composite_excluding(None), ai_keys, primary_h)
    variants["full_ai"] = {"ic": full_ic, "n": full_n}
    for layer in AI_LAYERS:
        ic, n = _ic_for(_composite_excluding(layer), ai_keys, primary_h)
        marginal = round(full_ic - ic, 4) if (full_ic is not None and ic is not None) else None
        variants[f"drop_{layer}"] = {"ic": ic, "n": n, "marginal_ic_of_layer": marginal}

    # Factor-only and AI+factor (rank-combined on the intersection) for an AI-vs-factor read.
    factor_keys = [k for k in ai_keys if k in factor_index]
    factor_ic, factor_n = _ic_for(lambda k: factor_index.get(k), factor_keys, primary_h)
    variants["factor_only"] = {"ic": factor_ic, "n": factor_n}

    both_keys = [k for k in ai_keys if k in factor_index]
    combined_ic: float | None = None
    if both_keys:
        ai_scores = [_composite_ai_score(grouped[k]) for k in both_keys]
        fa_scores = [factor_index[k] for k in both_keys]
        ai_r = _ranks(ai_scores)
        fa_r = _ranks(fa_scores)
        combined = {k: ai_r[i] + fa_r[i] for i, k in enumerate(both_keys)}
        combined_ic, _ = _ic_for(lambda k: combined.get(k), both_keys, primary_h)
    variants["ai_plus_factor"] = {"ic": combined_ic, "n": len(both_keys)}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "primary_horizon": primary_h,
        "ai_signal_count": len(signals),
        "matched_symbol_runs": len(ai_keys),
        "variants": variants,
        "note": "Read-only ablation on persisted signals (no historical AI re-run). Small samples are "
                "noisy — wait for 15-30 run dates. marginal_ic_of_layer = full_ai IC - leave-one-out IC.",
    }


def default_ai_ablation_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "ai_ablation.json"


def default_ai_ablation_md_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "ai_ablation.md"


def _fmt_ic(value: Any) -> str:
    return f"{value:+.3f}" if isinstance(value, (int, float)) else "—"


def format_ai_ablation_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AI Layer Ablation (H3 step 3)",
        "",
        f"_Generated {report['generated_at']}._ AI signals: {report['ai_signal_count']} · "
        f"matched symbol-runs: {report['matched_symbol_runs']} · horizon: {report['primary_horizon']}d",
        "",
        "> Read-only. Combined AI conviction = Σ(direction × confidence). `marginal_ic_of_layer` is how "
        "much the combined rank IC drops when that layer is removed — a positive marginal means the "
        "layer adds predictive value. Small samples are noisy.",
        "",
    ]
    variants = report.get("variants") or {}
    if not variants or (variants.get("full_ai") or {}).get("n", 0) == 0:
        lines.append("_No AI signals matched to forward returns yet._")
        return "\n".join(lines) + "\n"

    full = variants.get("full_ai") or {}
    lines.append(f"- **full AI:** IC {_fmt_ic(full.get('ic'))} (n={full.get('n', 0)})")
    for layer in AI_LAYERS:
        v = variants.get(f"drop_{layer}") or {}
        lines.append(f"- drop {layer}: IC {_fmt_ic(v.get('ic'))} (n={v.get('n', 0)})  ·  "
                     f"marginal of {layer}: {_fmt_ic(v.get('marginal_ic_of_layer'))}")
    fo = variants.get("factor_only") or {}
    af = variants.get("ai_plus_factor") or {}
    lines.append(f"- factor only: IC {_fmt_ic(fo.get('ic'))} (n={fo.get('n', 0)})")
    lines.append(f"- AI + factor (rank-combined): IC {_fmt_ic(af.get('ic'))} (n={af.get('n', 0)})")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_ai_ablation_report(
    agent_root: Path,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    since: str | None = None,
    until: str | None = None,
    price_loader: PriceLoader = default_price_loader,
) -> tuple[Path, Path]:
    report = ai_ablation_report(agent_root, horizons=horizons, since=since, until=until, price_loader=price_loader)
    json_path = default_ai_ablation_path(agent_root)
    md_path = default_ai_ablation_md_path(agent_root)
    write_json(json_path, report)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(format_ai_ablation_markdown(report), encoding="utf-8")
    return json_path, md_path
