# Known Live API Quirks and Mitigations

The categories below describe recurring Live API failure shapes rather than one project-specific incident. The cited Live Object Model documentation currently describes Live 12.3.5; this project targets a Live 12.4 beta and therefore retains manual verification gates.

## Don't try these yet

The five categories below are the most likely to surprise or burn an AI agent that has not read this document end-to-end. Read the linked section before attempting anything in the same neighbourhood.

- [Path-ids are session locators, not persistent handles.](#category-g--session-local-integer-paths) A `track:N` index from one call can refer to a different track on the next call; always re-resolve after structural edits. ([Category G](#category-g--session-local-integer-paths))
- [`run_batch` is not a transaction.](#category-h--multi-command-undo-is-not-rollback) If command N fails after commands 1..N-1 already mutated the Set, a single Ctrl+Z reverts the whole prefix, not just the failing step; there is no automatic rollback. ([Category H](#category-h--multi-command-undo-is-not-rollback))
- [WSL loopback is not Windows loopback.](#category-k--wsl-loopback-is-not-windows-loopback-under-nat) `127.0.0.1:9888` in WSL is the WSL-side NAT interface, not the Windows process hosting Live. Tool discovery works; live calls will be refused. ([Category K](#category-k--wsl-loopback-is-not-windows-loopback-under-nat))
- [Protocol constants must be vendored, not hand-edited.](#category-f--duplicated-protocol-constants-drift) The MCP server and the Live Remote Script will silently diverge if `contracts.py` is changed without re-running `scripts/vendor_contracts.py`. ([Category F](#category-f--duplicated-protocol-constants-drift))
- [Prefix-based mutation blocking is gone; explicit allowlist applies.](#category-i--over-defensive-prefix-blocking) A tool such as `set_tempo` is permitted because it is explicitly allowlisted, not because it passes a prefix heuristic. Do not infer permissions from tool names. ([Category I](#category-i--over-defensive-prefix-blocking))

## Category A — Deferred transport setters

**Symptom:** a transport property accepts a write but reads back a different value.

**Root cause:** Live can accept a write on one UI tick and expose the new value only after the handler returns. Sleeping on the UI thread prevents the tick that would apply the state.

**Mitigation:** mutations are generators advanced by `update_display`. They write, yield to Live, read back on a later tick, and retry without blocking. Failure raises a typed error; playhead quantization is restored in `finally`.

## Category B — Toggle operations and Arrangement playback position

**Symptom:** calling `Song.set_or_delete_cue()` deletes a cue when one already exists at the playhead.

**Root cause:** it is a toggle, not a create-only operation. The official [Song LOM reference](https://docs.cycling74.com/apiref/lom/song/#set_or_delete_cue) states that it acts at `current_song_time`. Hardware-in-loop testing on Live 12.4.5b7 additionally shows that the call can snap that position to the Arrangement editing grid even while `clip_trigger_quantization` is `None`. `Song.start_time` controls where playback will begin and is not the cue cursor.

**Mitigation:** enumerate cue points first. Existing cues are renamed idempotently. New operations move and verify only `current_song_time`, snapshot locators, invoke the toggle once, and observe the exact state change. Exact placement is verified before naming. If Live snaps to another time, the script reverses the unintended creation or deletion, restores the original cue name when needed, and returns `CUE_SNAPPED_TO_GRID`. Disable Arrangement Snap-to-Grid or use a grid-aligned time. The public LOM does not expose the Arrangement grid switch, so the MCP does not fake exact placement. `start_time` is never written by cue tools.

## Category C — Read-only properties that look writable

**Symptom:** assigning `Song.song_length` raises because it has no setter.

**Root cause:** song length is derived from Arrangement content. The official [Song LOM reference](https://docs.cycling74.com/apiref/lom/song/) marks it read-only.

**Mitigation:** expose `get_song_length` only. To grow the Set length, put a MIDI or audio clip on the Arrangement timeline.

## Category D — Non-existent methods

**Symptom:** code attempts `song.delete_cue_point(cue)` and fails with `AttributeError`.

**Root cause:** the Python LOM exposes cue deletion through the same toggle used for creation.

**Mitigation:** resolve the cue, move the playhead with verification, then call `set_or_delete_cue()`.

## Category E — Custom beat-time values

**Symptom:** arithmetic against `cue.time` behaves unexpectedly.

**Root cause:** Live may return a beat-time wrapper rather than a plain Python float.

**Mitigation:** cast `float(cue.time)` and compare with `0.01` beat tolerance.

## Category O — Track reordering has no public API

**Symptom:** an agent is asked to "move the drums group above the bass" and looks for a `move_track` tool, or invents one by duplicating the track and deleting the original.

**Root cause:** the public LOM exposes track *creation at an index* and track *deletion by index* — `Song.create_audio_track(index)`, `Song.create_midi_track(index)`, `Song.duplicate_track(index)`, `Song.delete_track(index)` — and nothing that repositions an existing track. `song.tracks` and `song.visible_tracks` are read-only lists (the [Song LOM reference](https://docs.cycling74.com/apiref/lom/song/) marks them get/observe), and `Track.group_track` is read-only, so a track cannot be moved into or out of a group either. The Ableton Extension SDK has the same gap: `ableton-extensions-sdk` 1.0.0-beta.0 ships `songCreateMidiTrack`, `songCreateAudioTrack`, `songDuplicateTrack` and `songDeleteTrack`, its `Song.createAudioTrack()` / `createMidiTrack()` do not even take an index ("Inserted after the last selected track, or appended if no track is selected"), and there is no reposition binding anywhere in its DataModel surface.

**Mitigation:** five tools — `move_track`, `reorder_tracks`, `move_track_to_group`, `ungroup_track`, `merge_groups` — are registered so the gap is discoverable, and every one of them validates the request against the live Set and then refuses with a typed `CAPABILITY_UNAVAILABLE` whose `details` carry the API evidence (`contracts.UNSUPPORTED_CAPABILITIES` / `contracts.CAPABILITY_EVIDENCE`). Validation runs *first*, so a bad index still returns `INVALID_PARAMS` / `WRONG_TYPE` / `BAD_INPUT` and stays distinguishable from the permanent gap. None of them opens an undo step or writes anything. `get_bridge_status().capability_gaps` exposes the same evidence without triggering a refusal.

Duplicate-then-delete is **not** an acceptable emulation, and it does not even work: `duplicate_track(index)` always inserts the copy immediately after the original, so relative order cannot change — and it would destroy the original track. Devices, unlike tracks, *can* be moved between tracks via `Song.move_device(device, target, target_position)`; that is the one repositioning primitive the LOM does offer. Create tracks at the index you want, or reorder and group by hand in Live.

## Category P — `#` in a track name is Live's auto-numbering token

**Symptom:** a track renamed to `# DRUMS` shows up as `1 DRUMS`, and reading the name back returns the rendered form, not the string that was sent.

**Root cause:** Live treats `#` inside a track or clip name as a placeholder for the track's automatic number, exactly as it does in the Rename dialog. This is native Live behaviour, not a bridge bug and not a transport encoding problem. The LOM has no escape syntax for a literal `#` and no separate "display name" property, so there is nothing to preserve the character with.

**Mitigation:** `rename_track` sends the string unchanged and verifies the readback, so the substitution is visible instead of silent. Do not add an escape mechanism or rewrite names on the way through — that would hide a real Live behaviour from the caller. If a literal `#` is required, it cannot be had through the public API. Identifying a Group Track never depends on its rendered name: use `is_group_track` from `get_track_list` / `get_track_state`, which reads `Track.is_foldable`.

## Category F — Duplicated protocol constants drift

**Symptom:** one process permits a command that the other rejects.

**Root cause:** independently maintained command sets diverge.

**Mitigation:** edit root `contracts.py` only, then run `python scripts/vendor_contracts.py`. Tests compare the deterministic generated file byte-for-byte after its header.

## Category G — Session-local integer paths

**Symptom:** a stored `track:N` path becomes invalid or refers to a different current index after structural edits.

**Root cause:** the Remote Script surface has no persistent cross-process Live handle.

**Mitigation:** resolve paths against current state on every call. Missing indexes raise `STALE_REFERENCE`. Re-list after any structural change. Path-ids are locators, not immutable identities.

## Category H — Multi-command undo is not rollback

**Symptom:** command two fails after command one already changed the Set.

**Root cause:** closing an undo step groups mutations; it does not reverse a successful prefix.

**Mitigation:** `run_batch` aborts at the first error, closes the step in `finally`, returns `rolled_back: false`, and documents that one Ctrl+Z reverts the successful prefix. Automatic reverse replay is not implemented because not every mutation has a safe inverse.

**Runtime limitation:** `begin_undo_step`/`end_undo_step` are host-facing Remote Script capabilities rather than documented Max LOM calls. The script resolves a target that exposes both methods and refuses to mutate when no such target exists. Confirm the target on the installed Live build.

## Category I — Over-defensive prefix blocking

**Symptom:** debug tools such as `set_tempo` or `fire_clip` are rejected merely because their names start with mutation verbs.

**Root cause:** a prefix rule cannot distinguish debug mutations from creative/destructive ones.

**Mitigation:** explicit sets replace prefixes. `create_clip`, `fire_clip`, and `add_notes_to_clip` are allowed. Track creation/deletion, renaming, Browser loading, and view switching remain blocked.

## Additional limitation — Ambiguous network failure

If a connection fails after a mutation was sent, the client cannot know whether Live executed it. Reads may reconnect and retry. Mutations fail without automatic replay; inspect current state before deciding to retry. Socket failures are returned as typed `LIVE_UNAVAILABLE` results. Client and server share a deadline scaled to bulk/batch size, and idle connections are not closed merely because no request arrived for ten seconds.

## Category M — Empty arrays in MCP content

**Symptom:** a valid empty result such as `get_clip_notes` on an empty MIDI clip appears as `""` in a content-only MCP client.

**Root cause:** FastMCP interprets a raw empty Python list as zero content blocks.

**Mitigation:** the MCP boundary emits structured `[]` plus an explicit textual `[]` fallback. The JSONL bridge contract remains an ordinary list.

## Category N — Expected errors mistaken for server crashes

**Symptom:** repeated `WRONG_TYPE` or `INVALID_PARAMS` calls make a supervising agent report the MCP subprocess as unreachable even though stdio is still alive.

**Root cause:** typed bridge exceptions were escaping into FastMCP, which logged framework tracebacks and returned generic tool failures.

**Mitigation:** expected bridge errors are converted to structured MCP error results with `isError=true`. They remain errors, but no longer look like unhandled server exceptions. A stdio reproduction confirms subsequent calls remain available.

## Category J — Max LOM and Python Remote Script note APIs differ

**Symptom:** `Clip.add_new_notes({"notes": [...]})` raises a C++ conversion error referring to `TNoteSpecification`.

**Root cause:** the public Max LOM documentation describes a dictionary argument. The embedded Python Remote Script binding expects an iterable of `Live.Clip.MidiNoteSpecification` objects.

**Mitigation:** validate JSON/Pydantic note dictionaries at the MCP boundary, construct Python note specification objects inside Live, and pass them as a tuple.

## Category K — WSL loopback is not Windows loopback under NAT

**Symptom:** MCP tool discovery succeeds in WSL, but every Live call is refused at `127.0.0.1:9888`.

**Root cause:** `tools/list` is local metadata discovery, and WSL2 NAT has a network namespace separate from the Windows process hosting Live.

**Mitigation:** keep the Remote Script loopback-only and launch the Windows `.venv-win/Scripts/ableton-mcp-server.exe` from WSL. Use `ableton-mcp doctor` for an actual bridge probe. Do not bind the unauthenticated protocol to `0.0.0.0`.

## Category L — Cross-platform log discovery

**Symptom:** `get_ableton_logs` cannot find `APPDATA` when the MCP process is not a Windows process.

**Mitigation:** prefer `ABLETON_MCP_LOG_PATH`, then search native Windows/macOS locations and mounted Windows profiles. The canonical WSL deployment uses Windows Python and therefore receives `APPDATA` normally.

## Category Q — A plugin reports no parameters until the user clicks Configure

**Symptom:** `get_device_list` on a track holding a VST/VST3/AU returns that device with a single `Device On` parameter, and `set_parameter_value` answers `INVALID_PARAMS` for every real plugin control. The plugin looks parameterless even though its own window is full of knobs.

**Cause:** Live does not publish a plugin's parameters to the Live Object Model. `PluginDevice.parameters` contains `Device On` plus only the controls a user added by hand through the device's **Configure** button in Live's device panel. The same gate applies to MIDI mapping and clip automation, so this is Live's design and not a bridge limitation. No remote API can add an entry to the Configure list.

**Mitigation:** the bridge reports the state instead of returning a silently empty list. Plugin devices carry a `plugin_state` block in `get_device_list` and `list_device_params`; with nothing configured it reads `{"status": "not_configured", "hint": "PLUGIN_NOT_CONFIGURED", ...}`, and parameter lookups fail with the same explanation under `details.hint_code`. Ask the user to configure the controls in Live. `PluginDevice.presets` and `selected_preset_index` are exempt from the Configure gate, so `get_plugin_presets` / `set_plugin_preset` work regardless.

## LOM calls used for clip debugging

The implementation follows the official references for [`ClipSlot.create_clip` and `ClipSlot.fire`](https://docs.cycling74.com/apiref/lom/clipslot/) and adapts [`Clip.add_new_notes` / `get_notes_extended`](https://docs.cycling74.com/apiref/lom/clip/) to the embedded Python binding.
