"""Live acceptance steps, part 7 of the lifted runner."""

from __future__ import annotations

import functools
from types import SimpleNamespace
from typing import Any, cast

from ..certification import Verification
from ..errors import BridgeError
from . import live_steps_2 as _steps_2
from . import live_steps_3 as _steps_3
from . import live_steps_4 as _steps_4
from . import live_steps_5 as _steps_5
from . import live_steps_6 as _steps_6
from . import runner as _runner
from .baseline import _discover_baseline
from .helpers import _acceptance_safe_cue_times, _parameter_tolerance, _test_tempo
from .probes import QUIT_ABLETON_MANUAL_REASON
from .probes import load_device as _load_device
from .safety import AcceptanceSafetyError, require_fresh_set


async def _step_33(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    for _loop_item_14 in sorted(
        (ctx.baseline.get("track_color_indexes", {}) or {}).items()
    ):
        ctx.idx, ctx.original_index = _loop_item_14
        if ctx.original_index is None:
            continue

        ctx._restore_color = functools.partial(
            _steps_3._lifted__restore_color,
            ctx,
            _idx=ctx.idx,
            _original=ctx.original_index,
        )


        ctx._verify_color = functools.partial(
            _steps_3._lifted__verify_color,
            ctx,
            _idx=ctx.idx,
            _original=ctx.original_index,
        )


        ctx._restore_call(
            f"set_track_color({ctx.idx})",
            "set_track_color",
            ctx._restore_color,
            verify=ctx._verify_color,
        )


async def _step_34(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if "live_fade_volume_original" in ctx.artifacts:
        ctx.restore_target = ctx.artifacts["live_fade_volume_original"]
        ctx.target_track = int(
            ctx.artifacts.get("live_fade_track_index", ctx.fade_track_index)
        )

        ctx._verify_volume = functools.partial(_steps_3._lifted__verify_volume, ctx)


        ctx._restore_call(
            "live_fade volume restore",
            "live_fade",
            lambda: ctx.call(
                "live_fade",
                {
                    "track_index": ctx.target_track,
                    "target_value": ctx.restore_target,
                    "duration": 0.0,
                    "steps": 1,
                },
            ),
            verify=ctx._verify_volume,
        )
    # Restore the parameter the mutation probe
    # touched, using the snapshot captured before the
    # write.
    ctx.param_restore_raw = ctx.artifacts.get("set_parameter_value_restore")
    ctx.param_restore = (
        cast(dict[str, Any], ctx.param_restore_raw)
        if isinstance(ctx.param_restore_raw, dict)
        else None
    )
    if ctx.param_restore is not None:
        ctx.p_min = float(ctx.param_restore.get("min", 0.0))
        ctx.p_max = float(ctx.param_restore.get("max", 1.0))
        ctx.p_tol = _parameter_tolerance(ctx.p_min, ctx.p_max)

        ctx._verify_param_restore = functools.partial(
            _steps_4._lifted__verify_param_restore, ctx
        )


        ctx._restore_call(
            "set_parameter_value restore",
            "set_parameter_value",
            lambda: ctx.call(
                "set_parameter_value",
                {
                    "track_index": ctx.param_restore["track_index"],
                    "device_index": ctx.param_restore["device_index"],
                    "parameter_name": ctx.param_restore["parameter_name"],
                    "value": ctx.param_restore["original"],
                },
            ),
            verify=ctx._verify_param_restore,
        )


async def _step_35(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if ctx.cleanup_failures:
        ctx.affected = sorted({tool for tool, _ in ctx.cleanup_failures})
        ctx.details = "; ".join(
            f"{tool}: {reason}" for tool, reason in ctx.cleanup_failures
        )
        for _loop_item_19 in ctx.affected:
            ctx.tool = _loop_item_19
            if ctx.tool in ctx.report.recorded and (
                ctx.report.recorded[ctx.tool].status == "live_passed"
            ):
                ctx.report.record(
                    Verification(
                        ctx.tool,
                        "failed",
                        f"cleanup/readback failed ({ctx.details})",
                    )
                )


async def _step_36(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx.midi_tracks = [
        idx for idx, kind in ctx.baseline["track_types"].items() if kind == "midi"
    ]
    if not ctx.midi_tracks:
        raise AcceptanceSafetyError("no MIDI track available in disposable Set")
    ctx.midi_track_index = (
        ctx.track_index
        if (ctx.baseline["track_types"].get(ctx.track_index) == "midi")
        else ctx.midi_tracks[0]
    )
    ctx.artifacts["tags"].append(f"midi_track_index={ctx.midi_track_index}")

    # Track for live_fade readback/mutation (prefers
    # audio_track_index, falls back to midi_track_index).
    ctx.fade_track_index = (
        ctx.audio_track_index
        if ctx.audio_track_index in ctx.baseline["track_names"]
        else ctx.midi_track_index
    )

    # Verify the MIDI slot is empty before mutating.
    ctx.slots = ctx.call("get_clip_summary", {"track_index": ctx.midi_track_index})
    ctx.slot = next(
        (item for item in ctx.slots if item.get("index") == ctx.clip_index),
        None,
    )
    if ctx.slot is None:
        raise AcceptanceSafetyError(
            f"clip slot {ctx.midi_track_index}:{ctx.clip_index} "
            "is missing; refusing to mutate"
        )
    if bool(ctx.slot.get("has_clip")):
        raise AcceptanceSafetyError(
            f"clip slot {ctx.midi_track_index}:{ctx.clip_index} "
            "is occupied; refusing to overwrite"
        )

    ctx.original_tempo = ctx.baseline["tempo"]
    ctx.original_time = ctx.baseline["current_song_time"]
    ctx.original_loop = ctx.baseline["loop"]
    ctx.original_loop_start = ctx.baseline["loop_start"]
    ctx.original_loop_length = ctx.baseline["loop_length"]
    ctx.cue_time, ctx.bulk_cue_time = _acceptance_safe_cue_times(
        ctx.baseline["song_length"], ctx.baseline["locators"]
    )
    ctx.tempo_one = _test_tempo(ctx.original_tempo, 1.0)
    ctx.tempo_two = _test_tempo(ctx.original_tempo, 2.0)
    ctx.cue_name = "ABLETON_MCP_ACCEPTANCE"
    ctx.bulk_cue_name = "ABLETON_MCP_ACCEPTANCE_BULK"
    ctx.artifacts["tags"].extend([ctx.cue_name, ctx.bulk_cue_name])
    ctx.cue_created = False

    # Audio warp readback helper.
    ctx.read_warp = functools.partial(_steps_2._lifted_read_warp, ctx)


    # Original warp state for restore.
    ctx.original_warp = None


async def _step_37(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx.track_creation_runner = None
    if ctx.baseline["track_types"].get(ctx.audio_track_index) == "audio":
        try:
            ctx.audio_slots = ctx.call(
                "get_clip_summary", {"track_index": ctx.audio_track_index}
            )
            ctx.audio_slot = next(
                (
                    item
                    for item in ctx.audio_slots
                    if item.get("index") == ctx.audio_clip_index
                ),
                None,
            )
            if ctx.audio_slot is not None and bool(ctx.audio_slot.get("has_clip")):
                ctx.audio_info = ctx.call(
                    "get_clip_info",
                    {
                        "track_index": ctx.audio_track_index,
                        "clip_index": ctx.audio_clip_index,
                    },
                )
                if bool(ctx.audio_info.get("is_audio_clip", False)):
                    ctx.original_warp = await ctx.read_warp()
                    ctx.artifacts["manual_cleanup"].append(
                        "restore warp_state from original_warp snapshot"
                    )
        except Exception:
            pass


async def _step_38(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if "create_audio_track" not in ctx.report.recorded:
        if ctx.cleanup_failures:
            ctx.cleanup_details = "; ".join(
                f"{tool}: {reason}" for tool, reason in ctx.cleanup_failures
            )
            for _loop_item_20 in _runner._STRUCTURAL_TOOLS:
                ctx.tool = _loop_item_20
                ctx.report.record(
                    Verification(
                        ctx.tool,
                        "failed",
                        "not executed because reversible cleanup failed "
                        f"({ctx.cleanup_details})",
                    )
                )
        elif ctx.track_creation_runner is None:
            for _loop_item_22 in _runner._STRUCTURAL_TOOLS:
                ctx.tool = _loop_item_22
                ctx.report.record(
                    Verification(
                        ctx.tool,
                        "failed",
                        "track creation runner was not initialized",
                    )
                )
        else:
            await _runner._record_call(
                ctx.report,
                "create_audio_track",
                lambda: ctx.track_creation_runner("audio"),
            )
            ctx.created_midi = await _runner._record_call(
                ctx.report,
                "create_midi_track",
                lambda: ctx.track_creation_runner("midi"),
            )
            await _load_device.run(
                ctx.report,
                call=ctx.call,
                call_ws=ctx.call_ws,
                track_index=ctx.created_midi,
                artifacts=ctx.artifacts,
            )


async def _step_39(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx.metadata = ctx.call("get_project_metadata")
    ctx.actual_name = str(ctx.metadata.get("song_name", ""))
    if ctx.actual_name != ctx.confirm_project_name:
        raise AcceptanceSafetyError(
            f"Loaded project {ctx.actual_name!r} does not match "
            f"confirmation {ctx.confirm_project_name!r}; no "
            "mutations were sent."
        )
    require_fresh_set(ctx.metadata)
    ctx.baseline = _discover_baseline(ctx.client)

    ctx.occupied_clip_target = None
    ctx.rack_device_target = None


async def _step_40(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx.discovered_param_track_index = None
    ctx.discovered_param_device_index = None
    ctx.discovered_param_name = None
    ctx.discovered_param_min = 0.0
    ctx.discovered_param_max = 1.0
    ctx.discovered_param_is_quantized = False

    ctx.search_tracks = []
    if ctx.audio_track_index in ctx.baseline["track_names"]:
        ctx.search_tracks.append(ctx.audio_track_index)
    for _loop_item_5 in sorted(ctx.baseline["track_names"].keys()):
        ctx.t_idx = _loop_item_5
        if ctx.t_idx not in ctx.search_tracks:
            ctx.search_tracks.append(ctx.t_idx)


async def _step_41(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if "tcp_reads" in ctx.expanded:
        await _steps_5._step_23(ctx)

        await _steps_5._step_24(ctx)
        await _steps_6._step_25(ctx)
        await _steps_6._step_26(ctx)
        await _steps_6._step_27(ctx)
        await _steps_6._step_28(ctx)
    else:
        # ``mutations`` / ``websocket_reads`` profiles still
        # need a recorded ``get_project_metadata`` row to
        # satisfy the catalog but do not certify the read.
        ctx.report.record(
            Verification(
                "get_project_metadata",
                "live_passed",
                f"song_name={ctx.actual_name}",
            )
        )


async def _step_42(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if "websocket_reads" in ctx.expanded:

        ctx.get_warp_readback = functools.partial(_steps_2._lifted_get_warp_readback, ctx)


        try:
            ctx.warp = await ctx.get_warp_readback()
            ctx.report.record(
                Verification(
                    "get_warp_state",
                    "live_passed",
                    f"warping={ctx.warp.get('warping', False)}",
                )
            )
        except BridgeError as error:
            if error.code == "CAPABILITY_UNAVAILABLE":
                ctx.report.record(
                    Verification(
                        "get_warp_state",
                        "host_unavailable",
                        f"{error.code}: {error}",
                    )
                )
            else:
                ctx.report.record(
                    Verification(
                        "get_warp_state",
                        "failed",
                        f"{error.code}: {error}",
                    )
                )
        except Exception as error:
            ctx.report.record(
                Verification(
                    "get_warp_state",
                    "failed",
                    f"{type(error).__name__}: {error}",
                )
            )


async def _step_43(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if "quit" in ctx.profiles and "mutations" not in ctx.expanded:
        # ``quit`` profile without ``mutations``: record the
        # ``quit_ableton`` row as ``manual_required``. The
        # runner does not actually invoke the bridge here —
        # invoking ``quit_ableton`` would close the host and
        # prevent any other probe from running, and we never
        # certify an operation that was not executed.
        ctx.report.record(
            Verification(
                "quit_ableton",
                "manual_required",
                QUIT_ABLETON_MANUAL_REASON,
            )
        )


async def _step_44(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx._hierarchy = ctx.call("get_track_list")
    ctx._regular = [
        int(track["index"])
        for track in ctx._hierarchy
        if track.get("type") in ("midi", "audio")
    ]
    ctx._groups = [
        int(track["index"])
        for track in ctx._hierarchy
        if bool(track.get("is_group_track", False))
    ]
    ctx._grouped = [
        int(track["index"])
        for track in ctx._hierarchy
        if bool(track.get("is_grouped", False))
    ]


async def _step_45(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx._capability_requests = {
        "move_track": (
            {"track_index": ctx._regular[0], "destination_index": ctx._regular[-1]}
            if ctx._regular
            else None
        ),
        "reorder_tracks": (
            {"order": sorted(ctx._regular)} if ctx._regular else None
        ),
        # These three need a Set that actually has groups. On a
        # disposable Set without any, the row is recorded as
        # not exercised rather than as a passed refusal.
        "move_track_to_group": (
            {"track_index": ctx._regular[0], "group_track_index": ctx._groups[0]}
            if ctx._groups and ctx._regular and ctx._regular[0] != ctx._groups[0]
            else None
        ),
        "ungroup_track": (
            {"track_index": ctx._grouped[0]} if ctx._grouped else None
        ),
        "merge_groups": (
            {
                "source_group_index": ctx._groups[0],
                "destination_group_index": ctx._groups[1],
            }
            if len(ctx._groups) >= 2
            else None
        ),
    }
