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
