"""Live acceptance steps, part 4 of the lifted runner."""

from __future__ import annotations

import functools
from types import SimpleNamespace
from typing import Any

from ..certification import Verification
from . import live_steps_2 as _steps_2
from . import runner as _runner
from .helpers import _parameter_tolerance


def _lifted__verify_param_restore(ctx: SimpleNamespace, _o: Any) -> None:
    observed_val = float(
        ctx.call(
            "get_parameter_value",
            {
                "track_index": ctx.param_restore["track_index"],
                "device_index": ctx.param_restore["device_index"],
                "parameter_name": ctx.param_restore["parameter_name"],
            },
        ).get("value", 0.0)
    )
    expected_val = float(ctx.param_restore["original"])
    if abs(observed_val - expected_val) > ctx.p_tol:
        raise AssertionError(
            "set_parameter_value restore readback mismatch: "
            f"observed={observed_val} expected={expected_val} "
            f"(tol {ctx.p_tol})"
        )


async def _step_7(lctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    lctx.save_steps = (
        lctx.gui_workflow.get("save")
        if isinstance(lctx.gui_workflow, dict)
        else None
    )
    if not (
        isinstance(lctx.save_steps, list)
        and lctx.save_steps
        and all(
            isinstance(step, str) and bool(step.strip())
            for step in lctx.save_steps
        )
    ):
        raise AssertionError(
            "save_set manual fallback requires a non-empty "
            "gui_workflow.save string list"
        )
    lctx.ctx.report.record(
        Verification(
            "save_set",
            "manual_required",
            "Host does not expose Song.save API "
            "(save_set requires GUI workflow or manual save)",
        )
    )


async def _step_8(lctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    lctx.original_param_resp = lctx.ctx.call(
        "get_parameter_value",
        {
            "track_index": lctx.ctx.discovered_param_track_index,
            "device_index": lctx.ctx.discovered_param_device_index,
            "parameter_name": lctx.ctx.discovered_param_name,
        },
    )
    if not isinstance(lctx.original_param_resp, dict):
        raise AssertionError("get_parameter_value must return a dict")
    lctx.live_val = float(lctx.original_param_resp.get("value", 0.0))
    lctx.min_val = float(lctx.ctx.discovered_param_min)
    lctx.max_val = float(lctx.ctx.discovered_param_max)
    lctx.is_quant = bool(lctx.ctx.discovered_param_is_quantized)

    lctx.prop_tol = _parameter_tolerance(lctx.min_val, lctx.max_val)

    lctx.target = None


async def _step_9(lctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if lctx.target is None:
        raise AssertionError(
            "could not compute valid target value for parameter write"
        )

    lctx.ctx.artifacts["set_parameter_value_restore"] = {
        "track_index": lctx.ctx.discovered_param_track_index,
        "device_index": lctx.ctx.discovered_param_device_index,
        "parameter_name": lctx.ctx.discovered_param_name,
        "original": lctx.live_val,
        "min": lctx.min_val,
        "max": lctx.max_val,
        "is_quantized": lctx.is_quant,
    }
    lctx.ctx.call(
        "set_parameter_value",
        {
            "track_index": lctx.ctx.discovered_param_track_index,
            "device_index": lctx.ctx.discovered_param_device_index,
            "parameter_name": lctx.ctx.discovered_param_name,
            "value": lctx.target,
        },
    )
    lctx.rb_value = lctx.ctx.call(
        "get_parameter_value",
        {
            "track_index": lctx.ctx.discovered_param_track_index,
            "device_index": lctx.ctx.discovered_param_device_index,
            "parameter_name": lctx.ctx.discovered_param_name,
        },
    )
    if not isinstance(lctx.rb_value, dict):
        raise AssertionError(
            "set_parameter_value readback failed (no dict response)"
        )
    lctx.rb_val = float(lctx.rb_value.get("value", 0.0))
    if abs(lctx.rb_val - lctx.target) > lctx.prop_tol:
        raise AssertionError(
            f"set_parameter_value readback failed: "
            f"expected {lctx.target} but got {lctx.rb_val} (tol {lctx.prop_tol})"
        )


async def _step_10(lctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    lctx.range_val = abs(lctx.max_val - lctx.min_val)
    for _loop_item_2 in [lctx.min_val, lctx.max_val]:
        lctx.c = _loop_item_2
        if abs(lctx.c - lctx.live_val) > lctx.range_val * 0.1:
            lctx.target = lctx.c
            break
    if lctx.target is None:
        lctx.mid = (lctx.min_val + lctx.max_val) / 2.0
        if abs(lctx.mid - lctx.live_val) > lctx.prop_tol:
            lctx.target = lctx.mid
        elif abs(lctx.max_val - lctx.live_val) > lctx.prop_tol:
            lctx.target = lctx.max_val
        elif abs(lctx.min_val - lctx.live_val) > lctx.prop_tol:
            lctx.target = lctx.min_val


async def _step_11(lctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    lctx.tool_name = f"create_{lctx.kind}_track"
    lctx.pre_tracks = lctx.ctx.call("get_track_list")
    if not isinstance(lctx.pre_tracks, list):
        raise AssertionError(
            f"get_track_list prior to {lctx.tool_name} returned non-list"
        )
    lctx.pre_total_count = len(lctx.pre_tracks)
    lctx.pre_regular = [
        t for t in lctx.pre_tracks if t.get("type") in ("midi", "audio")
    ]
    lctx.pre_regular_count = len(lctx.pre_regular)

    lctx.res = lctx.ctx.call(lctx.tool_name, {"index": -1})
    if not isinstance(lctx.res, dict):
        raise AssertionError(f"{lctx.tool_name} must return a dict")
    lctx.new_index = lctx.res.get("track_index")
    if not isinstance(lctx.new_index, int):
        raise AssertionError(f"{lctx.tool_name} missing track_index")

    if lctx.new_index != lctx.pre_regular_count:
        raise AssertionError(
            f"{lctx.tool_name} returned track_index {lctx.new_index}, "
            f"expected {lctx.pre_regular_count}"
        )

    lctx.post_tracks = lctx.ctx.call("get_track_list")
    if (
        not isinstance(lctx.post_tracks, list)
        or len(lctx.post_tracks) != lctx.pre_total_count + 1
    ):
        lctx.post_str = (
            len(lctx.post_tracks)
            if isinstance(lctx.post_tracks, list)
            else "non-list"
        )
        raise AssertionError(
            f"{lctx.tool_name} did not increase total track count by 1: "
            f"pre={lctx.pre_total_count}, post={lctx.post_str}"
        )

    lctx.post_regular = [
        t for t in lctx.post_tracks if t.get("type") in ("midi", "audio")
    ]


async def _step_12(lctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if len(lctx.post_regular) != lctx.pre_regular_count + 1:
        raise AssertionError(
            f"{lctx.tool_name} did not increase regular track count by 1: "
            f"pre={lctx.pre_regular_count}, post={len(lctx.post_regular)}"
        )

    lctx.created_track = next(
        (t for t in lctx.post_tracks if int(t.get("index", -1)) == lctx.new_index),
        None,
    )
    if lctx.created_track is None or lctx.created_track.get("type") != lctx.kind:
        raise AssertionError(
            f"{lctx.tool_name} {lctx.new_index} missing or not "
            f"{lctx.kind} in get_track_list"
        )

    for _loop_item_1 in lctx.pre_regular:
        lctx.t = _loop_item_1
        lctx.idx = int(lctx.t.get("index", -1))
        lctx.match = next(
            (pt for pt in lctx.post_tracks if int(pt.get("index", -1)) == lctx.idx),
            None,
        )
        if (
            lctx.match is None
            or lctx.match.get("name") != lctx.t.get("name")
            or lctx.match.get("type") != lctx.t.get("type")
        ):
            raise AssertionError(
                f"Pre-existing regular track {lctx.idx} mutated: {lctx.t} vs {lctx.match}"
            )


async def _step_13(lctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    lctx.pre_special = [
        t for t in lctx.pre_tracks if t.get("type") not in ("midi", "audio")
    ]
    for _loop_item_2 in lctx.pre_special:
        lctx.t = _loop_item_2
        lctx.old_idx = int(lctx.t.get("index", -1))
        lctx.expected_new_idx = lctx.old_idx + 1
        lctx.match = next(
            (
                pt
                for pt in lctx.post_tracks
                if int(pt.get("index", -1)) == lctx.expected_new_idx
            ),
            None,
        )
        if (
            lctx.match is None
            or lctx.match.get("name") != lctx.t.get("name")
            or lctx.match.get("type") != lctx.t.get("type")
        ):
            raise AssertionError(
                f"Return/master track {lctx.t.get('name')} mismatched "
                f"post-creation: expected index {lctx.expected_new_idx}, "
                f"found {lctx.match}"
            )

    lctx.ctx.artifacts["tracks_created"].append(f"{lctx.kind}:{lctx.new_index}")
    lctx.ctx.artifacts["manual_cleanup"].append(
        f"delete {lctx.kind} track at index {lctx.new_index} "
        "(originally created by acceptance runner)"
    )


async def _step_14(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx.run_save_set = functools.partial(_steps_2._lifted_run_save_set, ctx)


    try:
        await ctx.run_save_set()
    except Exception as error:
        if getattr(error, "code", None) == "CAPABILITY_UNAVAILABLE":
            ctx.err_code = getattr(error, "code", "CAPABILITY_UNAVAILABLE")
            ctx.report.record(
                Verification(
                    "save_set",
                    "host_unavailable",
                    f"{ctx.err_code}: {error}",
                )
            )
        else:
            ctx.report.record(
                Verification(
                    "save_set", "failed", f"{type(error).__name__}: {error}"
                )
            )

    # ----- cue points -----
    ctx.run_create_cue = functools.partial(_steps_2._lifted_run_create_cue, ctx)


    await _runner._record_call(
        ctx.report, "create_cue_point", ctx.run_create_cue
    )
    ctx.cue_created = (
        "create_cue_point" in ctx.report.recorded
        and ctx.report.recorded["create_cue_point"].status == "live_passed"
    )

    ctx.run_bulk_cue = functools.partial(_steps_2._lifted_run_bulk_cue, ctx)


    await _runner._record_call(
        ctx.report, "bulk_create_cue_points", ctx.run_bulk_cue
    )

    ctx.run_delete_cue = functools.partial(_steps_2._lifted_run_delete_cue, ctx)


    await _runner._record_call(
        ctx.report, "delete_cue_point", ctx.run_delete_cue
    )
    # Assume deleted (restore will clean up if still present anyway)
    ctx.cue_created = False

    # ----- transport -----
    ctx.run_set_tempo = functools.partial(_steps_2._lifted_run_set_tempo, ctx)


    await _runner._record_call(ctx.report, "set_tempo", ctx.run_set_tempo)

    ctx.run_set_time = functools.partial(_steps_2._lifted_run_set_time, ctx)


async def _step_15(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    await _runner._record_call(
        ctx.report, "set_current_song_time", ctx.run_set_time
    )

    ctx.run_set_loop_start = functools.partial(_steps_2._lifted_run_set_loop_start, ctx)


    await _runner._record_call(
        ctx.report, "set_loop_start", ctx.run_set_loop_start
    )

    ctx.run_set_loop_length = functools.partial(
        _steps_2._lifted_run_set_loop_length, ctx
    )


    await _runner._record_call(
        ctx.report, "set_loop_length", ctx.run_set_loop_length
    )

    ctx.run_set_loop = functools.partial(_steps_2._lifted_run_set_loop, ctx)


    await _runner._record_call(ctx.report, "set_loop", ctx.run_set_loop)

    # ----- clip + notes mutations -----
    ctx.run_create_clip = functools.partial(_steps_2._lifted_run_create_clip, ctx)


    await _runner._record_call(ctx.report, "create_clip", ctx.run_create_clip)
    ctx.create_clip_ok = (
        "create_clip" in ctx.report.recorded
        and ctx.report.recorded["create_clip"].status == "live_passed"
    )

    if not ctx.create_clip_ok:
        ctx.report.record(
            Verification(
                "add_notes_to_clip",
                "failed",
                "Skipped: create_clip dependency failed",
            )
        )
    else:

        ctx.run_add_notes = functools.partial(_steps_2._lifted_run_add_notes, ctx)


        await _runner._record_call(
            ctx.report, "add_notes_to_clip", ctx.run_add_notes
        )


async def _step_16(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if not ctx.create_clip_ok:
        ctx.report.record(
            Verification(
                "clear_clip_notes",
                "failed",
                "Skipped: create_clip dependency failed",
            )
        )
    else:

        ctx.run_clear_notes = functools.partial(_steps_2._lifted_run_clear_notes, ctx)


        await _runner._record_call(
            ctx.report, "clear_clip_notes", ctx.run_clear_notes
        )

    if not ctx.create_clip_ok:
        ctx.report.record(
            Verification(
                "set_clip_properties",
                "failed",
                "Skipped: create_clip dependency failed",
            )
        )
    else:

        ctx.run_set_clip_props = functools.partial(
            _steps_2._lifted_run_set_clip_props, ctx
        )


        await _runner._record_call(
            ctx.report, "set_clip_properties", ctx.run_set_clip_props
        )

    if not ctx.create_clip_ok:
        ctx.report.record(
            Verification(
                "create_clip_automation",
                "failed",
                "Skipped: create_clip dependency failed",
            )
        )
    else:

        ctx.run_clip_automation = functools.partial(
            _steps_2._lifted_run_clip_automation, ctx
        )


        await _runner._record_call(
            ctx.report, "create_clip_automation", ctx.run_clip_automation
        )

    # ----- transport fire/stop -----
    ctx.run_start_playback = functools.partial(_steps_2._lifted_run_start_playback, ctx)
