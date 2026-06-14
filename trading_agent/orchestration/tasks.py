from __future__ import annotations

import subprocess
from pathlib import Path


def run_script(script_path: Path) -> int:
    return subprocess.run(["bash", str(script_path)], check=False).returncode
