"""Live acceptance steps, part 5 of the lifted runner."""

from __future__ import annotations

import functools
from types import SimpleNamespace

from ..certification import Verification
from . import live_steps_1 as _steps_1
from . import live_steps_2 as _steps_2
from . import live_steps_3 as _steps_3
from . import runner as _runner
from .probes import QUIT_ABLETON_MANUAL_REASON
from .probes import tcp_reads as _tcp_reads
from .report import _record_unavailable


async def _step_17(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    await _runner._record_call(
        ctx.report, "start_playback", ctx.run_start_playback
    )

    ctx.run_stop_playback = functools.partial(_steps_2._lifted_run_stop_playback, ctx)


    await _runner._record_call(
        ctx.report, "stop_playback", ctx.run_stop_playback
    )

    # ----- run_batch -----
    ctx.run_run_batch = functools.partial(_steps_2._lifted_run_run_batch, ctx)


    await _runner._record_call(ctx.report, "run_batch", ctx.run_run_batch)

    # ----- fire_clip (optional) -----
    if not ctx.fire_clip:
        _record_unavailable(
            ctx.report,
            "fire_clip",
            "fire_clip requires --fire-clip flag",
        )
    elif not ctx.create_clip_ok:
        ctx.report.record(
            Verification(
                "fire_clip", "failed", "Skipped: create_clip dependency failed"
            )
        )
    else:

        ctx.run_fire_clip = functools.partial(_steps_2._lifted_run_fire_clip, ctx)


        await _runner._record_call(ctx.report, "fire_clip", ctx.run_fire_clip)
        import contextlib
        ctx.contextlib = contextlib

        with ctx.contextlib.suppress(Exception):
            ctx.call("stop_playback")

    # ----- fire_scene -----
    ctx.run_fire_scene = functools.partial(_steps_2._lifted_run_fire_scene, ctx)


    await _runner._record_call(ctx.report, "fire_scene", ctx.run_fire_scene)


async def _step_18(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    with ctx.contextlib.suppress(Exception):
        ctx.call("stop_playback")

    # ----- set_track_property + readback -----
    ctx.run_set_track_prop = functools.partial(_steps_2._lifted_run_set_track_prop, ctx)


    await _runner._record_call(
        ctx.report, "set_track_property", ctx.run_set_track_prop
    )
    try:
        ctx.original_mute = bool(
            ctx.baseline.get("track_mutes", {}).get(ctx.midi_track_index, False)
        )
        ctx.call(
            "set_track_property",
            {
                "track_index": ctx.midi_track_index,
                "property": "mute",
                "value": ctx.original_mute,
            },
        )
    except Exception:
        pass

    # ----- set_track_color + readback -----
    # Live's palette has 70 swatches. We pick a slot the
    # track is not already using so the readback proves a
    # real write instead of matching the prior value.
    ctx._baseline_color_index = ctx.baseline.get("track_color_indexes", {}).get(
        ctx.midi_track_index
    )
    ctx._probe_color_index = 1 if ctx._baseline_color_index == 0 else 0

    ctx.run_set_track_color = functools.partial(
        _steps_2._lifted_run_set_track_color, ctx
    )


    await _runner._record_call(
        ctx.report, "set_track_color", ctx.run_set_track_color
    )
    try:
        if ctx._baseline_color_index is not None:
            ctx.call(
                "set_track_color",
                {
                    "track_index": ctx.midi_track_index,
                    "color_index": ctx._baseline_color_index,
                },
            )
    except Exception:
        pass


async def _step_19(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if not ctx.create_clip_ok:
        ctx.report.record(
            Verification(
                "set_clip_color",
                "failed",
                "Skipped: create_clip dependency failed",
            )
        )
    else:

        ctx.run_set_clip_color = functools.partial(
            _steps_2._lifted_run_set_clip_color, ctx
        )


        await _runner._record_call(
            ctx.report, "set_clip_color", ctx.run_set_clip_color
        )

    # ----- rename_track + readback -----
    ctx.run_rename_track = functools.partial(_steps_2._lifted_run_rename_track, ctx)


    await _runner._record_call(ctx.report, "rename_track", ctx.run_rename_track)
    try:
        ctx.original_track_name = ctx.baseline["track_names"].get(
            ctx.midi_track_index, ""
        )
        if ctx.original_track_name:
            ctx.call(
                "rename_track",
                {
                    "track_index": ctx.midi_track_index,
                    "new_name": ctx.original_track_name,
                },
            )
    except Exception:
        pass


async def _step_20(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if not ctx.create_clip_ok:
        ctx.report.record(
            Verification(
                "delete_clip",
                "failed",
                "Skipped: create_clip dependency failed",
            )
        )
    else:

        ctx.run_delete_clip = functools.partial(_steps_3._lifted_run_delete_clip, ctx)


        await _runner._record_call(
            ctx.report, "delete_clip", ctx.run_delete_clip
        )

    # ----- set_parameter_value + readback -----
    if ctx.discovered_param_track_index is None:
        ctx.report.record(
            Verification(
                "set_parameter_value",
                "environment_unavailable",
                "No writable parameter found in the loaded project devices",
            )
        )
    else:

        ctx.run_set_parameter_value = functools.partial(
            _steps_3._lifted_run_set_parameter_value, ctx
        )


        await _runner._record_call(
            ctx.report, "set_parameter_value", ctx.run_set_parameter_value
        )

    # ----- set_plugin_preset -----
    # The probe re-selects the preset that is already
    # active. That still exercises resolution, the write
    # and the verified readback, but leaves the owner's
    # plugin exactly as it was, so no restore is needed.
    (
        ctx.plugin_track_index,
        ctx.plugin_device_index,
    ) = _tcp_reads._discover_first_plugin_device(ctx.baseline, ctx.call)
    ctx.plugin_presets = []
    ctx.plugin_selected = None


async def _step_21(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if ctx.plugin_track_index is not None:
        ctx.presets_resp = ctx.call(
            "get_plugin_presets",
            {
                "track_index": ctx.plugin_track_index,
                "device_index": ctx.plugin_device_index,
            },
        )
        if isinstance(ctx.presets_resp, dict):
            ctx.raw_presets = ctx.presets_resp.get("presets")
            if isinstance(ctx.raw_presets, list):
                ctx.plugin_presets = ctx.raw_presets
            ctx.plugin_selected = ctx.presets_resp.get("selected_preset_index")

    if not ctx.plugin_presets or not isinstance(ctx.plugin_selected, int):
        ctx.report.record(
            Verification(
                "set_plugin_preset",
                "environment_unavailable",
                "no plugin exposing presets found in current Set",
            )
        )
    else:

        ctx.run_set_plugin_preset = functools.partial(
            _steps_3._lifted_run_set_plugin_preset, ctx
        )


        await _runner._record_call(
            ctx.report, "set_plugin_preset", ctx.run_set_plugin_preset
        )

    # ----- live_fade -----
    ctx.run_live_fade = functools.partial(_steps_3._lifted_run_live_fade, ctx)


    await _runner._record_call(ctx.report, "live_fade", ctx.run_live_fade)

    # ----- set_warp_state + readback -----
    ctx.run_set_warp_state = functools.partial(_steps_3._lifted_run_set_warp_state, ctx)


    await _runner._record_call(
        ctx.report, "set_warp_state", ctx.run_set_warp_state
    )

    if "quit" not in ctx.profiles and "quit_ableton" not in ctx.report.recorded:
        ctx.report.record(
            Verification(
                "quit_ableton",
                "manual_required",
                QUIT_ABLETON_MANUAL_REASON,
            )
        )


async def _step_22(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx._run_track_creation = functools.partial(
        _steps_3._lifted__run_track_creation, ctx
    )


    ctx.track_creation_runner = ctx._run_track_creation


async def _step_23(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    await _runner._record_call(
        ctx.report, "get_project_metadata", lambda: ctx.metadata, passed= (
            "live_passed"
        )
    )
    await _runner._record_call(
        ctx.report,
        "get_session_info",
        lambda: ctx.call("get_session_info"),
        passed="live_passed",
    )
    await _runner._record_call(
        ctx.report,
        "get_track_list",
        lambda: ctx.call("get_track_list"),
        passed="live_passed",
    )

    ctx.run_diagnose_clip_targets = functools.partial(
        _steps_1._lifted_run_diagnose_clip_targets, ctx
    )


    await _runner._record_call(
        ctx.report, "diagnose_clip_targets", ctx.run_diagnose_clip_targets
    )

    ctx.run_get_arrangement_clips = functools.partial(
        _steps_1._lifted_run_get_arrangement_clips, ctx
    )


    await _runner._record_call(
        ctx.report,
        "get_arrangement_clips",
        ctx.run_get_arrangement_clips,
        passed="live_passed",
    )

    if ctx.rack_device_target is None:
        _record_unavailable(
            ctx.report,
            "get_device_chains",
            "no Rack device found in the disposable Set",
        )
    else:

        ctx.run_get_device_chains = functools.partial(
            _steps_1._lifted_run_get_device_chains, ctx
        )


        await _runner._record_call(
            ctx.report,
            "get_device_chains",
            ctx.run_get_device_chains,
            passed="live_passed",
        )


async def _step_24(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx.run_get_midi_chain_report = functools.partial(
        _steps_1._lifted_run_get_midi_chain_report, ctx
    )


    await _runner._record_call(
        ctx.report,
        "get_midi_chain_report",
        ctx.run_get_midi_chain_report,
        passed="live_passed",
    )

    ctx.run_describe_instrument = functools.partial(
        _steps_2._lifted_run_describe_instrument, ctx
    )


    await _runner._record_call(
        ctx.report, "describe_instrument", ctx.run_describe_instrument, passed= (
            "live_passed"
        )
    )

    # The mutation slot must start empty, so read an envelope
    # from a separate occupied clip discovered in the Set.
    if ctx.occupied_clip_target is None:
        _record_unavailable(
            ctx.report,
            "get_clip_automation",
            "no occupied session clip found in the disposable Set",
        )
    else:

        ctx.run_get_clip_automation = functools.partial(
            _steps_2._lifted_run_get_clip_automation, ctx
        )


        await _runner._record_call(
            ctx.report,
            "get_clip_automation",
            ctx.run_get_clip_automation,
            passed="live_passed",
        )

    await _runner._record_call(
        ctx.report,
        "get_track_state",
        lambda: ctx.call("get_track_state", {"track_index": ctx.track_index}),
        passed="live_passed",
    )
    await _runner._record_call(
        ctx.report, "get_locators", lambda: ctx.call(
            "get_locators"
        ), passed="live_passed"
    )
