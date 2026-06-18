from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.io import read_json, write_json

# K1 — Portfolio Layer (first version). The problem it addresses: NVDA/AVGO/ANET/MRVL/VRT look like 5
# positions but are really one AI-infra bet. This computes the *actual* portfolio composition (cash,
# per-position weight, per-theme exposure) and the target caps, and flags breaches.
#
# HARD RED LINE: advisory + write-only. It NEVER adds a buy signal and NEVER places/sizes a trade.
# Its only directional effect, once wired into sizing later, is to TIGHTEN (cap concentration / hold
# cash) — never to add or enlarge a position. First version just writes portfolio_target.json.

DEFAULT_CASH_TARGET = 0.20        # target minimum cash fraction
DEFAULT_MAX_POSITION_SIZE = 0.08  # cap on a single name's portfolio weight
DEFAULT_THEME_CAP = 0.35          # cap on a single theme's portfolio weight
DEFAULT_SECTOR_CAP = 0.40         # cap on a single sector's portfolio weight (broader than theme)


def _load_field_map(config_dir: Path, field: str) -> dict[str, str]:
    """symbol -> <field> from universe_meta.json (symbols missing the field are simply omitted,
    so callers treat them as 'unknown' per the universe_meta convention)."""
    path = config_dir / "universe_meta.json"
    if not path.exists():
        return {}
    meta = read_json(path)
    if not isinstance(meta, dict):
        return {}
    out: dict[str, str] = {}
    for symbol, data in meta.items():
        if isinstance(data, dict) and data.get(field):
            out[symbol.upper()] = str(data[field])
    return out


def load_theme_map(config_dir: Path) -> dict[str, str]:
    """symbol -> theme from universe_meta.json (missing => 'unknown')."""
    return _load_field_map(config_dir, "theme")


def load_sector_map(config_dir: Path) -> dict[str, str]:
    """symbol -> sector from universe_meta.json (missing => 'unknown'). Sector is broader than theme
    (e.g. many AI themes roll up to 'technology'); the field is optional and filled incrementally."""
    return _load_field_map(config_dir, "sector")


def _position_market_value(position: dict[str, Any]) -> float:
    try:
        qty = float(position.get("quantity", 0) or 0)
        price = float(position.get("market_price") or position.get("average_cost") or 0)
    except (TypeError, ValueError):
        return 0.0
    return qty * price


def build_portfolio_target(
    positions: dict[str, Any],
    cash: float,
    theme_map: dict[str, str],
    *,
    cash_target: float = DEFAULT_CASH_TARGET,
    max_position_size: float = DEFAULT_MAX_POSITION_SIZE,
    theme_cap: float = DEFAULT_THEME_CAP,
    sector_map: dict[str, str] | None = None,
    sector_cap: float = DEFAULT_SECTOR_CAP,
) -> dict[str, Any]:
    """Compute current composition + target caps + breaches. Pure. Weights are fractions of total
    equity (cash + position market value). sector_map is optional: when supplied, sector exposure is
    computed and capped (broader than theme); symbols without a sector roll up to 'unknown'."""
    sector_map = sector_map or {}
    pos_values = {sym.upper(): _position_market_value(p) for sym, p in positions.items() if isinstance(p, dict)}
    pos_values = {sym: v for sym, v in pos_values.items() if v > 0}
    positions_mv = sum(pos_values.values())
    total_equity = round(cash + positions_mv, 2)

    position_weights: dict[str, float] = {}
    theme_exposure: dict[str, float] = {}
    sector_exposure: dict[str, float] = {}
    if total_equity > 0:
        for sym, mv in pos_values.items():
            w = mv / total_equity
            position_weights[sym] = round(w, 4)
            theme = theme_map.get(sym, "unknown")
            theme_exposure[theme] = round(theme_exposure.get(theme, 0.0) + w, 4)
            sector = sector_map.get(sym, "unknown")
            sector_exposure[sector] = round(sector_exposure.get(sector, 0.0) + w, 4)

    cash_weight = round(cash / total_equity, 4) if total_equity > 0 else 1.0
    oversize = sorted([s for s, w in position_weights.items() if w > max_position_size])
    overexposed = sorted([t for t, w in theme_exposure.items() if w > theme_cap])
    # Only flag a sector breach when we actually know the sector (don't penalize 'unknown').
    oversector = sorted([s for s, w in sector_exposure.items() if s != "unknown" and w > sector_cap])

    return {
        "total_equity": total_equity,
        "cash": round(cash, 2),
        "cash_weight": cash_weight,
        "targets": {
            "cash_target": cash_target,
            "max_position_size": max_position_size,
            "theme_cap": theme_cap,
            "sector_cap": sector_cap,
        },
        "position_weights": dict(sorted(position_weights.items(), key=lambda kv: -kv[1])),
        "theme_exposure": dict(sorted(theme_exposure.items(), key=lambda kv: -kv[1])),
        "sector_exposure": dict(sorted(sector_exposure.items(), key=lambda kv: -kv[1])),
        "breaches": {
            "below_cash_target": cash_weight < cash_target,
            "oversize_positions": oversize,
            "overexposed_themes": overexposed,
            "overexposed_sectors": oversector,
        },
        "notes": "Advisory only (K1): describes current concentration vs target caps. Never a buy "
                 "signal; once wired into sizing it can only tighten (cap/hold cash), never enlarge.",
    }


def default_portfolio_target_path(agent_root: Path, run_date: str) -> Path:
    from trading_agent.core.context import build_runtime_paths

    return build_runtime_paths(agent_root, run_date=run_date).planner_dir / "portfolio_target.json"


def build_and_write_portfolio_target(agent_root: Path, run_date: str) -> Path:
    """Read paper positions + account cash + theme map, compute the portfolio target, write it.
    Read-only w.r.t. trading; produces one advisory artifact."""
    from trading_agent.core.context import build_runtime_paths

    paths = build_runtime_paths(agent_root, run_date=run_date)
    positions = read_json(paths.paper_positions_path) if paths.paper_positions_path.exists() else {}
    if not isinstance(positions, dict):
        positions = {}
    account = read_json(paths.paper_account_path) if paths.paper_account_path.exists() else {}
    cash = float(account.get("cash", 0) or 0) if isinstance(account, dict) else 0.0
    theme_map = load_theme_map(paths.config_dir)
    sector_map = load_sector_map(paths.config_dir)

    payload = {
        "date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        **build_portfolio_target(positions, cash, theme_map, sector_map=sector_map),
    }
    out = default_portfolio_target_path(agent_root, run_date)
    write_json(out, payload)
    return out
