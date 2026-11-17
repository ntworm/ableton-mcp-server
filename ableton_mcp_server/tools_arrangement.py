"""Device chain, automation, arrangement and group tools."""

from __future__ import annotations

from typing import Any, Literal, cast

from . import models
from . import server as _s
from .server import (
    mcp,
)


@mcp.tool()
def get_device_chains(track_index: int, device_index: int) -> Any:
    """Open one rack and list its chains, their mixer state and inner devices.

    Side effects: none.
    Example: ``get_device_chains(39, 0)`` reveals the four guitar chains and
    the volume of each, which ``get_device_list`` cannot show.
    Edge cases: a device that is not a rack returns ``WRONG_TYPE``.
    """
    return _s._remote(
        "get_device_chains",
        models.GetDeviceChainsRequest(track_index=track_index, device_index=device_index),
    )


@mcp.tool()
def get_midi_chain_report(track_index: int) -> Any:
    """Report the MIDI effects that rewrite what a clip says, before writing one.

    Side effects: none.
    Example: ``get_midi_chain_report(58)`` reveals that a Note Length device
    overrides every written duration and which parameter actually controls it.
    Edge cases: a track with no such device returns ``rewrites_input: false``.
    """
    return _s._remote(
        "get_midi_chain_report",
        models.GetMidiChainReportRequest(track_index=track_index),
    )


@mcp.tool()
def describe_instrument(track_index: int) -> Any:
    """Describe a track's instrument and what the user must still set up.

    Side effects: none.
    Example: ``describe_instrument(60)`` returns the SWAM plugin's automatable
    parameters, or a ``setup_requests`` entry asking the user to press
    Configure when a plugin exposes none.
    Edge cases: a track without an instrument returns ``has_instrument: false``
    with the request to load one.
    """
    return _s._remote(
        "describe_instrument",
        models.DescribeInstrumentRequest(track_index=track_index),
    )


@mcp.tool()
def get_clip_automation(
    track_index: int,
    clip_index: int,
    parameter_name: str,
    device_index: int | None = None,
    resolution: float = 0.25,
) -> Any:
    """Read back one clip envelope as a sampled curve.

    Side effects: none.
    Example: ``get_clip_automation(38, 0, "FILTER", resolution=0.5)`` returns
    the written shape so intent can be compared against reality.
    Edge cases: the LOM exposes no breakpoint list, so the answer is sampled at
    ``resolution`` beats; a parameter name shared by several devices returns
    ``AMBIGUOUS_MATCH`` unless ``device_index`` is given.
    """
    return _s._remote(
        "get_clip_automation",
        models.GetClipAutomationRequest(
            track_index=track_index,
            clip_index=clip_index,
            parameter_name=parameter_name,
            device_index=device_index,
            resolution=resolution,
        ),
        exclude_none=True,
    )


@mcp.tool()
def create_clip_automation_curve(
    track_index: int,
    clip_index: int,
    parameter_name: str,
    control_points: list[dict[str, float]],
    shape: str = "linear",
    resolution: float = 0.25,
    device_index: int | None = None,
) -> Any:
    """Write a smooth envelope from a handful of control points.

    Side effects: replaces one clip envelope in one Live undo step.
    Example: ``create_clip_automation_curve(38, 0, "FILTER",
    [{"time": 0, "value": 12}, {"time": 16, "value": 110}], shape="exp")``
    expands into contiguous steps on the server.
    Edge cases: Live's envelopes are stepped, so the expansion is a dense
    staircase capped at 500 steps; raise ``resolution`` if it overflows.
    """
    return _s._remote(
        "create_clip_automation_curve",
        models.CreateClipAutomationCurveRequest(
            track_index=track_index,
            clip_index=clip_index,
            parameter_name=parameter_name,
            control_points=[models.CurveControlPoint(**point) for point in control_points],
            shape=cast(Literal["linear", "exp", "log", "hold"], shape),
            resolution=resolution,
            device_index=device_index,
        ),
        exclude_none=True,
    )


@mcp.tool()
def add_notes_pattern(
    track_index: int,
    clip_index: int,
    cell: list[dict[str, Any]],
    cell_length: float,
    repeats: int,
    transpose_per_repeat: int = 0,
    velocity_scale_per_repeat: float = 1.0,
) -> Any:
    """Repeat one note cell N times instead of sending every note.

    Side effects: adds notes in one Live undo step; existing notes remain.
    Example: ``add_notes_pattern(59, 0, cell, cell_length=4, repeats=16,
    transpose_per_repeat=0)`` writes a sixteen-bar ostinato from one bar.
    Edge cases: the same validation as ``add_notes_to_clip`` applies to every
    expanded note; pitch and velocity are clamped to the MIDI range.
    """
    return _s._remote(
        "add_notes_pattern",
        models.AddNotesPatternRequest(
            track_index=track_index,
            clip_index=clip_index,
            cell=[models.PatternNote(**note) for note in cell],
            cell_length=cell_length,
            repeats=repeats,
            transpose_per_repeat=transpose_per_repeat,
            velocity_scale_per_repeat=velocity_scale_per_repeat,
        ),
    )


@mcp.tool()
def set_arrangement_clip_properties(
    track_index: int,
    clip_index: int,
    name: str | None = None,
    muted: bool | None = None,
) -> Any:
    """Rename or mute one Arrangement clip, verified by readback.

    Side effects: changes one Arrangement clip in one Live undo step.
    Example: ``set_arrangement_clip_properties(44, 2, muted=False)`` unmutes a
    clip that was silenced by hand.
    Edge cases: ``clip_index`` indexes ``Track.arrangement_clips`` and shifts
    after structural changes; provide at least one of ``name`` or ``muted``.
    """
    return _s._remote(
        "set_arrangement_clip_properties",
        models.SetArrangementClipPropertiesRequest(
            track_index=track_index,
            clip_index=clip_index,
            name=name,
            muted=muted,
        ),
        exclude_none=True,
    )


@mcp.tool()
def move_arrangement_clip(track_index: int, clip_index: int, time: float) -> Any:
    """Move one Arrangement clip to a new beat.

    Side effects: copies the clip to ``time``, then deletes the original once the copy is listed
    (same tick on Live 12.4, so one Ctrl+Z undoes it). The LOM has no ``Clip.start_time`` setter,
    so this is the only way to reposition; a failed copy leaves the original in place.
    Example: ``move_arrangement_clip(3, 2, 96.0)``.
    Edge cases: indices shift after the move — re-read with
    ``get_arrangement_clips``.
    """
    return _s._remote(
        "move_arrangement_clip",
        models.MoveArrangementClipRequest(
            track_index=track_index,
            clip_index=clip_index,
            time=time,
        ),
    )


# ---------------------------------------------------------------------------
# Track hierarchy — validated, never applied
#
# Live's public LOM and the Ableton Extension SDK expose no operation that
# moves, reorders, re-parents, or ungroups an existing track. These tools
# validate the request against the live Set (so a bad index still returns
# INVALID_PARAMS / BAD_INPUT / WRONG_TYPE) and then return a typed
# CAPABILITY_UNAVAILABLE whose ``details`` carry the API evidence. They never
# mutate the Set and never emulate the operation destructively.
# ---------------------------------------------------------------------------


@mcp.tool()
def move_track(track_index: int, destination_index: int) -> Any:
    """Attempt to move one track to another index; Live's API cannot do this.

    Side effects: none — the request is validated and refused.
    Example: ``move_track(3, 0)`` returns ``CAPABILITY_UNAVAILABLE`` with the
    LOM and Extension SDK evidence in ``details``.
    Edge cases: invalid indexes return ``INVALID_PARAMS`` and return/main
    tracks return ``WRONG_TYPE``, so a malformed request stays
    distinguishable from the capability gap. Create tracks at the index you
    want, or reorder by hand in Live.
    """
    return _s._remote(
        "move_track",
        models.MoveTrackRequest(track_index=track_index, destination_index=destination_index),
    )


@mcp.tool()
def reorder_tracks(order: list[int]) -> Any:
    """Attempt to reorder every track at once; Live's API cannot do this.

    Side effects: none — the request is validated and refused.
    Example: ``reorder_tracks([2, 0, 1])`` returns ``CAPABILITY_UNAVAILABLE``
    with the API evidence in ``details``.
    Edge cases: ``order`` must be a permutation of the regular track indexes;
    anything else returns ``BAD_INPUT`` before the capability refusal.
    """
    return _s._remote("reorder_tracks", models.ReorderTracksRequest(order=order))


@mcp.tool()
def move_track_to_group(track_index: int, group_track_index: int) -> Any:
    """Attempt to move a track into a Group Track; Live's API cannot do this.

    Side effects: none — the request is validated and refused.
    Example: ``move_track_to_group(4, 1)`` returns ``CAPABILITY_UNAVAILABLE``
    with the API evidence in ``details``.
    Edge cases: ``Track.group_track`` is read-only in the LOM and the
    Extension SDK exposes only a getter. A non-foldable target returns
    ``WRONG_TYPE``; a self-nesting or cyclic request returns ``BAD_INPUT``.
    """
    return _s._remote(
        "move_track_to_group",
        models.MoveTrackToGroupRequest(
            track_index=track_index,
            group_track_index=group_track_index,
        ),
    )


@mcp.tool()
def ungroup_track(track_index: int) -> Any:
    """Attempt to take a track out of its group; Live's API cannot do this.

    Side effects: none — the request is validated and refused. Nothing is
    deleted under any circumstance.
    Example: ``ungroup_track(2)`` returns ``CAPABILITY_UNAVAILABLE`` with the
    API evidence in ``details``.
    Edge cases: a track that is not grouped returns ``WRONG_TYPE`` before the
    capability refusal.
    """
    return _s._remote("ungroup_track", models.UngroupTrackRequest(track_index=track_index))


@mcp.tool()
def merge_groups(
    source_group_index: int,
    destination_group_index: int,
    delete_empty_source: bool = False,
) -> Any:
    """Attempt to move one group's members into another; Live's API cannot.

    Side effects: none — the request is validated and refused. This bridge
    never deletes a track, so an emptied group would always be left in place.
    Example: ``merge_groups(5, 1)`` returns ``CAPABILITY_UNAVAILABLE`` with
    the API evidence in ``details``.
    Edge cases: both indexes must be Group Tracks (``WRONG_TYPE`` otherwise),
    must differ, and must not nest into each other (``BAD_INPUT``).
    ``delete_empty_source=True`` is rejected with ``BAD_INPUT``.
    """
    return _s._remote(
        "merge_groups",
        models.MergeGroupsRequest(
            source_group_index=source_group_index,
            destination_group_index=destination_group_index,
            delete_empty_source=delete_empty_source,
        ),
    )
