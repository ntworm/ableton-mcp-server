"""Live acceptance steps, part 3 of the lifted runner."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any, cast

from . import live_steps_4 as _steps_4
from .helpers import LIVE_FADE_UNITY_VALUE


async def _lifted_run_duplicate_to_arrangement(ctx: SimpleNamespace, ) -> str:
    ctx.call(
        "duplicate_session_clip_to_arrangement",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": ctx.clip_index,
            "time": ctx.probe_beat,
        },
    )
    placed = ctx.arrangement_clip_at(ctx.probe_beat)
    if placed is None:
        raise AssertionError(
            "duplicate_session_clip_to_arrangement left no clip "
            f"at beat {ctx.probe_beat}"
        )
    return f"placed at {ctx.probe_beat}"


async def _lifted_run_add_notes_pattern(ctx: SimpleNamespace, ) -> str:
    ctx.call(
        "add_notes_pattern",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": ctx.clip_index,
            "cell": [
                {
                    "pitch": 60,
                    "start_time": 0.0,
                    "duration": 0.25,
                    "velocity": 90,
                }
            ],
            "cell_length": 1.0,
            "repeats": 2,
        },
    )
    return "cell repeated twice"


async def _lifted_run_create_clip_automation_curve(ctx: SimpleNamespace, ) -> str:
    ctx.call(
        "create_clip_automation_curve",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": ctx.clip_index,
            "parameter_name": "volume",
            "control_points": [
                {"time": 0.0, "value": 0.6},
                {"time": 2.0, "value": 0.85},
            ],
            "shape": "linear",
            "resolution": 0.5,
        },
    )
    return "curve expanded server-side"


async def _lifted_run_set_arrangement_clip_properties(ctx: SimpleNamespace, ) -> str:
    placed = ctx.arrangement_clip_at(ctx.probe_beat)
    if placed is None:
        raise AssertionError("no probe clip to rename")
    ctx.call(
        "set_arrangement_clip_properties",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": int(placed["clip_index"]),
            "name": "acceptance probe",
        },
    )
    return "arrangement clip renamed"


async def _lifted_run_move_arrangement_clip(ctx: SimpleNamespace, ) -> str:
    placed = ctx.arrangement_clip_at(ctx.probe_beat)
    if placed is None:
        raise AssertionError("no probe clip to move")
    ctx.call(
        "move_arrangement_clip",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": int(placed["clip_index"]),
            "time": ctx.probe_beat + 64.0,
        },
    )
    if ctx.arrangement_clip_at(ctx.probe_beat) is not None:
        raise AssertionError("move left a clip at the old position")
    if ctx.arrangement_clip_at(ctx.probe_beat + 64.0) is None:
        raise AssertionError(
            "move produced no clip at the new position"
        )
    return f"moved to {ctx.probe_beat + 64.0}"


async def _lifted_run_delete_arrangement_clip(ctx: SimpleNamespace, ) -> str:
    placed = ctx.arrangement_clip_at(ctx.probe_beat + 64.0)
    if placed is None:
        raise AssertionError("no probe clip to delete")
    ctx.call(
        "delete_arrangement_clip",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": int(placed["clip_index"]),
        },
    )
    if ctx.arrangement_clip_at(ctx.probe_beat + 64.0) is not None:
        raise AssertionError("delete_arrangement_clip left the clip")
    return "probe clip removed"


async def _lifted_run_delete_clip(ctx: SimpleNamespace, ) -> str:
    ctx.call(
        "delete_clip",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": ctx.clip_index,
        },
    )
    info_after_delete = ctx.call(
        "get_clip_info",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": ctx.clip_index,
        },
    )
    if bool(info_after_delete.get("has_clip", False)):
        raise AssertionError("delete_clip did not remove clip")
    return f"track={ctx.midi_track_index} slot={ctx.clip_index}"


async def _lifted_run_set_parameter_value(ctx: SimpleNamespace, ) -> str:
    lctx = SimpleNamespace(
        ctx=ctx,
    )
    await _steps_4._step_8(lctx)
    if lctx.is_quant:
        for _loop_item_1 in [lctx.min_val, lctx.max_val]:
            lctx.c = _loop_item_1
            if abs(lctx.c - lctx.live_val) > lctx.prop_tol:
                lctx.target = lctx.c
                break
        if lctx.target is None:
            lctx.i_min = int(lctx.min_val)
            lctx.i_max = int(lctx.max_val)
            for _loop_item_3 in range(lctx.i_min, lctx.i_max + 1):
                lctx.c = _loop_item_3
                if abs(float(lctx.c) - lctx.live_val) > lctx.prop_tol:
                    lctx.target = float(lctx.c)
                    break
    else:
        await _steps_4._step_10(lctx)

    await _steps_4._step_9(lctx)
    return (
        f"param={lctx.ctx.discovered_param_name} "
        f"live_val={lctx.live_val} target={lctx.target}"
    )


async def _lifted_run_set_plugin_preset(ctx: SimpleNamespace, ) -> str:
    response = ctx.call(
        "set_plugin_preset",
        {
            "track_index": ctx.plugin_track_index,
            "device_index": ctx.plugin_device_index,
            "preset_index": ctx.plugin_selected,
        },
    )
    if not isinstance(response, dict):
        raise AssertionError("set_plugin_preset must return a dict")
    if response.get("selected_preset_index") != ctx.plugin_selected:
        raise AssertionError(
            "set_plugin_preset readback failed: expected "
            f"{ctx.plugin_selected} but got "
            f"{response.get('selected_preset_index')}"
        )
    return (
        f"track={ctx.plugin_track_index} "
        f"device={ctx.plugin_device_index} "
        f"preset={ctx.plugin_selected}"
    )


async def _lifted_run_live_fade(ctx: SimpleNamespace, ) -> str:
    pre_state = ctx.call("get_track_state", {"track_index": ctx.fade_track_index})
    if not isinstance(pre_state, dict) or "volume" not in pre_state:
        raise AssertionError(
            "live_fade pre-readback failed "
            "(get_track_state missing 'volume')"
        )
    original_volume = float(pre_state["volume"])
    ctx.artifacts["live_fade_volume_original"] = original_volume
    ctx.artifacts["live_fade_track_index"] = ctx.fade_track_index

    ctx.call(
        "live_fade",
        {
            "track_index": ctx.fade_track_index,
            "target_percent": 50.0,
            "duration": 0.0,
            "steps": 1,
        },
    )
    post_immediate = ctx.call(
        "get_track_state", {"track_index": ctx.fade_track_index}
    )
    if (
        not isinstance(post_immediate, dict)
        or "volume" not in post_immediate
    ):
        raise AssertionError("live_fade immediate readback failed")
    _expected_immediate = LIVE_FADE_UNITY_VALUE * (50.0 / 100.0)
    if abs(float(post_immediate["volume"]) - _expected_immediate) > 0.05:
        raise AssertionError(
            "live_fade immediate target mismatch "
            f"(expected {_expected_immediate}, "
            f"got {post_immediate['volume']})"
        )

    ctx.call(
        "live_fade",
        {
            "track_index": ctx.fade_track_index,
            "target_percent": 80.0,
            "duration": 0.2,
            "steps": 4,
        },
    )
    post_fade = ctx.call("get_track_state", {"track_index": ctx.fade_track_index})
    if not isinstance(post_fade, dict) or "volume" not in post_fade:
        raise AssertionError("live_fade timed readback failed")
    _expected_timed = LIVE_FADE_UNITY_VALUE * (80.0 / 100.0)
    if abs(float(post_fade["volume"]) - _expected_timed) > 0.05:
        raise AssertionError(
            "live_fade timed target mismatch "
            f"(expected {_expected_timed}, "
            f"got {post_fade['volume']})"
        )
    return "duration=0.2 monotonic fade readback OK"


async def _lifted_run_set_warp_state(ctx: SimpleNamespace, ) -> str:
    if ctx.original_warp is None:
        raise AssertionError(
            "warp setup failed "
            "(audio clip missing or WebSocket unreachable)"
        )
    await ctx.call_ws(
        "set_warp_state",
        {
            "track_index": ctx.audio_track_index,
            "clip_index": ctx.audio_clip_index,
            "warping": True,
        },
    )
    rb_warp = await ctx.read_warp()
    if not bool(rb_warp.get("warping", False)):
        raise AssertionError("set_warp_state readback failed")
    return f"warping=True readback={rb_warp}"


async def _lifted__run_track_creation(ctx: SimpleNamespace, kind: str) -> int:
    lctx = SimpleNamespace(
        ctx=ctx,
        kind=kind
    )
    await _steps_4._step_11(lctx)
    await _steps_4._step_12(lctx)

    await _steps_4._step_13(lctx)
    return cast(int, lctx.new_index)


def _lifted__restore_call(ctx: SimpleNamespace,
    action: str,
    tool: str,
    restore: Callable[[], Any],
    *,
    verify: Callable[[Any], None],
) -> None:
    try:
        observed = restore()
        verify(observed)
    except Exception as error:  # noqa: BLE001
        ctx.cleanup_failures.append(
            (tool, f"{action} readback failed: {error}")
        )


async def _lifted__restore_ws(ctx: SimpleNamespace,
    action: str,
    tool: str,
    restore: Callable[[], Awaitable[Any]],
    *,
    verify: Callable[[Any], Awaitable[None]],
) -> None:
    try:
        observed = await restore()
        await verify(observed)
    except Exception as error:  # noqa: BLE001
        ctx.cleanup_failures.append(
            (tool, f"{action} readback failed: {error}")
        )


def _lifted__eq(ctx: SimpleNamespace, observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        raise AssertionError(
            f"{label} readback mismatch: "
            f"observed={observed!r} "
            f"expected={expected!r}"
        )


def _lifted__verify_cue_absent(ctx: SimpleNamespace, _observed: Any) -> None:
    if any(
        abs(float(item.get("time", -1)) - ctx.cue_time) < 0.01
        for item in ctx.call("get_locators")
    ):
        raise AssertionError(
            f"cue at {ctx.cue_time} still present after delete"
        )


async def _lifted__verify_warp(ctx: SimpleNamespace, _observed: Any) -> None:
    rb = await ctx.read_warp()
    if bool(rb.get("warping", False)) != (ctx.expected_warp):
        raise AssertionError(
            f"warp restore: observed="
            f"{rb.get('warping')!r} expected="
            f"{ctx.expected_warp!r}"
        )


def _lifted__restore_mute(ctx: SimpleNamespace,
    _idx: int,
    _original: bool                    ) -> Any:
    return ctx.call(
        "set_track_property",
        {
            "track_index": _idx,
            "property": "mute",
            "value": _original,
        },
    )


def _lifted__verify_mute(ctx: SimpleNamespace,
    _observed: Any,
    _idx: int,
    _original: bool                    ) -> None:
    ctx._eq(
        bool(
            ctx.call("get_track_state", {"track_index": _idx}).get(
                "mute", False
            )
        ),
        _original,
        f"track:{_idx}.mute",
    )


def _lifted__restore_solo(ctx: SimpleNamespace,
    _idx: int,
    _original: bool                    ) -> Any:
    return ctx.call(
        "set_track_property",
        {
            "track_index": _idx,
            "property": "solo",
            "value": _original,
        },
    )


def _lifted__verify_solo(ctx: SimpleNamespace,
    _observed: Any,
    _idx: int,
    _original: bool                    ) -> None:
    ctx._eq(
        bool(
            ctx.call("get_track_state", {"track_index": _idx}).get(
                "solo", False
            )
        ),
        _original,
        f"track:{_idx}.solo",
    )


def _lifted__restore_arm(ctx: SimpleNamespace,
    _idx: int,
    _original: bool                    ) -> Any:
    return ctx.call(
        "set_track_property",
        {
            "track_index": _idx,
            "property": "arm",
            "value": _original,
        },
    )


def _lifted__verify_arm(ctx: SimpleNamespace,
    _observed: Any,
    _idx: int,
    _original: bool                    ) -> None:
    ctx._eq(
        bool(
            ctx.call("get_track_state", {"track_index": _idx}).get(
                "arm", False
            )
        ),
        _original,
        f"track:{_idx}.arm",
    )


def _lifted__restore_color(ctx: SimpleNamespace,
    _idx: int,
    _original: int                    ) -> Any:
    return ctx.call(
        "set_track_color",
        {"track_index": _idx, "color_index": _original},
    )


def _lifted__verify_color(ctx: SimpleNamespace,
    _observed: Any,
    _idx: int,
    _original: int                    ) -> None:
    ctx._eq(
        ctx.call("get_track_state", {"track_index": _idx}).get(
            "color_index"
        ),
        _original,
        f"track:{_idx}.color_index",
    )


def _lifted__verify_volume(ctx: SimpleNamespace, _o: Any) -> None:
    state = ctx.call(
        "get_track_state",
        {"track_index": ctx.target_track},
    )
    if not isinstance(state, dict) or ("volume" not in state):
        raise AssertionError(
            "live_fade restore readback missing 'volume' "
            "from get_track_state"
        )
    ctx._eq(
        float(state["volume"]),
        ctx.restore_target,
        f"track:{ctx.target_track}.volume",
    )
