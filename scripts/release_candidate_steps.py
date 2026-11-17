"""The steps that turn a source tree into release candidate artifacts.

``scripts/build_release_candidates.py`` orchestrates the release; the steps
that write the checksums, the install guide, the release notes and the
acceptance evidence live here.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ableton_mcp_server.catalog import TOOL_CATALOG

# The builder keeps the same constant; it is repeated here so that the steps
# module does not have to import the builder it was extracted from.
EXPECTED_TOOL_COUNT = len(TOOL_CATALOG)


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


def _build_extension_ablx(
    root: Path,
    output_directory: Path,
    *,
    version: str,
    subprocess_runner: Callable[..., Any] | None = None,
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
    out = output_directory / f"AbletonMCPServer-Extension-{version}.ablx"
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


def _write_install_md(output_directory: Path, *, version: str, stable: bool) -> Path:
    suffix = "" if stable else "-rc1"
    audience = (
        "This stable release passed the repository's guarded certification gate."
        if stable
        else "This release candidate is not promoted until guarded certification passes."
    )
    body = (
        f"# Install v{version}{suffix}\n\n"
        f"{audience}\n\n"
        "## Python wheel\n\n"
        "```\n"
        f"pip install {output_directory.as_posix()}"
        f"/ableton_mcp_server-{version}-py3-none-any.whl\n"
        "```\n\n"
        "## MIDI Remote Script\n\n"
        f"Extract `AbletonMCPServer_RemoteScript-{version}.zip` into "
        "your Live MIDI Remote Scripts folder, e.g.\n"
        "`%USERPROFILE%\\Documents\\Ableton\\User Library\\"
        "Remote Scripts\\`.\n\n"
        "## Extension Host\n\n"
        "### 1. Preferred Installation Flow (Auto)\n"
        f"Double-click `AbletonMCPServer-Extension-{version}.ablx` or drag and drop "
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


def _write_release_notes(
    artifacts: dict[str, Path],
    output_directory: Path,
    *,
    version: str,
    stable: bool,
) -> Path:
    state = (
        "This stable release is bound to a guarded acceptance report with "
        "`release_ready=true`."
        if stable
        else "This candidate is not certified and cannot be promoted until the guarded "
        "acceptance report returns `release_ready=true`."
    )
    body = (
        f"# v{version}\n\n"
        f"{state}\n\n"
        "## Highlights\n\n"
        f"- {EXPECTED_TOOL_COUNT}-tool capability catalog is the single source of truth for "
        "the FastMCP surface and the per-tool certification report.\n"
        "- Deterministic offline music generation and Groove Intelligence are included.\n"
        "- The Extension WebSocket binds explicitly to `127.0.0.1:9889`; "
        "LAN exposure is forbidden by design.\n"
        "- `ableton-mcp acceptance --profile baseline` runs the full "
        f"{EXPECTED_TOOL_COUNT}-tool surface against the disposable Set, returns a "
        "CertificationReport, and the CLI exits non-zero on any "
        "`failed` row.\n\n"
        "## Artifacts\n\n"
    )
    for _label, path in artifacts.items():
        body += f"- `{path.name}` (sha256 `{_sha256(path)}`)\n"
    out = output_directory / "RELEASE-NOTES.md"
    out.write_text(body, encoding="utf-8")
    return out


def _validated_acceptance_report(
    path: Path,
    *,
    source_commit: str,
    expected_tool_count: int,
) -> dict[str, Any]:
    """Validate the evidence required to promote stable artifacts."""
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"acceptance report is unreadable: {error}") from error
    if not isinstance(report, dict):
        raise ValueError("acceptance report must contain a JSON object")

    certification = report.get("certification", report)
    if not isinstance(certification, dict) or certification.get("release_ready") is not True:
        raise ValueError("stable release requires acceptance report release_ready=true")

    report_tool_count = report.get("tool_count", certification.get("tool_count"))
    if report_tool_count != expected_tool_count:
        raise ValueError(
            "acceptance report tool count does not match the catalog: "
            f"{report_tool_count!r} != {expected_tool_count}"
        )

    report_commit = report.get("source_commit")
    if report_commit is not None and report_commit != source_commit:
        raise ValueError(
            "acceptance report source commit does not match HEAD: "
            f"{report_commit!r} != {source_commit!r}"
        )
    return report
