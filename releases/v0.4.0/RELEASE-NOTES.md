# Release notes — v0.4.0

**Date**: 2026-07-11
**Branch**: `main`
**Base**: local `main` at `ce7fe9c`
**Merge commit**: `e62892e`
**Tag**: annotated `v0.4.0`, local-only; no push has been performed

## What ships

v0.4.0 expands the FastMCP surface from 46 to 56 tools:

- verified `set_parameter_value` writes with bounds, enabled-state, suggestions, readback, and batch support;
- `get_clip_info`, local `get_session_overview`, and bounded TCP `search_browser` reads;
- `delete_clip`, deferred `clear_clip_notes`, and `fire_scene` Session operations;
- verified `set_track_property` and `set_clip_properties` writes;
- capability-gated `create_clip_automation` for Session clip parameter envelopes.

`load_device_to_track` remains the existing WebSocket tool. Its validation now forwards the normalized URI, and its timeout/routing behavior has explicit tests. It was not duplicated.

MIDI note payloads gain optional `probability`, `release_velocity`, and `velocity_deviation`. `get_bridge_status` adds version, tool count, WebSocket endpoint/methods, runtime, and a fixed feature whitelist without removing existing fields.

Design inspiration is credited to:

- `pnomolos/live-wire` at `7fc8b06` — https://github.com/pnomolos/live-wire
- `hidingwill/AbletonBridge` at `01c31c4e` — https://github.com/hidingwill/AbletonBridge

No competitor code or dependency is vendored.

## Safety and compatibility

- All Python LOM access remains on Live's UI-thread queue.
- New mutations are explicit `ALLOWED_MUTATIONS`, own one undo step, and are never replayed after ambiguous network failure.
- `run_batch` still preserves a successful prefix and reports `rolled_back:false`.
- Browser traversal is bounded by depth 5, 500 children per node, 5000 visited objects, and 200 results.
- Automation is limited to Session clips and fails with a structured availability error when the host API is missing.
- Optional note-expression fields are omitted from legacy payloads unless requested.
- Session path IDs remain index locators and must be refreshed after structural edits.

The TCP listener explicitly binds `127.0.0.1`. The Extension WebSocket server still does not explicitly set its bind host. Do not expose or forward port `9889`; code-enforced loopback remains a separate security follow-up.

## Automated verification

| Gate | Result |
|---|---|
| `python -m pytest -q --tb=line` | 250 passed |
| `python scripts/coverage_check.py` | 85.9%, threshold passed |
| Ruff | clean |
| mypy `--strict` | clean across 14 source files |
| public FastMCP count | 56 |
| Extension `npm audit --audit-level=low` | 0 vulnerabilities |
| Extension `npm run build` | TypeScript check and bundle succeeded |
| contract vendoring | canonical and generated copies match |

The Extension build still emits an upstream deprecation warning for a transitive `glob` package from the pinned Ableton tooling, but npm reports no known vulnerabilities.

## Required owner acceptance before merge/tag

Automated tests do not prove connectivity to Ableton Live or real undo behavior. Before approving the merge, run against a disposable Live Set on Windows:

1. `ableton-mcp doctor --json` for a real TCP round trip.
2. Load the Extension and exercise `load_device_to_track` over WebSocket.
3. Write and undo a continuous and quantized device parameter.
4. Execute a three-item parameter batch and verify one Ctrl+Z reverts the group.
5. Exercise clip deletion/note clearing, scene firing, property writes, Browser search, and Session clip automation on disposable material.

After owner approval: merge with an explicit merge commit on `main`, rerun the release gates, create annotated tag `v0.4.0`, and request separate authorization before pushing branch, main, or tag.
