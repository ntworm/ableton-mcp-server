"""``scripts/build_mcpb.py`` must keep the MCP Bundle catalog-driven and honest.

These tests run offline. They prove the manifest stays inside the strict MCPB
0.4 schema, lists exactly the catalog tools, takes every count from the
catalog, declares Windows only, and launches the same entry point as the
``ableton-mcp-server`` console script. The network steps (wheel build,
``uv lock``, ``mcpb validate``/``pack``) and the stdio smoke run only through
the script itself.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pytest

from ableton_mcp_server import __version__
from ableton_mcp_server.catalog import TOOL_CATALOG, Route
from ableton_mcp_server.server import PUBLIC_TOOL_FUNCTIONS
from ableton_mcp_server.tool_counts import build_tool_count_snapshot
from scripts.build_mcpb import (
    DEPENDENCY_CUTOFF,
    LAUNCHER,
    LAUNCHER_SOURCE,
    MANIFEST_VERSION,
    BundleError,
    build_manifest,
    bundle_pyproject,
    manifest_command,
    python_requirement,
    safe_extract,
    stage_bundle,
    tool_entries,
    wheel_filename,
)

ROOT = Path(__file__).resolve().parents[1]

# Keys of the strict MCPB 0.4 schema (@anthropic-ai/mcpb 2.1.2, src/schemas/0.4.ts).
MANIFEST_KEYS = {
    "$schema",
    "dxt_version",
    "manifest_version",
    "name",
    "display_name",
    "version",
    "description",
    "long_description",
    "author",
    "repository",
    "homepage",
    "documentation",
    "support",
    "icon",
    "icons",
    "screenshots",
    "localization",
    "server",
    "tools",
    "tools_generated",
    "prompts",
    "prompts_generated",
    "keywords",
    "license",
    "privacy_policies",
    "compatibility",
    "user_config",
    "_meta",
}


def _manifest() -> dict[str, object]:
    return build_manifest(
        version=__version__,
        requires_python=python_requirement(),
        tools=tool_entries(),
        snapshot=build_tool_count_snapshot(),
    )


def test_manifest_stays_inside_the_strict_mcpb_schema() -> None:
    manifest = _manifest()

    assert set(manifest) <= MANIFEST_KEYS
    assert manifest["manifest_version"] == MANIFEST_VERSION == "0.4"
    assert set(manifest["author"]) <= {"name", "email", "url"}
    assert manifest["author"]["name"]
    assert set(manifest["repository"]) == {"type", "url"}
    server = manifest["server"]
    assert set(server) == {"type", "entry_point", "mcp_config"}
    assert set(server["mcp_config"]) <= {"command", "args", "env", "platform_overrides"}
    assert set(manifest["compatibility"]) <= {"claude_desktop", "platforms", "runtimes"}
    assert set(manifest["compatibility"]["runtimes"]) <= {"python", "node"}
    assert all(set(tool) <= {"name", "description"} for tool in manifest["tools"])
    assert "icon" not in manifest
    json.dumps(manifest)


def test_manifest_lists_exactly_the_catalog_and_derives_every_count() -> None:
    manifest = _manifest()
    snapshot = build_tool_count_snapshot()
    names = [tool["name"] for tool in manifest["tools"]]

    assert names == [spec.name for spec in TOOL_CATALOG]
    assert len(names) == len(TOOL_CATALOG) == snapshot.active_total
    assert manifest["tools_generated"] is False
    assert manifest["version"] == __version__
    assert f"{snapshot.active_total} tools" in manifest["description"]
    assert f"{snapshot.headless_total} of them usable without Live" in manifest["description"]
    long_description = manifest["long_description"]
    assert f"for the {snapshot.live_required_total} tools that may require" in long_description
    assert f"The {snapshot.headless_total} local/headless tools" in long_description
    for spec in TOOL_CATALOG:
        if spec.route is Route.LOCAL:
            assert f"`{spec.name}`" in long_description


def test_manifest_declares_windows_and_the_project_python_requirement() -> None:
    manifest = _manifest()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert manifest["compatibility"]["platforms"] == ["win32"]
    assert manifest["compatibility"]["runtimes"] == {"python": python_requirement()}
    assert f'requires-python = "{python_requirement()}"' in pyproject
    assert "Ableton Live 12" in manifest["long_description"]
    assert manifest["license"] == "MIT"


def test_manifest_launches_the_console_script_entry_point() -> None:
    manifest = _manifest()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    server = manifest["server"]

    assert server["type"] == "uv"
    assert server["entry_point"] == LAUNCHER
    assert server["mcp_config"]["command"] == "uv"
    assert server["mcp_config"]["args"] == [
        "run",
        "--directory",
        "${__dirname}",
        "--frozen",
        LAUNCHER,
    ]
    assert 'ableton-mcp-server = "ableton_mcp_server.server:main"' in pyproject
    assert "from ableton_mcp_server.server import main" in LAUNCHER_SOURCE
    compile(LAUNCHER_SOURCE, LAUNCHER, "exec")


def test_tool_descriptions_are_the_registered_docstring_summaries() -> None:
    summaries = {
        function.__name__: (function.__doc__ or "").strip().splitlines()[0].strip()
        for function in PUBLIC_TOOL_FUNCTIONS
    }
    for tool in tool_entries():
        assert tool["description"] == summaries[tool["name"]]
        assert tool["description"]


def test_manifest_refuses_a_tool_list_that_drifts_from_the_catalog() -> None:
    with pytest.raises(BundleError, match="catalog has"):
        build_manifest(
            version=__version__,
            requires_python=python_requirement(),
            tools=tool_entries()[:-1],
            snapshot=build_tool_count_snapshot(),
        )


def test_bundle_pyproject_pins_the_wheel_platform_and_resolution_cutoff() -> None:
    text = bundle_pyproject(
        version="9.8.7", requires_python=">=3.10", wheel_name=wheel_filename("9.8.7")
    )

    assert 'requires-python = ">=3.10"' in text
    assert 'dependencies = ["ableton-mcp-server==9.8.7"]' in text
    assert "package = false" in text
    assert f'exclude-newer = "{DEPENDENCY_CUTOFF}"' in text
    assert re.search(r"^\s+\"sys_platform == 'win32'\",$", text, re.MULTILINE)
    assert 'path = "wheels/ableton_mcp_server-9.8.7-py3-none-any.whl"' in text


def test_stage_bundle_writes_only_the_bundle_files(tmp_path: Path) -> None:
    wheel = tmp_path / wheel_filename(__version__)
    wheel.write_bytes(b"wheel")
    staging = tmp_path / "bundle"

    manifest = stage_bundle(
        staging,
        wheel=wheel,
        version=__version__,
        requires_python=python_requirement(),
        tools=tool_entries(),
        snapshot=build_tool_count_snapshot(),
    )

    files = sorted(path.relative_to(staging).as_posix() for path in staging.rglob("*"))
    assert files == sorted(
        [
            "LICENSE",
            "manifest.json",
            "pyproject.toml",
            "server",
            LAUNCHER,
            "wheels",
            f"wheels/{wheel.name}",
        ]
    )
    assert json.loads((staging / "manifest.json").read_text(encoding="utf-8")) == manifest
    for name in ("manifest.json", "pyproject.toml", LAUNCHER):
        assert b"\r\n" not in (staging / name).read_bytes()


def test_stage_bundle_rejects_a_foreign_wheel_or_a_dirty_staging(tmp_path: Path) -> None:
    arguments = {
        "version": __version__,
        "requires_python": python_requirement(),
        "tools": tool_entries(),
        "snapshot": build_tool_count_snapshot(),
    }
    foreign = tmp_path / wheel_filename("0.0.1")
    foreign.write_bytes(b"wheel")
    with pytest.raises(BundleError, match="expected wheel"):
        stage_bundle(tmp_path / "a", wheel=foreign, **arguments)

    wheel = tmp_path / wheel_filename(__version__)
    wheel.write_bytes(b"wheel")
    dirty = tmp_path / "b"
    dirty.mkdir()
    (dirty / "left-over").write_text("x", encoding="utf-8")
    with pytest.raises(BundleError, match="not empty"):
        stage_bundle(dirty, wheel=wheel, **arguments)


def test_safe_extract_refuses_paths_outside_the_destination(tmp_path: Path) -> None:
    evil = tmp_path / "evil.mcpb"
    with zipfile.ZipFile(evil, "w") as archive:
        archive.writestr("../escape.txt", "x")
    with pytest.raises(BundleError, match="unsafe path"):
        safe_extract(evil, tmp_path / "out")

    good = tmp_path / "good.mcpb"
    with zipfile.ZipFile(good, "w") as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr("server/main.py", "")
    safe_extract(good, tmp_path / "ok")
    assert (tmp_path / "ok" / "server" / "main.py").is_file()


def test_manifest_command_substitutes_the_install_directory(tmp_path: Path) -> None:
    command, args = manifest_command(_manifest(), tmp_path)

    assert command == "uv"
    assert args == ["run", "--directory", str(tmp_path), "--frozen", LAUNCHER]
