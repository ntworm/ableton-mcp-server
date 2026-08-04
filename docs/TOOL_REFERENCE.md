# Tool Reference

The FastMCP server exposes 65 snake_case tools. Remote examples below show the JSONL command envelope after MCP/Pydantic validation. All error responses use `{"status":"error","code","message","hint?"}`.

A machine-readable view of these tools (route, risk, acceptance mode, reversibility) is exposed at runtime via the `get_bridge_status` tool's `tools` list and `capability_counts` keys, derived from the canonical `TOOL_CATALOG`.

The promotion gates that consume the per-tool status rows recorded by
the acceptance runner are documented in
[`docs/CERTIFICATION.md`](CERTIFICATION.md). That document is canonical
for what each status means and which `environment_unavailable` rows
are explicitly allowed.

## v0.5.0 set lifecycle

### `lifecycle_status()`

- Params: none.
- Returns: a read-only probe of save/quit API availability plus runtime identity tag.
- Edge cases / side effects: pure read; registered in `READ_COMMANDS`.

### `save_set(require_api: bool = False)`

- Params: `require_api` (default `False`) — when `True`, the call fails unless a write API is available.
- Side effects: calls `Song.save()` if the API is present; no-op otherwise.
- Edge cases / side effects: mutation gated by `ALLOWED_MUTATIONS`; one undo step; never replayed after ambiguous network failure.

### `quit_ableton()`

- Params: none.
- Side effects: saves the Set (when the API is available) then schedules a quit. GUI fallback is scheduled so the call cannot hang.
- Edge cases / side effects: mutation gated by `ALLOWED_MUTATIONS`; one undo step.

### `live_fade(target: str, from_value: float, to_value: float, duration_s: float, steps: int = 30, easing: str = "smoothstep")`

- Params: `target` (mixer path-id), numeric `from_value`/`to_value`, `duration_s`, `steps`, `easing` (`smoothstep` or `linear`).
- Side effects: distributes writes across the requested `duration_s` via
  `time.monotonic` and yields between steps; the Live main thread stays
  responsive because there is no `time.sleep` and no busy-wait.
- Edge cases / side effects: 60-second timeout override; `min(60, steps + 1)` work units; mutation gated by `ALLOWED_MUTATIONS`.

## v0.5.0 track creation

### `create_audio_track(index: int = -1, name: str | None = None)`

- Params: optional insertion `index` and `name`.
- Side effects: creates a new empty audio track; mirrors `create_midi_track`.
- Edge cases / side effects: respects the 96-track safety limit; mutation gated by `ALLOWED_MUTATIONS`.

## v0.5.0 offline mix analysis

### `analyze_audio(path: str)`

- Params: local path to a `.wav` / audio file.
- Returns: LUFS-I, true-peak, RMS, and per-band energy summary.
- Side effects: reads the file from disk; dependency-free of Live.
- Edge cases / side effects: missing files and unsupported encodings return a structured `{"ok": False, "reason": ...}`.

### `find_frequency_masking(target_path: str, reference_path: str, threshold_db: float = 6.0)`

- Params: `target_path`, `reference_path`, `threshold_db`.
- Returns: bands where the target exceeds the reference by at least `threshold_db` dB.
- Side effects: reads both files.
- Edge cases / side effects: mismatched sample rates raise a structured error; identical paths are rejected at the model layer.

### `analyze_mix(stems: list[str])`

- Params: list of stem paths, max 16.
- Returns: per-stem analysis plus pair-wise masking scores.
- Side effects: reads each stem from disk.
- Edge cases / side effects: more than 16 stems raises a structured error.

### `extract_single_cycle(path: str, frame_size: int = 2048)`

- Params: local path plus optional `frame_size`.
- Returns: detected pitch plus a single-cycle sample buffer (or `{"ok": False, "reason": ...}` on aperiodic content).
- Side effects: reads the file from disk.
- Edge cases / side effects: aperiodic content returns a structured failure rather than crashing.

## v0.4.0 capability expansion

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
- Returns: all regular, return, and master tracks as `{id,index,name,type}` plus the hierarchy block `{color,color_index,is_group_track,is_grouped,group_track_index,group_track_id,is_visible,fold_state}`.
- Request: `{"type":"get_track_list","params":{}}`
- Response: `{"status":"ok","result":[{"id":"track:0","index":0,"name":"Bass","type":"midi","color":3368601,"color_index":3,"is_group_track":false,"is_grouped":false,"group_track_index":null,"group_track_id":null,"is_visible":true,"fold_state":0}]}`
- Edge cases / side effects: pure read; re-list after structural changes. Mixer state (`mute`/`solo`/`arm`/`volume`) is deliberately **not** here — read it from `get_track_state`.
- Group Tracks: `type` stays `audio` for a Group Track because Live gives it no MIDI input. Detect groups with `is_group_track` (LOM `Track.is_foldable`), membership with `is_grouped`, and the parent with `group_track_index`. Never infer "group" from `type == "audio"`.
- Properties a host does not expose are reported as `null` (`color_index`, `fold_state`, `group_track_index`) or `false`, never invented. `is_visible` is `false` for a track hidden inside a folded group.

### `get_track_state(track_index: int)`

- Params: non-negative `track_index` in the combined regular/return/master list.
- Returns: path-id, the same hierarchy block as `get_track_list`, mixer state, sends, devices, parameters, and Session clip slots.
- Request: `{"type":"get_track_state","params":{"track_index":0}}`
- Response: `{"status":"ok","result":{"id":"track:0","name":"Bass","color_index":3,"is_group_track":false,"devices":[],"clip_slots":[]}}`
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
- Edge cases / side effects: one undo step; move-and-toggle; no match returns `deleted:false`. An off-grid snap is reversed—including restoration of a different locator temporarily removed by Live—and returns `CUE_SNAPPED_TO_GRID`.

### `set_current_song_time(time: float)`

- Params: finite beat time 0..100000.
- Returns: observed `current_song_time`.
- Request: `{"type":"set_current_song_time","params":{"time":32.0}}`
- Response: `{"status":"ok","result":{"current_song_time":32.0}}`
- Edge cases / side effects: one undo step; set/yield/read/retry across up to ten Live UI ticks; exhaustion returns `PLAYHEAD_NOT_MOVED`.

### `set_tempo(tempo: float)`

- Params: finite BPM 20..999.
- Returns: observed tempo plus canonical `resolved` identity (`kind: "tempo"` and observed `tempo`).
- Request: `{"type":"set_tempo","params":{"tempo":128.0}}`
- Response: `{"status":"ok","result":{"tempo":128.0,"resolved":{"kind":"tempo","tempo":128.0}}}`
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

- Params: track/slot indexes and 1..2048 notes (`pitch`, `start_time`, `duration`, optional `velocity`, `mute`, `probability`, `release_velocity`, `velocity_deviation`).
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
- Returns: creation flag, clip path-id, length, and canonical `resolved` clip identity (resolved indexes, track name when available, and post-mutation clip path-id).
- Request: `{"type":"create_clip","params":{"track_index":0,"clip_index":1,"length_beats":4.0}}`
- Response: `{"status":"ok","result":{"created":true,"clip_id":"track:0/clipslot:1/clip","length_beats":4.0,"resolved":{"kind":"clip","track_index":0,"clip_index":1,"track_name":"Bass","clip_id":"track:0/clipslot:1/clip"}}}`
- Edge cases / side effects: one undo step; only empty Session slots on MIDI tracks are supported.

## v0.4.0 capability expansion

### `set_parameter_value(track_index, device_index, parameter_name, value)`

- Params: exact parameter name and finite value within the parameter's reported bounds.
- Returns: requested target, observed value, `is_quantized`, and canonical `resolved` device identity (resolved indexes, parameter name, and track/device names when available).
- Request: `{"type":"set_parameter_value","params":{"track_index":0,"device_index":0,"parameter_name":"Filter Freq","value":0.75}}`
- Edge cases / side effects: one undo step; disabled, unknown, or out-of-range parameters are rejected. Unknown names include close suggestions. The write is read back and retried once; it is valid inside `run_batch`.

### `get_clip_info(track_index, clip_index)`

- Returns stable Session slot metadata including name, loop bounds, color, type, playing/trigger state, mute state, and time signature.
- Empty slots return `{"has_clip":false,"clip_id":null}`.
- Edge cases / side effects: pure TCP read; return/master tracks return `WRONG_TYPE`.

### `get_session_overview()`

- Locally composes `get_session_info`, `get_track_list`, and `get_scenes` into `session`, `tracks`, and `scenes` keys.
- Edge cases / side effects: performs three read-only TCP calls; it is not a new remote command.

### `search_browser(query, category_type=None, limit=50)`

- Performs case-insensitive depth-first search through `application.browser` over TCP.
- Returns display name, URI when exposed, category, path, and `is_loadable`.
- Edge cases / side effects: pure read; limit is 1..200 and traversal is capped at depth 5, 500 children per node, and 5000 visited nodes.

### `delete_clip(track_index, clip_index)`

- Deletes one occupied Session clip and returns its prior clip path-id.
- Edge cases / side effects: one undo step; an empty slot returns `BAD_INPUT`.

### `clear_clip_notes(track_index, clip_index)`

- Removes all notes from one MIDI Session clip and returns the observed `notes_removed` delta.
- Edge cases / side effects: one undo step with deferred readback; empty and audio clips are rejected.

### `fire_scene(scene_index)`

- Calls `Scene.fire()` and returns the fired scene index and name.
- Edge cases / side effects: triggers clips under Live's current quantization; invalid indexes return `INVALID_PARAMS`.

### `set_track_property(track_index, property, value)`

- `property` is exactly `mute`, `solo`, or `arm`; `value` is boolean.
- Returns the verified observed property value.
- Edge cases / side effects: one undo step; return/master tracks cannot be armed.

### `set_track_color(track_index, color_index=None, color=None)`

- Exactly one of `color_index` (Live's 70-swatch palette, `0..69`) and `color` (packed `0x00rrggbb`, `0..0xFFFFFF`) is required; supplying both or neither returns `INVALID_PARAMS`.
- Writes LOM `Track.color_index` or `Track.color`, then reads the value back on a later Live UI tick and returns `{track_id, track_index, property, color, color_index, resolved}`.
- `resolved` follows the canonical convention: `{"kind":"track","track_index":N,"track_name":"…"}` with `track_name` omitted when the name is unavailable.
- Edge cases / side effects: one undo step; clips are never recoloured — clip colour is a separate LOM property and there is no tool for it. A track that does not expose the property returns `WRONG_TYPE`; a write that does not land returns `VERIFICATION_FAILED`. The write is issued **once** — mutations are never retried. Return and master tracks accept colour.
- The `color_index` upper bound is enforced by this server, not by the LOM reference (which documents `color` but leaves the `color_index` range unspecified). A host that disagrees fails the readback rather than silently accepting a bad slot.

### `set_clip_color(track_index, clip_index, scope="session", color_index=None, color=None)`

- Exactly one of `color_index` (`0..69`) and `color` (packed `0x00rrggbb`) is required; both or neither returns `INVALID_PARAMS`.
- `scope="session"` addresses `track.clip_slots[clip_index].clip`; `scope="arrangement"` addresses `track.arrangement_clips[clip_index]`. `Clip.color` and `Clip.color_index` are `getsetobserve` in the LOM, so **both lanes are genuinely writable** — unlike track reordering.
- Writes once, reads back on a later UI tick, returns `{clip_id, scope, track_index, clip_index, property, color, color_index, resolved}` with `resolved.kind == "clip"`.
- Edge cases / side effects: one undo step. An empty Session slot returns `BAD_INPUT`. `Track.arrangement_clips` needs Live 11+; a host without it returns `CAPABILITY_UNAVAILABLE` for `scope="arrangement"`. An out-of-range Arrangement index returns `INVALID_PARAMS`. No retry on failure.

### `diagnose_clip_targets(track_index=None)`

- Read-only sweep answering "which clips can `set_clip_color` actually reach?".
- Returns `{tracks, session_clip_count, arrangement_clip_count, inaccessible}`. Each track entry carries `session_clips`, `arrangement_clips`, and `arrangement_supported`; each clip entry carries `id`, `scope`, `name`, `is_midi_clip`, `color`, `color_index`, and `colorable`.
- `inaccessible` names every target that cannot be coloured **and why** — a host without `Track.arrangement_clips` produces an entry per track rather than a silent zero count.
- Edge cases / side effects: pure read; omit `track_index` to sweep the whole Set.

### Track hierarchy: `move_track`, `reorder_tracks`, `move_track_to_group`, `ungroup_track`, `merge_groups`

These five tools are registered, documented, and fully validated — and they **always refuse**. No public API can perform them.

| Tool | Signature |
|---|---|
| `move_track` | `(track_index, destination_index)` |
| `reorder_tracks` | `(order: list[int])` |
| `move_track_to_group` | `(track_index, group_track_index)` |
| `ungroup_track` | `(track_index)` |
| `merge_groups` | `(source_group_index, destination_group_index, delete_empty_source=False)` |

- **Validation runs first**, against the live Set, so a malformed request stays distinguishable from the capability gap: unknown indexes return `INVALID_PARAMS`; return/main tracks return `WRONG_TYPE`; a non-foldable group target returns `WRONG_TYPE`; a non-permutation `order`, a self-nesting request, a cycle, or `delete_empty_source=True` return `BAD_INPUT`.
- A well-formed request returns `CAPABILITY_UNAVAILABLE`. The error carries a `details` object with the exact evidence: `lom_song_functions_checked`, `lom_verdict`, `sdk_bindings_checked`, `sdk_verdict`, `rejected_workarounds`, `supported_alternative`, the echoed `request`, and `applied: false`.
- **Nothing is written.** No undo step is opened, no track is added or removed, and no clip, device, note, automation, mixer value, routing or colour changes. This is covered by tests, not just by intent.
- Evidence: Live's LOM `Song` exposes `create_audio_track(index)`, `create_midi_track(index)`, `duplicate_track(index)`, `delete_track(index)`, `move_device(...)` — and no reposition call. `song.tracks` / `song.visible_tracks` are get/observe lists and `Track.group_track` is get-only, so re-parenting is impossible too. The Ableton Extension SDK 1.0.0-beta.0 matches: `songCreateMidiTrack`, `songCreateAudioTrack`, `songDuplicateTrack`, `songDeleteTrack`, `trackGetGroupTrack` — no move, no grouping, and its create calls take no index.
- Duplicate + delete is not an escape hatch: `duplicate_track` always inserts the copy immediately after the original, so relative order cannot change at all — and it would destroy the original track. Devices, unlike tracks, *can* be moved between tracks (`Song.move_device`), but no tool exposes that yet.
- Discover the gap without triggering it: `get_bridge_status().capability_gaps` carries the same evidence.

### `set_clip_properties(track_index, clip_index, loop_start=None, loop_end=None, name=None)`

- Requires at least one requested property and validates the final loop interval before writing.
- Returns only requested observed fields plus the clip path-id.
- Edge cases / side effects: one undo step; each property is verified over later Live UI ticks.

### `create_clip_automation(track_index, clip_index, parameter_name, automation_points)`

- Replaces one Session clip envelope with 1..500 sorted `{time,value}` breakpoints.
- Resolves exact device parameters plus mixer aliases `volume`, `pan`/`panning`, and `send_a` through `send_h`.
- Edge cases / side effects: one undo step; only Session clips are supported. Values must fit parameter bounds, and hosts without the automation-envelope API return `LIVE_UNAVAILABLE`.

### `get_warp_state(track_index, clip_index)` and `set_warp_state(...)`

- `get_warp_state` exposes the current `warping` boolean, `warp_mode`, and
  the read-only `warp_markers` array (sample-time / beat-time pairs).
- `set_warp_state` accepts only `warping` and `warp_mode`. It rejects any
  `warp_markers` payload at the model layer (`VALIDATION_ERROR`) — marker
  writes were retired at v0.5.0 and must not reach the Extension bridge.
