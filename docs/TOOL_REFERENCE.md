# Tool Reference

The FastMCP server exposes 37 snake_case tools. Remote examples below show the JSONL command envelope after MCP/Pydantic validation. All error responses use `{"status":"error","code","message","hint?"}`.

## Reads

### `get_session_info()`

- Params: none.
- Returns: tempo, time signature, playing state, and current song time.
- Request: `{"type":"get_session_info","params":{}}`
- Response: `{"status":"ok","result":{"tempo":120.0,"signature_numerator":4,"signature_denominator":4,"is_playing":false,"current_song_time":0.0}}`
- Edge cases / side effects: pure read; fails if the Remote Script is unavailable.

### `get_bridge_status()`

- Params: none.
- Returns: endpoint, Python runtime/WSL detection, bridge availability, a live `get_session_info` probe, error, and actionable hint.
- Request: local MCP invocation; the probe sends `{"type":"get_session_info","params":{}}` to the Remote Script.
- Response: `{"status":"ok","bridge_available":true,"endpoint":{"host":"127.0.0.1","port":9888},"live":{"tempo":120.0}}`
- Edge cases / side effects: pure diagnostic read; under WSL, a failed native Linux probe recommends invoking the native Windows executable rather than exposing the listener.

### `get_track_list()`

- Params: none.
- Returns: all regular, return, and master tracks as `{id,index,name,type}`.
- Request: `{"type":"get_track_list","params":{}}`
- Response: `{"status":"ok","result":[{"id":"track:0","index":0,"name":"Bass","type":"midi"}]}`
- Edge cases / side effects: pure read; re-list after structural changes.

### `get_track_state(track_index: int)`

- Params: non-negative `track_index` in the combined regular/return/master list.
- Returns: path-id, mixer state, sends, devices, parameters, and Session clip slots.
- Request: `{"type":"get_track_state","params":{"track_index":0}}`
- Response: `{"status":"ok","result":{"id":"track:0","name":"Bass","devices":[],"clip_slots":[]}}`
- Edge cases / side effects: pure read; invalid indexes return `INVALID_PARAMS`.

### `get_locators()`

- Params: none.
- Returns: cue-point names and float beat times.
- Request: `{"type":"get_locators","params":{}}`
- Response: `{"status":"ok","result":[{"name":"Verse","time":8.0}]}`
- Edge cases / side effects: pure read; custom beat-time objects are converted to floats.

### `take_snapshot()`

- Params: none.
- Returns: schema version, Unix epoch capture time, Live version, transport, tracks, control surfaces, scenes, locators, selection, metadata, and loop settings.
- Request: `{"type":"take_snapshot","params":{}}`
- Response: `{"status":"ok","result":{"schema_version":1,"captured_at_unix_ms":1719878400000,"tracks":[]}}`
- Edge cases / side effects: pure read; large Sets create large responses.

### `get_ableton_logs(lines: int = 100)`

- Params: `lines`, 1..5000.
- Returns: tail text from the newest supported Ableton `Preferences/Log.txt` location.
- Request: local MCP argument `{"lines":100}`; no Remote Script command.
- Response: plain text containing log lines or an `Error:` diagnostic.
- Edge cases / side effects: local filesystem read only; supports Windows, macOS, mounted Windows profiles under WSL, and the `ABLETON_MCP_LOG_PATH` override; missing logs are not protocol errors.

### `get_control_surfaces()`

- Params: none.
- Returns: available control-surface class names.
- Request: `{"type":"get_control_surfaces","params":{}}`
- Response: `{"status":"ok","result":[{"name":"AbletonMCPServer","type":"remote_script"}]}`
- Edge cases / side effects: pure read; Live can omit unavailable surfaces.

### `get_scenes()`

- Params: none.
- Returns: scene index, name, and `is_empty`.
- Request: `{"type":"get_scenes","params":{}}`
- Response: `{"status":"ok","result":[{"index":0,"name":"Verse","is_empty":false}]}`
- Edge cases / side effects: pure read; a scene is non-empty when any slot contains a clip.

### `get_scene_state(scene_index: int)`

- Params: non-negative scene index.
- Returns: scene summary and its per-track clip-slot state.
- Request: `{"type":"get_scene_state","params":{"scene_index":0}}`
- Response: `{"status":"ok","result":{"index":0,"name":"Verse","clip_slots":[{"track_id":"track:0"}]}}`
- Edge cases / side effects: pure read; invalid indexes return `INVALID_PARAMS`.

### `get_project_metadata()`

- Params: none.
- Returns: Set name, file path, and dirty flag.
- Request: `{"type":"get_project_metadata","params":{}}`
- Response: `{"status":"ok","result":{"song_name":"Debug Set","file_path":"C:\\Music\\Debug Set.als","is_dirty":false}}`
- Edge cases / side effects: pure read; unsaved Sets can have an empty path.

### `get_loop_settings()`

- Params: none.
- Returns: Arrangement loop enablement, start, and length in beats.
- Request: `{"type":"get_loop_settings","params":{}}`
- Response: `{"status":"ok","result":{"loop":false,"loop_start":0.0,"loop_length":4.0}}`
- Edge cases / side effects: pure read; values can change during user interaction.

### `get_selected_context()`

- Params: none.
- Returns: selected track, scene, and device indexes/names/path-ids.
- Request: `{"type":"get_selected_context","params":{}}`
- Response: `{"status":"ok","result":{"selected_track_id":"track:0","selected_scene_index":0}}`
- Edge cases / side effects: pure read; absent selections use `null` or `-1`.

### `get_clip_summary(track_index: int)`

- Params: non-negative track index.
- Returns: Session clip slots with slot/clip path-ids, name, length, type, and playing state.
- Request: `{"type":"get_clip_summary","params":{"track_index":0}}`
- Response: `{"status":"ok","result":[{"id":"track:0/clipslot:0","clip_id":"track:0/clipslot:0/clip","has_clip":true}]}`
- Edge cases / side effects: pure read; return/master tracks produce `WRONG_TYPE`.

### `get_clip_notes(track_index: int, clip_index: int)`

- Params: non-negative track and Session slot indexes.
- Returns: MIDI note pitch, start, duration, velocity, and mute state.
- Request: `{"type":"get_clip_notes","params":{"track_index":0,"clip_index":0}}`
- Response: `{"status":"ok","result":[{"pitch":60,"start_time":0.0,"duration":1.0,"velocity":100,"mute":false}]}`
- Edge cases / side effects: pure read; empty slots return structured `[]` with a textual `[]` fallback, while audio clips return typed `WRONG_TYPE`.

### `get_device_list(track_index: int)`

- Params: non-negative track index.
- Returns: device path-ids, class/name/activity, and parameter snapshots.
- Request: `{"type":"get_device_list","params":{"track_index":0}}`
- Response: `{"status":"ok","result":[{"id":"track:0/device:0","name":"Operator","parameters":[]}]}`
- Edge cases / side effects: pure read; special tracks can return an empty list.

### `get_parameter_value(track_index: int, device_index: int, parameter_name: str)`

- Params: non-negative track/device indexes and exact non-empty parameter name.
- Returns: parameter path-id, value, bounds, enablement, and quantization.
- Request: `{"type":"get_parameter_value","params":{"track_index":0,"device_index":0,"parameter_name":"Device On"}}`
- Response: `{"status":"ok","result":{"id":"track:0/device:0/param:0","name":"Device On","value":1.0,"min":0.0,"max":1.0}}`
- Edge cases / side effects: pure read; lookup is case-sensitive and exact.

### `get_routing(track_index: int)`

- Params: non-negative track index.
- Returns: input/output routing and sub-routing display names.
- Request: `{"type":"get_routing","params":{"track_index":0}}`
- Response: `{"status":"ok","result":{"input_routing":"Ext. In","output_routing":"Master"}}`
- Edge cases / side effects: pure read; unavailable routes are empty strings.

### `get_browser_categories()`

- Params: none.
- Returns: top-level Browser category display names available in the running Live version.
- Request: `{"type":"get_browser_categories","params":{}}`
- Response: `{"status":"ok","result":["Sounds","Drums","Instruments"]}`
- Edge cases / side effects: pure read; missing version-specific categories are omitted.

### `diff_snapshots_tool(snap_a: dict, snap_b: dict)`

- Params: two JSON-object snapshots.
- Returns: deterministic `added`, `removed`, and `changed` path lists.
- Request: local MCP arguments `{"snap_a":{"tempo":120},"snap_b":{"tempo":128}}`; no Remote Script command.
- Response: `{"added":[],"removed":[],"changed":[{"path":"tempo","before":120,"after":128}]}`
- Edge cases / side effects: pure local computation; lists compare by position.

### `get_song_length()`

- Params: none.
- Returns: derived Arrangement length in beats.
- Request: `{"type":"get_song_length","params":{}}`
- Response: `{"status":"ok","result":{"song_length":64.25}}`
- Edge cases / side effects: pure read; the property has no setter.

### `live_find_track(query: str)`

- Params: non-empty case-insensitive name substring.
- Returns: matching `{id,index,name,type}` records.
- Request: `{"type":"live_find_track","params":{"query":"bass"}}`
- Response: `{"status":"ok","result":[{"id":"track:0","index":0,"name":"Bass","type":"midi"}]}`
- Edge cases / side effects: pure read; no match returns `[]`.

### `list_device_params(track_id: str)`

- Params: current path-id in exact form `track:N`.
- Returns: each device id/name with parameter snapshots and ids.
- Request: `{"type":"list_device_params","params":{"track_id":"track:0"}}`
- Response: `{"status":"ok","result":[{"device_id":"track:0/device:0","parameters":[]}]}`
- Edge cases / side effects: pure read; a missing target returns `STALE_REFERENCE`.

## Mutations

### `create_cue_point(name: str, time: float)`

- Params: trimmed name, 1..256 characters; finite beat time 0..100000.
- Returns: name, observed time, and action `created` or `renamed`.
- Request: `{"type":"create_cue_point","params":{"name":"Verse","time":8.0}}`
- Response: `{"status":"ok","result":{"name":"Verse","time":8.0,"action":"created"}}`
- Edge cases / side effects: one undo step; moves only `current_song_time`, toggles exactly once, verifies creation and naming across UI ticks, then restores playback position without changing `start_time`. If Live's Arrangement grid snaps the toggle to another time, the unintended state change is reversed and the call returns `CUE_SNAPPED_TO_GRID`.

### `bulk_create_cue_points(items: list[CuePointSpec])`

- Params: 1..500 `{name,time}` objects.
- Returns: per-item status/result or typed error.
- Request: `{"type":"bulk_create_cue_points","params":{"items":[{"name":"Verse","time":8.0}]}}`
- Response: `{"status":"ok","result":{"results":[{"index":0,"status":"ok","result":{"action":"created"}}]}}`
- Edge cases / side effects: one undo step for the command; item failures do not stop later items; off-grid snaps are reversed per item and reported as `CUE_SNAPPED_TO_GRID`; one shared cursor scope is restored after the bulk finishes; the transport deadline scales with item count.

### `delete_cue_point(time: float)`

- Params: finite beat time 0..100000.
- Returns: `deleted`, and the actual cue time when found.
- Request: `{"type":"delete_cue_point","params":{"time":8.0}}`
- Response: `{"status":"ok","result":{"deleted":true,"time":8.0}}`
- Edge cases / side effects: one undo step; move-and-toggle; no match returns `deleted:false`.

### `set_current_song_time(time: float)`

- Params: finite beat time 0..100000.
- Returns: observed `current_song_time`.
- Request: `{"type":"set_current_song_time","params":{"time":32.0}}`
- Response: `{"status":"ok","result":{"current_song_time":32.0}}`
- Edge cases / side effects: one undo step; set/yield/read/retry across up to ten Live UI ticks; exhaustion returns `PLAYHEAD_NOT_MOVED`.

### `set_tempo(tempo: float)`

- Params: finite BPM 20..999.
- Returns: observed tempo.
- Request: `{"type":"set_tempo","params":{"tempo":128.0}}`
- Response: `{"status":"ok","result":{"tempo":128.0}}`
- Edge cases / side effects: one undo step; tempo automation can subsequently change the value.

### `start_playback()`

- Params: none.
- Returns: observed `is_playing`.
- Request: `{"type":"start_playback","params":{}}`
- Response: `{"status":"ok","result":{"is_playing":true}}`
- Edge cases / side effects: starts transport inside one undo-scoped command.

### `stop_playback()`

- Params: none.
- Returns: observed `is_playing`.
- Request: `{"type":"stop_playback","params":{}}`
- Response: `{"status":"ok","result":{"is_playing":false}}`
- Edge cases / side effects: stops transport inside one undo-scoped command.

### `set_loop(enabled: bool)`

- Params: boolean loop state.
- Returns: observed `loop`.
- Request: `{"type":"set_loop","params":{"enabled":true}}`
- Response: `{"status":"ok","result":{"loop":true}}`
- Edge cases / side effects: one undo step; non-booleans are rejected.

### `set_loop_start(start_beat: float)`

- Params: finite beat 0..100000.
- Returns: observed `loop_start`.
- Request: `{"type":"set_loop_start","params":{"start_beat":16.0}}`
- Response: `{"status":"ok","result":{"loop_start":16.0}}`
- Edge cases / side effects: one undo step; set/read/retry verification.

### `set_loop_length(length_beats: float)`

- Params: finite positive length up to 100000 beats.
- Returns: observed `loop_length`.
- Request: `{"type":"set_loop_length","params":{"length_beats":8.0}}`
- Response: `{"status":"ok","result":{"loop_length":8.0}}`
- Edge cases / side effects: one undo step; zero/negative lengths are rejected.

### `run_batch(commands: list[CommandSpec])`

- Params: 1..100 allowed mutation commands; nested batches are forbidden.
- Returns: ordered results, completed count, failing index or `null`, and `rolled_back:false`.
- Request: `{"type":"run_batch","params":{"commands":[{"type":"set_tempo","params":{"tempo":128.0}}]}}`
- Response: `{"status":"ok","result":{"results":[{"index":0,"status":"ok","result":{"tempo":128.0}}],"completed":1,"aborted_at":null,"rolled_back":false}}`
- Edge cases / side effects: one outer undo step, including deferred children; stops at first error; prior successes persist until one Ctrl+Z.

### `add_notes_to_clip(track_index: int, clip_index: int, notes: list[NoteSpec])`

- Params: track/slot indexes and 1..2048 notes (`pitch`, `start_time`, `duration`, optional `velocity`, `mute`).
- Returns: added count, returned note ids, and clip path-id.
- Request: `{"type":"add_notes_to_clip","params":{"track_index":0,"clip_index":0,"notes":[{"pitch":60,"start_time":0.0,"duration":1.0,"velocity":100,"mute":false}]}}`
- Response: `{"status":"ok","result":{"added":1,"note_ids":[42],"clip_id":"track:0/clipslot:0/clip"}}`
- Edge cases / side effects: one undo step; adds without deleting existing notes; requires a MIDI clip. The JSON contract remains dictionaries, while the embedded Python bridge converts them to `Live.Clip.MidiNoteSpecification` objects.

### `fire_clip(track_index: int, clip_index: int)`

- Params: non-negative track and Session slot indexes.
- Returns: `fired:true` and clip path-id.
- Request: `{"type":"fire_clip","params":{"track_index":0,"clip_index":0}}`
- Response: `{"status":"ok","result":{"fired":true,"clip_id":"track:0/clipslot:0/clip"}}`
- Edge cases / side effects: launches the clip; empty slots are rejected rather than starting recording.

### `create_clip(track_index: int, clip_index: int, length_beats: float)`

- Params: non-negative track/slot indexes and finite positive length up to 100000 beats.
- Returns: creation flag, clip path-id, and length.
- Request: `{"type":"create_clip","params":{"track_index":0,"clip_index":1,"length_beats":4.0}}`
- Response: `{"status":"ok","result":{"created":true,"clip_id":"track:0/clipslot:1/clip","length_beats":4.0}}`
- Edge cases / side effects: one undo step; only empty Session slots on MIDI tracks are supported.
