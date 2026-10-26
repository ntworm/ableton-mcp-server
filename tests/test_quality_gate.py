from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repository_passes_its_structure_gate() -> None:
    """No function or file grows past the limits or above quality-baseline.json."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "quality_gate.py"), "--root", str(ROOT)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
