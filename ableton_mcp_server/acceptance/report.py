"""Verification recording + release-ready policy.

Thin layer over ``ableton_mcp_server.certification`` so the runner does
not import certification internals directly.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from ..certification import CertificationReport, Verification  # re-export

__all__ = [
    "CertificationReport",
    "Verification",
    "_is_full_baseline",
    "_record_call",
    "_record_unavailable",
    "_release_ready",
    "build_baseline_report",
    "is_full_baseline",
    "record_call",
    "record_unavailable",
    "release_ready",
]


async def _record_call(
    report: CertificationReport,
    tool: str,
    action: Callable[[], Any | Awaitable[Any]],
    *,
    passed: str = "live_passed",
) -> Any:
    """Invoke ``action`` and record one verification row.

    The caller is responsible for performing any readback inside ``action``
    and raising if the mutation didn't take effect. This function only
    records the result of the whole encapsulated action.

    ``BridgeError`` with code ``CAPABILITY_UNAVAILABLE`` is mapped to
    ``host_unavailable``; every other exception becomes ``failed``.
    """
    try:
        value = action()
        if inspect.isawaitable(value):
            value = await value
    except Exception as error:  # noqa: BLE001 — recording layer swallows all
        if getattr(error, "code", None) == "CAPABILITY_UNAVAILABLE":
            report.record(
                Verification(
                    tool,
                    "host_unavailable",
                    f"{getattr(error, 'code', 'CAPABILITY_UNAVAILABLE')}: {error}",
                )
            )
        else:
            report.record(Verification(tool, "failed", f"{type(error).__name__}: {error}"))
        return None
    report.record(Verification(tool, passed, "call and readback completed"))
    return value


def _record_unavailable(report: CertificationReport, tool: str, reason: str) -> None:
    report.record(Verification(tool, "environment_unavailable", reason))


def build_baseline_report(
    profiles: tuple[str, ...] | None = None,
) -> CertificationReport:
    """Return a report covering exactly the catalogued tools.

    The runner calls this and then manually records every selected tool;
    the report itself does not pre-classify unselected tools.
    """
    from .helpers import _baseline_tool_names
    from .probes import _expand_profiles

    selected = profiles or tuple(_expand_profiles(("baseline",)))
    for _profile in _expand_profiles(selected):
        pass
    catalog_names = _baseline_tool_names()
    return CertificationReport(tool_names=catalog_names)


def _is_full_baseline(profiles: tuple[str, ...]) -> bool:
    from .probes import BASELINE_PROBE_GROUPS, _expand_profiles

    expanded = _expand_profiles(profiles)
    return set(expanded) == set(BASELINE_PROBE_GROUPS)


def _release_ready(
    report: CertificationReport, profiles: tuple[str, ...], *, fire_clip: bool
) -> bool:
    """Compute the final ``release_ready`` decision.

    Rules (in order):

    1. Any ``failed`` row blocks promotion.
    2. Partial profiles (not full baseline) are never release-ready.
    3. ``fire_clip`` must have been exercised (the flag toggled on).
    4. ``host_unavailable`` blocks promotion.
    5. ``environment_unavailable`` blocks promotion, except ``build_extension``.
    6. ``manual_required`` blocks promotion, except ``quit_ableton`` and the
       strictly validated manual fallback for ``save_set``.
    7. Otherwise the report is release-ready.
    """
    rows = list(report.recorded.values())
    if any(row.status == "failed" for row in rows):
        return False
    if not _is_full_baseline(profiles):
        return False
    if not fire_clip:
        return False
    if any(row.status == "host_unavailable" for row in rows):
        return False
    if any(
        row.status == "environment_unavailable"
        and row.tool != "build_extension"
        for row in rows
    ):
        return False
    return not any(
        row.status == "manual_required" and row.tool not in ("quit_ableton", "save_set")
        for row in rows
    )


# Public aliases for new code. The legacy underscore-prefixed names above
# stay in place so the monolith body in ``runner.py`` keeps working
# without an import-time rename.
record_call = _record_call
record_unavailable = _record_unavailable
is_full_baseline = _is_full_baseline
release_ready = _release_ready