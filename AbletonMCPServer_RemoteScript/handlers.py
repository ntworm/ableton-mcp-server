"""Registry of the named command handlers the dispatcher falls back to."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .arrangement import cmd_diagnose_clip_targets, cmd_get_arrangement_clips
from .automation import cmd_get_clip_automation
from .clips import (
    cmd_add_notes_pattern,
    cmd_add_notes_to_clip,
    cmd_create_clip,
    cmd_delete_clip,
    cmd_fire_clip,
    cmd_fire_scene,
)
from .composition import cmd_diagnose_midi_clip, cmd_get_composition_structure
from .devices import cmd_get_parameter_value, cmd_get_plugin_presets, cmd_list_device_params
from .instruments import cmd_describe_instrument, cmd_get_device_chains, cmd_get_midi_chain_report
from .lifecycle import cmd_lifecycle_status, cmd_save_set, live_fade_steps, quit_ableton_steps
from .reads import (
    cmd_get_browser_categories,
    cmd_get_clip_info,
    cmd_get_clip_notes,
    cmd_get_clip_summary,
    cmd_get_control_surfaces,
    cmd_get_device_list,
    cmd_get_locators,
    cmd_get_loop_settings,
    cmd_get_project_metadata,
    cmd_get_routing,
    cmd_get_scene_state,
    cmd_get_scenes,
    cmd_get_selected_context,
    cmd_get_session_info,
    cmd_get_song_length,
    cmd_get_track_list,
    cmd_get_track_state,
    cmd_live_find_clip,
    cmd_live_find_device,
    cmd_live_find_track,
    cmd_search_browser,
    cmd_take_snapshot,
)
from .tracks import cmd_create_audio_track, cmd_create_midi_track, cmd_rename_track

CommandHandler = Callable[[Any, Any, dict[str, Any]], Any]


COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "get_session_info": cmd_get_session_info,
    "get_track_list": cmd_get_track_list,
    "get_track_state": cmd_get_track_state,
    "get_locators": cmd_get_locators,
    "take_snapshot": cmd_take_snapshot,
    "get_control_surfaces": cmd_get_control_surfaces,
    "get_scenes": cmd_get_scenes,
    "get_scene_state": cmd_get_scene_state,
    "get_project_metadata": cmd_get_project_metadata,
    "get_loop_settings": cmd_get_loop_settings,
    "get_selected_context": cmd_get_selected_context,
    "get_clip_summary": cmd_get_clip_summary,
    "get_clip_notes": cmd_get_clip_notes,
    "get_clip_info": cmd_get_clip_info,
    "get_device_list": cmd_get_device_list,
    "get_parameter_value": cmd_get_parameter_value,
    "get_routing": cmd_get_routing,
    "get_browser_categories": cmd_get_browser_categories,
    "search_browser": cmd_search_browser,
    "get_song_length": cmd_get_song_length,
    "live_find_track": cmd_live_find_track,
    "live_find_device": cmd_live_find_device,
    "live_find_clip": cmd_live_find_clip,
    "list_device_params": cmd_list_device_params,
    # v0.5.4 — plugin presets bypass Live's Configure gate
    "get_plugin_presets": cmd_get_plugin_presets,
    "create_clip": cmd_create_clip,
    "fire_clip": cmd_fire_clip,
    "delete_clip": cmd_delete_clip,
    "fire_scene": cmd_fire_scene,
    "add_notes_to_clip": cmd_add_notes_to_clip,
    # v0.3.0
    "get_composition_structure": cmd_get_composition_structure,
    "diagnose_midi_clip": cmd_diagnose_midi_clip,
    "create_midi_track": cmd_create_midi_track,
    "rename_track": cmd_rename_track,
    # v0.5.0 — audio-track mirror of create_midi_track. Zero-touch on the midi path.
    "create_audio_track": cmd_create_audio_track,
    # v0.5.3 — clip colour target discovery (Session + Arrangement)
    "diagnose_clip_targets": cmd_diagnose_clip_targets,
    # v0.5.5 — Arrangement timeline read
    "get_arrangement_clips": cmd_get_arrangement_clips,
    # v0.5.6 — instrument comprehension and authoring shorthands
    "get_device_chains": cmd_get_device_chains,
    "get_midi_chain_report": cmd_get_midi_chain_report,
    "describe_instrument": cmd_describe_instrument,
    "get_clip_automation": cmd_get_clip_automation,
    "add_notes_pattern": cmd_add_notes_pattern,
    # v0.5.0 — set lifecycle
    "lifecycle_status": cmd_lifecycle_status,
    "save_set": cmd_save_set,
    "quit_ableton": quit_ableton_steps,
    "live_fade": live_fade_steps,
}
