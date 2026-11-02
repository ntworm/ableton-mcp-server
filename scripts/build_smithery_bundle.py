"""Build and verify the Python-bootstrap MCP Bundle for the registry.

The registry bundle is derived from the official ``.mcpb``: the locked launcher
project is swapped for a pinned release wheel and the result is packed as
``ableton-mcp-server-<version>-smithery.mcpb`` so it is never confused with
the official bundle. ``verify`` launches the extracted bundle over stdio twice
and checks the tool catalog, the two tool calls, and the installed wheel files.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import zipfile
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ableton_mcp_server.catalog import TOOL_CATALOG  # noqa: E402
from scripts.build_mcpb import (  # noqa: E402
    LAUNCHER,
    MCPB_CLI,
    REPOSITORY,
    BundleError,
    _require_executable,
    _run,
    _write_text,
    bundle_filename,
    manifest_command,
    safe_extract,
    sha256_file,
)

MAX_BUNDLE_BYTES = 25 * 1024 * 1024

# requirements.txt already carries the complete hash-pinned closure. Without
# --no-deps, pip 23 on Python 3.10 resolves the pydantic[email] extra to the
# newest release and then refuses the --require-hashes mode.
BOOTSTRAP = '''"""Install the pinned public wheel in a bundle-local environment, then serve MCP."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    if sys.platform != "win32" or sys.version_info < (3, 10):
        raise SystemExit("Ableton MCP Server requires Windows and Python >=3.10")
    root = Path(__file__).resolve().parents[1]
    environment = root / ".venv"
    if not environment.resolve().is_relative_to(root):
        raise SystemExit("Bundle environment must remain inside the bundle directory")
    runtime = environment / "Scripts" / "python.exe"
    requirements = root / "requirements.txt"
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = environment / ".requirements-sha256"
    ready = runtime.is_file() and marker.is_file() and marker.read_text().strip() == digest
    if not ready:
        if not runtime.is_file():
            subprocess.run([sys.executable, "-m", "venv", str(environment)],
                           check=True, stdout=sys.stderr, stderr=sys.stderr)
        subprocess.run([str(runtime), "-m", "pip", "--isolated", "--disable-pip-version-check",
                        "install", "--no-deps", "--require-hashes", "--only-binary=:all:",
                        "--no-input", "-r", str(requirements)],
                       check=True, stdout=sys.stderr, stderr=sys.stderr)
        marker.write_text(digest + "\\n", encoding="utf-8")
    os.execv(str(runtime), [str(runtime), str(root / "server" / "main.py")])


if __name__ == "__main__":
    main()
'''

PYTHON_BOOTSTRAP_NOTE = (
    "- Python >=3.10 must be available on Windows. On first launch the Python bootstrap "
    "creates a bundle-local virtual environment and downloads the SHA-pinned "
    "server wheel from GitHub and locked dependencies from PyPI. Internet access is "
    "required for this first launch."
)

_WHEEL_PATTERN = re.compile(
    r"^ableton_mcp_server-([0-9a-zA-Z.]+)-py3-none-any\.whl$"
)


def parse_wheel_version(wheel_name: str) -> str:
    """Derive version string from wheel filename."""
    match = _WHEEL_PATTERN.match(wheel_name)
    if match is None:
        raise BundleError(f"invalid wheel filename: {wheel_name}")
    return match.group(1)


def wheel_url(tag: str, wheel_name: str) -> str:
    """Compose public GitHub release wheel download URL."""
    return f"{REPOSITORY}/releases/download/{tag}/{wheel_name}"


def smithery_bundle_filename(version: str) -> str:
    """Name the registry bundle so it is never confused with the official MCPB."""
    stem = bundle_filename(version).removesuffix(".mcpb")
    return f"{stem}-smithery.mcpb"


def check_out_dir(out_dir: Path) -> None:
    """Refuse existing output directory."""
    if out_dir.exists():
        raise BundleError(f"output directory already exists: {out_dir}")


def swap_source(pyproject_text: str, wheel_name: str, url: str) -> str:
    """Swap wheel file path source for pinned release URL source in pyproject.toml."""
    target = f'path = "wheels/{wheel_name}"'
    if target not in pyproject_text:
        raise BundleError(f"target {target} not found in pyproject.toml")
    return pyproject_text.replace(target, f'url = "{url}"')


def _replace_uv_line(text: str) -> str:
    lines = text.splitlines()
    replaced = False
    new_lines: list[str] = []
    for line in lines:
        if line.startswith("- `uv` provisions Python"):
            new_lines.append(PYTHON_BOOTSTRAP_NOTE)
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        raise BundleError("manifest does not contain '- `uv` provisions Python' line")
    return "\n".join(new_lines)


def adapt_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Adapt MCPB manifest for Python bootstrap and runtime discovery."""
    adapted = json.loads(json.dumps(manifest))
    declared_tools = adapted.get("tools", [])
    if not declared_tools:
        raise BundleError("manifest does not declare any tools")
    count = len(declared_tools)
    adapted["server"] = {
        "type": "python",
        "entry_point": "server/bootstrap.py",
        "mcp_config": {
            "command": "python",
            "args": ["${__dirname}/server/bootstrap.py"],
        },
    }
    adapted["tools"] = []
    adapted["tools_generated"] = True
    long_desc = adapted.get("long_description", "")
    long_desc = _replace_uv_line(long_desc)
    suffix = f"\n\nClients discover all {count} tools at runtime on connection."
    if suffix.strip() not in long_desc:
        long_desc += suffix
    adapted["long_description"] = long_desc
    return adapted


def _extract_bundle_files(mcpb: Path, staging: Path) -> bytes:
    with tempfile.TemporaryDirectory(prefix="smithery-extract-") as tmp:
        tmp_path = Path(tmp)
        safe_extract(mcpb, tmp_path)
        required = ("LICENSE", LAUNCHER, "uv.lock", "pyproject.toml", "manifest.json")
        for rel in required:
            src = tmp_path / rel
            if not src.is_file():
                raise BundleError(f"mcpb is missing {rel}")
            dst = staging / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return (tmp_path / "uv.lock").read_bytes()


def _check_lock(original_lock_bytes: bytes, new_lock_path: Path, url: str, wheel_sha: str) -> None:
    try:
        import tomllib
    except ModuleNotFoundError as exc:
        raise BundleError("build needs Python 3.11 or newer") from exc

    original_lock = tomllib.loads(original_lock_bytes.decode("utf-8"))
    new_lock = tomllib.loads(new_lock_path.read_text(encoding="utf-8"))
    old_pkgs = sorted((p["name"], p["version"]) for p in original_lock.get("package", []))
    new_pkgs = sorted((p["name"], p["version"]) for p in new_lock.get("package", []))
    if old_pkgs != new_pkgs:
        raise BundleError("package versions in uv.lock drifted after relocking")
    server_pkg = next(
        (p for p in new_lock.get("package", []) if p.get("name") == "ableton-mcp-server"),
        None,
    )
    if server_pkg is None:
        raise BundleError("ableton-mcp-server not found in locked packages")
    if server_pkg.get("source") != {"url": url}:
        raise BundleError(f"locked source does not match expected url {url}")
    wheels = server_pkg.get("wheels", [])
    expected_hash = f"sha256:{wheel_sha}"
    if not wheels or wheels[0].get("hash") != expected_hash:
        raise BundleError(f"locked wheel hash does not match expected {expected_hash}")


def _prepare_bundle(
    *,
    mcpb: Path,
    staging: Path,
    wheel: Path,
    url: str,
    wheel_sha: str,
    uv: str,
) -> dict[str, Any]:
    """Extract the MCPB, pin the wheel, relock, and adapt the manifest."""
    original_lock_bytes = _extract_bundle_files(mcpb, staging)

    pyproject_file = staging / "pyproject.toml"
    pyproject_text = pyproject_file.read_text(encoding="utf-8")
    _write_text(pyproject_file, swap_source(pyproject_text, wheel.name, url))

    lock_output = _run([uv, "lock", "--directory", str(staging)])
    _check_lock(original_lock_bytes, staging / "uv.lock", url, wheel_sha)

    reqs_file = staging / "requirements.txt"
    export_output = _run(
        [
            uv, "export", "--directory", str(staging), "--frozen", "--no-dev",
            "--no-emit-project", "--no-header", "--format", "requirements-txt",
            "--output-file", str(reqs_file),
        ]
    )
    reqs_text = reqs_file.read_text(encoding="utf-8")
    if url not in reqs_text or wheel_sha not in reqs_text:
        raise BundleError("requirements.txt does not contain pinned wheel url and sha")

    _write_text(staging / "server" / "bootstrap.py", BOOTSTRAP)

    manifest_file = staging / "manifest.json"
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    adapted = adapt_manifest(manifest_data)
    _write_text(manifest_file, json.dumps(adapted, indent=2) + "\n")

    return {"lock": lock_output.splitlines(), "export": export_output.splitlines()}


def _pack_bundle(*, staging: Path, bundle_path: Path, npx: str) -> dict[str, Any]:
    """Validate the staging directory, pack it, and enforce the size limit."""
    validate_output = _run([npx, "--yes", MCPB_CLI, "validate", str(staging)])
    pack_output = _run([npx, "--yes", MCPB_CLI, "pack", str(staging), str(bundle_path)])
    bundle_size = bundle_path.stat().st_size
    if bundle_size > MAX_BUNDLE_BYTES:
        raise BundleError(f"bundle size {bundle_size} exceeds 25 MiB limit")
    return {
        "size_bytes": bundle_size,
        "validate": validate_output.splitlines(),
        "pack": pack_output.splitlines(),
    }


def build(*, mcpb: Path, wheel: Path, tag: str, out_dir: Path) -> dict[str, Any]:
    """Build the Smithery bundle from an existing MCPB and wheel."""
    check_out_dir(out_dir)
    version = parse_wheel_version(wheel.name)
    url = wheel_url(tag, wheel.name)
    wheel_sha = sha256_file(wheel)
    uv = _require_executable("uv")
    npx = _require_executable("npx")

    with tempfile.TemporaryDirectory(prefix="smithery-stage-") as scratch:
        staging = Path(scratch) / "bundle"
        staging.mkdir(parents=True, exist_ok=True)
        prepared = _prepare_bundle(
            mcpb=mcpb, staging=staging, wheel=wheel, url=url, wheel_sha=wheel_sha, uv=uv
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = out_dir / smithery_bundle_filename(version)
        packed = _pack_bundle(staging=staging, bundle_path=bundle_path, npx=npx)

    info = {
        "bundle": bundle_path.name,
        "sha256": sha256_file(bundle_path),
        "size_bytes": packed["size_bytes"],
        "version": version,
        "wheel": wheel.name,
        "wheel_url": url,
        "wheel_sha256": wheel_sha,
        "tag": tag,
        "server_type": "python",
        "tool_count": len(TOOL_CATALOG),
        "tools_generated": True,
        "mcpb_cli": MCPB_CLI,
        "lock": prepared["lock"],
        "export": prepared["export"],
        "validate": packed["validate"],
        "pack": packed["pack"],
    }
    _write_text(out_dir / f"{bundle_path.name}.build-info.json", json.dumps(info, indent=2) + "\n")
    return info


def no_seed_env(seed_bundle: Path) -> dict[str, str]:
    """Build the child environment that hides any private corpus from the server."""
    # A machine with a private corpus on the default path would answer
    # groove_search without error, so the verify run must point elsewhere.
    return {"ABLETON_GROOVE_SEED_BUNDLE": str(seed_bundle)}


async def _exercise_server(
    command: str, args: list[str], seed_bundle: Path, timeout: float
) -> dict[str, Any]:
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=command, args=args, env=no_seed_env(seed_bundle))
    with anyio.fail_after(timeout):
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write, read_timeout_seconds=timedelta(seconds=timeout)) as session,
        ):
            initialized = await session.initialize()
            listed: list[str] = []
            cursor: str | None = None
            while True:
                page = await session.list_tools(cursor=cursor)
                listed.extend(tool.name for tool in page.tools)
                cursor = page.nextCursor
                if not cursor:
                    break

            plan = await session.call_tool(
                "plan_user_journey",
                {"journey_type": "sequence_drums", "traits": "half time, dark"},
            )
            groove = await session.call_tool(
                "groove_search",
                {"schema_version": "groove.search.request.v1", "query": "funk", "limit": 2},
            )
            groove_text = "".join(
                getattr(item, "text", "")
                for item in (groove.content or [])
                if getattr(item, "type", "") == "text"
            )

    return {
        "tool_names": listed,
        "plan_is_error": plan.isError,
        "groove_is_error": groove.isError,
        "groove_text": groove_text,
        "protocol_version": initialized.protocolVersion,
        "server_info": initialized.serverInfo.model_dump(mode="json", exclude_none=True),
    }


def check_observed(observed: dict[str, Any]) -> None:
    """Raise BundleError when an observed server run breaks the bundle contract."""
    catalog_names = sorted(spec.name for spec in TOOL_CATALOG)
    listed = sorted(str(name) for name in (observed.get("tool_names") or []))
    if listed != catalog_names:
        raise BundleError(
            f"tool list differs from TOOL_CATALOG: count={len(listed)} vs {len(catalog_names)}"
        )
    if observed.get("plan_is_error"):
        raise BundleError("plan_user_journey returned an error")
    if not observed.get("groove_is_error"):
        raise BundleError("groove_search expected isError=True, got False")
    groove_text = str(observed.get("groove_text", ""))
    if "ABLETON_GROOVE_SEED_BUNDLE" not in groove_text:
        raise BundleError(
            f"groove_search error does not cite ABLETON_GROOVE_SEED_BUNDLE: {groove_text}"
        )


def _verify_site_packages(environment: Path, wheel: Path) -> int:
    installed = environment / "Lib" / "site-packages" / "ableton_mcp_server"
    if not installed.is_dir():
        raise BundleError(f"installed package directory not found in {environment}")

    checked = 0
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith("ableton_mcp_server/") and not name.endswith("/"):
                rel_path = name.removeprefix("ableton_mcp_server/")
                local = installed / rel_path
                if not local.is_file():
                    raise BundleError(f"installed file missing from site-packages: {rel_path}")
                if local.read_bytes() != archive.read(name):
                    raise BundleError(f"installed file content mismatch: {rel_path}")
                checked += 1
    if checked == 0:
        raise BundleError("no wheel files verified in site-packages")
    return checked


def verify(bundle: Path, *, wheel: Path, timeout: float = 900.0) -> dict[str, Any]:
    """Extract bundle, launch stdio twice, and verify tool catalog and env."""
    import anyio

    with tempfile.TemporaryDirectory(
        prefix="smithery-verify-", ignore_cleanup_errors=True
    ) as tmp:
        target = Path(tmp) / "bundle"
        target.mkdir(parents=True, exist_ok=True)
        safe_extract(bundle, target)

        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        command, args = manifest_command(manifest, target)
        executable = _require_executable(command)

        # The seed folder does not exist, so no private corpus can be read.
        seed_bundle = Path(tmp) / "no-seed"
        first_run = anyio.run(_exercise_server, executable, args, seed_bundle, timeout)
        check_observed(first_run)

        environment = target / ".venv"
        reqs_file = target / "requirements.txt"
        if not reqs_file.is_file():
            raise BundleError("requirements.txt not found in bundle target")
        expected_digest = sha256_file(reqs_file)
        marker = environment / ".requirements-sha256"
        if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != expected_digest:
            raise BundleError(".requirements-sha256 marker mismatch after cold launch")
        marker_mtime_before = marker.stat().st_mtime_ns

        second_run = anyio.run(_exercise_server, executable, args, seed_bundle, timeout)
        check_observed(second_run)
        marker_mtime_after = marker.stat().st_mtime_ns
        if marker_mtime_after != marker_mtime_before:
            raise BundleError(".requirements-sha256 was modified during warm launch")

        checked_count = _verify_site_packages(environment, wheel)

    verification_info = {
        "status": "ok",
        "bundle": bundle.name,
        "bundle_sha256": sha256_file(bundle),
        "wheel": wheel.name,
        "first_run": first_run,
        "second_run": second_run,
        "warm_launch_skips_install": True,
        "installed_package_files_checked": checked_count,
    }
    verification_path = bundle.parent / f"{bundle.name}.verification.json"
    _write_text(verification_path, json.dumps(verification_info, indent=2) + "\n")
    return verification_info


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    build_parser = commands.add_parser("build", help="build the smithery bundle")
    build_parser.add_argument("--mcpb", type=Path, required=True, help="input MCPB bundle")
    build_parser.add_argument("--wheel", type=Path, required=True, help="wheel file")
    build_parser.add_argument("--tag", type=str, required=True, help="release tag")
    build_parser.add_argument("--out-dir", type=Path, required=True, help="output directory")

    verify_parser = commands.add_parser("verify", help="verify the smithery bundle")
    verify_parser.add_argument("bundle", type=Path, help="bundle file to verify")
    verify_parser.add_argument("--wheel", type=Path, required=True, help="expected wheel file")
    verify_parser.add_argument("--timeout", type=float, default=900.0, help="timeout in seconds")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    try:
        if args.command == "build":
            result = build(
                mcpb=args.mcpb.resolve(),
                wheel=args.wheel.resolve(),
                tag=args.tag,
                out_dir=args.out_dir.resolve(),
            )
        else:
            result = verify(
                bundle=args.bundle.resolve(),
                wheel=args.wheel.resolve(),
                timeout=args.timeout,
            )
    except BundleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result.get("status", "ok") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
