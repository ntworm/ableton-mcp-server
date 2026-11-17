"""Live acceptance steps, part 6 of the lifted runner."""

from __future__ import annotations

import functools
from types import SimpleNamespace

from ..certification import Verification
from . import live_steps_3 as _steps_3
from . import runner as _runner
from .probes import tcp_reads as _tcp_reads
from .safety import _resolve_track_id


async def _step_25(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    await _runner._record_call(
        ctx.report, "take_snapshot", lambda: ctx.call(
            "take_snapshot"
        ), passed="live_passed"
    )
    await _runner._record_call(
        ctx.report,
        "get_control_surfaces",
        lambda: ctx.call("get_control_surfaces"),
        passed="live_passed",
    )
    await _runner._record_call(
        ctx.report, "get_scenes", lambda: ctx.call(
            "get_scenes"
        ), passed="live_passed"
    )
    await _runner._record_call(
        ctx.report,
        "get_scene_state",
        lambda: ctx.call("get_scene_state", {"scene_index": 0}),
        passed="live_passed",
    )
    await _runner._record_call(
        ctx.report,
        "get_loop_settings",
        lambda: ctx.call("get_loop_settings"),
        passed="live_passed",
    )
    await _runner._record_call(
        ctx.report,
        "get_selected_context",
        lambda: ctx.call("get_selected_context"),
        passed="live_passed",
    )
    await _runner._record_call(
        ctx.report,
        "get_clip_summary",
        lambda: ctx.call("get_clip_summary", {"track_index": ctx.track_index}),
        passed="live_passed",
    )
    await _runner._record_call(
        ctx.report,
        "get_clip_notes",
        lambda: ctx.call(
            "get_clip_notes", {
                "track_index": ctx.track_index, "clip_index": ctx.clip_index
            }
        ),
        passed="live_passed",
    )


async def _step_26(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    await _runner._record_call(
        ctx.report,
        "get_clip_info",
        lambda: ctx.call(
            "get_clip_info", {
                "track_index": ctx.track_index, "clip_index": ctx.clip_index
            }
        ),
        passed="live_passed",
    )
    await _runner._record_call(
        ctx.report,
        "get_device_list",
        lambda: ctx.call("get_device_list", {"track_index": ctx.track_index}),
        passed="live_passed",
    )
    if ctx.discovered_param_track_index is not None:
        await _runner._record_call(
            ctx.report,
            "get_parameter_value",
            lambda: ctx.call(
                "get_parameter_value",
                {
                    "track_index": ctx.discovered_param_track_index,
                    "device_index": ctx.discovered_param_device_index,
                    "parameter_name": ctx.discovered_param_name,
                },
            ),
            passed="live_passed",
        )
    else:
        ctx.report.record(
            Verification(
                "get_parameter_value",
                "environment_unavailable",
                "no device parameter found in current Set",
            )
        )
    await _runner._record_call(
        ctx.report,
        "get_routing",
        lambda: ctx.call("get_routing", {"track_index": ctx.track_index}),
        passed="live_passed",
    )
    await _runner._record_call(
        ctx.report,
        "get_browser_categories",
        lambda: ctx.call("get_browser_categories"),
        passed="live_passed",
    )
    # ``search_browser`` should be a small query against a
    # category the runner proves is present, not a guess.
    ctx.categories = ctx.call("get_browser_categories")
    ctx.query = "o" if ctx.categories else ""


async def _step_27(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    await _runner._record_call(
        ctx.report,
        "search_browser",
        lambda: ctx.call("search_browser", {"query": ctx.query, "limit": 10}),
        passed="live_passed",
    )
    await _runner._record_call(
        ctx.report,
        "get_song_length",
        lambda: ctx.call("get_song_length"),
        passed="live_passed",
    )
    # Discover the actual track that contains "bass" so we
    # do not hard-code a name the owner might have changed.
    ctx.matches = ctx.call("live_find_track", {"query": "bass"})
    ctx.discovered_track = ctx.track_index
    if isinstance(ctx.matches, list) and ctx.matches:
        ctx.idx = ctx.matches[0].get("index")
        if isinstance(ctx.idx, int):
            ctx.discovered_track = ctx.idx
    ctx.artifacts["tags"].append(
        f"live_find_track resolved bass track index={ctx.discovered_track}"
    )
    await _runner._record_call(
        ctx.report, "live_find_track", lambda: ctx.matches, passed="live_passed"
    )
    await _runner._record_call(
        ctx.report,
        "live_find_device",
        lambda: ctx.call(
            "live_find_device", {
                "track_index": ctx.track_index, "query": "operator"
            }
        ),
        passed="live_passed",
    )
    await _runner._record_call(
        ctx.report,
        "live_find_clip",
        lambda: ctx.call(
            "live_find_clip", {"track_index": ctx.track_index, "query": "verse"}
        ),
        passed="live_passed",
    )
    # ``list_device_params`` requires ``track_id``, not
    # ``track_index/device_index``.
    ctx.track_id = _resolve_track_id(ctx.client, ctx.track_index)
    await _runner._record_call(
        ctx.report,
        "list_device_params",
        lambda: ctx.call("list_device_params", {"track_id": ctx.track_id}),
        passed="live_passed",
    )


async def _step_28(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    await _runner._record_call(
        ctx.report,
        "get_composition_structure",
        lambda: ctx.call("get_composition_structure"),
        passed="live_passed",
    )
    await _runner._record_call(
        ctx.report,
        "diagnose_midi_clip",
        lambda: ctx.call(
            "diagnose_midi_clip",
            {"track_index": ctx.track_index, "clip_index": ctx.clip_index},
        ),
        passed="live_passed",
    )
    await _runner._record_call(
        ctx.report,
        "lifecycle_status",
        lambda: ctx.call("lifecycle_status"),
        passed="live_passed",
    )

    # ``get_plugin_presets`` needs a third-party plugin in the
    # Set. A disposable acceptance Set is not required to hold
    # one, so its absence is an environment gap rather than a
    # bridge failure — see ENVIRONMENT_OPTIONAL_TOOLS.
    (
        ctx.preset_track_index,
        ctx.preset_device_index,
    ) = _tcp_reads._discover_first_plugin_device(ctx.baseline, ctx.call)
    if ctx.preset_track_index is None:
        ctx.report.record(
            Verification(
                "get_plugin_presets",
                "environment_unavailable",
                "no VST/VST3/AU plugin device found in current Set",
            )
        )
    else:
        await _runner._record_call(
            ctx.report,
            "get_plugin_presets",
            lambda: ctx.call(
                "get_plugin_presets",
                {
                    "track_index": ctx.preset_track_index,
                    "device_index": ctx.preset_device_index,
                },
            ),
            passed="live_passed",
        )


async def _step_29(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx.cleanup_failures = []

    ctx._restore_call = functools.partial(_steps_3._lifted__restore_call, ctx)


    ctx._restore_ws = functools.partial(_steps_3._lifted__restore_ws, ctx)


    ctx._eq = functools.partial(_steps_3._lifted__eq, ctx)


    ctx._restore_call(
        "stop_playback",
        "stop_playback",
        lambda: ctx.call("stop_playback"),
        verify=lambda _o: ctx._eq(
            bool(ctx.call("get_session_info").get("is_playing", False)),
            False,
            "is_playing",
        ),
    )
    ctx._restore_call(
        "set_loop",
        "set_loop",
        lambda: ctx.call("set_loop", {"enabled": ctx.original_loop}),
        verify=lambda _o: ctx._eq(
            bool(ctx.call("get_loop_settings").get("loop", False)),
            ctx.original_loop,
            "loop",
        ),
    )
    ctx._restore_call(
        "set_loop_start",
        "set_loop_start",
        lambda: ctx.call(
            "set_loop_start", {"start_beat": ctx.original_loop_start}
        ),
        verify=lambda _o: ctx._eq(
            float(ctx.call("get_loop_settings").get("loop_start", 0.0)),
            ctx.original_loop_start,
            "loop_start",
        ),
    )
    ctx._restore_call(
        "set_loop_length",
        "set_loop_length",
        lambda: ctx.call(
            "set_loop_length", {"length_beats": ctx.original_loop_length}
        ),
        verify=lambda _o: ctx._eq(
            float(ctx.call("get_loop_settings").get("loop_length", 0.0)),
            ctx.original_loop_length,
            "loop_length",
        ),
    )


async def _step_30(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx._restore_call(
        "set_tempo",
        "set_tempo",
        lambda: ctx.call("set_tempo", {"tempo": ctx.original_tempo}),
        verify=lambda _o: ctx._eq(
            float(ctx.call("get_session_info").get("tempo", 0.0)),
            ctx.original_tempo,
            "tempo",
        ),
    )
    ctx._restore_call(
        "set_current_song_time",
        "set_current_song_time",
        lambda: ctx.call("set_current_song_time", {"time": ctx.original_time}),
        verify=lambda _o: ctx._eq(
            float(ctx.call("get_session_info").get("current_song_time", 0.0)),
            ctx.original_time,
            "current_song_time",
        ),
    )
    if ctx.cue_created:

        ctx._verify_cue_absent = functools.partial(
            _steps_3._lifted__verify_cue_absent, ctx
        )


        ctx._restore_call(
            "delete_cue_point",
            "delete_cue_point",
            lambda: ctx.call("delete_cue_point", {"time": ctx.cue_time}),
            verify=ctx._verify_cue_absent,
        )
    if ctx.original_warp is not None:
        ctx.expected_warp = bool(ctx.original_warp.get("warping", False))

        ctx._verify_warp = functools.partial(_steps_3._lifted__verify_warp, ctx)


        await ctx._restore_ws(
            "set_warp_state",
            "set_warp_state",
            lambda: ctx.call_ws(
                "set_warp_state",
                {
                    "track_index": ctx.audio_track_index,
                    "clip_index": ctx.audio_clip_index,
                    "warping": ctx.expected_warp,
                },
            ),
            verify=ctx._verify_warp,
        )


async def _step_31(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx._cleanup_types = ctx.baseline.get("track_types", {}) or {}
    # The mute / solo cleanup loops iterate over
    # every track that has a mixer property: midi,
    # audio, and returns. Master is excluded
    # because Live rejects mute and solo on the
    # master track.
    ctx._cleanup_indices_mute_solo = sorted(
        idx
        for idx, ttype in ctx._cleanup_types.items()
        if ttype in ("midi", "audio", "return")
    )
    # The arm cleanup loop is narrower: only midi
    # and audio tracks may be armed. Master has no
    # arm state, and the disposable Set's return
    # tracks are explicitly out of scope for arm
    # restoration.
    ctx._cleanup_indices_arm = sorted(
        idx
        for idx, ttype in ctx._cleanup_types.items()
        if ttype in ("midi", "audio")
    )
    for _loop_item_11 in ctx._cleanup_indices_mute_solo:
        ctx.idx = _loop_item_11
        ctx.original = bool(
            ctx.baseline.get("track_mutes", {}).get(ctx.idx, False)
        )

        ctx._restore_mute = functools.partial(
            _steps_3._lifted__restore_mute, ctx, _idx=ctx.idx, _original=ctx.original
        )


        ctx._verify_mute = functools.partial(
            _steps_3._lifted__verify_mute, ctx, _idx=ctx.idx, _original=ctx.original
        )


        ctx._restore_call(
            f"set_track_property(mute:{ctx.idx})",
            "set_track_property",
            ctx._restore_mute,
            verify=ctx._verify_mute,
        )


async def _step_32(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    for _loop_item_12 in ctx._cleanup_indices_mute_solo:
        ctx.idx = _loop_item_12
        ctx.original = bool(
            ctx.baseline.get("track_solos", {}).get(ctx.idx, False)
        )

        ctx._restore_solo = functools.partial(
            _steps_3._lifted__restore_solo, ctx, _idx=ctx.idx, _original=ctx.original
        )


        ctx._verify_solo = functools.partial(
            _steps_3._lifted__verify_solo, ctx, _idx=ctx.idx, _original=ctx.original
        )


        ctx._restore_call(
            f"set_track_property(solo:{ctx.idx})",
            "set_track_property",
            ctx._restore_solo,
            verify=ctx._verify_solo,
        )
    for _loop_item_13 in ctx._cleanup_indices_arm:
        ctx.idx = _loop_item_13
        ctx.original = bool(
            ctx.baseline.get("track_arms", {}).get(ctx.idx, False)
        )

        ctx._restore_arm = functools.partial(
            _steps_3._lifted__restore_arm, ctx, _idx=ctx.idx, _original=ctx.original
        )


        ctx._verify_arm = functools.partial(
            _steps_3._lifted__verify_arm, ctx, _idx=ctx.idx, _original=ctx.original
        )


        ctx._restore_call(
            f"set_track_property(arm:{ctx.idx})",
            "set_track_property",
            ctx._restore_arm,
            verify=ctx._verify_arm,
        )
