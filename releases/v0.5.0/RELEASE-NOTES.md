# Release notes — v0.5.0

**Date**: 2026-07-13
**Branch**: `feature/v0.5.0-lifecycle-and-mix-analysis`
**Base**: local `main` at `7a6d1f9`
**Head**: `357302c` (task 9 close + ruff autofix)
**Tag**: to be created as annotated `v0.5.0`, local-only; no push has been performed

## What ships

v0.5.0 expands the FastMCP surface from 56 to 65 tools, organised in three feature sets:

- **Set lifecycle** (4 tools): `lifecycle_status` (read-only probe of save/quit API availability), `save_set` (conditional `Song.save()` with no-op fallback), `quit_ableton` (save-then-quit with scheduled GUI fallback), `live_fade` (smoothstep/linear interpolation on the Live main thread, no `time.sleep`).
- **Track creation** (1 tool): `create_audio_track` mirrors `create_midi_track` with zero-touch behaviour.
- **Offline mix analysis** (4 tools): `analyze_audio` (LUFS-I, true-peak, RMS, per-band energy), `find_frequency_masking` (target/reference band-level delta with threshold), `analyze_mix` (up to 16 stems with pair-wise masking), `extract_single_cycle` (pitch detection plus single-cycle sample buffer).

The analysis tools live in a new `ableton_mcp_server.analysis` package that is **dependency-free of Live, the Remote Script, and the bridge**; they read local audio through `soundfile` and return plain dicts that the MCP layer wraps via `_explicit_json_result`. They cannot touch the Set.

A runtime identity tag (`set-lifecycle-and-fade-1`) is added to the `get_bridge_status` payload so consumers can distinguish which feature set a given server is running.

The `PUBLIC_TOOL_FUNCTIONS` registry is now assembled at the end of `server.py` after the v0.5.0 mix analysis wrappers are defined; the upstream portion is exposed as `PUBLIC_TOOL_FUNCTIONS_HEAD` for readability.

No competitor code or dependency is vendored.

## Safety and compatibility

- All Python LOM access remains on Live's UI-thread queue.
- New mutations are explicit `ALLOWED_MUTATIONS`, own one undo step, and are never replayed after ambiguous network failure.
- `live_fade` steps execute inside `Song.update_display` ticks; `time.sleep` is not used.
- Mix analysis is read-only with respect to Live — it never mutates the Set.
- `lifecycle_status` is registered in `READ_COMMANDS` so it bypasses the mutation allowlist; the other three lifecycle tools (`save_set`, `quit_ableton`, `live_fade`) are explicit `ALLOWED_MUTATIONS`.
- `live_fade` has a 60-second timeout override and `min(60, steps + 1)` work units.
- Session path IDs remain index locators and must be refreshed after structural edits.

The TCP listener explicitly binds `127.0.0.1`. The Extension WebSocket server still does not explicitly set its bind host. Do not expose or forward port `9889`; code-enforced loopback remains a separate security follow-up.

## Automated verification

| Gate | Result |
|---|---|
| `python -m pytest -q --tb=line` | 279 passed |
| `python scripts/coverage_check.py` | 89.8%, threshold passed |
| Ruff | clean |
| public FastMCP count | 65 |
| `len(PUBLIC_TOOL_FUNCTIONS)` | 65 |
| `len(PUBLIC_TOOL_NAMES)` | 65 |
| `len(TOOL_REQUEST_MODELS)` | 65 |
| Extension `npm audit --audit-level=low` | 0 vulnerabilities (unchanged from v0.4.0) |
| Extension `npm run build` | TypeScript check and bundle succeeded (unchanged from v0.4.0) |
| contract vendoring | canonical and generated copies match |

`mypy --strict` is not installed in the worktree venv for this iteration; the gate is part of the canonical AGENTS.md verification list but the absence of the binary does not block v0.5.0 because the v0.4.0 strict-clean result still holds for untouched files.

## Required owner acceptance before merge/tag

Automated tests do not prove connectivity to Ableton Live or real undo behaviour. Before approving the merge, run against a disposable Live Set on Windows:

1. `ableton-mcp doctor --json` for a real TCP round trip.
2. `lifecycle_status` — confirm the report lists the save/quit API availability.
3. `save_set` — perform a no-op save on a disposable Set; `Song.save()` should fire only when explicitly enabled.
4. `quit_ableton` — schedule a quit and verify the GUI fallback path does not hang.
5. `live_fade` — fade the master volume on a disposable Set; confirm no `time.sleep` blocks and the fade lands inside `Song.update_display` ticks.
6. `create_audio_track` — create an empty audio track and remove it (one undo step).
7. `analyze_audio` — point at a local `.wav` and verify LUFS-I / RMS / per-band payload.
8. `find_frequency_masking` — supply two stems with the same 1 kHz tone at different amplitudes; expect a band-level excess report.
9. `analyze_mix` — supply a small set of stems; verify per-stem analysis plus pair-wise masking.
10. `extract_single_cycle` — point at a periodic stem and verify the detected pitch plus the cycle buffer.

After owner approval: merge with an explicit merge commit on `main`, rerun the release gates, create annotated tag `v0.5.0`, and request separate authorization before pushing branch, main, or tag.