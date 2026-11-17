"""Live acceptance steps, part 2 of the lifted runner."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from ..certification import Verification
from . import live_steps_4 as _steps_4


async def _lifted_run_describe_instrument(ctx: SimpleNamespace, ) -> str:
    payload = ctx.call("describe_instrument", {"track_index": ctx.track_index})
    if "has_instrument" not in payload:
        raise AssertionError("describe_instrument must report has_instrument")
    return f"instrument={payload.get('name', 'none')}"


async def _lifted_run_get_clip_automation(ctx: SimpleNamespace, ) -> str:
    automation_track_index, automation_clip_index = (
        ctx.occupied_clip_target
    )
    payload = ctx.call(
        "get_clip_automation",
        {
            "track_index": automation_track_index,
            "clip_index": automation_clip_index,
            "parameter_name": "volume",
            "resolution": 1.0,
        },
    )
    if "has_envelope" not in payload:
        raise AssertionError(
            "get_clip_automation must report has_envelope"
        )
    return f"envelope={payload['has_envelope']}"


async def _lifted_get_warp_readback(ctx: SimpleNamespace, ) -> dict[str, Any]:
    warp = await ctx.call_ws(
        "get_warp_state",
        {
            "track_index": ctx.audio_track_index,
            "clip_index": ctx.audio_clip_index,
        },
    )
    # WS tools serialize to JSON strings — normalize.
    if isinstance(warp, str):
        import json as _json

        return cast(dict[str, Any], _json.loads(warp))
    return dict(warp or {})


async def _lifted_read_warp(ctx: SimpleNamespace, ) -> dict[str, Any]:
    raw = await ctx.call_ws(
        "get_warp_state",
        {
            "track_index": ctx.audio_track_index,
            "clip_index": ctx.audio_clip_index,
        },
    )
    import json as _json

    if isinstance(raw, str):
        return cast(dict[str, Any], _json.loads(raw))
    return dict(raw or {})


async def _lifted_run_save_set(ctx: SimpleNamespace, ) -> None:
    lctx = SimpleNamespace(
        ctx=ctx,
    )
    lctx.save_result = lctx.ctx.call("save_set")
    if not isinstance(lctx.save_result, dict):
        raise AssertionError(
            f"unexpected save_set response: {lctx.save_result!r}"
        )
    lctx.saved = lctx.save_result.get("saved")
    lctx.api_avail = lctx.save_result.get("api_available")
    lctx.gui_workflow = lctx.save_result.get("gui_workflow")

    if lctx.saved is True and lctx.api_avail is True:
        lctx.meta = lctx.ctx.call("get_project_metadata")
        if lctx.meta.get("is_dirty") is not False:
            lctx.dirty_val = lctx.meta.get("is_dirty")
            raise AssertionError(
                "save_set returned saved=true but "
                f"get_project_metadata still shows is_dirty={lctx.dirty_val}"
            )
        lctx.ctx.report.record(Verification("save_set", "live_passed", "saved=true"))
        return
    if lctx.saved is False and lctx.api_avail is False:
        await _steps_4._step_7(lctx)
        return
    raise AssertionError(f"ambiguous save_set response: {lctx.save_result}")


async def _lifted_run_create_cue(ctx: SimpleNamespace, ) -> str:
    ctx.call("create_cue_point", {"name": ctx.cue_name, "time": ctx.cue_time})
    locators = ctx.call("get_locators")
    if not any(
        abs(float(item.get("time", -1)) - ctx.cue_time) < 0.01
        and item.get("name") == ctx.cue_name
        for item in locators
    ):
        raise AssertionError("create_cue_point readback failed")
    return f"name={ctx.cue_name} time={ctx.cue_time}"


async def _lifted_run_bulk_cue(ctx: SimpleNamespace, ) -> str:
    bulk_targets = [
        {"name": ctx.bulk_cue_name, "time": ctx.bulk_cue_time},
    ]
    ctx.call("bulk_create_cue_points", {"items": bulk_targets})
    locators = ctx.call("get_locators")
    if not any(item.get("name") == ctx.bulk_cue_name for item in locators):
        raise AssertionError("bulk_create_cue_points readback failed")
    return f"created={len(bulk_targets)}"


async def _lifted_run_delete_cue(ctx: SimpleNamespace, ) -> str:
    delete_result = ctx.call("delete_cue_point", {"time": ctx.cue_time})
    if not bool(delete_result.get("deleted", False)):
        raise AssertionError("delete_cue_point did not return deleted=true")
    locators = ctx.call("get_locators")
    if any(
        abs(float(item.get("time", -1)) - ctx.cue_time) < 0.01
        for item in locators
    ):
        raise AssertionError("delete_cue_point readback left cue in place")

    # Second delete: bulk cue.
    delete_bulk = ctx.call("delete_cue_point", {"time": ctx.bulk_cue_time})
    if not bool(delete_bulk.get("deleted", False)):
        raise AssertionError("delete_cue_point (bulk) readback failed")
    return f"deleted={delete_result.get('deleted')}"


async def _lifted_run_set_tempo(ctx: SimpleNamespace, ) -> str:
    ctx.call("set_tempo", {"tempo": ctx.tempo_one})
    rb_tempo = float(ctx.call("get_session_info")["tempo"])
    if abs(rb_tempo - ctx.tempo_one) > 0.01:
        raise AssertionError("set_tempo readback mismatch")
    return f"tempo={ctx.tempo_one} readback={rb_tempo}"


async def _lifted_run_set_time(ctx: SimpleNamespace, ) -> str:
    ctx.call("set_current_song_time", {"time": 8.0})
    rb_time = float(ctx.call("get_session_info")["current_song_time"])
    if abs(rb_time - 8.0) > 0.5:
        raise AssertionError(
            f"set_current_song_time readback {rb_time} far from 8.0"
        )
    return f"time=8.0 readback={rb_time}"


async def _lifted_run_set_loop_start(ctx: SimpleNamespace, ) -> str:
    ctx.call("set_loop_start", {"start_beat": 4.0})
    rb_loop_start = float(ctx.call("get_loop_settings")["loop_start"])
    if abs(rb_loop_start - 4.0) > 0.01:
        raise AssertionError("set_loop_start readback mismatch")
    return f"start_beat=4.0 readback={rb_loop_start}"


async def _lifted_run_set_loop_length(ctx: SimpleNamespace, ) -> str:
    ctx.call("set_loop_length", {"length_beats": 8.0})
    rb_loop_length = float(ctx.call("get_loop_settings")["loop_length"])
    if abs(rb_loop_length - 8.0) > 0.01:
        raise AssertionError("set_loop_length readback mismatch")
    return f"length_beats=8.0 readback={rb_loop_length}"


async def _lifted_run_set_loop(ctx: SimpleNamespace, ) -> str:
    ctx.call("set_loop", {"enabled": True})
    rb_loop = bool(ctx.call("get_loop_settings")["loop"])
    if not rb_loop:
        raise AssertionError("set_loop readback did not enable loop")
    return f"enabled=True readback={rb_loop}"


async def _lifted_run_create_clip(ctx: SimpleNamespace, ) -> str:
    ctx.call(
        "create_clip",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": ctx.clip_index,
            "length_beats": 4.0,
        },
    )
    clip_info = ctx.call(
        "get_clip_info",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": ctx.clip_index,
        },
    )
    if not bool(clip_info.get("has_clip", False)):
        raise AssertionError("create_clip readback failed")
    return f"track={ctx.midi_track_index} slot={ctx.clip_index}"


async def _lifted_run_add_notes(ctx: SimpleNamespace, ) -> str:
    notes = [
        {
            "pitch": pitch,
            "start_time": float(index),
            "duration": 0.75,
            "velocity": 72 + index * 4,
            "mute": False,
        }
        for index, pitch in enumerate((60, 64, 67, 72))
    ]
    added = ctx.call(
        "add_notes_to_clip",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": ctx.clip_index,
            "notes": notes,
        },
    )
    if int(added.get("added", 0)) != 4:
        raise AssertionError(
            f"add_notes_to_clip added={added.get('added')} expected 4"
        )
    observed = ctx.call(
        "get_clip_notes",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": ctx.clip_index,
        },
    )
    if len(observed) != 4:
        raise AssertionError("add_notes_to_clip readback failed")
    return "added=4, observed=4"


async def _lifted_run_clear_notes(ctx: SimpleNamespace, ) -> str:
    ctx.call(
        "clear_clip_notes",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": ctx.clip_index,
        },
    )
    cleared = ctx.call(
        "get_clip_notes",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": ctx.clip_index,
        },
    )
    if cleared:
        raise AssertionError("clear_clip_notes did not empty clip")
    return "notes cleared (0)"


async def _lifted_run_set_clip_props(ctx: SimpleNamespace, ) -> str:
    ctx.call(
        "set_clip_properties",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": ctx.clip_index,
            "name": "ABLETON_MCP_ACCEPTANCE",
        },
    )
    info = ctx.call(
        "get_clip_info",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": ctx.clip_index,
        },
    )
    if info.get("name") != "ABLETON_MCP_ACCEPTANCE":
        raise AssertionError("set_clip_properties did not rename clip")
    ctx.artifacts["tags"].append("clip:ABLETON_MCP_ACCEPTANCE")
    return "name=ABLETON_MCP_ACCEPTANCE"


async def _lifted_run_clip_automation(ctx: SimpleNamespace, ) -> str:
    auto_points = [
        {"time": 0.0, "value": 0.0},
        {"time": 1.0, "value": 1.0},
    ]
    auto_resp = ctx.call(
        "create_clip_automation",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": ctx.clip_index,
            "parameter_name": "volume",
            "automation_points": auto_points,
        },
    )
    if not isinstance(auto_resp, dict):
        raise AssertionError(
            "create_clip_automation must return a dict "
            "with 'points_written'"
        )
    if int(auto_resp.get("points_written", -1)) != len(auto_points):
        raise AssertionError(
            "create_clip_automation points readback "
            f"mismatch: {auto_resp}"
        )
    return f"points_written={auto_resp.get('points_written')}"


async def _lifted_run_start_playback(ctx: SimpleNamespace, ) -> str:
    ctx.call("start_playback")
    playback_state = ctx.call("get_session_info")
    if not bool(playback_state.get("is_playing", False)):
        raise AssertionError("start_playback did not engage transport")
    return f"is_playing={playback_state.get('is_playing')}"


async def _lifted_run_stop_playback(ctx: SimpleNamespace, ) -> str:
    ctx.call("stop_playback")
    stop_state = ctx.call("get_session_info")
    if bool(stop_state.get("is_playing", False)):
        raise AssertionError("stop_playback left transport playing")
    return "transport stopped and readback confirmed"


async def _lifted_run_run_batch(ctx: SimpleNamespace, ) -> str:
    batch = ctx.call(
        "run_batch",
        {
            "commands": [
                {"type": "set_tempo", "params": {"tempo": ctx.tempo_two}},
                {"type": "set_loop", "params": {"enabled": True}},
                {
                    "type": "create_clip",
                    "params": {
                        "track_index": ctx.midi_track_index,
                        "clip_index": ctx.clip_index,
                        "length_beats": 4.0,
                    },
                },
                {"type": "set_tempo", "params": {"tempo": ctx.tempo_one}},
            ],
        },
    )
    if (
        int(batch.get("completed", 0)) < 2
        or int(batch.get("aborted_at", -1)) < 2
        or bool(batch.get("rolled_back", True))
    ):
        raise AssertionError(f"Unexpected run_batch result: {batch}")
    return (
        f"completed={batch.get('completed')} "
        f"aborted_at={batch.get('aborted_at')}"
    )


async def _lifted_run_fire_clip(ctx: SimpleNamespace, ) -> str:
    fire_resp = ctx.call(
        "fire_clip",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": ctx.clip_index,
        },
    )
    if not isinstance(fire_resp, dict):
        raise AssertionError("fire_clip must return a dict")
    if not bool(fire_resp.get("fired", False)):
        raise AssertionError("fire_clip did not return fired=true")
    playing = ctx.call("get_session_info").get("is_playing", False)
    if not bool(playing):
        raise AssertionError("fire_clip left transport stopped")
    return f"track={ctx.midi_track_index} slot={ctx.clip_index}"


async def _lifted_run_fire_scene(ctx: SimpleNamespace, ) -> str:
    scene_resp = ctx.call("fire_scene", {"scene_index": ctx.clip_index})
    if not isinstance(scene_resp, dict):
        raise AssertionError("fire_scene must return a dict")
    if "scene_index" not in scene_resp:
        raise AssertionError("fire_scene response missing scene_index")
    scene_playing = ctx.call("get_session_info").get("is_playing", False)
    if not bool(scene_playing):
        raise AssertionError("fire_scene left transport stopped")
    return f"scene={ctx.clip_index}"


async def _lifted_run_set_track_prop(ctx: SimpleNamespace, ) -> str:
    ctx.call(
        "set_track_property",
        {
            "track_index": ctx.midi_track_index,
            "property": "mute",
            "value": True,
        },
    )
    state = ctx.call("get_track_state", {"track_index": ctx.midi_track_index})
    if not bool(state.get("mute", False)):
        raise AssertionError("set_track_property mute readback failed")
    return "mute=True readback OK"


async def _lifted_run_set_track_color(ctx: SimpleNamespace, ) -> str:
    ctx.call(
        "set_track_color",
        {
            "track_index": ctx.midi_track_index,
            "color_index": ctx._probe_color_index,
        },
    )
    state = ctx.call("get_track_state", {"track_index": ctx.midi_track_index})
    observed = state.get("color_index")
    if observed != ctx._probe_color_index:
        raise AssertionError(
            "set_track_color readback mismatch: "
            f"observed={observed!r} expected={ctx._probe_color_index!r}"
        )
    return f"color_index={ctx._probe_color_index} readback OK"


async def _lifted_run_set_clip_color(ctx: SimpleNamespace, ) -> str:
    ctx.call(
        "set_clip_color",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": ctx.clip_index,
            "color_index": 1,
        },
    )
    info = ctx.call(
        "get_clip_info",
        {
            "track_index": ctx.midi_track_index,
            "clip_index": ctx.clip_index,
        },
    )
    observed = (
        info.get("color_index") if isinstance(info, dict) else None
    )
    if observed != 1:
        raise AssertionError(
            "set_clip_color readback mismatch: "
            f"observed={observed!r} expected=1"
        )
    return "clip color_index=1 readback OK"


async def _lifted_run_rename_track(ctx: SimpleNamespace, ) -> str:
    tag_name = "ABLETON_MCP_ACCEPTANCE"
    ctx.call(
        "rename_track",
        {
            "track_index": ctx.midi_track_index,
            "new_name": tag_name,
        },
    )
    tracks = ctx.call("get_track_list")
    renamed = next(
        (t for t in tracks if int(t.get("index", -1)) == ctx.midi_track_index),
        None,
    )
    if renamed is None or renamed.get("name") != tag_name:
        raise AssertionError("rename_track readback failed")
    ctx.artifacts["tags"].append(f"track:{tag_name}")
    return f"renamed to {tag_name}"


def _lifted_arrangement_clip_at(ctx: SimpleNamespace, beat: float) -> dict[str, Any] | None:
    listing = ctx.call(
        "get_arrangement_clips",
        {"track_index": ctx.midi_track_index},
    )
    for entry in listing.get("clips", []):
        start = entry.get("start_time")
        if start is not None and abs(float(start) - beat) < 0.01:
            return dict(entry)
    return None
