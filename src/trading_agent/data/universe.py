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


def parse_active_watchlist(config_dir: Path) -> list[str]:
    """Return active_watchlist symbols, falling back to full universe if file is absent."""
    active_path = config_dir / "active_watchlist.txt"
    if active_path.exists():
        return parse_universe(active_path)
    return parse_universe(config_dir / "universe.txt")
