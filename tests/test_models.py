from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from ableton_mcp_server.models import (
    TOOL_REQUEST_MODELS,
    AddNotesToClipRequest,
    BulkCuePointsRequest,
    CreateClipRequest,
    CuePointSpec,
    NoteSpec,
    RunBatchRequest,
    SetTempoRequest,
)


def test_every_public_tool_has_an_explicit_request_model() -> None:
    reads = {
        "get_session_info",
        "get_bridge_status",
        "get_track_list",
        "get_track_state",
        "get_locators",
        "take_snapshot",
        "get_ableton_logs",
        "get_control_surfaces",
        "get_scenes",
        "get_scene_state",
        "get_project_metadata",
        "get_loop_settings",
        "get_selected_context",
        "get_clip_summary",
        "get_clip_notes",
        "get_device_list",
        "get_parameter_value",
        "get_routing",
        "get_browser_categories",
        "diff_snapshots_tool",
        "get_song_length",
        "live_find_track",
        "list_device_params",
        # v0.3.0
        "get_composition_structure",
        "diagnose_midi_clip",
        "get_warp_state",
        "get_clip_info",
        "get_session_overview",
        "search_browser",
    }
    mutations = {
        "create_cue_point",
        "bulk_create_cue_points",
        "delete_cue_point",
        "set_current_song_time",
        "set_tempo",
        "start_playback",
        "stop_playback",
        "set_loop",
        "set_loop_start",
        "set_loop_length",
        "run_batch",
        "add_notes_to_clip",
        "fire_clip",
        "create_clip",
        # v0.3.0
        "create_midi_track",
        "rename_track",
        "set_warp_state",
        "load_device_to_track",
        "set_parameter_value",
        "delete_clip",
        "clear_clip_notes",
        "fire_scene",
        "set_track_property",
        "set_clip_properties",
        "create_clip_automation",
        "scaffold_extension",
        "build_extension",
        "lifecycle_status",
        "save_set",
        "quit_ableton",
        "live_fade",
        "create_audio_track",
        "analyze_audio",
        "find_frequency_masking",
        "analyze_mix",
        "extract_single_cycle",
    }
    assert set(TOOL_REQUEST_MODELS) == reads | mutations
    assert len(TOOL_REQUEST_MODELS) == 65
    assert len(set(TOOL_REQUEST_MODELS.values())) == 65


@pytest.mark.parametrize("tempo", [19.99, 999.01, math.nan, math.inf])
def test_tempo_rejects_out_of_range_or_non_finite_values(tempo: float) -> None:
    with pytest.raises(ValidationError):
        SetTempoRequest(tempo=tempo)


def test_models_forbid_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CreateClipRequest(track_index=0, clip_index=0, length_beats=4.0, unexpected=True)


def test_cue_and_note_models_normalize_without_losing_values() -> None:
    cue = CuePointSpec(name=" Verse ", time=16)
    assert cue.name == "Verse"
    request = AddNotesToClipRequest(
        track_index=0,
        clip_index=1,
        notes=[{"pitch": 60, "start_time": 0, "duration": 1, "velocity": 100}],
    )
    assert request.notes[0].pitch == 60
    assert request.notes[0].duration == 1.0


def test_note_spec_accepts_bounded_expression_fields() -> None:
    note = NoteSpec(
        pitch=60,
        start_time=0,
        duration=1,
        probability=0.5,
        release_velocity=64,
        velocity_deviation=-12,
    )
    assert note.probability == 0.5
    assert note.release_velocity == 64
    assert note.velocity_deviation == -12

    with pytest.raises(ValidationError):
        NoteSpec(pitch=60, start_time=0, duration=1, probability=1.1)


def test_bulk_has_safe_size_bounds() -> None:
    with pytest.raises(ValidationError):
        BulkCuePointsRequest(items=[])
    with pytest.raises(ValidationError):
        BulkCuePointsRequest(items=[CuePointSpec(name=f"cue-{i}", time=i) for i in range(501)])


def test_batch_rejects_nested_batch_and_blocked_commands() -> None:
    with pytest.raises(ValidationError, match="run_batch cannot contain run_batch"):
        RunBatchRequest(commands=[{"type": "run_batch", "params": {"commands": []}}])
    with pytest.raises(ValidationError, match="not an allowed mutation"):
        RunBatchRequest(commands=[{"type": "delete_track", "params": {"track_index": 0}}])
