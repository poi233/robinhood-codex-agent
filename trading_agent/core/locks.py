from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path


@contextmanager
def directory_lock(lock_dir: Path):
    lock_dir.mkdir(parents=True, exist_ok=False)
    try:
        yield
    finally:
        lock_dir.rmdir()
