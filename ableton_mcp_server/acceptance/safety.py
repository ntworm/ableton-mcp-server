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
