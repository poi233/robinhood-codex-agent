from __future__ import annotations

from pathlib import Path
from typing import Any

from trading_agent.core.io import read_json


def parse_universe(path: Path) -> list[str]:
    seen: set[str] = set()
    symbols: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        candidate = line.strip().upper()
        if not candidate or candidate.startswith("#") or candidate in seen:
            continue
        seen.add(candidate)
        symbols.append(candidate)
    return symbols


def _resolve_watchlist_filename(config_dir: Path) -> str:
    """The watchlist filename the active strategy declares (B5). Lets switching
    `active_strategy` change which symbols get the expensive premarket analysis. Falls back
    to ``active_watchlist.txt`` if the registry is missing/unreadable, so unconfigured
    checkouts behave exactly as before."""
    try:
        from trading_agent.strategy.registry import load_active_strategy

        agent_root = config_dir.parent.parent  # config_dir == agent_root/src/config
        return str(load_active_strategy(agent_root).get("watchlist") or "active_watchlist.txt")
    except Exception:
        return "active_watchlist.txt"


def parse_active_watchlist(config_dir: Path, *, watchlist_filename: str | None = None) -> list[str]:
    """Return active_watchlist symbols.

    The filename is resolved from the active strategy's ``watchlist`` field (B5) unless an
    explicit ``watchlist_filename`` is passed (e.g. a challenger's own watchlist). Falls back
    to the full universe if the resolved file is absent.
    """
    filename = watchlist_filename or _resolve_watchlist_filename(config_dir)
    active_path = config_dir / filename
    if active_path.exists():
        return parse_universe(active_path)
    return parse_universe(config_dir / "universe.txt")


def _tier_of(meta: dict[str, dict], symbol: str) -> str:
    entry = meta.get(symbol) or {}
    return str(entry.get("tier") or "watch")


def _screen_score(meta: dict[str, dict], symbol: str) -> float | None:
    value = (meta.get(symbol) or {}).get("screen_score")
    return float(value) if isinstance(value, (int, float)) else None


def select_dynamic_active(
    *,
    universe: list[str],
    meta: dict[str, dict],
    pins: list[str],
    active_max: int,
) -> dict[str, Any]:
    """O2: choose the day's active set = pins ∪ top-N universe by ``screen_score``.

    Pins (the active_watchlist anchors) are always included — even if they exceed ``active_max``,
    so anchors are never dropped. Remaining slots up to ``active_max`` are filled by the highest
    ``screen_score`` universe symbols (written weekly by O1), excluding ``tier:passive`` and pins.
    Symbols without a ``screen_score`` sort last (after all scored), in universe order. Pure +
    deterministic; returns the active list plus provenance for ``active_selection.json``.
    """
    pins_seen: set[str] = set()
    ordered_pins: list[str] = []
    for raw in pins:
        symbol = raw.strip().upper()
        if symbol and symbol not in pins_seen:
            pins_seen.add(symbol)
            ordered_pins.append(symbol)

    pool: list[tuple[bool, float, int, str]] = []
    for index, symbol in enumerate(universe):
        if symbol in pins_seen or _tier_of(meta, symbol) == "passive":
            continue
        score = _screen_score(meta, symbol)
        # key: scored-first (False<True), higher score first, then universe order
        pool.append((score is None, -(score or 0.0), index, symbol))
    pool.sort()

    active = list(ordered_pins)
    from_screen: list[dict[str, Any]] = []
    for is_unscored, neg_score, _index, symbol in pool:
        if len(active) >= active_max:
            break
        active.append(symbol)
        from_screen.append(
            {"symbol": symbol, "screen_score": None if is_unscored else round(-neg_score, 4)}
        )

    return {
        "active": active,
        "pins": ordered_pins,
        "from_screen": from_screen,
        "active_max": active_max,
        "universe_size": len(universe),
    }


def load_dynamic_active(config_dir: Path, *, active_max: int) -> dict[str, Any]:
    """Read universe.txt + universe_meta.json + pins and return :func:`select_dynamic_active`.

    Fail-safe: a missing/malformed universe_meta just means no screen scores (everyone sorts as
    unscored, universe order). A missing universe.txt yields pins-only.
    """
    universe_path = config_dir / "universe.txt"
    meta_path = config_dir / "universe_meta.json"
    universe = parse_universe(universe_path) if universe_path.exists() else []
    meta: dict[str, dict] = {}
    if meta_path.exists():
        try:
            raw = read_json(meta_path)
            if isinstance(raw, dict):
                meta = {k: v for k, v in raw.items() if isinstance(v, dict)}
        except Exception:
            meta = {}
    pins = parse_active_watchlist(config_dir)
    return select_dynamic_active(universe=universe, meta=meta, pins=pins, active_max=active_max)
