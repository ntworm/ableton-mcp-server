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
    package = Path(__file__).resolve().parent if package_dir is None else package_dir
    checkout_source = package.parent / REMOTE_SCRIPT_NAME
    if checkout_source.is_dir():
        return checkout_source
    wheel_source = package / "_remote_script"
    if wheel_source.is_dir():
        return wheel_source
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
) -> dict[str, Any]:
    info = detect_runtime() if runtime is None else runtime
    base: dict[str, Any] = {
        "endpoint": {"host": client.host, "port": client.port},
        "runtime": asdict(info),
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
