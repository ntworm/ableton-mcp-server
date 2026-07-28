"""Composed probe group.

``get_bridge_status`` + ``get_session_overview`` are composed tools —
they are not 1:1 bridge commands. ``get_bridge_status`` wraps
``ableton_mcp_server.diagnostics.bridge_status``; ``get_session_overview``
fans out into three TCP reads (``get_session_info``, ``get_track_list``,
``get_scenes``). The runner must perform the composition explicitly so
the certification row reflects the wrapper path, not the underlying
primitive.
"""

from __future__ import annotations

from typing import Any

from ...certification import CertificationReport
from ...diagnostics import bridge_status as _bridge_status_fn
from ..report import _record_call
from ..safety import AcceptanceClient

TOOLS: tuple[str, ...] = ("get_bridge_status", "get_session_overview")

__all__ = ["TOOLS", "run"]


async def run(report: CertificationReport, *, client: AcceptanceClient) -> None:
    """Record one ``live_passed`` row for each composed tool."""

    def bridge_status_probe() -> dict[str, Any]:
        # ``get_bridge_status`` is a composed tool that wraps
        # ``diagnostics.bridge_status(client, tool_count=...)``. The
        # runner must call the wrapper, not the underlying
        # ``get_session_info`` TCP command.
        return _bridge_status_fn(client, tool_count=65)

    def session_overview_probe() -> dict[str, Any]:
        # ``get_session_overview`` is composed from three TCP reads.
        # The runner must do the same composition explicitly; the
        # bridge does not expose a single ``get_session_overview``
        # command.
        return {
            "session": client.call("get_session_info", {}),
            "tracks": client.call("get_track_list", {}),
            "scenes": client.call("get_scenes", {}),
        }

    await _record_call(
        report, "get_bridge_status", bridge_status_probe, passed="live_passed"
    )
    await _record_call(
        report, "get_session_overview", session_overview_probe, passed="live_passed"
    )