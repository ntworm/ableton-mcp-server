from __future__ import annotations

import json
import re
from pathlib import Path

from ableton_mcp_server import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_aligned_across_package_metadata() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    extension_manifest = json.loads(
        (ROOT / "AbletonMCPServer_Extension" / "package.json").read_text(encoding="utf-8")
    )
    extension_manifest_json = json.loads(
        (ROOT / "AbletonMCPServer_Extension" / "manifest.json").read_text(encoding="utf-8")
    )
    extension_lock = json.loads(
        (ROOT / "AbletonMCPServer_Extension" / "package-lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert __version__ == "0.5.1"
    assert manifest["version"] == "0.5.1"
    assert extension_manifest["version"] == "0.5.1"
    assert extension_manifest_json["version"] == "0.5.1"
    assert extension_lock["version"] == "0.5.1"
    assert 'version = "0.5.1"' in pyproject


def test_runtime_dependencies_cover_imported_analysis_and_fastmcp_websockets() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"websockets>=15.0.1,<17"' in pyproject
    assert '"numpy>=2.2,<3"' in pyproject
    assert '"soundfile>=0.13,<1"' in pyproject


def test_baseline_docs_match_current_state() -> None:
    """Slice 1 Task 10: public docs must reflect the certified 65-tool
    baseline, the primary ``device_name`` contract, read-only warp markers,
    the new error codes, the clean-install command, and certification
    statuses. They must not advertise the stale ``37 registered tools``
    figure."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    tool_reference = (ROOT / "docs" / "TOOL_REFERENCE.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for label, text in (
        ("README", readme),
        ("ARCHITECTURE", architecture),
        ("TOOL_REFERENCE", tool_reference),
        ("CHANGELOG", changelog),
    ):
        # The count must be present; the wording may be "65 tools" or
        # "65 snake_case tools" / "65 cataloged public tools".
        assert re.search(r"\b65\b", text), (
            f"{label} should advertise the 65-tool baseline"
        )
        assert "37 registered tools" not in text, (
            f"{label} still references the stale 37-tool count"
        )

    assert "device_name" in readme, "README must document device_name primary"
    assert (
        "warp_markers" in tool_reference or "warp_markers are read-only" in tool_reference
    ), "TOOL_REFERENCE must mention warp markers are read-only"
    assert (
        "CAPABILITY_UNAVAILABLE" in architecture
        or "CAPABILITY_UNAVAILABLE" in readme
    ), "docs must surface the new CAPABILITY_UNAVAILABLE error code"
    assert (
        "verify_clean_install" in readme or "verify_clean_install" in architecture
    ), "docs must surface the clean-install command"


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
    assert "Version 0.5.1 exposes 65 tools" in readme
    for tool in new_tools:
        assert f"`{tool}`" in readme
        assert f"`{tool}" in reference
    assert "pnomolos/live-wire" in changelog
    assert "hidingwill/AbletonBridge" in changelog


def test_v050_public_docs_cover_lifecycle_fade_tracks_and_analysis() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    reference = (ROOT / "docs" / "TOOL_REFERENCE.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    new_tools = {
        "lifecycle_status",
        "save_set",
        "quit_ableton",
        "live_fade",
        "create_audio_track",
        "analyze_audio",
        "find_frequency_masking",
        "analyze_mix",
        "extract_single_cycle",
    }
    assert "65 tools" in readme
    for tool in new_tools:
        assert f"`{tool}`" in readme
        assert f"`{tool}`" in reference or f"`{tool}(" in reference
        assert f"`{tool}`" in changelog


def test_wheel_configuration_includes_contracts_and_remote_script() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'ableton-mcp = "ableton_mcp_server.cli:main"' in pyproject
    assert '"contracts.py" = "contracts.py"' in pyproject
    assert (
        '"AbletonMCPServer_RemoteScript" = "ableton_mcp_server/_remote_script"'
        in pyproject
    )
    assert (
        '"AbletonMCPServer_Extension/vendor" = "ableton_mcp_server/_extension_vendor"'
        in pyproject
    )


def test_built_wheel_contains_extension_vendor_tarballs(tmp_path: Path) -> None:
    """The built wheel MUST contain both extension vendor tarballs inside
    ableton_mcp_server/_extension_vendor/ directory."""
    import zipfile

    from scripts.build_release_candidates import _build_python_wheel

    wheel_path = _build_python_wheel(ROOT, tmp_path)
    with zipfile.ZipFile(wheel_path, "r") as zf:
        names = zf.namelist()
        sdk_prefix = "ableton_mcp_server/_extension_vendor/ableton-extensions-sdk-"
        cli_prefix = "ableton_mcp_server/_extension_vendor/ableton-extensions-cli-"
        sdk = next((n for n in names if n.startswith(sdk_prefix)), None)
        cli = next((n for n in names if n.startswith(cli_prefix)), None)
        assert sdk is not None, f"SDK tarball missing from wheel entries: {names}"
        assert cli is not None, f"CLI tarball missing from wheel entries: {names}"




def test_windows_bootstrap_uses_a_distinct_native_virtualenv() -> None:
    script = (ROOT / "scripts" / "setup_windows.ps1").read_text(encoding="utf-8")
    assert ".venv-win" in script
    assert "py -3" in script
    assert 'pip install -e "$RepoRoot"' in script
    assert ".venv-win/" in (ROOT / ".gitignore").read_text(encoding="utf-8")
