# Known Live API Quirks and Mitigations

The categories below describe recurring Live API failure shapes rather than one project-specific incident. The cited Live Object Model documentation currently describes Live 12.3.5; this project targets a Live 12.4 beta and therefore retains manual verification gates.

## Category A — Non-deterministic transport setters

**Symptom:** a transport property accepts a write but reads back a different value.

**Root cause:** Live can clamp, quantize, defer, or ignore transport changes while other state is transitioning.

**Mitigation:** transport writes suspend clip-trigger quantization, set, read the named attribute, compare, sleep, and retry three times. Failure raises `PLAYHEAD_NOT_MOVED`; dependent operations do not run. Quantization is restored in `finally`.

## Category B — Toggle operations masquerading as create

**Symptom:** calling `Song.set_or_delete_cue()` deletes a cue when one already exists at the playhead.

**Root cause:** it is a toggle, not a create-only operation.

**Mitigation:** enumerate cue points before the call. Existing cues are renamed idempotently. Creation toggles only after confirming the target is empty and the playhead reached it.

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

## LOM calls used for clip debugging

The implementation follows the official references for [`ClipSlot.create_clip` and `ClipSlot.fire`](https://docs.cycling74.com/apiref/lom/clipslot/) and [`Clip.add_new_notes` / `get_notes_extended`](https://docs.cycling74.com/apiref/lom/clip/).
