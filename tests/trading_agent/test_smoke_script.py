from __future__ import annotations

import os
import subprocess
from pathlib import Path

_SMOKE = Path(__file__).resolve().parents[2] / "src" / "scripts" / "smoke" / "run_smoke.sh"


def test_smoke_script_exists_and_executable():
    assert _SMOKE.exists(), f"missing {_SMOKE}"
    assert os.access(_SMOKE, os.X_OK), "smoke script must be executable"


def test_smoke_script_has_valid_bash_syntax():
    result = subprocess.run(["bash", "-n", str(_SMOKE)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
