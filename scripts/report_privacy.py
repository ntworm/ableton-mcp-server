"""Refuse a public report that carries a local path or a user folder."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_DRIVE = re.compile(r"\b[A-Za-z]:[\\/]")
_USERS = re.compile(r"(?i)[\\/]users[\\/]")


def personal_path_hits(value: Any, home: Path | None = None) -> list[str]:
    """Every string inside ``value`` that names a drive, a user folder or the home folder."""
    home_text = str(home or Path.home()).replace("\\", "/").lower()
    hits: list[str] = []
    for text in _strings(value):
        lowered = text.replace("\\", "/").lower()
        if _DRIVE.search(text) or _USERS.search(text) or home_text in lowered:
            hits.append(text)
    return hits


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in _strings(k) + _strings(v)]
    if isinstance(value, (list, tuple)):
        return [s for item in value for s in _strings(item)]
    return []


def require_public(value: Any) -> None:
    hits = personal_path_hits(value)
    if hits:
        raise SystemExit(f"refusing to write a report with local paths: {hits[:3]}")
