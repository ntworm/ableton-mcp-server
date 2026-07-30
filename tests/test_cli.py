from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from ableton_mcp_server.cli import main


@patch("ableton_mcp_server.cli.bridge_status")
@patch("ableton_mcp_server.cli.Client")
def test_doctor_returns_nonzero_only_when_live_bridge_is_unavailable(
    mock_client: MagicMock,
    mock_status: MagicMock,
    capsys: MagicMock,
) -> None:
    mock_status.return_value = {"status": "ok", "bridge_available": True}
    assert main(["doctor", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["bridge_available"] is True

    mock_status.return_value = {
        "status": "error",
        "bridge_available": False,
        "hint": "Use Windows Python",
    }
    assert main(["doctor", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["hint"] == "Use Windows Python"
    assert mock_client.call_count == 2


@patch("ableton_mcp_server.cli.bridge_status")
@patch("ableton_mcp_server.cli.Client")
def test_doctor_passes_catalog_tool_count_to_bridge_status(
    mock_client: MagicMock,
    mock_status: MagicMock,
) -> None:
    from ableton_mcp_server.catalog import TOOL_CATALOG

    mock_status.return_value = {
        "status": "ok",
        "bridge_available": True,
        "tool_count": len(TOOL_CATALOG),
    }

    assert main(["doctor", "--json"]) == 0
    mock_status.assert_called_once()
    assert mock_status.call_args.kwargs.get("tool_count") == len(TOOL_CATALOG)
    assert mock_status.call_args.kwargs.get("tool_count") == 65


def test_cli_installs_and_checks_remote_script(tmp_path: Path, capsys: MagicMock) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "__init__.py").write_text("REMOTE = 1\n", encoding="utf-8")
    (source / "_contracts.py").write_text("PORT = 9888\n", encoding="utf-8")
    (source / "README.md").write_text("remote\n", encoding="utf-8")
    destination = tmp_path / "Remote Scripts"

    assert (
        main(
            [
                "install-script",
                "--source",
                str(source),
                "--destination",
                str(destination),
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "installed"

    assert (
        main(
            [
                "install-status",
                "--source",
                str(source),
                "--destination",
                str(destination),
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "current"


def test_cli_install_status_is_nonzero_for_stale_copy(tmp_path: Path, capsys: MagicMock) -> None:
    source = tmp_path / "source"
    target = tmp_path / "Remote Scripts" / "AbletonMCPServer_RemoteScript"
    source.mkdir(parents=True)
    target.mkdir(parents=True)
    for name in ("__init__.py", "_contracts.py", "README.md"):
        (source / name).write_text("new\n", encoding="utf-8")
        (target / name).write_text("old\n", encoding="utf-8")

    assert (
        main(
            [
                "install-status",
                "--source",
                str(source),
                "--destination",
                str(target.parent),
                "--json",
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["status"] == "stale"


@patch("ableton_mcp_server.cli.run_live_acceptance")
@patch("ableton_mcp_server.cli.Client")
def test_cli_acceptance_requires_explicit_disposable_project_confirmation(
    mock_client: MagicMock,
    mock_acceptance: MagicMock,
    capsys: MagicMock,
) -> None:
    mock_acceptance.return_value = {
        "status": "ok",
        "certification": {"release_ready": True, "tools": []},
    }
    assert (
        main(
            [
                "acceptance",
                "--confirm-project-name",
                "TESTE_CODEX",
                "--track-index",
                "0",
                "--clip-index",
                "3",
                "--fire-clip",
                "--json",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "ok"
    mock_acceptance.assert_called_once()
    kwargs = mock_acceptance.call_args.kwargs
    assert kwargs["confirm_project_name"] == "TESTE_CODEX"
    assert kwargs["track_index"] == 0
    assert kwargs["clip_index"] == 3
    assert kwargs["fire_clip"] is True


@patch("ableton_mcp_server.cli.run_live_acceptance")
@patch("ableton_mcp_server.cli.Client")
def test_cli_parser_accepts_full_acceptance_command(
    mock_client: MagicMock,
    mock_acceptance: MagicMock,
) -> None:
    """The exact command documented in the Slice 1 plan must be accepted."""
    mock_acceptance.return_value = {
        "status": "ok",
        "certification": {"release_ready": True, "tools": []},
    }
    rc = main(
        [
            "acceptance",
            "--confirm-project-name",
            "TESTE_CODEX",
            "--track-index",
            "0",
            "--clip-index",
            "3",
            "--audio-track-index",
            "2",
            "--audio-clip-index",
            "0",
            "--fire-clip",
            "--profile",
            "baseline",
            "--json",
        ]
    )
    assert rc == 0


@patch("ableton_mcp_server.cli.run_live_acceptance")
@patch("ableton_mcp_server.cli.Client")
def test_acceptance_passes_profile_and_audio_indices_to_runner(
    mock_client: MagicMock,
    mock_acceptance: MagicMock,
) -> None:
    mock_acceptance.return_value = {"status": "ok"}
    rc = main(
        [
            "acceptance",
            "--confirm-project-name",
            "TESTE_CODEX",
            "--track-index",
            "0",
            "--clip-index",
            "3",
            "--audio-track-index",
            "2",
            "--audio-clip-index",
            "0",
            "--profile",
            "baseline",
        ]
    )
    assert rc == 0
    mock_acceptance.assert_called_once()
    kwargs = mock_acceptance.call_args.kwargs
    assert kwargs["confirm_project_name"] == "TESTE_CODEX"
    assert kwargs["track_index"] == 0
    assert kwargs["clip_index"] == 3
    assert kwargs["audio_track_index"] == 2
    assert kwargs["audio_clip_index"] == 0
    assert kwargs["profiles"] == ("baseline",)
    assert kwargs["fire_clip"] is False


@patch("ableton_mcp_server.cli.run_live_acceptance")
@patch("ableton_mcp_server.cli.Client")
def test_acceptance_returns_nonzero_when_runner_reports_failure(
    mock_client: MagicMock,
    mock_acceptance: MagicMock,
    capsys: MagicMock,
) -> None:
    """Any ``failed`` row in the certification must produce a non-zero exit."""
    mock_acceptance.return_value = {
        "status": "failed",
        "certification": {"release_ready": False, "failed": ["set_tempo"]},
    }
    rc = main(
        [
            "acceptance",
            "--confirm-project-name",
            "TESTE_CODEX",
            "--track-index",
            "0",
            "--clip-index",
            "3",
            "--profile",
            "baseline",
        ]
    )
    assert rc != 0
    assert "failed" in capsys.readouterr().out.lower()
