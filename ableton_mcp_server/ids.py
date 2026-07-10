from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

PathKind = Literal["track", "device", "parameter", "clip_slot", "session_clip", "arrangement_clip"]

_PATH_RE = re.compile(
    r"^track:(?P<track>\d+)"
    r"(?:/device:(?P<device>\d+)(?:/param:(?P<param>\d+))?"
    r"|/clipslot:(?P<clipslot>\d+)(?P<session_clip>/clip)?"
    r"|/clip:(?P<arrangement_clip>\d+))?$"
)


@dataclass(frozen=True)
class ParsedPath:
    raw: str
    kind: PathKind
    track_index: int
    device_index: int | None = None
    parameter_index: int | None = None
    clip_index: int | None = None

    def __str__(self) -> str:
        return self.raw


def parse_path(path: str) -> ParsedPath:
    match = _PATH_RE.fullmatch(path)
    if match is None:
        raise ValueError(f"Invalid path-id: {path!r}")

    groups = match.groupdict()
    track_index = int(groups["track"])
    if groups["param"] is not None:
        return ParsedPath(
            path,
            "parameter",
            track_index,
            device_index=int(groups["device"]),
            parameter_index=int(groups["param"]),
        )
    if groups["device"] is not None:
        return ParsedPath(path, "device", track_index, device_index=int(groups["device"]))
    if groups["clipslot"] is not None:
        kind: PathKind = "session_clip" if groups["session_clip"] else "clip_slot"
        return ParsedPath(path, kind, track_index, clip_index=int(groups["clipslot"]))
    if groups["arrangement_clip"] is not None:
        return ParsedPath(
            path,
            "arrangement_clip",
            track_index,
            clip_index=int(groups["arrangement_clip"]),
        )
    return ParsedPath(path, "track", track_index)


def format_path(*segments: str) -> str:
    path = "/".join(segments)
    parse_path(path)
    return path
