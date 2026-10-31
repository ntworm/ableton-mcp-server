"""Regression proofs that the public distribution never ships the private seed.

The proofs stage the distribution sources in a temporary directory, plant a fake
private seed in that staging area only, and build the wheel and the sdist
offline. The archives must contain neither the seed path nor its sentinel.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "ableton_mcp_server"
PRIVATE_SEED_PARTS = ("ableton_mcp_server", "resources", "groove_seed")
SENTINEL_NAME = "PRIVATE-SEED-SENTINEL.txt"
REQUIRED_STAGE_ITEMS = (
    PACKAGE_NAME,
    "pyproject.toml",
    "README.md",
    "contracts.py",
    "AbletonMCPServer_RemoteScript",
    "AbletonMCPServer_Extension/vendor",
)
OPTIONAL_STAGE_ITEMS = ("LICENSE", ".gitignore")
EXCLUDED_DIR_NAMES = frozenset(
    {".git", ".local", ".venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache"}
)


def _is_excluded(parts: tuple[str, ...]) -> bool:
    if any(part in EXCLUDED_DIR_NAMES for part in parts):
        return True
    return parts[: len(PRIVATE_SEED_PARTS)] == PRIVATE_SEED_PARTS


def _stage_directory(stage: Path, name: str) -> None:
    source = REPO_ROOT / name
    for root, dirnames, filenames in os.walk(source):
        current = Path(root)
        relative_dir = Path(name) / current.relative_to(source)
        keep = [item for item in dirnames if not _is_excluded(relative_dir.parts + (item,))]
        dirnames[:] = keep
        for filename in filenames:
            entry = current / filename
            relative = relative_dir / filename
            if _is_excluded(relative.parts):
                continue
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry, target)


def _stage_repository(tmp_path: Path) -> Path:
    stage = tmp_path / "stage"
    stage.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_STAGE_ITEMS:
        source = REPO_ROOT / name
        assert source.exists(), f"missing distribution source: {name}"
        if source.is_dir():
            _stage_directory(stage, name)
        else:
            shutil.copy2(source, stage / name)
    for name in OPTIONAL_STAGE_ITEMS:
        source = REPO_ROOT / name
        if source.exists():
            shutil.copy2(source, stage / name)
    return stage


def _plant_fake_seed(stage: Path) -> Path:
    seed = stage.joinpath(*PRIVATE_SEED_PARTS)
    seed.mkdir(parents=True, exist_ok=True)
    (seed / "index.sqlite").write_bytes(b"fake private seed index")
    (seed / "manifest.json").write_text('{"fake": true}', encoding="utf-8")
    sentinel = seed / SENTINEL_NAME
    sentinel.write_text("private seed sentinel\n", encoding="utf-8")
    return sentinel


def _build_archives(stage: Path, output: Path) -> list[Path]:
    environment = dict(os.environ)
    environment["PIP_NO_INDEX"] = "1"
    environment["HTTP_PROXY"] = "http://127.0.0.1:9"
    environment["HTTPS_PROXY"] = "http://127.0.0.1:9"
    environment["http_proxy"] = "http://127.0.0.1:9"
    environment["https_proxy"] = "http://127.0.0.1:9"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "hatchling",
            "build",
            "-t",
            "wheel",
            "-t",
            "sdist",
            "-d",
            str(output),
        ],
        cwd=stage,
        env=environment,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert completed.returncode == 0, f"{completed.stdout}\n{completed.stderr}"
    return sorted(path for path in output.iterdir() if path.is_file())


def _archive_file_names(archive: Path) -> list[str]:
    if archive.suffix == ".whl":
        with zipfile.ZipFile(archive) as bundle:
            return [name for name in bundle.namelist() if not name.endswith("/")]
    with tarfile.open(archive) as bundle:
        return [member.name for member in bundle.getmembers() if member.isfile()]


def _pick(archives: list[Path], suffix: str) -> Path:
    matches = [path for path in archives if path.name.endswith(suffix)]
    assert matches, f"missing {suffix} archive"
    return matches[0]


def _assert_no_seed_in_archives(archives: list[Path]) -> None:
    for archive in archives:
        names = _archive_file_names(archive)
        leaks = [name for name in names if "groove_seed" in name or SENTINEL_NAME in name]
        assert leaks == [], f"{archive.name} leaks {leaks}"


def test_staging_copies_sources_without_the_private_seed(tmp_path: Path) -> None:
    stage = _stage_repository(tmp_path)
    staged = sorted(path for path in stage.rglob("*") if path.is_file())
    assert staged
    assert all(path.is_relative_to(stage) for path in staged)
    assert all((stage / name).exists() for name in REQUIRED_STAGE_ITEMS)
    package_files = [path for path in staged if path.is_relative_to(stage / PACKAGE_NAME)]
    assert any(path.parent != stage / PACKAGE_NAME for path in package_files)
    assert not stage.joinpath(*PRIVATE_SEED_PARTS).exists()


def test_public_archives_exclude_the_private_seed(tmp_path: Path) -> None:
    if importlib.util.find_spec("hatchling") is None:
        pytest.skip("hatchling is required to build the public archives")
    stage = _stage_repository(tmp_path)
    sentinel = _plant_fake_seed(stage)
    assert sentinel.exists()
    assert not REPO_ROOT.joinpath(*PRIVATE_SEED_PARTS, SENTINEL_NAME).exists()
    archives = _build_archives(stage, tmp_path / "dist")
    assert archives
    _assert_no_seed_in_archives(archives)
    wheel_names = _archive_file_names(_pick(archives, ".whl"))
    sdist_names = _archive_file_names(_pick(archives, ".tar.gz"))
    assert "contracts.py" in wheel_names
    assert any(name.startswith(f"{PACKAGE_NAME}/") for name in wheel_names)
    assert any("AbletonMCPServer_RemoteScript/" in name for name in sdist_names)
