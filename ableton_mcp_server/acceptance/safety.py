"""Acceptance safety primitives.

Defines the protocol the runner uses to talk to the bridge, plus the
exception raised when the disposable Set cannot be proven safe before
any mutation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class AcceptanceClient(Protocol):
    """Minimal surface the runner needs from the Live bridge client."""

    host: str
    port: int

    def call(
        self,
        command_type: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any: ...

    async def call_ws(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 2.0,
    ) -> Any: ...


class AcceptanceSafetyError(RuntimeError):
    """Raised before mutation when the disposable Set cannot be proven safe."""


def require_fresh_set(metadata: Mapping[str, Any]) -> None:
    """Refuse a Set that may hold edits made since it was opened.

    Live 12.4.25b1 has no ``Song.is_dirty`` (``docs/KNOWN_BUGS.md`` Category
    S) and ``get_project_metadata`` answers ``null``, so the flag cannot prove
    a clean Set.
    An empty undo history (``can_undo is False``) can: nothing undoable
    happened since the Set was opened, so closing it without saving leaves the
    file on disk as it was. Anything else, unknown included, is refused before
    the first mutation.
    """
    if metadata.get("is_dirty") is True:
        raise AcceptanceSafetyError(
            "Loaded project reports unsaved changes (is_dirty=True); no mutations were sent."
        )
    can_undo = metadata.get("can_undo")
    if can_undo is not False:
        raise AcceptanceSafetyError(
            f"Loaded project has undo history (can_undo={can_undo!r}); acceptance needs a "
            "Set opened from disk with no edits since. Reopen the saved Set without "
            "saving and retry; no mutations were sent."
        )


def resolve_track_id(client: AcceptanceClient, index: int) -> str:
    """Return the Live-stable track id for the given index.

    The Remote Script surface returns session-local index locators, not
    stable cross-process identities. The runner still needs a stable
    handle for tools like ``list_device_params`` that demand ``track_id``.
    """
    tracks = client.call("get_track_list")
    match = next((t for t in tracks if int(t.get("index", -1)) == index), None)
    if match is None:
        raise AcceptanceSafetyError(f"track {index} not present")
    return str(match.get("id", f"track:{index}"))


# Back-compat alias for the legacy module surface.
_resolve_track_id = resolve_track_id
