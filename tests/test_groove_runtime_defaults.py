"""Regression proofs for the groove seed runtime defaults.

The public distribution no longer embeds the private seed: every default is
resolved at call time and a missing seed is reported as a configuration error.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastmcp import Client

from ableton_mcp_server import server
from ableton_mcp_server.groove_intelligence import GrooveIndexInvalid, seed_paths

SEED_ENV_VAR = "ABLETON_GROOVE_SEED_BUNDLE"
ARTIFACT_ENV_VAR = "ABLETON_GROOVE_ARTIFACT_STORE"
SEED_DIR_NAME = "AbletonMCPServer"
SEED_BUNDLE_NAME = "groove-seed"
ARTIFACT_DIR_NAME = "groove-artifacts-v1"


def _expected_seed(base: Path) -> Path:
    return (base / SEED_DIR_NAME / SEED_BUNDLE_NAME).resolve()


def _isolate_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point Path.home at a temporary directory so no real AppData is used."""
    home = tmp_path / "home"
    home.mkdir()

    def fake_home(cls: type[Path]) -> Path:
        return home

    monkeypatch.setattr(Path, "home", classmethod(fake_home))
    return home


def _isolate_missing_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make Path.home fail, as it does when no home directory is configured."""

    def raising_home(cls: type[Path]) -> Path:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", classmethod(raising_home))


def _isolate_local_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    local = tmp_path / "local-appdata"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    return local


def _result_text(result: object) -> str:
    blocks = getattr(result, "content", None) or []
    return "\n".join(text for text in (getattr(block, "text", "") for block in blocks) if text)


def test_importing_the_server_survives_an_environment_without_a_home() -> None:
    root = Path(__file__).resolve().parents[1]
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "PYTHONPATH": str(root),
    }
    result = subprocess.run(
        [sys.executable, "-c", "import ableton_mcp_server.server as m; print(m.__file__)"],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    loaded = Path(result.stdout.strip().splitlines()[-1])
    assert loaded.is_relative_to(root)


def test_env_override_takes_precedence_over_local_appdata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    override = tmp_path / "override-bundle"
    override.mkdir()
    _isolate_local_appdata(tmp_path, monkeypatch)
    monkeypatch.setenv(SEED_ENV_VAR, str(override))
    assert server.resolve_groove_seed_bundle().resolve() == override.resolve()


def test_default_seed_path_reads_local_appdata_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(SEED_ENV_VAR, raising=False)
    local = _isolate_local_appdata(tmp_path, monkeypatch)
    assert server.resolve_groove_seed_bundle().resolve() == _expected_seed(local)


def test_default_seed_path_falls_back_to_home_without_local_appdata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(SEED_ENV_VAR, raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(seed_paths.sys, "platform", "win32")
    home = _isolate_home(tmp_path, monkeypatch)
    expected = _expected_seed(home / "AppData" / "Local")
    assert server.resolve_groove_seed_bundle().resolve() == expected


def test_default_seed_path_uses_the_macos_application_support_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(SEED_ENV_VAR, raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(seed_paths.sys, "platform", "darwin")
    home = _isolate_home(tmp_path, monkeypatch)
    expected = _expected_seed(home / "Library" / "Application Support")
    assert server.resolve_groove_seed_bundle().resolve() == expected


def test_missing_home_and_local_appdata_report_the_configuration_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SEED_ENV_VAR, raising=False)
    monkeypatch.delenv(ARTIFACT_ENV_VAR, raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    _isolate_missing_home(monkeypatch)
    with pytest.raises(GrooveIndexInvalid, match=SEED_ENV_VAR):
        server.resolve_groove_seed_bundle()
    with pytest.raises(GrooveIndexInvalid, match=ARTIFACT_ENV_VAR):
        seed_paths.groove_artifact_root()


def test_artifact_root_uses_local_appdata_without_a_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ARTIFACT_ENV_VAR, raising=False)
    local = _isolate_local_appdata(tmp_path, monkeypatch)
    _isolate_missing_home(monkeypatch)
    expected = (local / SEED_DIR_NAME / ARTIFACT_DIR_NAME).resolve()
    assert seed_paths.groove_artifact_root() == expected


def test_env_override_resolves_a_missing_bundle_without_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "absent-bundle"
    monkeypatch.setenv(SEED_ENV_VAR, str(missing))
    assert server.resolve_groove_seed_bundle().resolve() == missing.resolve()


def test_get_groove_runtime_without_seed_reports_the_configuration_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(SEED_ENV_VAR, str(tmp_path / "absent-bundle"))
    with pytest.raises(GrooveIndexInvalid, match=SEED_ENV_VAR):
        server.get_groove_runtime()


def test_get_groove_runtime_reports_a_missing_seed_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "bundle-without-manifest"
    bundle.mkdir()
    monkeypatch.setenv(SEED_ENV_VAR, str(bundle))
    with pytest.raises(GrooveIndexInvalid) as error:
        server.get_groove_runtime()
    message = str(error.value)
    assert "No groove corpus configured" in message
    assert str(bundle.resolve()) in message
    assert SEED_ENV_VAR in message


def test_get_groove_runtime_reports_an_invalid_seed_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corrupt = tmp_path / "bundle-with-corrupt-manifest"
    corrupt.mkdir()
    (corrupt / "manifest.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(SEED_ENV_VAR, str(corrupt))
    with pytest.raises(GrooveIndexInvalid) as error:
        server.get_groove_runtime()
    message = str(error.value)
    cause = error.value.__cause__
    assert cause is not None
    assert "Invalid groove seed at " in message
    assert str(corrupt.resolve()) in message
    assert str(cause) in message
    assert SEED_ENV_VAR in message


@pytest.mark.asyncio
async def test_mcp_client_reports_missing_seed_configuration_without_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(SEED_ENV_VAR, raising=False)
    _isolate_local_appdata(tmp_path, monkeypatch)
    _isolate_home(tmp_path, monkeypatch)
    async with Client(server.mcp) as client:
        tools = await client.list_tools()
        result = await client.call_tool(
            "groove_search",
            {"schema_version": "groove.search.request.v1", "query": "drums", "limit": 1},
            raise_on_error=False,
        )
    assert len(tools) == 97
    assert result.is_error is True
    assert SEED_ENV_VAR in _result_text(result)
