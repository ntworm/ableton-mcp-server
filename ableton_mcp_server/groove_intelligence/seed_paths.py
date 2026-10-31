from __future__ import annotations

import os
from pathlib import Path

ENV_GROOVE_SEED_BUNDLE = "ABLETON_GROOVE_SEED_BUNDLE"


def default_groove_seed_bundle() -> Path:
    """Calculate the default private groove seed bundle path at call time.

    Resolves to LOCALAPPDATA/AbletonMCPServer/groove-seed, falling back
    to Path.home()/AppData/Local/AbletonMCPServer/groove-seed.
    """
    local_appdata = os.environ.get("LOCALAPPDATA")
    base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
    return (base / "AbletonMCPServer" / "groove-seed").expanduser().resolve(strict=False)


def resolve_groove_seed_bundle() -> Path:
    """Resolve the private groove seed bundle path.

    Precedence:
    1. ABLETON_GROOVE_SEED_BUNDLE environment variable if configured.
    2. Dynamic LOCALAPPDATA/AbletonMCPServer/groove-seed (or ~/AppData/Local fallback).
    """
    configured = os.environ.get(ENV_GROOVE_SEED_BUNDLE)
    if configured:
        return Path(configured).expanduser().resolve(strict=False)
    return default_groove_seed_bundle()


DEFAULT_GROOVE_SEED_BUNDLE = default_groove_seed_bundle()

__all__ = [
    "DEFAULT_GROOVE_SEED_BUNDLE",
    "ENV_GROOVE_SEED_BUNDLE",
    "default_groove_seed_bundle",
    "resolve_groove_seed_bundle",
]
