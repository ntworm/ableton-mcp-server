from __future__ import annotations

import hashlib
import os
import platform
import shutil
import sys
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from contracts import (
    ALLOWED_MUTATIONS,
    CAPABILITY_EVIDENCE,
    DEFAULT_HOST,
    DEFAULT_WS_PORT,
    READ_COMMANDS,
    READ_ONLY_COMMANDS,
    UNSUPPORTED_CAPABILITIES,
    WEBSOCKET_TARGET_COMMANDS,
)

from . import __version__
from .catalog import TOOL_CATALOG, Route


@dataclass(frozen=True)
class RuntimeInfo:
    platform: str
    is_wsl: bool
    python_executable: str


class BridgeClient(Protocol):
    host: str
    port: int

    def call(
        self,
        command_type: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float = 5.0,
    ) -> Any: ...


REMOTE_SCRIPT_FILES = ("__init__.py", "_contracts.py", "README.md")
REMOTE_SCRIPT_NAME = "AbletonMCPServer_RemoteScript"


def detect_runtime(env: Mapping[str, str] | None = None) -> RuntimeInfo:
    environment = os.environ if env is None else env
    release = platform.release().lower()
    is_wsl = bool(environment.get("WSL_DISTRO_NAME")) or "microsoft" in release
    return RuntimeInfo(
        platform=sys.platform,
        is_wsl=is_wsl,
        python_executable=sys.executable,
    )


def bundled_remote_script_path(package_dir: Path | None = None) -> Path:
    """Return the bundled Remote Script directory.

    Kept as a compatibility wrapper that returns ``BundledSource.path``.
    """
    return bundled_remote_script_source(package_dir).path


@dataclass(frozen=True)
class BundledSource:
    path: Path
    kind: str  # "checkout" or "wheel"


def bundled_remote_script_source(package_dir: Path | None = None) -> BundledSource:
    """Resolve which copy of the Remote Script is bundled with the package.

    Returns a typed descriptor so callers can tell whether they are running
    against a checkout tree (development) or an installed wheel (production).
    """
    package = Path(__file__).resolve().parent if package_dir is None else package_dir
    checkout_source = package.parent / REMOTE_SCRIPT_NAME
    if checkout_source.is_dir():
        return BundledSource(checkout_source, "checkout")
    wheel_source = package / "_remote_script"
    if wheel_source.is_dir():
        return BundledSource(wheel_source, "wheel")
    raise FileNotFoundError(
        "Bundled AbletonMCPServer_RemoteScript could not be found in the checkout or wheel."
    )


def default_remote_scripts_root(
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    environment = os.environ if env is None else env
    explicit = environment.get("ABLETON_MCP_REMOTE_SCRIPTS_DIR")
    if explicit:
        return Path(explicit).expanduser()
    user_home = Path.home() if home is None else home
    user_profile = environment.get("USERPROFILE")
    if user_profile:
        user_home = Path(user_profile)
    if sys.platform == "darwin":
        return user_home / "Music" / "Ableton" / "User Library" / "Remote Scripts"
    return user_home / "Documents" / "Ableton" / "User Library" / "Remote Scripts"


def bridge_status(
    client: BridgeClient,
    *,
    runtime: RuntimeInfo | None = None,
    timeout: float = 2.0,
    tool_count: int = 0,
) -> dict[str, Any]:
    info = detect_runtime() if runtime is None else runtime
    bundled = bundled_remote_script_source()
    base: dict[str, Any] = {
        "endpoint": {"host": client.host, "port": client.port},
        "runtime": asdict(info),
        "server_version": __version__,
        "tool_count": tool_count,
        "ws_endpoint": {"host": DEFAULT_HOST, "port": DEFAULT_WS_PORT},
        "extension_host_available": None,
        "ws_methods_registered": sorted(WEBSOCKET_TARGET_COMMANDS),
        "python_runtime": {"platform": info.platform, "is_wsl": info.is_wsl},
        # Slice 1 Task 8: tell callers whether they're running from a checkout
        # or an installed wheel, plus the resolved interpreter path.
        "source_kind": bundled.kind,
        "source": str(bundled.path),
        "python_executable": str(Path(sys.executable).resolve()),
        "features": [
            "device_parameter_write",
            "session_clip_automation",
            "session_clip_mutations",
            "bounded_browser_search",
            "extended_midi_notes",
        ],
        # R4 -- capability matrix derived from TOOL_CATALOG and contracts.*
        # at call time. No persisted JSON, no module-level cache. Adding a
        # tool requires no edits here.
        "tools": [
            {
                "name": spec.name,
                "domain": spec.domain,
                "route": spec.route.value,
                "risk": spec.risk.value,
                "acceptance": spec.acceptance.value,
                "reversible": spec.reversible,
            }
            for spec in TOOL_CATALOG
        ],
        "capability_counts": _capability_counts(),
        "capability_source": _capability_source(),
        "capability_gaps": capability_gaps(),
    }
    try:
        live = client.call("get_session_info", {}, timeout=timeout)
    except Exception as error:
        if info.is_wsl:
            hint = (
                "Run the Windows Python ableton-mcp-server.exe from WSL so the MCP process "
                "shares Live's Windows loopback network."
            )
        else:
            hint = (
                "Confirm Ableton Live is open, AbletonMCPServer is enabled as a Control "
                "Surface, and TCP 127.0.0.1:9888 is listening."
            )
        return {
            **base,
            "status": "error",
            "bridge_available": False,
            "live": None,
            "error": str(error),
            "hint": hint,
        }
    return {
        **base,
        "status": "ok",
        "bridge_available": True,
        "live": live,
        "error": None,
        "hint": None,
    }


def _capability_counts() -> dict[str, int]:
    """Return the R4 capability counts derived from catalog and contracts.

    Every value is computed at call time from the canonical sources
    (TOOL_CATALOG and contracts.*); nothing is cached at module level.
    live_required_tools is the public tool count minus every tool whose
    route is LOCAL (the six LOCAL_READS plus the two LOCAL_WRITES); none
    of those eight tools require an Ableton Live process.
    """
    routed = READ_COMMANDS | ALLOWED_MUTATIONS
    local_tools = {spec.name for spec in TOOL_CATALOG if spec.route is Route.LOCAL}
    live_required = len(TOOL_CATALOG) - len(local_tools)
    return {
        "public_tools": len(TOOL_CATALOG),
        "routed_commands": len(routed),
        "websocket_targets": len(WEBSOCKET_TARGET_COMMANDS),
        "read_only_blocked": len(READ_ONLY_COMMANDS),
        "feature_flags": 5,
        "live_required_tools": live_required,
        # Tools that validate a request and then refuse it because no public
        # Live API can perform it. They are neither reads nor mutations.
        "capability_unavailable": len(UNSUPPORTED_CAPABILITIES),
    }


def capability_gaps() -> dict[str, dict[str, Any]]:
    """Return the evidence behind every permanently unavailable operation.

    Surfaced by ``get_bridge_status`` so an agent can discover *why* an
    operation is refused without having to trigger the refusal first.
    """

    return {
        name: {
            "message": message,
            "evidence": CAPABILITY_EVIDENCE[name],
        }
        for name, message in UNSUPPORTED_CAPABILITIES.items()
    }


def _capability_source() -> dict[str, str]:
    """Provenance for each capability_counts key.

    Points a debugger at the canonical source so the count cannot drift
    silently from the catalog or the contracts module.
    """
    return {
        "catalog": "ableton_mcp_server.catalog:TOOL_CATALOG",
        "routed_commands": "contracts:READ_COMMANDS|ALLOWED_MUTATIONS",
        "websocket_targets": "contracts:WEBSOCKET_TARGET_COMMANDS",
        "read_only": "contracts:READ_ONLY_COMMANDS",
        "features": "ableton_mcp_server.diagnostics.bridge_status:features",
        "capability_unavailable": "contracts:UNSUPPORTED_CAPABILITIES",
    }


def _default_ableton_roots(environment: Mapping[str, str]) -> list[Path]:
    roots: list[Path] = []
    appdata = environment.get("APPDATA")
    if appdata:
        roots.append(Path(appdata) / "Ableton")
    roots.append(Path.home() / "Library" / "Preferences" / "Ableton")
    windows_users = Path("/mnt/c/Users")
    if windows_users.is_dir():
        with suppress(OSError):
            roots.extend(
                profile / "AppData" / "Roaming" / "Ableton"
                for profile in windows_users.iterdir()
                if profile.is_dir()
            )
    return roots


def find_ableton_log_path(
    *,
    env: Mapping[str, str] | None = None,
    ableton_roots: Sequence[Path] | None = None,
) -> Path | None:
    environment = os.environ if env is None else env
    explicit = environment.get("ABLETON_MCP_LOG_PATH")
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return path

    roots = _default_ableton_roots(environment) if ableton_roots is None else ableton_roots
    candidates: list[Path] = []
    for root in roots:
        try:
            candidates.extend(root.glob("Live */Preferences/Log.txt"))
        except OSError:
            continue
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        return None
    try:
        return max(existing, key=lambda path: path.stat().st_mtime)
    except OSError:
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remote_script_status(source: Path, destination_root: Path) -> dict[str, Any]:
    target = destination_root / REMOTE_SCRIPT_NAME
    mismatched: list[str] = []
    missing: list[str] = []
    for filename in REMOTE_SCRIPT_FILES:
        source_file = source / filename
        if not source_file.is_file():
            raise FileNotFoundError(f"Bundled Remote Script file is missing: {source_file}")
        target_file = target / filename
        if not target_file.is_file():
            missing.append(filename)
        elif _sha256(source_file) != _sha256(target_file):
            mismatched.append(filename)
    if missing:
        status = "missing"
    elif mismatched:
        status = "stale"
    else:
        status = "current"
    return {
        "status": status,
        "source": str(source),
        "target": str(target),
        "missing_files": missing,
        "mismatched_files": mismatched,
    }


def install_remote_script(source: Path, destination_root: Path) -> dict[str, Any]:
    for filename in REMOTE_SCRIPT_FILES:
        source_file = source / filename
        if not source_file.is_file():
            raise FileNotFoundError(f"Bundled Remote Script file is missing: {source_file}")
    target = destination_root / REMOTE_SCRIPT_NAME
    target.mkdir(parents=True, exist_ok=True)
    for filename in REMOTE_SCRIPT_FILES:
        shutil.copy2(source / filename, target / filename)
    cache = target / "__pycache__"
    if cache.is_dir():
        shutil.rmtree(cache)
    result = remote_script_status(source, destination_root)
    if result["status"] != "current":
        raise OSError(f"Remote Script verification failed: {result}")
    result["status"] = "installed"
    return result
