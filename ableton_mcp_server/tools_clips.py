"""Transport, cue point, clip and arrangement clip tools."""

from __future__ import annotations

from typing import Any, Literal

from . import models
from . import server as _s
from .server import (
    mcp,
)


@mcp.tool()
def create_cue_point(name: str, time: float) -> Any:
    """Create or idempotently rename a cue point at a beat time.

    Side effects: mutates the Set in one undo step and temporarily moves the playhead.
    Example: ``create_cue_point("Verse", 8.0)`` creates a locator.
    Edge cases: verified movement failure raises ``PLAYHEAD_NOT_MOVED`` before toggling.
    Arrangement-grid snap is reversed and raises ``CUE_SNAPPED_TO_GRID``.
    """
    return _s._remote("create_cue_point", models.CreateCuePointRequest(name=name, time=time))


@mcp.tool()
def bulk_create_cue_points(items: list[dict[str, Any]]) -> Any:
    """Create or rename multiple cue points as one command.

    Side effects: mutates all successful items inside one undo step.
    Example: ``bulk_create_cue_points([{"name": "A", "time": 0}])``.
    Edge cases: per-item errors are aggregated instead of aborting later items;
    off-grid snaps are reversed and reported as ``CUE_SNAPPED_TO_GRID``.
    """
    request = models.BulkCuePointsRequest.model_validate({"items": items})
    return _s._remote("bulk_create_cue_points", request)


@mcp.tool()
def delete_cue_point(time: float) -> Any:
    """Delete a cue point by verified move-and-toggle.

    Side effects: mutates the Set in one undo step and temporarily moves the playhead.
    Example: ``delete_cue_point(8.0)`` deletes a cue near beat eight.
    Edge cases: no cue at the time returns ``deleted: false``; an Arrangement-grid
    snap is reversed and raises ``CUE_SNAPPED_TO_GRID``.
    """
    return _s._remote("delete_cue_point", models.DeleteCuePointRequest(time=time))


@mcp.tool()
def set_current_song_time(time: float) -> Any:
    """Move the Arrangement playhead with set/read/retry verification.

    Side effects: writes transport state in one undo step.
    Example: ``set_current_song_time(32.0)`` moves to beat thirty-two.
    Edge cases: a stuck setter raises ``PLAYHEAD_NOT_MOVED`` after three attempts.
    """
    return _s._remote("set_current_song_time", models.SetCurrentSongTimeRequest(time=time))


@mcp.tool()
def set_tempo(tempo: float, dry_run: bool = False) -> Any:
    """Set the Live Set tempo in BPM.

    Side effects: writes tempo in one undo step.
    Example: ``set_tempo(128.0)`` sets 128 BPM.
    Edge cases: values outside 20..999 or non-finite values are rejected. With
    ``dry_run=True``, the change is validated but not committed.
    """
    return _s._remote("set_tempo", models.SetTempoRequest(tempo=tempo, dry_run=dry_run))


@mcp.tool()
def start_playback() -> Any:
    """Start Live's transport.

    Side effects: starts playback in one undo-scoped command.
    Example: ``start_playback()`` returns the observed playing state.
    Edge cases: Live can reject the call while shutting down.
    """
    return _s._remote("start_playback", models.StartPlaybackRequest())


@mcp.tool()
def stop_playback() -> Any:
    """Stop Live's transport.

    Side effects: stops playback in one undo-scoped command.
    Example: ``stop_playback()`` returns the observed playing state.
    Edge cases: Live can reject the call while shutting down.
    """
    return _s._remote("stop_playback", models.StopPlaybackRequest())


@mcp.tool()
def set_loop(enabled: bool) -> Any:
    """Enable or disable the Arrangement loop.

    Side effects: writes loop state in one undo step.
    Example: ``set_loop(True)`` enables looping.
    Edge cases: only a boolean value is accepted.
    """
    return _s._remote("set_loop", models.SetLoopRequest(enabled=enabled))


@mcp.tool()
def set_loop_start(start_beat: float) -> Any:
    """Set Arrangement loop start with read-back verification.

    Side effects: writes loop geometry in one undo step.
    Example: ``set_loop_start(16.0)`` starts the loop at beat sixteen.
    Edge cases: a stuck setter raises ``PLAYHEAD_NOT_MOVED``.
    """
    return _s._remote("set_loop_start", models.SetLoopStartRequest(start_beat=start_beat))


@mcp.tool()
def set_loop_length(length_beats: float) -> Any:
    """Set Arrangement loop length with read-back verification.

    Side effects: writes loop geometry in one undo step.
    Example: ``set_loop_length(8.0)`` makes an eight-beat loop.
    Edge cases: length must be positive and a stuck setter raises an error.
    """
    return _s._remote(
        "set_loop_length",
        models.SetLoopLengthRequest(length_beats=length_beats),
    )


@mcp.tool()
def run_batch(commands: list[dict[str, Any]]) -> Any:
    """Run allowed mutations in order; undo them one Ctrl+Z at a time and re-read the Set.

    Side effects: commands that finish in one tick (Arrangement edits, create_clip, notes) share a
    Ctrl+Z; one read back a tick later (tempo, loop, colours, cue points) ends it. No rollback.
    Example: ``run_batch([{"type": "set_tempo", "params": {"tempo": 128}}])``.
    Edge cases: aborts at the first error, keeping the prefix applied; nested batches are rejected.
    """
    request = models.RunBatchRequest.model_validate({"commands": commands})
    return _s._remote("run_batch", request, exclude_defaults=True)


@mcp.tool()
def add_notes_to_clip(track_index: int, clip_index: int, notes: list[dict[str, Any]]) -> Any:
    """Add validated MIDI notes to an existing Session clip.

    Side effects: adds notes in one undo step; existing notes remain.
    Example: ``add_notes_to_clip(0, 0, [{"pitch": 60, ...}])``.
    Edge cases: audio clips, empty slots, and invalid MIDI ranges are rejected.
    """
    request = models.AddNotesToClipRequest.model_validate(
        {"track_index": track_index, "clip_index": clip_index, "notes": notes}
    )
    return _s._remote("add_notes_to_clip", request, exclude_none=True)


@mcp.tool()
def fire_clip(track_index: int, clip_index: int) -> Any:
    """Fire an existing Session clip through its clip slot.

    Side effects: launches playback in one undo-scoped command.
    Example: ``fire_clip(0, 1)`` launches slot one on track zero.
    Edge cases: empty or invalid slots are rejected.
    """
    return _s._remote(
        "fire_clip",
        models.FireClipRequest(track_index=track_index, clip_index=clip_index),
    )


@mcp.tool()
def create_clip(
    track_index: int, clip_index: int, length_beats: float, dry_run: bool = False
) -> Any:
    """Create an empty MIDI clip in an empty Session slot.

    Side effects: creates a clip in one undo step.
    Example: ``create_clip(0, 1, 4.0)`` creates a four-beat clip.
    Edge cases: only empty slots on MIDI tracks accept this operation. With
    ``dry_run=True``, the change is validated but not committed.
    """
    return _s._remote(
        "create_clip",
        models.CreateClipRequest(
            track_index=track_index,
            clip_index=clip_index,
            length_beats=length_beats,
            dry_run=dry_run,
        ),
    )


@mcp.tool()
def delete_clip(track_index: int, clip_index: int) -> Any:
    """Delete one occupied Session clip slot.

    Side effects: deletes a clip in one Live undo step.
    Example: ``delete_clip(0, 1)`` removes the clip in slot one.
    Edge cases: empty slots return ``BAD_INPUT``.
    """
    return _s._remote(
        "delete_clip",
        models.DeleteClipRequest(track_index=track_index, clip_index=clip_index),
    )


@mcp.tool()
def clear_clip_notes(track_index: int, clip_index: int) -> Any:
    """Remove every MIDI note from one Session clip and report the observed delta.

    Side effects: clears notes in one Live undo step.
    Example: ``clear_clip_notes(0, 1)`` empties a MIDI clip without deleting it.
    Edge cases: empty or audio clips return structured errors.
    """
    return _s._remote(
        "clear_clip_notes",
        models.ClearClipNotesRequest(track_index=track_index, clip_index=clip_index),
    )


@mcp.tool()
def fire_scene(scene_index: int) -> Any:
    """Fire one Session scene using Live's current launch quantization.

    Side effects: triggers all playable clips in the selected scene.
    Example: ``fire_scene(0)`` launches the first scene.
    Edge cases: an out-of-range index returns ``INVALID_PARAMS``.
    """
    return _s._remote("fire_scene", models.FireSceneRequest(scene_index=scene_index))


@mcp.tool()
def set_track_property(
    track_index: int,
    property: Literal["mute", "solo", "arm"],
    value: bool,
) -> Any:
    """Set and verify one boolean track property.

    Side effects: changes mute, solo, or arm in one Live undo step.
    Example: ``set_track_property(0, "mute", True)`` mutes the first track.
    Edge cases: arm is rejected for return and master tracks.
    """
    return _s._remote(
        "set_track_property",
        models.SetTrackPropertyRequest(track_index=track_index, property=property, value=value),
    )


@mcp.tool()
def set_track_color(
    track_index: int,
    color_index: int | None = None,
    color: int | None = None,
) -> Any:
    """Set and verify one track colour, by palette index or packed RGB.

    Side effects: writes ``Track.color_index`` or ``Track.color`` in one Live
    undo step and reads the value back; clips are never recoloured.
    Example: ``set_track_color(0, color_index=12)`` or
    ``set_track_color(0, color=0x336699)``.
    Edge cases: exactly one of ``color_index`` (0..69) and ``color``
    (0x000000..0xFFFFFF) is required; a track that does not expose the
    property returns ``WRONG_TYPE`` and a rejected write returns
    ``VERIFICATION_FAILED`` — the write is never retried.
    """
    return _s._remote(
        "set_track_color",
        models.SetTrackColorRequest(
            track_index=track_index,
            color_index=color_index,
            color=color,
        ),
        exclude_none=True,
    )


@mcp.tool()
def set_clip_color(
    track_index: int,
    clip_index: int,
    scope: Literal["session", "arrangement"] = "session",
    color_index: int | None = None,
    color: int | None = None,
) -> Any:
    """Set and verify one clip colour, by palette index or packed RGB.

    Side effects: writes ``Clip.color_index`` or ``Clip.color`` in one Live
    undo step and reads the value back. Only the addressed clip changes.
    Example: ``set_clip_color(0, 1, color_index=12)`` colours a Session clip;
    ``set_clip_color(0, 0, scope="arrangement", color=0x336699)`` colours the
    first Arrangement clip on that track.
    Edge cases: exactly one of ``color_index`` (0..69) and ``color``
    (0x000000..0xFFFFFF) is required. An empty Session slot returns
    ``BAD_INPUT``. Arrangement scope needs ``Track.arrangement_clips`` (Live
    11+); a host without it returns ``CAPABILITY_UNAVAILABLE`` — run
    ``diagnose_clip_targets`` to see what is reachable. The write is issued
    once and never retried.
    """
    return _s._remote(
        "set_clip_color",
        models.SetClipColorRequest(
            track_index=track_index,
            clip_index=clip_index,
            scope=scope,
            color_index=color_index,
            color=color,
        ),
        exclude_none=True,
    )


@mcp.tool()
def diagnose_clip_targets(track_index: int | None = None) -> Any:
    """Report which clips ``set_clip_color`` can and cannot reach.

    Side effects: none; a read-only sweep of Session slots and Arrangement
    clips.
    Example: ``diagnose_clip_targets(0)`` inspects one track;
    ``diagnose_clip_targets()`` sweeps the whole Set.
    Edge cases: returns ``arrangement_supported: false`` and an ``inaccessible``
    entry for a host that does not expose ``Track.arrangement_clips``, instead
    of reporting zero Arrangement clips.
    """
    return _s._remote(
        "diagnose_clip_targets",
        models.DiagnoseClipTargetsRequest(track_index=track_index),
        exclude_none=True,
    )


@mcp.tool()
def get_arrangement_clips(track_index: int) -> Any:
    """List one track's Arrangement clips with their placement on the timeline.

    Side effects: none.
    Example: ``get_arrangement_clips(3)`` returns each clip's ``start_time``,
    ``end_time`` and length in beats, sorted by position.
    Edge cases: a host without ``Track.arrangement_clips`` returns
    ``CAPABILITY_UNAVAILABLE`` instead of an empty list.
    """
    return _s._remote(
        "get_arrangement_clips",
        models.GetArrangementClipsRequest(track_index=track_index),
    )


@mcp.tool()
def duplicate_session_clip_to_arrangement(track_index: int, clip_index: int, time: float) -> Any:
    """Place a Session clip onto the Arrangement timeline at an exact beat.

    Side effects: adds one Arrangement clip in one Live undo step. The Session
    clip stays where it is, and clip envelopes travel with the copy.
    Example: ``duplicate_session_clip_to_arrangement(38, 0, 468.0)`` drops slot
    one of track 38 at beat 468.
    Edge cases: an empty slot returns ``BAD_INPUT``; a host without
    ``Track.duplicate_clip_to_arrangement`` returns ``CAPABILITY_UNAVAILABLE``.
    """
    return _s._remote(
        "duplicate_session_clip_to_arrangement",
        models.DuplicateSessionClipToArrangementRequest(
            track_index=track_index,
            clip_index=clip_index,
            time=time,
        ),
    )


@mcp.tool()
def delete_arrangement_clip(track_index: int, clip_index: int) -> Any:
    """Delete one clip from the Arrangement timeline.

    Side effects: removes one Arrangement clip in one Live undo step.
    Example: ``delete_arrangement_clip(3, 2)`` deletes the third clip of the
    track's Arrangement lane.
    Edge cases: ``clip_index`` indexes ``Track.arrangement_clips``; re-read it
    after any structural change because the indices shift.
    """
    return _s._remote(
        "delete_arrangement_clip",
        models.DeleteArrangementClipRequest(track_index=track_index, clip_index=clip_index),
    )
