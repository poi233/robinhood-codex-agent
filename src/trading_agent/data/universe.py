from __future__ import annotations

from pathlib import Path


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
