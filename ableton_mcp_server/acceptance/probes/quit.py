"""Quit probe group.

``quit_ableton`` is a destructive operation: invoking it would close
the host and prevent every subsequent probe from running. The runner
never invokes the bridge here — it records the row as
``manual_required`` so the certification report never claims
``live_passed`` for an operation that was not executed. Promotion to
``manual_passed`` requires an out-of-band owner confirmation that a
real shutdown handshake completed.

The slice extracted here covers the simple-quit branch (``"quit"`` in
profiles but no ``tcp_reads`` / ``mutations`` / ``websocket_reads``).
The near-duplicate inside the mutations branch stays in ``runner.py``
because it shares state with the mutations safety guard.
"""

from __future__ import annotations

from ...certification import CertificationReport, Verification

TOOLS: tuple[str, ...] = ("quit_ableton",)

# Kept local so this module is self-contained and the wording stays
# identical to the runner's pre-refactor branch. ``ableton_mcp_server/
# acceptance/probes/__init__.py`` also exports the same string under
# the same name for backwards-compatible imports.
QUIT_ABLETON_MANUAL_REASON = (
    "quit_ableton requires out-of-band owner confirmation; "
    "automated probe never invokes a destructive shutdown"
)

__all__ = ["QUIT_ABLETON_MANUAL_REASON", "TOOLS", "run"]


async def run(report: CertificationReport) -> None:
    """Record the ``quit_ableton`` row as ``manual_required``."""
    report.record(
        Verification(
            "quit_ableton",
            "manual_required",
            QUIT_ABLETON_MANUAL_REASON,
        )
    )