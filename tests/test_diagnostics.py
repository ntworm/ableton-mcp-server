from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from ableton_mcp_server.diagnostics import (
    RuntimeInfo,
    bridge_status,
    bundled_remote_script_path,
    default_remote_scripts_root,
    detect_runtime,
    find_ableton_log_path,
    install_remote_script,
    remote_script_status,
)


class HealthyClient:
    host = "127.0.0.1"
    port = 9888

    def call(self, command: str, params: dict[str, Any], *, timeout: float) -> Any:
        assert command == "get_session_info"
        assert params == {}
        assert timeout == 2.0
        return {"tempo": 120.0, "is_playing": False}


class BrokenClient(HealthyClient):
    def call(self, command: str, params: dict[str, Any], *, timeout: float) -> Any:
        raise ConnectionError("connection refused")


def test_bridge_status_probes_live_instead_of_tool_discovery() -> None:
    result = bridge_status(
        HealthyClient(),
        runtime=RuntimeInfo(platform="win32", is_wsl=False, python_executable="python.exe"),
        tool_count=56,
    )
    assert result["status"] == "ok"
    assert result["bridge_available"] is True
    assert result["endpoint"] == {"host": "127.0.0.1", "port": 9888}
    assert result["live"] == {"tempo": 120.0, "is_playing": False}
    assert result["runtime"]["is_wsl"] is False
    assert result["server_version"] == "0.5.6"
    assert result["tool_count"] == 88
    assert result["ws_endpoint"] == {"host": "127.0.0.1", "port": 9889}
    assert result["extension_host_available"] is None
    assert result["ws_methods_registered"] == [
        "get_warp_state",
        "load_device_to_track",
        "set_warp_state",
    ]
    assert "device_parameter_write" in result["features"]


def test_bridge_status_explains_wsl_nat_failure_without_relaxing_loopback() -> None:
    result = bridge_status(
        BrokenClient(),
        runtime=RuntimeInfo(platform="linux", is_wsl=True, python_executable="/usr/bin/python3"),
    )
    assert result["status"] == "error"
    assert result["bridge_available"] is False
    assert result["endpoint"] == {"host": "127.0.0.1", "port": 9888}
    assert "Windows Python" in result["hint"]
    assert "0.0.0.0" not in result["hint"]


def test_log_discovery_prefers_explicit_override(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit" / "Log.txt"
    explicit.parent.mkdir()
    explicit.write_text("explicit", encoding="utf-8")
    fallback = tmp_path / "fallback" / "Live 12" / "Preferences" / "Log.txt"
    fallback.parent.mkdir(parents=True)
    fallback.write_text("fallback", encoding="utf-8")

    assert (
        find_ableton_log_path(
            env={"ABLETON_MCP_LOG_PATH": str(explicit)},
            ableton_roots=[tmp_path / "fallback"],
        )
        == explicit
    )


def test_log_discovery_uses_newest_candidate_across_roots(tmp_path: Path) -> None:
    older = tmp_path / "user-a" / "Live 12.1" / "Preferences" / "Log.txt"
    newer = tmp_path / "user-b" / "Live 12.2" / "Preferences" / "Log.txt"
    older.parent.mkdir(parents=True)
    newer.parent.mkdir(parents=True)
    older.write_text("old", encoding="utf-8")
    newer.write_text("new", encoding="utf-8")
    older.touch()
    newer.touch()
    older_mtime = older.stat().st_mtime
    newer_mtime = max(older_mtime + 10, newer.stat().st_mtime + 10)
    import os

    os.utime(newer, (newer_mtime, newer_mtime))

    assert (
        find_ableton_log_path(env={}, ableton_roots=[tmp_path / "user-a", tmp_path / "user-b"])
        == newer
    )


def test_remote_script_install_and_status_are_hash_verified(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "__init__.py").write_text("VERSION = 1\n", encoding="utf-8")
    (source / "_contracts.py").write_text("PORT = 9888\n", encoding="utf-8")
    (source / "README.md").write_text("remote\n", encoding="utf-8")
    destination_root = tmp_path / "Remote Scripts"

    installed = install_remote_script(source, destination_root)
    assert installed["status"] == "installed"
    assert installed["target"] == str(destination_root / "AbletonMCPServer_RemoteScript")
    assert remote_script_status(source, destination_root)["status"] == "current"

    target_init = destination_root / "AbletonMCPServer_RemoteScript" / "__init__.py"
    target_init.write_text("VERSION = 0\n", encoding="utf-8")
    status = remote_script_status(source, destination_root)
    assert status["status"] == "stale"
    assert status["mismatched_files"] == ["__init__.py"]


def test_remote_script_install_dry_run_reports_plan_without_writing(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    for name in ("__init__.py", "_contracts.py", "README.md"):
        (source / name).write_text(name, encoding="utf-8")
    destination_root = tmp_path / "Remote Scripts"

    result = install_remote_script(source, destination_root, dry_run=True)

    assert result["status"] == "dry_run"
    assert result["target"] == str(destination_root / "AbletonMCPServer_RemoteScript")
    assert [entry["filename"] for entry in result["plan"]] == [
        "__init__.py",
        "_contracts.py",
        "README.md",
    ]
    assert not destination_root.exists()


def test_bundled_remote_script_path_supports_checkout_and_wheel_layout(tmp_path: Path) -> None:
    package = tmp_path / "ableton_mcp_server"
    package.mkdir()
    checkout_source = tmp_path / "AbletonMCPServer_RemoteScript"
    checkout_source.mkdir()
    assert bundled_remote_script_path(package) == checkout_source

    checkout_source.rmdir()
    wheel_source = package / "_remote_script"
    wheel_source.mkdir()
    assert bundled_remote_script_path(package) == wheel_source


def test_bundled_remote_script_source_distinguishes_checkout_and_wheel(tmp_path: Path) -> None:
    """Slice 1 Task 8: callers must be able to tell checkout vs wheel apart
    so that diagnostics reports an honest source identity."""
    from ableton_mcp_server.diagnostics import bundled_remote_script_source

    package = tmp_path / "ableton_mcp_server"
    package.mkdir()
    checkout_source = tmp_path / "AbletonMCPServer_RemoteScript"
    checkout_source.mkdir()
    src = bundled_remote_script_source(package)
    assert src.kind == "checkout"
    assert src.path == checkout_source

    checkout_source.rmdir()
    wheel_source = package / "_remote_script"
    wheel_source.mkdir()
    src = bundled_remote_script_source(package)
    assert src.kind == "wheel"
    assert src.path == wheel_source


def test_bridge_status_reports_source_kind_and_python_executable(tmp_path: Path) -> None:
    """Slice 1 Task 8: install/status output must surface source identity
    so an unfamiliar agent can tell checkout vs wheel and the exact
    interpreter in use."""
    import sys

    from ableton_mcp_server.diagnostics import bridge_status, bundled_remote_script_source

    package = tmp_path / "ableton_mcp_server"
    package.mkdir()
    checkout_source = tmp_path / "AbletonMCPServer_RemoteScript"
    checkout_source.mkdir()

    class _Stub:
        host = "127.0.0.1"
        port = 9888

        def call(self, *_args, **_kwargs):
            return {"tempo": 120.0}

    with patch(
        "ableton_mcp_server.diagnostics.bundled_remote_script_source",
        return_value=bundled_remote_script_source(package),
    ):
        status = bridge_status(_Stub(), tool_count=88)

    assert status["source_kind"] == "checkout"
    assert status["source"] == str(checkout_source)
    assert status["python_executable"] == str(Path(sys.executable).resolve())


def test_runtime_and_remote_script_defaults_cover_wsl_windows_and_macos(tmp_path: Path) -> None:
    assert detect_runtime({"WSL_DISTRO_NAME": "Ubuntu"}).is_wsl is True
    explicit = tmp_path / "explicit-scripts"
    assert (
        default_remote_scripts_root(
            {"ABLETON_MCP_REMOTE_SCRIPTS_DIR": str(explicit)}, home=tmp_path
        )
        == explicit
    )
    profile = tmp_path / "WindowsUser"
    assert default_remote_scripts_root({"USERPROFILE": str(profile)}, home=tmp_path) == (
        profile / "Documents" / "Ableton" / "User Library" / "Remote Scripts"
    )
    with patch("ableton_mcp_server.diagnostics.sys.platform", "darwin"):
        assert default_remote_scripts_root({}, home=tmp_path) == (
            tmp_path / "Music" / "Ableton" / "User Library" / "Remote Scripts"
        )


def test_missing_bundled_or_installed_remote_script_files_are_explicit(tmp_path: Path) -> None:
    package = tmp_path / "ableton_mcp_server"
    package.mkdir()
    with pytest.raises(FileNotFoundError, match="could not be found"):
        bundled_remote_script_path(package)

    source = tmp_path / "source"
    source.mkdir()
    for name in ("__init__.py", "_contracts.py", "README.md"):
        (source / name).write_text(name, encoding="utf-8")
    status = remote_script_status(source, tmp_path / "Remote Scripts")
    assert status["status"] == "missing"
    assert status["missing_files"] == ["__init__.py", "_contracts.py", "README.md"]

    (source / "README.md").unlink()
    with pytest.raises(FileNotFoundError, match="Bundled Remote Script file is missing"):
        install_remote_script(source, tmp_path / "Remote Scripts")
