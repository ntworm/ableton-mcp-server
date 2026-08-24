from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.fixtures.groove_bundle import REPO_ROOT, run_pilot_cli


def test_two_pilot_builds_have_equal_manifest_and_logical_digests(tmp_path: Path) -> None:
    first = run_pilot_cli(tmp_path / "one")
    second = run_pilot_cli(tmp_path / "two")
    assert first["bundle_manifest_digest"] == second["bundle_manifest_digest"]
    assert first["logical_index_digest"] == second["logical_index_digest"]
    assert first["artifact_ids"] == second["artifact_ids"]


def test_cli_does_not_accept_unbounded_scan_flag() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_groove_seed.py",
            "--help",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "--input-root" in result.stdout and "--max-files" not in result.stdout


def test_cli_rejects_manifest_over_pilot_bound(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({"files": ["missing.mid"] * 5001}), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_groove_seed.py",
            "--input-root",
            str(root),
            "--manifest",
            str(manifest),
            "--output",
            str(tmp_path / "bundle"),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "pilot limit" in result.stderr
