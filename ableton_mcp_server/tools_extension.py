"""Ableton Extension scaffold and build tools."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from . import models
from . import server as _s
from .server import (
    mcp,
)

# ---------------------------------------------------------------------------
# v0.3.0 — Extension Scaffolding & Building
# ---------------------------------------------------------------------------
_EXTENSION_TEMPLATE_TSCONFIG = {
    "compilerOptions": {
        "target": "ES2022",
        "module": "NodeNext",
        "moduleResolution": "NodeNext",
        "esModuleInterop": True,
        "strict": True,
        "outDir": "./dist",
        "declaration": True,
        "sourceMap": True,
    },
    "include": ["src"],
}

_EXTENSION_ENTRYPOINT_REL = "dist/extension.js"
_EXTENSION_BUILD_STEP_NAME = "build"
_EXTENSION_INSTALL_STEP_NAME = "install"


def _extension_vendor_dir() -> Path | None:
    """Locate the bundled ``vendor/`` directory shipped with the package.

    Checks the package-local ``_extension_vendor`` directory first (for
    wheel installations) and falls back to the checkout's
    ``AbletonMCPServer_Extension/vendor`` directory.
    """
    pkg_dir = Path(__file__).resolve().parent
    local_vendor = pkg_dir / "_extension_vendor"
    if local_vendor.is_dir():
        return local_vendor
    repo_root = pkg_dir.parent
    candidate = repo_root / "AbletonMCPServer_Extension" / "vendor"
    return candidate if candidate.is_dir() else None


def _read_extension_vendor_tarballs() -> dict[str, Path]:
    """Return a mapping of dependency name → absolute tarball path.

    Returns an empty mapping when the ``vendor/`` directory is not available.
    """
    vendor = _extension_vendor_dir()
    if vendor is None:
        return {}
    found: dict[str, Path] = {}
    sdk = next(vendor.glob("ableton-extensions-sdk-*.tgz"), None)
    cli = next(vendor.glob("ableton-extensions-cli-*.tgz"), None)
    if sdk is not None:
        found["@ableton-extensions/sdk"] = sdk
    if cli is not None:
        found["@ableton-extensions/cli"] = cli
    return found


def _build_extension_package_json(
    *,
    name: str,
    tarballs: dict[str, Path],
) -> dict[str, Any]:
    """Compose the ``package.json`` body for the scaffolded project.

    The dependency graph mirrors the repository's own Extension: the SDK
    tarball is a runtime dependency, the CLI tarball is a devDependency
    used to package the final ``.ablx``. The ``main`` field points to
    ``dist/extension.js`` so Node treats that file as the package
    entry; ``build_extension`` reads the same field to validate the
    build artefact.
    """
    pkg: dict[str, Any] = {
        "name": name.lower().replace(" ", "-"),
        "version": "0.5.2",
        "private": True,
        "type": "module",
        "main": _EXTENSION_ENTRYPOINT_REL,
        "scripts": {
            "build": "tsc --noEmit && tsx build.ts",
            "build:prod": "tsc --noEmit && tsx build.ts --production",
            "package": "npm run build:prod && extensions-cli package",
        },
        "engines": {"node": ">=18.0.0"},
        "dependencies": {},
        "devDependencies": {},
    }
    for dep_name, tarball in tarballs.items():
        target = pkg["dependencies"] if dep_name.endswith("/sdk") else pkg["devDependencies"]
        target[dep_name] = f"file:./vendor/{tarball.name}"
    if not any(dep.startswith("@ableton-extensions/") for dep in pkg["dependencies"]):
        # Mirror the real extension's runtime ws dependency so the
        # scaffolded project type-checks even when the SDK tarball is
        # missing from the install environment.
        pkg["dependencies"]["ws"] = "^8.18.0"
    pkg["devDependencies"].update(
        {
            "@types/node": "^24.1.0",
            "@types/ws": "^8.5.13",
            "esbuild": "0.28.1",
            "tsx": "^4.19.0",
            "typescript": "^5.9.3",
        }
    )
    return pkg


def _build_extension_manifest(*, name: str, author: str) -> dict[str, Any]:
    """Compose the Extension ``manifest.json`` payload."""
    return {
        "name": name,
        "author": author,
        "entry": _EXTENSION_ENTRYPOINT_REL,
        "version": "0.5.2",
        "minimumApiVersion": "1.0.0",
    }


_EXTENSION_TEMPLATE_EXTENSION_TS = """\
import {{ initialize, type ActivationContext }} from '@ableton-extensions/sdk';

/**
 * {name} — Ableton Live Extension scaffold
 *
 * Auto-scaffolded by ableton-mcp-server. The SDK contract is the only
 * requirement for a real Extension; this scaffold keeps the surface
 * minimal so future agents can iterate on real handlers.
 */

let activated = false;

function activate(activation: ActivationContext): void {{
  if (activated) {{
    console.log('[{name}] activate() called while already active');
    return;
  }}
  activated = true;
  const context = initialize(activation, '1.0.0');
  // Hand the SDK context to the real handlers (see ./index.js).
  console.log('[{name}] extension activated');
  void context;
}}

function deactivate(): void {{
  if (!activated) return;
  activated = false;
  console.log('[{name}] extension deactivated');
}}

export {{ activate, deactivate }};
"""


_EXTENSION_TEMPLATE_BUILD_TS = """\
import * as esbuild from 'esbuild';
import * as fs from 'node:fs';

const manifest = JSON.parse(fs.readFileSync('manifest.json', 'utf8'));
const production = process.argv.includes('--production');

await esbuild.build({
  entryPoints: ['src/extension.ts'],
  outfile: manifest.entry,
  bundle: true,
  format: 'cjs',
  platform: 'node',
  sourcesContent: false,
  logLevel: production ? 'silent' : 'info',
  sourcemap: !production,
});
"""


@mcp.tool()
def scaffold_extension(name: str, author: str = "ntworm", output_directory: str = ".") -> str:
    """Create a template Ableton Extension project folder.

    The scaffold produces an extension that follows the same shape as
    the repository's own ``AbletonMCPServer_Extension``: it imports
    ``@ableton-extensions/sdk``, declares ``dist/extension.js`` as the
    package entry in both ``package.json["main"]`` and
    ``manifest.json["entry"]``, and bundles via ``tsx build.ts``. Vendor
    tarballs shipped with the package are copied locally into the new
    project so local SDK/CLI packages are used during build. In the
    acceptance report, ``offline_passed`` indicates a probe that runs
    without requiring a connection to Ableton Live.

    Side effects: creates files on disk. No Ableton connection required.
    Example: ``scaffold_extension("MyEffect", output_directory="/tmp/ext")``
    Edge cases: returns a ``status="error"`` JSON when vendor tarballs are
    missing or output directory is not writable; never raises during disk writes.
    A name that carries a path separator, ``..`` or a drive letter is refused
    by the request model before anything is written.
    """
    tarballs = _read_extension_vendor_tarballs()
    if (
        len(tarballs) < 2
        or "@ableton-extensions/sdk" not in tarballs
        or "@ableton-extensions/cli" not in tarballs
    ):
        return json.dumps(
            {
                "status": "error",
                "message": (
                    "vendor tarballs for @ableton-extensions/sdk and "
                    "@ableton-extensions/cli are missing"
                ),
            },
            indent=2,
        )

    request = models.ScaffoldExtensionRequest(
        name=name, author=author, output_directory=output_directory
    )
    project_dir = Path(request.output_directory) / request.name
    error_document = _create_extension_project_dir(project_dir)
    if error_document is not None:
        return error_document
    files = _write_extension_scaffold(project_dir, request, tarballs)

    return json.dumps(
        {
            "status": "scaffolded",
            "project_path": str(project_dir),
            "entrypoint": _EXTENSION_ENTRYPOINT_REL,
            "files": files,
        },
        indent=2,
    )


def _create_extension_project_dir(project_dir: Path) -> str | None:
    """Create the new project folder; return an error document when it fails."""
    try:
        project_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return json.dumps(
            {
                "status": "error",
                "message": f"project directory already exists: {project_dir}",
            },
            indent=2,
        )
    except OSError as error:
        return json.dumps(
            {
                "status": "error",
                "message": f"cannot create project directory: {error}",
            },
            indent=2,
        )
    return None


def _write_extension_scaffold(
    project_dir: Path,
    request: models.ScaffoldExtensionRequest,
    tarballs: dict[str, Path],
) -> list[str]:
    """Write the scaffold files and vendor tarballs; return their relative paths."""
    src_dir = project_dir / "src"
    src_dir.mkdir(exist_ok=True)

    vendor_target = project_dir / "vendor"
    vendor_target.mkdir(exist_ok=True)
    copied_vendor_files: list[str] = []
    for tarball in tarballs.values():
        (vendor_target / tarball.name).write_bytes(tarball.read_bytes())
        copied_vendor_files.append(f"vendor/{tarball.name}")

    pkg = _build_extension_package_json(
        name=request.name,
        tarballs=tarballs,
    )
    (project_dir / "package.json").write_text(json.dumps(pkg, indent=2), encoding="utf-8")
    (project_dir / "tsconfig.json").write_text(
        json.dumps(_EXTENSION_TEMPLATE_TSCONFIG, indent=2), encoding="utf-8"
    )
    (project_dir / "manifest.json").write_text(
        json.dumps(
            _build_extension_manifest(name=request.name, author=request.author),
            indent=2,
        ),
        encoding="utf-8",
    )
    (project_dir / "build.ts").write_text(_EXTENSION_TEMPLATE_BUILD_TS, encoding="utf-8")
    (src_dir / "extension.ts").write_text(
        _EXTENSION_TEMPLATE_EXTENSION_TS.format(name=request.name),
        encoding="utf-8",
    )

    files = [
        "package.json",
        "tsconfig.json",
        "manifest.json",
        "build.ts",
        "src/extension.ts",
        *copied_vendor_files,
    ]
    return files


@mcp.tool()
def build_extension(project_path: str) -> str:
    """Run a build of an Ableton Extension project.

    Side effects: runs ``npm install`` and ``npm run build`` in the
    supplied project directory.

    Contract (v0.5.1): the JSON document returned by this tool has the
    following shape::

        {
            "status": "built" | "error",
            "entrypoint": "dist/extension.js",
            "entrypoint_exists": true,
            "steps": [
                {"step": "install", "returncode": 0,
                 "stdout": "...", "stderr": "..."},
                {"step": "build", "returncode": 0,
                 "stdout": "...", "stderr": "..."}
            ],
            "artifacts": ["dist/extension.js", "..."]
        }

    ``entrypoint`` is read from ``package.json["main"]`` (falling back
    to ``manifest.json["entry"]`` when ``main`` is missing) so the
    contract reflects the project's own declaration. ``artifacts`` is
    populated when ``status == "built"`` and lists every file under
    ``dist/`` relative to the project root. When the build completes
    but the declared entrypoint is missing on disk, ``status`` flips
    to ``"error"`` and ``entrypoint_exists`` is ``false``.

    Example: ``build_extension("/path/to/my-extension")`` runs
    ``npm install`` then ``npm run build`` and returns the JSON
    document above. Requires Node.js and npm on the host machine.
    Edge cases: returns ``{"status": "error", "message": ...}``
    when ``package.json`` is missing; never raises during the
    subprocess execution — every step's ``returncode`` is reported
    in the ``steps`` array instead.
    """
    request = models.BuildExtensionRequest(project_path=project_path)
    project = Path(request.project_path)
    entrypoint_rel, error_document = _extension_build_preflight(project)
    if entrypoint_rel is None:
        return error_document
    steps, step_error = _run_extension_build_steps(project, entrypoint_rel)
    if step_error is not None:
        return step_error

    artifacts = _extension_dist_artifacts(project)
    entrypoint_exists = (project / entrypoint_rel).is_file()
    status = "built" if entrypoint_exists else "error"
    return json.dumps(
        {
            "status": status,
            "entrypoint": entrypoint_rel,
            "entrypoint_exists": entrypoint_exists,
            "steps": steps,
            "artifacts": artifacts,
        },
        indent=2,
    )


def _extension_build_preflight(project: Path) -> tuple[str | None, str]:
    """Return (entrypoint, "") or (None, error document) before any build step runs."""
    if not (project / "package.json").is_file():
        return None, json.dumps(
            {"status": "error", "message": "no package.json found", "project_path": str(project)},
            indent=2,
        )

    entrypoint_rel = _resolve_extension_entrypoint(project)
    if entrypoint_rel is None:
        return None, json.dumps(
            {
                "status": "error",
                "message": (
                    "package.json has no 'main' and manifest.json has no 'entry'; "
                    "cannot validate build artefact"
                ),
            },
            indent=2,
        )
    return entrypoint_rel, ""


def _run_extension_build_steps(
    project: Path, entrypoint_rel: str
) -> tuple[list[dict[str, Any]], str | None]:
    """Run npm install and npm run build; return the steps and an error document on failure."""
    steps: list[dict[str, Any]] = []
    # Use an argument list rather than shell=True so the user-supplied
    # project_path can never be interpreted by a shell. Each step is a
    # separate subprocess so a failing install does not mask a build failure.
    npm_bin = shutil.which("npm") or "npm"
    for step_name, raw_cmd in (
        (_EXTENSION_INSTALL_STEP_NAME, [npm_bin, "install"]),
        (_EXTENSION_BUILD_STEP_NAME, [npm_bin, "run", "build"]),
    ):
        cmd = ["cmd.exe", "/c"] + raw_cmd if _s.os.name == "nt" else raw_cmd
        result = _s.subprocess.run(
            cmd,
            cwd=str(project),
            shell=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        steps.append(
            {
                "step": step_name,
                "returncode": result.returncode,
                "stdout": result.stdout[-2000:] if result.stdout else "",
                "stderr": result.stderr[-2000:] if result.stderr else "",
            }
        )
        if result.returncode != 0:
            return steps, json.dumps(
                {
                    "status": "error",
                    "entrypoint": entrypoint_rel,
                    "entrypoint_exists": ((project / entrypoint_rel).is_file()),
                    "steps": steps,
                    "artifacts": [],
                },
                indent=2,
            )
    return steps, None


def _extension_dist_artifacts(project: Path) -> list[str]:
    """List every file under ``dist/`` relative to the project root."""
    dist_dir = project / "dist"
    artifacts: list[str] = []
    if dist_dir.is_dir():
        for candidate in sorted(dist_dir.rglob("*")):
            if candidate.is_file():
                artifacts.append(candidate.relative_to(project).as_posix())
    return artifacts


def _resolve_extension_entrypoint(project: Path) -> str | None:
    """Discover the canonical Extension entrypoint.

    Prefers ``package.json["main"]`` (Node's package entry convention).
    Falls back to ``manifest.json["entry"]`` so legacy scaffolds that
    only declared ``manifest.entry`` still validate. Returns ``None``
    when neither source is present.
    """
    pkg_path = project / "package.json"
    main = _json_string_field(pkg_path, "main")
    if main is not None:
        return main
    manifest_path = project / "manifest.json"
    return _json_string_field(manifest_path, "entry")


def _json_string_field(path: Path, key: str) -> str | None:
    """Return the stripped, non-empty string at KEY of a JSON object file, or None."""
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        document = None
    if isinstance(document, dict):
        value = document.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
