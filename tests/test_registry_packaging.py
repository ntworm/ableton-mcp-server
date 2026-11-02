"""Tests for MCP Registry metadata and Smithery bundle packaging helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from ableton_mcp_server import __version__
from ableton_mcp_server.catalog import TOOL_CATALOG
from scripts.build_mcpb import BUNDLE_NAME, BundleError, bundle_filename
from scripts.build_smithery_bundle import (
    BOOTSTRAP,
    adapt_manifest,
    check_observed,
    check_out_dir,
    no_seed_env,
    parse_wheel_version,
    smithery_bundle_filename,
    swap_source,
    wheel_url,
)

ROOT = Path(__file__).resolve().parents[1]


def _server_json() -> dict[str, Any]:
    """The registry metadata published in the repository root."""
    path = ROOT / "server.json"
    assert path.is_file(), "server.json must exist in the repository root"
    return json.loads(path.read_text(encoding="utf-8"))


def test_server_json_declares_the_registry_metadata() -> None:
    data = _server_json()
    assert data.get("$schema") == (
        "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
    )
    assert data.get("name") == f"io.github.ntworm/{BUNDLE_NAME}"
    assert data.get("title") == "Ableton MCP Server"
    assert data.get("websiteUrl") == "https://ntworm.github.io/ableton-mcp-server/"
    assert data.get("repository") == {
        "url": "https://github.com/ntworm/ableton-mcp-server",
        "source": "github",
    }

    # Description cites real TOOL_CATALOG count
    catalog_count = len(TOOL_CATALOG)
    description = data.get("description", "")
    assert f"{catalog_count} tools" in description


def test_server_json_declares_the_registry_version() -> None:
    data = _server_json()

    # Version starts with package version
    server_version = data.get("version", "")
    assert server_version.startswith(__version__)


def test_server_json_declares_a_single_mcpb_package() -> None:
    data = _server_json()
    server_version = data.get("version", "")

    # Single package validation
    packages = data.get("packages")
    assert isinstance(packages, list) and len(packages) == 1
    package = packages[0]
    assert package.get("registryType") == "mcpb"
    assert package.get("version") == server_version

    identifier = package.get("identifier", "")
    assert f"/v{server_version}/" in identifier
    assert f"ableton-mcp-server-{__version__}.mcpb" in identifier

    file_sha256 = package.get("fileSha256", "")
    assert re.fullmatch(r"^[0-9a-f]{64}$", file_sha256) is not None

    assert package.get("transport") == {"type": "stdio"}


def test_wheel_url_and_version_derivation() -> None:
    tag = "v0.8.1-rc1"
    wheel_name = f"ableton_mcp_server-{__version__}-py3-none-any.whl"
    url = wheel_url(tag, wheel_name)
    assert url == (
        f"https://github.com/ntworm/ableton-mcp-server/releases/download/{tag}/{wheel_name}"
    )

    version = parse_wheel_version(wheel_name)
    assert version == __version__

    with pytest.raises(BundleError, match="invalid wheel filename"):
        parse_wheel_version("not_a_valid_wheel.whl")


def test_swap_source() -> None:
    wheel_name = "ableton_mcp_server-0.8.1-py3-none-any.whl"
    url = "https://example.com/wheel.whl"
    original_toml = (
        "[tool.uv.sources]\n"
        f'ableton-mcp-server = {{ path = "wheels/{wheel_name}" }}\n'
    )
    swapped = swap_source(original_toml, wheel_name, url)
    assert f'url = "{url}"' in swapped
    assert "wheels/" not in swapped

    with pytest.raises(BundleError, match="target .* not found"):
        swap_source("[tool.uv]\npackage = false\n", wheel_name, url)


def _dummy_manifest() -> dict[str, Any]:
    """A manifest that declares two tools and the uv provisioning line."""
    catalog_count = len(TOOL_CATALOG)
    return {
        "manifest_version": "0.4",
        "name": BUNDLE_NAME,
        "description": f"Ableton MCP Server: {catalog_count} tools",
        "long_description": (
            f"{catalog_count} MCP tools for Ableton Live.\n"
            "- `uv` provisions Python >=3.10 and the locked dependencies on first launch, "
            "which downloads packages from PyPI.\n"
        ),
        "server": {
            "type": "uv",
            "entry_point": "server/main.py",
            "mcp_config": {"command": "uv", "args": ["run"]},
        },
        "tools": [
            {"name": "tool_a", "description": "desc a"},
            {"name": "tool_b", "description": "desc b"},
        ],
        "tools_generated": False,
    }


def test_adapt_manifest_switches_to_the_python_bootstrap_server() -> None:
    dummy_manifest = _dummy_manifest()
    adapted = adapt_manifest(dummy_manifest)
    assert adapted["server"] == {
        "type": "python",
        "entry_point": "server/bootstrap.py",
        "mcp_config": {
            "command": "python",
            "args": ["${__dirname}/server/bootstrap.py"],
        },
    }
    assert adapted["tools"] == []
    assert adapted["tools_generated"] is True


def test_adapt_manifest_rewrites_the_long_description() -> None:
    catalog_count = len(TOOL_CATALOG)
    adapted = adapt_manifest(_dummy_manifest())

    long_desc = adapted["long_description"]
    assert "- `uv` provisions Python" not in long_desc
    assert "- Python >=3.10 must be available on Windows." in long_desc
    assert "Clients discover all 2 tools at runtime on connection." in long_desc
    assert f"Clients discover all {catalog_count} tools" not in long_desc
    assert "0.7.0" not in long_desc
    assert ".local" not in long_desc
    assert "seed completo" not in long_desc
    assert "complete groove seed" not in long_desc


def test_adapt_manifest_refuses_a_manifest_it_cannot_adapt() -> None:
    dummy_manifest = _dummy_manifest()

    # Missing uv provisions line raises BundleError
    invalid_manifest = dict(dummy_manifest, long_description="No uv line here.")
    with pytest.raises(BundleError, match="does not contain '- `uv` provisions Python'"):
        adapt_manifest(invalid_manifest)

    # A manifest without tools raises BundleError instead of falling back
    empty_manifest = dict(dummy_manifest, tools=[])
    with pytest.raises(BundleError, match="does not declare any tools"):
        adapt_manifest(empty_manifest)


def test_smithery_bundle_filename_is_not_the_official_bundle() -> None:
    name = smithery_bundle_filename("0.8.1")
    assert name == "ableton-mcp-server-0.8.1-smithery.mcpb"
    assert name != bundle_filename("0.8.1")
    assert bundle_filename("0.8.1") == "ableton-mcp-server-0.8.1.mcpb"


def test_check_out_dir_refuses_existing_directory(tmp_path: Path) -> None:
    with pytest.raises(BundleError, match="output directory already exists"):
        check_out_dir(tmp_path)

    non_existing = tmp_path / "fresh_output_dir"
    check_out_dir(non_existing)


def _clean_observed() -> dict[str, Any]:
    """One observed stdio run that satisfies every bundle contract."""
    return {
        "tool_names": [spec.name for spec in TOOL_CATALOG],
        "plan_is_error": False,
        "groove_is_error": True,
        "groove_text": "ABLETON_GROOVE_SEED_BUNDLE is not available in this bundle",
        "protocol_version": "2025-06-18",
        "server_info": {"name": BUNDLE_NAME},
    }


def test_check_observed_accepts_a_clean_run() -> None:
    check_observed(_clean_observed())


def test_check_observed_rejects_a_short_tool_list() -> None:
    observed = _clean_observed()
    observed["tool_names"] = [spec.name for spec in TOOL_CATALOG][:-1]
    with pytest.raises(BundleError, match="tool list differs from TOOL_CATALOG"):
        check_observed(observed)


def test_check_observed_rejects_a_failing_plan_call() -> None:
    observed = _clean_observed()
    observed["plan_is_error"] = True
    with pytest.raises(BundleError, match="plan_user_journey returned an error"):
        check_observed(observed)


def test_check_observed_rejects_a_succeeding_groove_call() -> None:
    observed = _clean_observed()
    observed["groove_is_error"] = False
    with pytest.raises(BundleError, match="groove_search expected isError=True"):
        check_observed(observed)


def test_check_observed_rejects_a_groove_error_without_the_seed_marker() -> None:
    observed = _clean_observed()
    observed["groove_text"] = "the groove index is unavailable"
    with pytest.raises(BundleError, match="ABLETON_GROOVE_SEED_BUNDLE"):
        check_observed(observed)


def test_no_seed_env_points_the_server_at_a_missing_seed_bundle(tmp_path: Path) -> None:
    """The verify run must not reach a private corpus on the default path."""
    seed_bundle = tmp_path / "no-seed"
    assert not seed_bundle.exists()
    assert no_seed_env(seed_bundle) == {
        "ABLETON_GROOVE_SEED_BUNDLE": str(seed_bundle)
    }


def test_bootstrap_installs_the_pinned_closure_without_resolving_dependencies() -> None:
    """The bundle bootstrap must not let pip resolve transitive dependencies."""
    assert '"--no-deps"' in BOOTSTRAP
    assert '"--require-hashes"' in BOOTSTRAP
    assert BOOTSTRAP.index('"install"') < BOOTSTRAP.index('"--no-deps"')
