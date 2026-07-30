"""Build v0.5.1-rc1 release candidates into an injected output directory.

This script produces three artifacts plus a SHA256SUMS file, an
INSTALL.md, a RELEASE-NOTES.md, and a manifest.json:

- ``ableton_mcp_server-0.5.1-py3-none-any.whl``
- ``AbletonMCPServer_RemoteScript-0.5.1.zip``
- ``AbletonMCPServer-Extension-0.5.1.ablx``

The script is deliberately testable: every public function takes the
output directory as a parameter so unit tests can run in ``tmp_path``
without polluting the project tree. The CLI entrypoint keeps the
default ``releases/v0.5.1-rc1`` location so existing workflows do not
change.

The manifest always flags ``live_certified=false`` and
``promotion_ready=false``; the owner flips both to ``true`` after the
Live acceptance checkpoint returns 65 rows with zero failures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

VERSION = "0.5.1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE_DIR = ROOT / "releases" / f"v{VERSION}-rc1"

_HEX_COMMIT_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")


def _run_git_command(
    args: list[str],
    *,
    root: Path | None = None,
    runner: Callable[..., Any] | None = None,
) -> Any:
    exec_runner = runner or subprocess.run
    cwd_str = str(root) if root else None
    cmd = ["git"] + args
    try:
        proc = exec_runner(cmd, cwd=cwd_str, capture_output=True, text=True, check=False)
        if getattr(proc, "returncode", 1) == 0:
            return proc
    except Exception:
        pass

    # Windows git.exe cannot parse /mnt/c/ paths in .git worktree pointer files created by WSL git.
    # Fallback to `wsl git` on Windows.
    if sys.platform == "win32" or os.name == "nt":
        wsl_cmd = ["wsl", "git"] + args
        try:
            wsl_proc = exec_runner(
                wsl_cmd, cwd=cwd_str, capture_output=True, text=True, check=False
            )
            if getattr(wsl_proc, "returncode", 1) == 0:
                return wsl_proc
        except Exception:
            pass

    return exec_runner(cmd, cwd=cwd_str, capture_output=True, text=True, check=False)


def _validate_source_commit(
    value: str | None,
    *,
    root: Path | None = None,
    git_runner: Callable[..., Any] | None = None,
) -> str:
    """Validate a 40-char git commit hash and verify existence in git repository.

    The release manifest must always carry a real, full 40-character commit hash
    that exists as a commit object in the git repository.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "source_commit must be a non-empty string; pass "
            "`git rev-parse HEAD` (or `--source-commit <hash>`) explicitly"
        )
    candidate = value.strip().lower()
    if candidate == "unknown":
        raise ValueError(
            "source_commit='unknown' is forbidden; the release owner "
            "must supply a real git commit hash"
        )
    if not _HEX_COMMIT_PATTERN.match(candidate):
        raise ValueError(
            f"source_commit {candidate!r} is not a valid 40-character hexadecimal git commit hash"
        )

    proc = _run_git_command(
        ["cat-file", "-e", f"{candidate}^{{commit}}"],
        root=root,
        runner=git_runner,
    )
    returncode = getattr(proc, "returncode", 1)
    if returncode != 0:
        raise ValueError(
            f"source_commit {candidate!r} does not correspond to an existing git commit object"
        )
    return candidate


def _resolve_source_commit(*, root: Path, runner: Callable[..., Any] | None = None) -> str:
    """Resolve the source commit hash from the worktree.

    Production callers do not pass ``runner``; the helper invokes
    ``git rev-parse HEAD`` in the project root so the manifest always
    records the real commit, even when ``build_release`` is called
    directly without ``--source-commit``. Tests can swap in a fake
    runner so the resolution path stays deterministic.
    """
    proc = _run_git_command(["rev-parse", "HEAD"], root=root, runner=runner)
    if getattr(proc, "returncode", 1) != 0:
        raise RuntimeError(
            f"Failed to resolve git rev-parse HEAD in {root}: {getattr(proc, 'stderr', '')}"
        )
    raw_out = getattr(proc, "stdout", "")
    raw_hash = raw_out.strip() if isinstance(raw_out, str) else str(raw_out).strip()
    return _validate_source_commit(raw_hash, root=root, git_runner=runner)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest()


def _purge_stale_candidates(output_directory: Path, *, extensions: tuple[str, ...]) -> None:
    """Remove any pre-existing artifacts in the output directory.

    The builder must not pick up a stale wheel / .ablx / zip from a
    previous run; if it did, ``candidates[0]`` would point at the old
    artifact rather than the fresh one.
    """
    if not output_directory.exists():
        return
    for pattern in extensions:
        for path in output_directory.glob(f"*.{pattern}"):
            path.unlink()


def _build_python_wheel(root: Path, output_directory: Path) -> Path:
    """Build the Python wheel via ``python -m build`` in the worktree venv."""
    import os
    import sys

    if sys.platform == "win32" or os.name == "nt":
        py = root / ".venv-win" / "Scripts" / "python.exe"
        if not py.exists():
            py = root / ".venv" / "Scripts" / "python.exe"
    else:
        py = root / ".venv" / "bin" / "python"
        if not py.exists():
            py = Path(sys.executable)

    if not py.exists():
        raise RuntimeError(
            "Neither .venv-win nor .venv found; create one with "
            "`python -m venv .venv && pip install -e .[dev]`."
        )
    subprocess.run([str(py), "-m", "pip", "install", "--quiet", "build"], check=True)
    subprocess.run(
        [str(py), "-m", "build", "--wheel", "--outdir", str(output_directory)],
        cwd=str(root),
        check=True,
    )
    wheels = sorted(output_directory.glob("ableton*.whl"))
    if not wheels:
        wheels = sorted(output_directory.glob("*.whl"))
    if not wheels:
        raise RuntimeError(
            f"Python wheel was not produced in {output_directory}; "
            f"found contents: {list(output_directory.iterdir())}"
        )
    return wheels[0]


def _build_remote_script_zip(root: Path, output_directory: Path) -> Path:
    """Zip the vendored Remote Script payload (Live drop-in folder)."""
    src = root / "AbletonMCPServer_RemoteScript"
    out = output_directory / f"AbletonMCPServer_RemoteScript-{VERSION}.zip"
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src.rglob("*")):
            if path.is_dir():
                continue
            if path.suffix == ".pyc":
                continue
            rel = path.relative_to(src)
            if "__pycache__" in rel.parts:
                continue
            arcname = path.relative_to(root).as_posix()
            zf.write(path, arcname)
    return out


def _build_extension_ablx(
    root: Path, output_directory: Path, *, subprocess_runner: Callable[..., Any] | None = None
) -> Path:
    """Build the Extension Host ``.ablx`` payload using ``extensions-cli``.

    The ``extensions-cli package`` step is invoked through an injectable
    ``subprocess_runner`` so unit tests can swap in a fake without relying
    on shell scripting. Production callers keep the default
    ``subprocess.run``; the call uses a list-form argv (no ``shell=True``)
    so it is portable across Windows and POSIX runners.
    """
    if subprocess_runner is None:
        subprocess_runner = subprocess.run
    ext_dir = root / "AbletonMCPServer_Extension"
    # ``npm run package`` is defined in package.json as
    # ``build:prod && extensions-cli package``.
    # Resolve ``npm`` through ``shutil.which`` so Windows and Linux both
    # find the executable in their native form (``npm.cmd``/``npm``).
    npm_exe = shutil.which("npm") or shutil.which("npm.cmd") or "npm"
    subprocess_runner(
        [npm_exe, "run", "package"],
        cwd=str(ext_dir),
        check=True,
    )
    candidates = list(ext_dir.glob("*.ablx"))
    if not candidates:
        raise RuntimeError("extensions-cli did not produce an .ablx archive")
    src = candidates[0]
    out = output_directory / f"AbletonMCPServer-Extension-{VERSION}.ablx"
    shutil.copy2(src, out)
    return out


def _write_sha256_sums(artifacts: list[Path], output_directory: Path) -> Path:
    """Write ``SHA256SUMS`` listing every artifact with its forward-slash name."""
    lines = []
    for path in sorted(artifacts):
        rel = path.relative_to(output_directory).as_posix()
        lines.append(f"{_sha256(path)}  {rel}\n")
    out = output_directory / "SHA256SUMS"
    out.write_text("".join(lines), encoding="utf-8")
    return out


def _write_install_md(output_directory: Path, root: Path) -> Path:
    body = (
        f"# Install v{VERSION}-rc1\n\n"
        "These release candidates install on the owner machine only. Do "
        "not run them from a CI environment.\n\n"
        "## Python wheel\n\n"
        "```\n"
        f"pip install {output_directory.as_posix()}"
        f"/ableton_mcp_server-{VERSION}-py3-none-any.whl\n"
        "```\n\n"
        "## MIDI Remote Script\n\n"
        f"Extract `AbletonMCPServer_RemoteScript-{VERSION}.zip` into "
        "your Live MIDI Remote Scripts folder, e.g.\n"
        "`%USERPROFILE%\\Documents\\Ableton\\User Library\\"
        "Remote Scripts\\`.\n\n"
        "## Extension Host\n\n"
        "### 1. Preferred Installation Flow (Auto)\n"
        f"Double-click `AbletonMCPServer-Extension-{VERSION}.ablx` or drag and drop "
        "it directly into the Ableton Live window to let Ableton install the "
        "extension automatically.\n\n"
        "### 2. Manual Extraction Fallback\n"
        "If the preferred flow fails or is not supported by your Live version, "
        "you can manually extract/unzip the `.ablx` file (which is a zip archive) "
        "into the following directory:\n"
        "- **Windows**: `%LOCALAPPDATA%\\Ableton\\Extensions\\"
        "ntworm.abletonmcpserver-extension`\n"
        "- **macOS**: `~/Library/Application Support/Ableton/Extensions/"
        "ntworm.abletonmcpserver-extension`\n\n"
        "## Restarting Requirement\n"
        "**CRITICAL**: You MUST completely close and restart Ableton Live for the "
        "new Extension and MIDI Remote Script to be registered and loaded.\n\n"
        "## Verification\n"
        "1. Verify that `manifest.json` in the installed extension folder "
        "displays the correct version and metadata.\n"
        "2. Ensure the installed files match the hashes in `SHA256SUMS`.\n"
        "3. Run the following status commands to check the installation:\n"
        "```\n"
        ".venv-win\\Scripts\\ableton-mcp.exe install-status --json\n"
        ".venv-win\\Scripts\\ableton-mcp.exe doctor --json\n"
        "```\n\n"
        "Then open the disposable Set `TESTE_CODEX` and run the gated "
        "baseline certification (owner-driven; see RELEASE-NOTES.md).\n"
    )
    out = output_directory / "INSTALL.md"
    out.write_text(body, encoding="utf-8")
    return out


def _write_release_notes(artifacts: dict[str, Path], output_directory: Path) -> Path:
    body = (
        f"# v{VERSION} — Slice 1 stabilization\n\n"
        "This release candidate bundles the Slice 1 corrections on top of "
        "v0.5.0. It is **not yet certified** — the baseline acceptance "
        "run against the disposable `TESTE_CODEX` Set must finish with "
        "zero `failed` rows before promotion to a stable tag.\n\n"
        "## Highlights\n\n"
        "- 65-tool capability catalog is the single source of truth for "
        "the FastMCP surface and the per-tool certification report.\n"
        "- `live_fade` distributes its writes across the requested "
        "`duration` via `time.monotonic` and never blocks the Live main "
        "thread.\n"
        "- The Extension WebSocket binds explicitly to `127.0.0.1:9889`; "
        "LAN exposure is forbidden by design.\n"
        "- Cross-bridge error taxonomy adds `CAPABILITY_UNAVAILABLE`, "
        "`AMBIGUOUS_MATCH`, `VERIFICATION_FAILED`, "
        "`ACCEPTANCE_GUARD_FAILED` on top of the existing transport "
        "codes.\n"
        "- `ableton-mcp acceptance --profile baseline` runs the full "
        "65-tool surface against the disposable Set, returns a "
        "CertificationReport, and the CLI exits non-zero on any "
        "`failed` row.\n\n"
        "## Artifacts\n\n"
    )
    for _label, path in artifacts.items():
        body += f"- `{path.name}` (sha256 `{_sha256(path)}`)\n"
    out = output_directory / "RELEASE-NOTES.md"
    out.write_text(body, encoding="utf-8")
    return out


def build_release(
    *,
    root: Path = ROOT,
    output_directory: Path | None = None,
    subprocess_runner: Callable[..., Any] | None = None,
    source_commit: str | None = None,
    git_runner: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Build the release candidates and return a structured summary.

    The summary mirrors the contents of ``manifest.json`` so tests can
    inspect it without re-reading the JSON file.

    ``subprocess_runner`` is injectable for tests; production callers
    keep the default (``subprocess.run`` resolved at call time).

    ``source_commit`` is the git commit hash that produced the
    candidates. When ``None`` (the default), ``build_release`` resolves
    it via ``git rev-parse HEAD`` in ``root``. The hash is validated as
    hexadecimal and the literal string ``"unknown"`` is forbidden — a
    release built without a verifiable commit cannot be promoted.
    """
    if subprocess_runner is None:
        subprocess_runner = subprocess.run

    resolved_head = _resolve_source_commit(root=root, runner=git_runner)

    if source_commit is None:
        source_commit = resolved_head
    else:
        validated_commit = _validate_source_commit(source_commit, root=root, git_runner=git_runner)
        if validated_commit != resolved_head:
            raise ValueError(
                f"source_commit {validated_commit!r} does not match "
                f"worktree HEAD {resolved_head!r}; release candidates must be "
                "produced strictly from the active HEAD"
            )

        source_commit = validated_commit

    output_directory = output_directory or DEFAULT_RELEASE_DIR
    output_directory.mkdir(parents=True, exist_ok=True)

    # Always clear stale candidates before producing fresh ones so the
    # builder never picks up a previous run's ``.ablx`` / wheel / zip.
    _purge_stale_candidates(
        output_directory,
        extensions=("whl", "zip", "ablx"),
    )
    # Also clear stale artifacts inside the Extension source dir so the
    # ``npm run package`` step does not pick up a previous build. The
    # variable name avoids the unused-binding lint without hiding the
    # intentional side effect below.
    ext_dir = root / "AbletonMCPServer_Extension"
    for path in ext_dir.glob("*.ablx"):
        path.unlink()

    wheel = _build_python_wheel(root, output_directory)
    remote_zip = _build_remote_script_zip(root, output_directory)
    ablx = _build_extension_ablx(
        root,
        output_directory,
        subprocess_runner=subprocess_runner,
    )

    artifacts = {
        "wheel": wheel,
        "remote_script_zip": remote_zip,
        "extension_ablx": ablx,
    }
    sums = _write_sha256_sums(
        [wheel, remote_zip, ablx],
        output_directory,
    )
    install = _write_install_md(output_directory, root)
    notes = _write_release_notes(artifacts, output_directory)

    manifest: dict[str, Any] = {
        "version": VERSION,
        "candidate": "rc1",
        "source_commit": source_commit,
        "artifacts": {
            label: {
                # Paths are always relative to the output directory and
                # use POSIX separators so they survive Windows checkout
                # round-trips.
                "path": path.relative_to(output_directory).as_posix(),
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
            for label, path in artifacts.items()
        },
        "live_certified": False,
        "promotion_ready": False,
    }

    (output_directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return {
        **manifest,
        "files": {
            "sha256sums": str(sums.relative_to(output_directory).as_posix()),
            "install_md": str(install.relative_to(output_directory).as_posix()),
            "release_notes": str(notes.relative_to(output_directory).as_posix()),
            "manifest": "manifest.json",
        },
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    ``--source-commit`` is required at the CLI surface: the release
    owner must supply the commit hash so the manifest is traceable.
    Production ``main()`` also resolves the hash from the worktree
    git, so the CLI value (when present) takes precedence and the
    resolved value is the fallback.
    """
    parser = argparse.ArgumentParser(
        prog="build_release_candidates",
        description=(
            "Build the v0.5.1-rc1 release candidates (wheel, Remote "
            "Script zip, Extension .ablx) into releases/v0.5.1-rc1/."
        ),
    )
    parser.add_argument(
        "--source-commit",
        default=None,
        help=(
            "Optional git commit hash that produced the candidates. "
            "When omitted the script resolves the worktree's HEAD via "
            "`git rev-parse HEAD`. The literal value 'unknown' is "
            "rejected."
        ),
    )
    parser.add_argument(
        "--output-directory",
        default=None,
        help=("Optional output directory; defaults to releases/v0.5.1-rc1/ in the worktree root."),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    output_directory = Path(args.output_directory) if args.output_directory else None
    try:
        summary = build_release(
            output_directory=output_directory,
            source_commit=args.source_commit,
        )
    except ValueError as error:
        # ``source_commit`` validation (or any other builder invariant)
        # must surface as a non-zero CLI exit so the workflow stops
        # before producing a release with the ``unknown`` placeholder.
        print(f"build_release failed: {error}", file=__import__("sys").stderr)
        return 1
    print(f"Building into {output_directory or DEFAULT_RELEASE_DIR}")
    for label in ("wheel", "remote_script_zip", "extension_ablx"):
        print(f"  {label:20s} {summary['artifacts'][label]['path']}")
    print(f"  sha256sums           {summary['files']['sha256sums']}")
    print(f"  install              {summary['files']['install_md']}")
    print(f"  release notes        {summary['files']['release_notes']}")
    print(f"  source_commit        {summary['source_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
