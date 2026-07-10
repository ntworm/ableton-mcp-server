# Known Live API Quirks and Mitigations

The categories below describe recurring Live API failure shapes rather than one project-specific incident. The cited Live Object Model documentation currently describes Live 12.3.5; this project targets a Live 12.4 beta and therefore retains manual verification gates.

## Category A — Deferred transport setters

**Symptom:** a transport property accepts a write but reads back a different value.

**Root cause:** Live can accept a write on one UI tick and expose the new value only after the handler returns. Sleeping on the UI thread prevents the tick that would apply the state.

**Mitigation:** mutations are generators advanced by `update_display`. They write, yield to Live, read back on a later tick, and retry without blocking. Failure raises a typed error; playhead quantization is restored in `finally`.

## Category B — Toggle operations and dual cue cursors

**Symptom:** calling `Song.set_or_delete_cue()` deletes a cue when one already exists at the playhead.

**Root cause:** it is a toggle, not a create-only operation. In the Python Remote Script runtime the toggle also follows the Arrangement insert/start cursor, which can differ from `current_song_time` after stopping playback.

**Mitigation:** enumerate cue points first. Existing cues are renamed idempotently. New operations move and verify both `current_song_time` and `start_time`, toggle on a later tick, verify the exact cue, and restore both cursors.

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

If a connection fails after a mutation was sent, the client cannot know whether Live executed it. Reads may reconnect and retry. Mutations fail without automatic replay; inspect current state before deciding to retry.

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

## LOM calls used for clip debugging

The implementation follows the official references for [`ClipSlot.create_clip` and `ClipSlot.fire`](https://docs.cycling74.com/apiref/lom/clipslot/) and adapts [`Clip.add_new_notes` / `get_notes_extended`](https://docs.cycling74.com/apiref/lom/clip/) to the embedded Python binding.
