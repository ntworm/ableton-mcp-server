"""Offline, deterministic drum-groove corpus and index primitives."""

from __future__ import annotations


class GrooveError(Exception):
    """Base class for bounded groove-index failures."""


class GrooveMidiError(GrooveError):
    """The input SMF is malformed or exceeds parser limits."""


class GrooveBlobRejected(GrooveError):
    """A compressed payload failed codec, size, or integrity validation."""


class GrooveBuildError(GrooveError):
    """A build input or generated seed failed a publication gate."""


class GrooveIndexError(GrooveError):
    """A portable index cannot be opened or queried safely."""


class GrooveIndexReadOnlyError(GrooveIndexError):
    """An attempted mutation of a read-only index was rejected."""


class GrooveIndexInvalid(GrooveIndexError):
    """An index or manifest failed its integrity checks."""


class GrooveSchemaUnsupported(GrooveIndexError):
    """The index schema is newer or otherwise unsupported."""


__all__ = [
    "GrooveBlobRejected",
    "GrooveBuildError",
    "GrooveError",
    "GrooveIndexError",
    "GrooveIndexInvalid",
    "GrooveIndexReadOnlyError",
    "GrooveMidiError",
    "GrooveSchemaUnsupported",
]
