from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ableton_mcp_server import server


def _extension_project(tmp_path: Path) -> Path:
    (tmp_path / "package.json").write_text(
        '{"name": "stub", "main": "dist/index.js"}', encoding="utf-8"
    )
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.js").write_text("// built\n", encoding="utf-8")
    return tmp_path


def _capture_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> list[list[str]]:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(server.subprocess, "run", fake_run)
    return commands


def _patch_os_name(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setattr(server, "os", SimpleNamespace(name=name))


def test_build_extension_prepends_cmd_exe_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _extension_project(tmp_path)
    commands = _capture_commands(monkeypatch)
    monkeypatch.setattr(server.shutil, "which", lambda _name: "npm")
    _patch_os_name(monkeypatch, "nt")

    server.build_extension(str(project))

    assert commands == [
        ["cmd.exe", "/c", "npm", "install"],
        ["cmd.exe", "/c", "npm", "run", "build"],
    ]


def test_build_extension_does_not_prepend_cmd_exe_off_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _extension_project(tmp_path)
    commands = _capture_commands(monkeypatch)
    monkeypatch.setattr(server.shutil, "which", lambda _name: "npm")
    _patch_os_name(monkeypatch, "posix")

    server.build_extension(str(project))

    assert commands == [["npm", "install"], ["npm", "run", "build"]]


def test_build_extension_uses_resolved_npm_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _extension_project(tmp_path)
    commands = _capture_commands(monkeypatch)
    npm_path = r"C:\Program Files\nodejs\npm.cmd"

    def fake_which(name: str) -> str:
        assert name == "npm"
        return npm_path

    monkeypatch.setattr(server.shutil, "which", fake_which)
    _patch_os_name(monkeypatch, "nt")

    server.build_extension(str(project))

    assert commands[0] == ["cmd.exe", "/c", npm_path, "install"]
    assert commands[1] == ["cmd.exe", "/c", npm_path, "run", "build"]


def test_build_extension_surfaces_nonzero_returncode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _extension_project(tmp_path)
    monkeypatch.setattr(server.shutil, "which", lambda _name: "/usr/bin/npm")
    _patch_os_name(monkeypatch, "posix")

    def failing_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="npm ERR! missing script")

    monkeypatch.setattr(server.subprocess, "run", failing_run)

    import json

    payload = json.loads(server.build_extension(str(project)))
    install_step = payload["steps"][0]
    assert install_step["step"] == "install"
    assert install_step["returncode"] == 1
    assert "missing script" in install_step["stderr"]
    assert payload["status"] == "error"
    assert len(payload["steps"]) == 1
    assert payload["artifacts"] == []


def test_build_extension_propagates_subprocess_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _extension_project(tmp_path)
    monkeypatch.setattr(server.shutil, "which", lambda _name: "/usr/bin/npm")
    _patch_os_name(monkeypatch, "posix")

    def fail_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.SubprocessError("npm crashed")

    monkeypatch.setattr(server.subprocess, "run", fail_run)

    with pytest.raises(subprocess.SubprocessError, match="npm crashed"):
        server.build_extension(str(project))
