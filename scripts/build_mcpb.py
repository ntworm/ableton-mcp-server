"""Build and smoke-test the MCP Bundle (``.mcpb``) for ableton-mcp-server.

The bundle uses the MCPB ``uv`` server type (manifest version 0.4). It carries
the project wheel built from this checkout, a two-line launcher, and a locked
launcher project. On first launch the host's ``uv`` provisions Python and
installs the locked dependencies from PyPI. The manifest version, the Python
requirement, every tool entry, and every tool count are derived from the
package, ``pyproject.toml``, and ``ableton_mcp_server.catalog.TOOL_CATALOG``.
Nothing here publishes.

    python scripts/build_mcpb.py build --out-dir <directory>
    python scripts/build_mcpb.py smoke <directory>/ableton-mcp-server-<version>.mcpb

``build`` needs network access for the isolated wheel build, ``uv lock``, and
the pinned ``mcpb`` CLI run through ``npx``. ``DEPENDENCY_CUTOFF`` pins the
dependency resolution, so a rebuild resolves the same versions. ``smoke``
extracts the bundle into a temporary directory, launches the manifest command
over stdio, and checks ``initialize``, ``tools/list`` against the catalog, and
one local tool. Neither command needs Ableton Live.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ableton_mcp_server import __version__  # noqa: E402
from ableton_mcp_server.catalog import TOOL_CATALOG, Route  # noqa: E402
from ableton_mcp_server.tool_counts import (  # noqa: E402
    ToolCountSnapshotV1,
    build_tool_count_snapshot,
)

BUNDLE_NAME = "ableton-mcp-server"
MANIFEST_VERSION = "0.4"
MCPB_CLI = "@anthropic-ai/mcpb@2.1.2"
DEPENDENCY_CUTOFF = "2026-10-09T00:00:00Z"
PLATFORMS = ("win32",)
LAUNCHER = "server/main.py"
WHEEL_DIRECTORY = "wheels"
REPOSITORY = "https://github.com/ntworm/ableton-mcp-server"
HOMEPAGE = "https://ntworm.github.io/ableton-mcp-server/"
SMOKE_TOOL = "plan_user_journey"
SMOKE_ARGUMENTS = {"journey_type": "sequence_drums", "traits": "half time, dark"}

LAUNCHER_SOURCE = '''"""MCPB launcher: serve ableton-mcp-server over stdio."""

from ableton_mcp_server.server import main

if __name__ == "__main__":
    main()
'''

_REQUIRES_PYTHON_PATTERN = re.compile(
    r"^requires-python\s*=\s*['\"]([^'\"]+)['\"]\s*$", re.MULTILINE
)


class BundleError(RuntimeError):
    """A build or smoke step failed in a way the caller must see."""


def python_requirement(root: Path = ROOT) -> str:
    """Read ``requires-python`` without requiring Python 3.11 ``tomllib``."""
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = _REQUIRES_PYTHON_PATTERN.search(text)
    if match is None:
        raise BundleError("pyproject.toml does not declare project.requires-python")
    return match.group(1)


def wheel_filename(version: str) -> str:
    return f"ableton_mcp_server-{version}-py3-none-any.whl"


def bundle_filename(version: str) -> str:
    return f"{BUNDLE_NAME}-{version}.mcpb"


def tool_entries() -> list[dict[str, str]]:
    """One manifest entry per catalog tool, described by its docstring summary."""
    from ableton_mcp_server.server import PUBLIC_TOOL_FUNCTIONS

    summaries: dict[str, str] = {}
    for function in PUBLIC_TOOL_FUNCTIONS:
        lines = (function.__doc__ or "").strip().splitlines()
        summaries[function.__name__] = lines[0].strip() if lines else ""
    catalog_names = [spec.name for spec in TOOL_CATALOG]
    if set(summaries) != set(catalog_names):
        raise BundleError(
            "registered tools and TOOL_CATALOG differ: "
            f"{sorted(set(summaries) ^ set(catalog_names))}"
        )
    undocumented = [name for name in catalog_names if not summaries[name]]
    if undocumented:
        raise BundleError(f"tools without a docstring summary: {undocumented}")
    return [{"name": name, "description": summaries[name]} for name in catalog_names]


def build_manifest(
    *,
    version: str,
    requires_python: str,
    tools: Sequence[dict[str, str]],
    snapshot: ToolCountSnapshotV1,
) -> dict[str, Any]:
    """Compose the MCPB manifest; every count comes from ``snapshot``."""
    if len(tools) != snapshot.active_total:
        raise BundleError(
            f"manifest lists {len(tools)} tools but the catalog has {snapshot.active_total}"
        )
    routes = snapshot.route_counts
    local_tools = ", ".join(
        f"`{spec.name}`" for spec in TOOL_CATALOG if spec.route is Route.LOCAL
    )
    long_description = "\n".join(
        (
            f"{snapshot.active_total} MCP tools to inspect, analyze, and safely edit a running "
            "Ableton Live Set. A Python FastMCP server talks to Live only over loopback: "
            "a MIDI Remote Script on TCP `127.0.0.1:9888` and an Ableton Extension on "
            "WebSocket `127.0.0.1:9889`.",
            "",
            "Requirements:",
            "",
            "- Windows. The bundle declares `win32` only.",
            f"- Ableton Live 12 with the `AbletonMCPServer` Remote Script selected as a "
            f"Control Surface for the {snapshot.live_required_total} tools that may require "
            f"Live ({routes.get('tcp', 0)} TCP, {routes.get('websocket', 0)} WebSocket, "
            f"{routes.get('composed', 0)} composed). The {routes.get('websocket', 0)} "
            "WebSocket tools also need the AbletonMCPServer Extension.",
            f"- The {snapshot.headless_total} local/headless tools run without Live: "
            f"{local_tools}.",
            f"- `uv` provisions Python {requires_python} and the locked dependencies on "
            "first launch, which downloads packages from PyPI.",
            "",
            "This bundle contains the server only. Install the Remote Script and the "
            f"Extension as described in {REPOSITORY}#readme.",
        )
    )
    return {
        "manifest_version": MANIFEST_VERSION,
        "name": BUNDLE_NAME,
        "display_name": "Ableton MCP Server",
        "version": version,
        "description": (
            f"Inspect, analyze, and safely edit a running Ableton Live Set on Windows: "
            f"{snapshot.active_total} tools, {snapshot.headless_total} of them usable "
            "without Live."
        ),
        "long_description": long_description,
        "author": {"name": "ntworm", "url": "https://github.com/ntworm"},
        "repository": {"type": "git", "url": f"{REPOSITORY}.git"},
        "homepage": HOMEPAGE,
        "documentation": f"{REPOSITORY}/blob/main/docs/TOOL_REFERENCE.md",
        "support": f"{REPOSITORY}/issues",
        "server": {
            "type": "uv",
            "entry_point": LAUNCHER,
            "mcp_config": {
                "command": "uv",
                "args": ["run", "--directory", "${__dirname}", "--frozen", LAUNCHER],
            },
        },
        "tools": [dict(tool) for tool in tools],
        "tools_generated": False,
        "keywords": ["ableton", "ableton-live", "daw", "music", "midi", "audio", "mcp"],
        "license": "MIT",
        "compatibility": {
            "platforms": list(PLATFORMS),
            "runtimes": {"python": requires_python},
        },
    }


def bundle_pyproject(*, version: str, requires_python: str, wheel_name: str) -> str:
    """The launcher project ``uv`` locks and runs inside the bundle."""
    return (
        "[project]\n"
        'name = "ableton-mcp-server-mcpb"\n'
        f'version = "{version}"\n'
        'description = "Launcher for the ableton-mcp-server MCP Bundle"\n'
        f'requires-python = "{requires_python}"\n'
        f'dependencies = ["ableton-mcp-server=={version}"]\n'
        "\n"
        "[tool.uv]\n"
        "package = false\n"
        f'exclude-newer = "{DEPENDENCY_CUTOFF}"\n'
        "environments = [\n"
        + "".join(f"    \"sys_platform == '{platform}'\",\n" for platform in PLATFORMS)
        + "]\n"
        "\n"
        "[tool.uv.sources]\n"
        f'ableton-mcp-server = {{ path = "{WHEEL_DIRECTORY}/{wheel_name}" }}\n'
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def stage_bundle(
    staging: Path,
    *,
    wheel: Path,
    version: str,
    requires_python: str,
    tools: Sequence[dict[str, str]],
    snapshot: ToolCountSnapshotV1,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Write every bundle file except ``uv.lock`` into an empty ``staging``."""
    expected_wheel = wheel_filename(version)
    if wheel.name != expected_wheel:
        raise BundleError(f"expected wheel {expected_wheel}, got {wheel.name}")
    if staging.exists() and any(staging.iterdir()):
        raise BundleError(f"staging directory is not empty: {staging}")
    manifest = build_manifest(
        version=version, requires_python=requires_python, tools=tools, snapshot=snapshot
    )
    _write_text(staging / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    _write_text(
        staging / "pyproject.toml",
        bundle_pyproject(
            version=version, requires_python=requires_python, wheel_name=wheel.name
        ),
    )
    _write_text(staging / LAUNCHER, LAUNCHER_SOURCE)
    (staging / WHEEL_DIRECTORY).mkdir(parents=True, exist_ok=True)
    shutil.copy2(wheel, staging / WHEEL_DIRECTORY / wheel.name)
    shutil.copy2(root / "LICENSE", staging / "LICENSE")
    return manifest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_executable(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise BundleError(f"{name} was not found on PATH")
    return found


def _run(command: Sequence[str], *, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        raise BundleError(f"{' '.join(command)} failed ({proc.returncode}):\n{output}")
    return output


def _build_wheel(output_directory: Path) -> Path:
    try:
        import build  # noqa: F401
    except ImportError as exc:
        raise BundleError(
            "the 'build' package is required: python -m pip install build"
        ) from exc
    _run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(output_directory), "."],
        cwd=ROOT,
    )
    wheel = output_directory / wheel_filename(__version__)
    if not wheel.is_file():
        raise BundleError(f"the wheel build did not produce {wheel.name}")
    return wheel


def _git(*args: str) -> str:
    return _run(["git", "-C", str(ROOT), *args])


def build(out_dir: Path, *, wheel: Path | None = None) -> dict[str, Any]:
    """Stage, lock, validate, and pack the bundle into ``out_dir``."""
    uv = _require_executable("uv")
    npx = _require_executable("npx")
    requires_python = python_requirement()
    snapshot = build_tool_count_snapshot()
    tools = tool_entries()
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = out_dir / bundle_filename(__version__)
    with tempfile.TemporaryDirectory(prefix="mcpb-build-") as scratch:
        scratch_path = Path(scratch)
        if wheel is None:
            wheel = _build_wheel(scratch_path / "dist")
        staging = scratch_path / "bundle"
        stage_bundle(
            staging,
            wheel=wheel,
            version=__version__,
            requires_python=requires_python,
            tools=tools,
            snapshot=snapshot,
        )
        lock_output = _run([uv, "lock", "--directory", str(staging)])
        validate_output = _run([npx, "--yes", MCPB_CLI, "validate", str(staging)])
        pack_output = _run([npx, "--yes", MCPB_CLI, "pack", str(staging), str(bundle)])
        wheel_sha256 = sha256_file(staging / WHEEL_DIRECTORY / wheel.name)
    bundle_sha256 = sha256_file(bundle)
    checksum = out_dir / f"{bundle.name}.sha256"
    _write_text(checksum, f"{bundle_sha256}  {bundle.name}\n")
    info = {
        "bundle": bundle.name,
        "sha256": bundle_sha256,
        "size_bytes": bundle.stat().st_size,
        "version": __version__,
        "source_commit": _git("rev-parse", "HEAD"),
        "source_dirty": bool(_git("status", "--porcelain")),
        "wheel": wheel.name,
        "wheel_sha256": wheel_sha256,
        "manifest_version": MANIFEST_VERSION,
        "server_type": "uv",
        "platforms": list(PLATFORMS),
        "requires_python": requires_python,
        "dependency_cutoff": DEPENDENCY_CUTOFF,
        "mcpb_cli": MCPB_CLI,
        "uv": _run([uv, "--version"]),
        "tool_count": snapshot.active_total,
        "headless_tools": snapshot.headless_total,
        "live_required_tools": snapshot.live_required_total,
        "lock": lock_output.splitlines(),
        "validate": validate_output.splitlines(),
    }
    _write_text(out_dir / f"{bundle.name}.build-info.json", json.dumps(info, indent=2) + "\n")
    info["pack"] = pack_output.splitlines()
    return info


def safe_extract(bundle: Path, destination: Path) -> None:
    """Extract ``bundle`` refusing absolute paths and parent traversal."""
    with zipfile.ZipFile(bundle) as archive:
        for member in archive.infolist():
            name = PurePosixPath(member.filename.replace("\\", "/"))
            if name.is_absolute() or ".." in name.parts or ":" in member.filename:
                raise BundleError(f"unsafe path in bundle: {member.filename}")
        archive.extractall(destination)


def manifest_command(manifest: dict[str, Any], dirname: Path) -> tuple[str, list[str]]:
    """Resolve ``server.mcp_config`` the way a host substitutes ``${__dirname}``."""
    config = manifest["server"]["mcp_config"]
    replace = str(dirname)
    command = str(config["command"]).replace("${__dirname}", replace)
    args = [str(arg).replace("${__dirname}", replace) for arg in config.get("args", [])]
    return command, args


async def _exercise_server(command: str, args: list[str], timeout: float) -> dict[str, Any]:
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=command, args=args)
    with anyio.fail_after(timeout):
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write, read_timeout_seconds=timedelta(seconds=timeout)) as session,
        ):
            initialized = await session.initialize()
            names: list[str] = []
            cursor: str | None = None
            while True:
                page = await session.list_tools(cursor=cursor)
                names.extend(tool.name for tool in page.tools)
                cursor = page.nextCursor
                if not cursor:
                    break
            called = await session.call_tool(SMOKE_TOOL, dict(SMOKE_ARGUMENTS))
    return {
        "protocol_version": initialized.protocolVersion,
        "server_info": initialized.serverInfo.model_dump(mode="json", exclude_none=True),
        "tool_names": names,
        "call_is_error": called.isError,
        "call_structured": called.structuredContent,
    }


def smoke(bundle: Path, *, timeout: float = 900.0, work_dir: Path | None = None) -> dict[str, Any]:
    """Run the extracted bundle over stdio and compare it with the catalog."""
    import anyio

    with tempfile.TemporaryDirectory(prefix="mcpb-smoke-", ignore_cleanup_errors=True) as tmp:
        target = work_dir if work_dir is not None else Path(tmp) / "bundle"
        target.mkdir(parents=True, exist_ok=True)
        if any(target.iterdir()):
            raise BundleError(f"smoke directory is not empty: {target}")
        safe_extract(bundle, target)
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        command, args = manifest_command(manifest, target)
        executable = _require_executable(command)
        observed = anyio.run(_exercise_server, executable, args, timeout)

    catalog_names = [spec.name for spec in TOOL_CATALOG]
    listed = observed["tool_names"]
    manifest_names = [tool["name"] for tool in manifest.get("tools", [])]
    structured = observed["call_structured"] or {}
    stages = [stage.get("stage") for stage in structured.get("stages", [])]
    checks = {
        "tools_list_matches_catalog": sorted(listed) == sorted(catalog_names),
        "manifest_tools_match_catalog": manifest_names == catalog_names,
        "tool_call_succeeded": observed["call_is_error"] is False and len(stages) == 4,
    }
    return {
        "status": "ok" if all(checks.values()) else "failed",
        "bundle": str(bundle),
        "sha256": sha256_file(bundle),
        "command": [command, *args],
        "initialize": {
            "protocol_version": observed["protocol_version"],
            "server_info": observed["server_info"],
        },
        "tools_list": {
            "count": len(listed),
            "catalog_count": len(catalog_names),
            "manifest_count": len(manifest_names),
            "missing": sorted(set(catalog_names) - set(listed)),
            "unexpected": sorted(set(listed) - set(catalog_names)),
        },
        "tool_call": {
            "name": SMOKE_TOOL,
            "arguments": SMOKE_ARGUMENTS,
            "is_error": observed["call_is_error"],
            "journey": structured.get("journey"),
            "stages": stages,
        },
        "checks": checks,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build", help="stage, lock, validate, and pack")
    build_parser.add_argument(
        "--out-dir", type=Path, default=ROOT / "dist" / "mcpb", help="output directory"
    )
    build_parser.add_argument(
        "--wheel", type=Path, default=None, help="use this wheel instead of building one"
    )
    smoke_parser = commands.add_parser("smoke", help="run an extracted bundle over stdio")
    smoke_parser.add_argument("bundle", type=Path)
    smoke_parser.add_argument("--timeout", type=float, default=900.0)
    smoke_parser.add_argument(
        "--work-dir", type=Path, default=None, help="extract here instead of a temp directory"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    try:
        if args.command == "build":
            wheel = args.wheel.resolve() if args.wheel is not None else None
            result = build(args.out_dir.resolve(), wheel=wheel)
        else:
            work_dir = args.work_dir.resolve() if args.work_dir is not None else None
            result = smoke(args.bundle.resolve(), timeout=args.timeout, work_dir=work_dir)
    except BundleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result.get("status", "ok") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
