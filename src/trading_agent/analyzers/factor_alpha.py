from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from trading_agent.core.io import read_json

DEFAULT_FACTOR_PROFILE = "baseline_price_factors_v1"


def load_factor_profile(agent_root: Path, *, profile_name: str | None = None) -> dict[str, Any]:
    """Resolve a factor weighting profile from src/config/factor_profiles.json by explicit name
    (else FACTOR_PROFILE env, else the file's default). By-name resolution mirrors
    load_scoring_profile/load_policy_profile so a future challenger can use its own factor profile
    without mutating os.environ. Returns {} (disabled) when the file is missing."""
    path = agent_root / "src" / "config" / "factor_profiles.json"
    if not path.exists():
        return {"name": profile_name or DEFAULT_FACTOR_PROFILE, "enabled": False, "weights": {}, "risk_filters": {}}
    payload = read_json(path)
    profiles = payload.get("profiles") if isinstance(payload, dict) else None
    if not isinstance(profiles, dict):
        return {"name": profile_name or DEFAULT_FACTOR_PROFILE, "enabled": False, "weights": {}, "risk_filters": {}}
    default_name = str(payload.get("default_profile") or DEFAULT_FACTOR_PROFILE)
    name = str(profile_name or os.environ.get("FACTOR_PROFILE") or default_name)
    selected = profiles.get(name) or profiles.get(default_name) or {}
    return {
        "name": name if name in profiles else default_name,
        "enabled": bool(selected.get("enabled", True)),
        "weights": dict(selected.get("weights") or {}),
        "risk_filters": dict(selected.get("risk_filters") or {}),
    }


def _percentile_ranks(values_by_symbol: dict[str, float]) -> dict[str, float]:
    """Cross-sectional percentile rank in [0, 100]; ties share their average rank. Single symbol → 50."""
    items = sorted(values_by_symbol.items(), key=lambda kv: kv[1])
    n = len(items)
    if n == 1:
        return {items[0][0]: 50.0}
    ranks: dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and items[j + 1][1] == items[i][1]:
            j += 1
        avg_pos = (i + j) / 2  # 0-indexed average position among ties
        pct = round(avg_pos / (n - 1) * 100, 2)
        for k in range(i, j + 1):
            ranks[items[k][0]] = pct
        i = j + 1
    return ranks


def _risk_flags(factors: dict[str, Any], risk_filters: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    beta = factors.get("beta_60d")
    if beta is not None and "max_beta_60d" in risk_filters and beta > float(risk_filters["max_beta_60d"]):
        flags.append("high_beta")
    dv = factors.get("dollar_volume_20d")
    if dv is not None and "min_dollar_volume_20d" in risk_filters and dv < float(risk_filters["min_dollar_volume_20d"]):
        flags.append("low_liquidity")
    vol = factors.get("realized_vol_20d")
    if vol is not None and "max_realized_vol_20d" in risk_filters and vol > float(risk_filters["max_realized_vol_20d"]):
        flags.append("high_volatility")
    return flags


def compute_factor_alpha(panel: dict[str, dict[str, Any]], profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Cross-sectional factor model: for each weighted factor, rank-normalize its values across the
    panel's symbols (0-100), then per symbol take a coverage-normalized weighted sum into
    factor_alpha_score (0-100). A positive weight ranks higher-raw-value better; a negative weight
    inverts (lower is better). Generic over the weights dict — adding a factor changes nothing here.

    Returns {symbol: {factor_alpha_score, factor_components, risk_flags, suggested_use}}.
    """
    weights = {k: float(v) for k, v in (profile.get("weights") or {}).items() if v}
    risk_filters = profile.get("risk_filters") or {}
    symbols = list(panel.keys())

    # Per-factor cross-sectional ranks (only over symbols that have a value for that factor).
    factor_ranks: dict[str, dict[str, float]] = {}
    for fname, weight in weights.items():
        cross = {sym: float(panel[sym][fname]) for sym in symbols
                 if isinstance(panel.get(sym), dict) and panel[sym].get(fname) is not None}
        if not cross:
            continue
        ranks = _percentile_ranks(cross)
        if weight < 0:  # lower raw value is better -> invert the rank
            ranks = {sym: round(100.0 - r, 2) for sym, r in ranks.items()}
        factor_ranks[fname] = ranks

    out: dict[str, dict[str, Any]] = {}
    for sym in symbols:
        factors = panel.get(sym) or {}
        components: dict[str, float] = {}
        weighted_sum = 0.0
        weight_total = 0.0
        for fname, weight in weights.items():
            rank = factor_ranks.get(fname, {}).get(sym)
            if rank is None:
                continue
            components[fname] = rank
            weighted_sum += abs(weight) * rank
            weight_total += abs(weight)
        score = round(weighted_sum / weight_total, 2) if weight_total > 0 else None
        out[sym] = {
            "factor_alpha_score": score,
            "factor_components": components,
            "coverage": round(weight_total / sum(abs(w) for w in weights.values()), 4) if weights else 0.0,
            "risk_flags": _risk_flags(factors, risk_filters),
            "suggested_use": "ranking_boost",
        }
    return out
