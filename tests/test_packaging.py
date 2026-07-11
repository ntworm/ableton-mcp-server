from __future__ import annotations

import json
from pathlib import Path

from ableton_mcp_server import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_aligned_across_package_metadata() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    extension_manifest = json.loads(
        (ROOT / "AbletonMCPServer_Extension" / "package.json").read_text(encoding="utf-8")
    )
    assert __version__ == "0.4.0"
    assert manifest["version"] == "0.4.0"
    assert extension_manifest["version"] == "0.4.0"
    assert 'version = "0.4.0"' in pyproject


def test_v040_public_docs_cover_tools_and_attribution() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    reference = (ROOT / "docs" / "TOOL_REFERENCE.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    new_tools = {
        "set_parameter_value",
        "get_clip_info",
        "get_session_overview",
        "search_browser",
        "delete_clip",
        "clear_clip_notes",
        "fire_scene",
        "set_track_property",
        "set_clip_properties",
        "create_clip_automation",
    }
    assert "Version 0.4.0 exposes 56 tools" in readme
    for tool in new_tools:
        assert f"`{tool}`" in readme
        assert f"`{tool}" in reference
    assert "pnomolos/live-wire" in changelog
    assert "hidingwill/AbletonBridge" in changelog


def test_wheel_configuration_includes_contracts_and_remote_script() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'ableton-mcp = "ableton_mcp_server.cli:main"' in pyproject
    assert '"contracts.py" = "contracts.py"' in pyproject
    assert (
        '"AbletonMCPServer_RemoteScript" = "ableton_mcp_server/_remote_script"'
        in pyproject
    )


def test_windows_bootstrap_uses_a_distinct_native_virtualenv() -> None:
    script = (ROOT / "scripts" / "setup_windows.ps1").read_text(encoding="utf-8")
    assert ".venv-win" in script
    assert "py -3" in script
    assert 'pip install -e "$RepoRoot"' in script
    assert ".venv-win/" in (ROOT / ".gitignore").read_text(encoding="utf-8")
