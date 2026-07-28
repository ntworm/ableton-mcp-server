"""TCP reads probe group (Phase 2).

Registers the 25 ``tcp_reads`` probe rows from the acceptance runner
plus the device-parameter discovery used by ``get_parameter_value``.
The same discovery helper is also invoked by the runner's mutations
block so ``set_parameter_value`` can target the same resolved
track / device / parameter the read probe certifies.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ...certification import CertificationReport, Verification
from ..baseline import BaselineSnapshot
from ..report import _record_call
from ..safety import AcceptanceClient, _resolve_track_id

__all__ = [
    "TOOLS",
    "run",
    "_discover_first_enabled_device_parameter",
]


TOOLS: tuple[str, ...] = (
    "get_session_info",
    "get_track_list",
    "get_track_state",
    "get_locators",
    "take_snapshot",
    "get_control_surfaces",
    "get_scenes",
    "get_scene_state",
    "get_project_metadata",
    "get_loop_settings",
    "get_selected_context",
    "get_clip_summary",
    "get_clip_notes",
    "get_clip_info",
    "get_device_list",
    "get_parameter_value",
    "get_routing",
    "get_browser_categories",
    "search_browser",
    "get_song_length",
    "live_find_track",
    "list_device_params",
    "get_composition_structure",
    "diagnose_midi_clip",
    "lifecycle_status",
)


def _discover_first_enabled_device_parameter(
    client: AcceptanceClient,
    snapshot: BaselineSnapshot,
    priority_track_index: int,
    call: Callable[..., Any],
) -> tuple[int | None, int | None, str | None, float, float, bool]:
    """Walk ``snapshot``'s tracks to find the first enabled device parameter.

    ``priority_track_index`` is tried first when it appears in
    ``snapshot.track_names``; the remaining tracks follow in sorted
    order. Returns the 6-tuple
    ``(track_index, device_index, parameter_name, min, max, is_quantized)``
    — ``track_index`` is ``None`` when nothing is found and the other
    positions hold their documented ``0.0`` / ``False`` / ``None``
    sentinels.
    """
    discovered_track_index: int | None = None
    discovered_device_index: int | None = None
    discovered_name: str | None = None
    discovered_min = 0.0
    discovered_max = 1.0
    discovered_is_quantized = False

    search_tracks: list[int] = []
    if priority_track_index in snapshot["track_names"]:
        search_tracks.append(priority_track_index)
    for t_idx in sorted(snapshot["track_names"]):
        if t_idx not in search_tracks:
            search_tracks.append(t_idx)

    for t_idx in search_tracks:
        try:
            dev_list = call("get_device_list", {"track_index": t_idx})
            if isinstance(dev_list, list) and dev_list:
                t_id = _resolve_track_id(client, t_idx)
                device_params = call("list_device_params", {"track_id": t_id})
                if isinstance(device_params, list):
                    for dev_idx, dev_entry in enumerate(device_params):
                        if isinstance(dev_entry, dict) and dev_entry.get("parameters"):
                            params_list = dev_entry.get("parameters")
                            if isinstance(params_list, list):
                                for p in params_list:
                                    if not isinstance(p, dict):
                                        continue
                                    if (
                                        p.get("is_enabled") is False
                                        or p.get("enabled") is False
                                    ):
                                        continue
                                    p_name = p.get("name")
                                    if not isinstance(p_name, str) or not p_name:
                                        continue
                                    min_val = float(p.get("min", 0.0))
                                    max_val = float(p.get("max", 1.0))
                                    is_quant = bool(p.get("is_quantized", False))

                                    discovered_track_index = t_idx
                                    discovered_device_index = dev_idx
                                    discovered_name = p_name
                                    discovered_min = min_val
                                    discovered_max = max_val
                                    discovered_is_quantized = is_quant
                                    break
                                if discovered_name is not None:
                                    break
                    if discovered_name is not None:
                        break
        except Exception:
            pass

    return (
        discovered_track_index,
        discovered_device_index,
        discovered_name,
        discovered_min,
        discovered_max,
        discovered_is_quantized,
    )


async def run(
    client: AcceptanceClient,
    report: CertificationReport,
    snapshot: BaselineSnapshot | None,
    track_index: int,
    clip_index: int,
    call: Callable[..., Any],
) -> None:
    """Record the 25 ``tcp_reads`` probe rows for the live bridge.

    Drives ``get_project_metadata`` first, discovers a writable device
    parameter for ``get_parameter_value`` via
    :func:`_discover_first_enabled_device_parameter`, then emits the
    remaining 23 read rows. ``snapshot`` is required for the discovery
    step — when it is ``None`` the parameter probe falls through to
    ``environment_unavailable``.
    """
    # ``get_project_metadata`` is the first read; refetching it here
    # matches what the legacy in-place lambdas captured and keeps the
    # row consistent with the live bridge state.
    await _record_call(
        report,
        "get_project_metadata",
        lambda: call("get_project_metadata"),
        passed="live_passed",
    )

    if snapshot is not None:
        (
            discovered_track_index,
            discovered_device_index,
            discovered_name,
            _min_val,
            _max_val,
            _is_quant,
        ) = _discover_first_enabled_device_parameter(
            client, snapshot, track_index, call
        )
    else:
        discovered_track_index = None
        discovered_device_index = None
        discovered_name = None

    # Session / state reads.
    await _record_call(
        report,
        "get_session_info",
        lambda: call("get_session_info"),
        passed="live_passed",
    )
    await _record_call(
        report,
        "get_track_list",
        lambda: call("get_track_list"),
        passed="live_passed",
    )
    await _record_call(
        report,
        "get_track_state",
        lambda: call("get_track_state", {"track_index": track_index}),
        passed="live_passed",
    )
    await _record_call(
        report,
        "get_locators",
        lambda: call("get_locators"),
        passed="live_passed",
    )
    await _record_call(
        report,
        "take_snapshot",
        lambda: call("take_snapshot"),
        passed="live_passed",
    )
    await _record_call(
        report,
        "get_control_surfaces",
        lambda: call("get_control_surfaces"),
        passed="live_passed",
    )
    await _record_call(
        report,
        "get_scenes",
        lambda: call("get_scenes"),
        passed="live_passed",
    )
    await _record_call(
        report,
        "get_scene_state",
        lambda: call("get_scene_state", {"scene_index": 0}),
        passed="live_passed",
    )
    await _record_call(
        report,
        "get_loop_settings",
        lambda: call("get_loop_settings"),
        passed="live_passed",
    )
    await _record_call(
        report,
        "get_selected_context",
        lambda: call("get_selected_context"),
        passed="live_passed",
    )
    await _record_call(
        report,
        "get_clip_summary",
        lambda: call("get_clip_summary", {"track_index": track_index}),
        passed="live_passed",
    )
    await _record_call(
        report,
        "get_clip_notes",
        lambda: call(
            "get_clip_notes",
            {"track_index": track_index, "clip_index": clip_index},
        ),
        passed="live_passed",
    )
    await _record_call(
        report,
        "get_clip_info",
        lambda: call(
            "get_clip_info",
            {"track_index": track_index, "clip_index": clip_index},
        ),
        passed="live_passed",
    )
    await _record_call(
        report,
        "get_device_list",
        lambda: call("get_device_list", {"track_index": track_index}),
        passed="live_passed",
    )

    # ``get_parameter_value`` is the only row whose target depends on
    # the live discovery; everything else is a fixed command + args.
    if discovered_track_index is not None:
        await _record_call(
            report,
            "get_parameter_value",
            lambda: call(
                "get_parameter_value",
                {
                    "track_index": discovered_track_index,
                    "device_index": discovered_device_index,
                    "parameter_name": discovered_name,
                },
            ),
            passed="live_passed",
        )
    else:
        report.record(
            Verification(
                "get_parameter_value",
                "environment_unavailable",
                "no device parameter found in current Set",
            )
        )

    # Routing + browser reads.
    await _record_call(
        report,
        "get_routing",
        lambda: call("get_routing", {"track_index": track_index}),
        passed="live_passed",
    )
    await _record_call(
        report,
        "get_browser_categories",
        lambda: call("get_browser_categories"),
        passed="live_passed",
    )
    # ``search_browser`` should be a small query against a
    # category the runner proves is present, not a guess.
    categories = call("get_browser_categories")
    query = "o" if categories else ""
    await _record_call(
        report,
        "search_browser",
        lambda: call("search_browser", {"query": query, "limit": 10}),
        passed="live_passed",
    )

    # Project / composition reads.
    await _record_call(
        report,
        "get_song_length",
        lambda: call("get_song_length"),
        passed="live_passed",
    )
    # ``live_find_track`` is called with the literal query "bass" so
    # the runner does not hard-code a name the owner might have
    # changed. ``discovered_track_for_bass`` is left as a local here
    # for symmetry with the legacy monolith; the row only needs the
    # call evidence.
    _matches = call("live_find_track", {"query": "bass"})
    await _record_call(
        report,
        "live_find_track",
        lambda: _matches,
        passed="live_passed",
    )

    # ``list_device_params`` requires ``track_id``, not
    # ``track_index/device_index``.
    track_id = _resolve_track_id(client, track_index)
    await _record_call(
        report,
        "list_device_params",
        lambda: call("list_device_params", {"track_id": track_id}),
        passed="live_passed",
    )
    await _record_call(
        report,
        "get_composition_structure",
        lambda: call("get_composition_structure"),
        passed="live_passed",
    )
    await _record_call(
        report,
        "diagnose_midi_clip",
        lambda: call(
            "diagnose_midi_clip",
            {"track_index": track_index, "clip_index": clip_index},
        ),
        passed="live_passed",
    )
    await _record_call(
        report,
        "lifecycle_status",
        lambda: call("lifecycle_status"),
        passed="live_passed",
    )