"""Resolve the private groove seed and the derived-artifact folder on this host.

The per-user data root is resolved in this order:
1. ``LOCALAPPDATA`` when the environment defines it.
2. macOS: ``~/Library/Application Support``.
3. Every other platform: ``~/AppData/Local``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import GrooveIndexInvalid

ENV_GROOVE_SEED_BUNDLE = "ABLETON_GROOVE_SEED_BUNDLE"
ENV_GROOVE_ARTIFACT_STORE = "ABLETON_GROOVE_ARTIFACT_STORE"
_APP_DIR = "AbletonMCPServer"


def _local_data_root(override_env: str) -> Path:
    """Return the per-user data root of this host.

    The environment variable in override_env names the explicit override that
    replaces this root when neither LOCALAPPDATA nor a home directory exists.
    """
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata)
    try:
        home = Path.home()
    except RuntimeError as error:
        raise GrooveIndexInvalid(
            "No per-user data directory: LOCALAPPDATA and the home directory are "
            f"unset. Set {override_env}."
        ) from error
    if sys.platform == "darwin":
        return home / "Library" / "Application Support"
    return home / "AppData" / "Local"


def default_groove_seed_bundle() -> Path:
    """Calculate the default private groove seed bundle path at call time.

    Resolves to LOCALAPPDATA/AbletonMCPServer/groove-seed, then to the macOS
    ~/Library/Application Support folder, and finally to ~/AppData/Local.
    """
    root = _local_data_root(ENV_GROOVE_SEED_BUNDLE)
    return (root / _APP_DIR / "groove-seed").expanduser().resolve(strict=False)


def resolve_groove_seed_bundle() -> Path:
    """Resolve the private groove seed bundle path.

    Precedence:
    1. ABLETON_GROOVE_SEED_BUNDLE environment variable if configured.
    2. The per-user data root: LOCALAPPDATA, macOS, or ~/AppData/Local.
    """
    configured = os.environ.get(ENV_GROOVE_SEED_BUNDLE)
    if configured:
        return Path(configured).expanduser().resolve(strict=False)
    return default_groove_seed_bundle()


def groove_artifact_root() -> Path:
    """Resolve the local folder that stores the derived groove artifacts."""
    configured = os.environ.get(ENV_GROOVE_ARTIFACT_STORE)
    if configured:
        return Path(configured).expanduser().resolve()
    root = _local_data_root(ENV_GROOVE_ARTIFACT_STORE)
    return (root / _APP_DIR / "groove-artifacts-v1").expanduser().resolve()


def seed_unavailable_message(bundle: Path, cause: Exception) -> str:
    """Explain why the groove seed at bundle cannot be opened."""
    if not (bundle / "manifest.json").is_file():
        return (
            f"No groove corpus configured: no seed bundle at {bundle}. "
            f"Set {ENV_GROOVE_SEED_BUNDLE}, or place a licensed seed there."
        )
    return (
        f"Invalid groove seed at {bundle}: {cause}. "
        f"Set {ENV_GROOVE_SEED_BUNDLE} to a valid seed bundle."
    )


__all__ = [
    "ENV_GROOVE_ARTIFACT_STORE",
    "ENV_GROOVE_SEED_BUNDLE",
    "default_groove_seed_bundle",
    "groove_artifact_root",
    "resolve_groove_seed_bundle",
    "seed_unavailable_message",
]
