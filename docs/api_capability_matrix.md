# API Capability Matrix

> This document is automatically generated. Do not edit manually.
> It represents the row-by-row source of truth for the capabilities exposed by the Ableton MCP Server.

## Overview

- **Total Public Tools**: 88
- **Routed Remote Commands**: 73
- **WebSocket Targets**: 3

## Categories

### Tempo & Transport

| Tool | Read / Write | Requires Extension | Live Required |
|---|---|---|---|
| `get_song_length` | Read-only | No | Yes |
| `set_current_song_time` | Write | No | Yes |
| `set_tempo` | Write | No | Yes |
| `start_playback` | Write | No | Yes |
| `stop_playback` | Write | No | Yes |

### Mixer & Tracks

| Tool | Read / Write | Requires Extension | Live Required |
|---|---|---|---|
| `create_audio_track` | Write | No | Yes |
| `create_midi_track` | Write | No | Yes |
| `get_routing` | Read-only | No | Yes |
| `get_track_list` | Read-only | No | Yes |
| `get_track_state` | Read-only | No | Yes |
| `live_fade` | Write | No | Yes |
| `merge_groups` | Read-only | No | Yes |
| `move_track` | Read-only | No | Yes |
| `move_track_to_group` | Read-only | No | Yes |
| `rename_track` | Write | No | Yes |
| `reorder_tracks` | Read-only | No | Yes |
| `set_track_color` | Write | No | Yes |
| `set_track_property` | Write | No | Yes |
| `ungroup_track` | Read-only | No | Yes |

### Devices & Parameters

| Tool | Read / Write | Requires Extension | Live Required |
|---|---|---|---|
| `get_device_list` | Read-only | No | Yes |
| `get_parameter_value` | Read-only | No | Yes |
| `list_device_params` | Read-only | No | Yes |
| `load_device_to_track` | Write | Yes | Yes |
| `set_parameter_value` | Write | No | Yes |

### Clips & Scenes

| Tool | Read / Write | Requires Extension | Live Required |
|---|---|---|---|
| `create_clip` | Write | No | Yes |
| `delete_clip` | Write | No | Yes |
| `diagnose_clip_targets` | Read-only | No | Yes |
| `fire_clip` | Write | No | Yes |
| `fire_scene` | Write | No | Yes |
| `get_clip_info` | Read-only | No | Yes |
| `get_clip_summary` | Read-only | No | Yes |
| `get_scene_state` | Read-only | No | Yes |
| `get_scenes` | Read-only | No | Yes |
| `set_clip_color` | Write | No | Yes |
| `set_clip_properties` | Write | No | Yes |

### MIDI Notes & Automation

| Tool | Read / Write | Requires Extension | Live Required |
|---|---|---|---|
| `add_notes_to_clip` | Write | No | Yes |
| `clear_clip_notes` | Write | No | Yes |
| `create_clip_automation` | Write | No | Yes |
| `diagnose_midi_clip` | Read-only | No | Yes |
| `get_clip_notes` | Read-only | No | Yes |

### Locators

| Tool | Read / Write | Requires Extension | Live Required |
|---|---|---|---|
| `bulk_create_cue_points` | Write | No | Yes |
| `create_cue_point` | Write | No | Yes |
| `delete_cue_point` | Write | No | Yes |
| `get_locators` | Read-only | No | Yes |

### Session & Project

| Tool | Read / Write | Requires Extension | Live Required |
|---|---|---|---|
| `get_composition_structure` | Read-only | No | Yes |
| `get_project_metadata` | Read-only | No | Yes |
| `get_selected_context` | Read-only | No | Yes |
| `get_session_info` | Read-only | No | Yes |
| `get_session_overview` | Read-only | No | Yes |
| `lifecycle_status` | Read-only | No | Yes |
| `quit_ableton` | Write | No | Yes |
| `save_set` | Write | No | Yes |
| `take_snapshot` | Read-only | No | Yes |

### Browser

| Tool | Read / Write | Requires Extension | Live Required |
|---|---|---|---|
| `get_browser_categories` | Read-only | No | Yes |
| `search_browser` | Read-only | No | Yes |

### Warping

| Tool | Read / Write | Requires Extension | Live Required |
|---|---|---|---|
| `get_warp_state` | Read-only | Yes | Yes |
| `set_warp_state` | Write | Yes | Yes |

### Batch

| Tool | Read / Write | Requires Extension | Live Required |
|---|---|---|---|
| `run_batch` | Write | No | Yes |

### Diagnostics & State

| Tool | Read / Write | Requires Extension | Live Required |
|---|---|---|---|
| `diff_snapshots_tool` | Read-only | No | No |
| `get_ableton_logs` | Read-only | No | No |
| `get_bridge_status` | Read-only | No | Yes |
| `get_control_surfaces` | Read-only | No | Yes |
| `get_loop_settings` | Read-only | No | Yes |
| `set_loop` | Write | No | Yes |
| `set_loop_length` | Write | No | Yes |
| `set_loop_start` | Write | No | Yes |

### Extension Management

| Tool | Read / Write | Requires Extension | Live Required |
|---|---|---|---|
| `build_extension` | Write | No | No |
| `scaffold_extension` | Write | No | No |

### Analysis (Offline)

| Tool | Read / Write | Requires Extension | Live Required |
|---|---|---|---|
| `analyze_audio` | Read-only | No | No |
| `analyze_mix` | Read-only | No | No |
| `extract_single_cycle` | Read-only | No | No |
| `find_frequency_masking` | Read-only | No | No |

### Search

| Tool | Read / Write | Requires Extension | Live Required |
|---|---|---|---|
| `live_find_clip` | Read-only | No | Yes |
| `live_find_device` | Read-only | No | Yes |
| `live_find_track` | Read-only | No | Yes |

### Other

| Tool | Read / Write | Requires Extension | Live Required |
|---|---|---|---|
| `add_notes_pattern` | Write | No | Yes |
| `create_clip_automation_curve` | Write | No | Yes |
| `delete_arrangement_clip` | Write | No | Yes |
| `describe_instrument` | Read-only | No | Yes |
| `duplicate_session_clip_to_arrangement` | Write | No | Yes |
| `get_arrangement_clips` | Read-only | No | Yes |
| `get_clip_automation` | Read-only | No | Yes |
| `get_device_chains` | Read-only | No | Yes |
| `get_midi_chain_report` | Read-only | No | Yes |
| `get_plugin_presets` | Read-only | No | Yes |
| `move_arrangement_clip` | Write | No | Yes |
| `set_arrangement_clip_properties` | Write | No | Yes |
| `set_plugin_preset` | Write | No | Yes |
