# Final Acceptance Certification Stabilization Design

## Objective

Finish the v0.5.1 release-candidate path without allowing the acceptance
runner to certify a Set that was not restored to its clean baseline. The
result must keep the 65-tool surface intact, remain honest about lifecycle
operations that Live 12 does not expose, and be safe to fast-forward into
`main` after offline verification.

## Confirmed failure modes

Two failures are reproducible against the in-process bridge model:

1. Structural track creation currently runs before cleanup. Return/master
   indexes move, and cleanup resolves tracks by name. Because Live permits
   duplicate names, the runner can restore the wrong track and still report
   `release_ready: true`.
2. `save_set` accepts the unrelated `song_save_available` field from
   `lifecycle_status`. Contradictory responses such as `saved=true` with
   `api_available=false` can therefore be recorded as `live_passed`.

## Accepted design

### Strict `save_set` state machine

The acceptance runner recognizes only the Remote Script's actual response
contract:

- `saved is True` and `api_available is True`: read project metadata and pass
  only when `is_dirty is False`.
- `saved is False`, `api_available is False`, and `gui_workflow.save` is a
  non-empty list of non-empty strings: record `manual_required`.
- Every other shape or contradictory combination: record `failed`.

`save_set` and `quit_ableton` are the only documented `manual_required`
exceptions in the full-baseline release policy. The clean-baseline safety
proof comes from the preflight `is_dirty is False` check, not from pretending
that a missing `Song.save()` API performed a save.

### Restore before structural track creation

All index-based reversible mutations and readbacks run before new tracks are
created. Cleanup uses the original session-local indexes while the track
layout is unchanged. Only after cleanup succeeds may the runner exercise
`create_audio_track` and `create_midi_track`. If cleanup fails, both structural
rows are recorded as failed without sending those mutations.

Track names are never used as identities. The realistic creation checks remain
based on regular-track counts, the returned append index, type, preservation
of the regular prefix, and the expected index shift of return/master tracks.

### Release and installation boundary

Code, tests, documentation, and plans belong to a source commit. Candidate
artifacts are then regenerated from that exact Git commit object ID and stored
in a second release-only commit. With Live closed, the wheel, Remote Script,
and Extension are installed and hash-checked. The feature branch may then be
fast-forwarded into local `main`; no tag, push, publication, or live
certification flag is authorized in this phase.

## Verification strategy

- TDD regressions reproduce duplicate-name restoration and malformed
  `save_set` responses before production changes.
- Full Windows and WSL pytest/coverage/Ruff/Mypy gates run after implementation.
- Clean-wheel installation and Extension production build/audit run fresh.
- Manifest, SHA256SUMS, artifact bytes, installed hashes, Git provenance, and
  worktree cleanliness are checked before integration.
- Real Live acceptance remains a separate, single-run guarded phase after the
  user opens the disposable `TESTE_CODEX` Set.

