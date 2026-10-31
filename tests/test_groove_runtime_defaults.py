"""Regression proofs for the groove seed runtime defaults.

The public distribution no longer embeds the private seed: every default is
resolved at call time and a missing seed is reported as a configuration error.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client

from ableton_mcp_server import server
from ableton_mcp_server.groove_intelligence import GrooveIndexInvalid

SEED_ENV_VAR = "ABLETON_GROOVE_SEED_BUNDLE"
SEED_DIR_NAME = "AbletonMCPServer"
SEED_BUNDLE_NAME = "groove-seed"


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


def _isolate_local_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    local = tmp_path / "local-appdata"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    return local


def _result_text(result: object) -> str:
    blocks = getattr(result, "content", None) or []
    return "\n".join(text for text in (getattr(block, "text", "") for block in blocks) if text)


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
    home = _isolate_home(tmp_path, monkeypatch)
    expected = _expected_seed(home / "AppData" / "Local")
    assert server.resolve_groove_seed_bundle().resolve() == expected


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
