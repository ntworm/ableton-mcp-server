# REQUEST: Borrow selected features from `pnomolos/live-wire` and `hidingwill/AbletonBridge`

**Author:** Worm (via Sotha)
**Date:** 2026-07-10
**Status:** OPEN
**Target version:** v0.4.0 (a single PR is too small for v0.3.1; this needs room)
**Branch suggestion:** `feature/v0.4.0-borrow-competitor-features`

---

## 1. Why this request exists

The Discord scan on 2026-07-10 found **two actively-maintained Ableton MCP servers** that solve problems our server does not. We are not the only ship in this category — `pnomolos/live-wire` and `hidingwill/AbletonBridge` both target the same niche from different angles.

| repo | stars/age | core idea | weaknesses vs us |
|---|---|---|---|
| [`pnomolos/live-wire`](https://github.com/pnomolos/live-wire) | 5★, v1.0.0 Jun 5 2026 | Reflection-based MCP via M4L Proxy + Extension (WebSocket bridge to v8+LiveAPI). Exposes the **entire LOM** as `live_get_property` / `live_call_method`. | Requires M4L (Suite-or-add-on only). Single 1-commit release — volatile. Our TCP/JSONL + LOM handlers are more deterministic. |
| [`hidingwill/AbletonBridge`](https://github.com/hidingwill/AbletonBridge) | mature, CHANGELOG 100KB | Remote Script (TCP+UDP) + M4L UDP/OSC bridge + Web dashboard. **340 core tools** + 19 ElevenLabs. | Massive surface, hard to test, ElevenLabs dependency. Many tools write to audio-effect device, not pure Python LOM. |

We should **not** wholesale-import either. We should:

1. **Adopt the gaps** that make our server less capable than theirs on **safe, well-isolated** primitives.
2. **Cite both projects** in the resulting PR descriptions and docs — credit, not clone.
3. **Stay focused** on what fits our `contracts.py` allowlist model and our existing tests.

The implementing agent must **selectively** pick what to bring across. Not every idea below is in scope — pick the safe ones and stop.

## 2. Candidate features (the implementing agent curates)

### From `live-wire`

| # | Feature | Why it matters | Safety check before adopting |
|---|---|---|---|
| LW-1 | **Reflection primitives** — `live_get_ref`, `live_introspect`, `live_navigate`, `live_get_property`, `live_set_property`, `live_call_method`, `live_list_refs` | Generic escape hatch: agents discover and call LOM without us hand-coding every property. | **HIGH RISK.** Reflection = arbitrary LOM writes. Bypasses our mutation allowlist. Reject unless scoped behind a `enable_reflection=true` flag off by default, mirroring `READ_ONLY_COMMANDS` model. |
| LW-2 | **`live_load_instrument(track_index, name)` / `live_list_available_instruments`** / effects equivalent | Today we only have `load_device_to_track(uri)` (browser URI). User can ask for "Operator" by name; today they'd have to know the URI. | **MEDIUM RISK.** LOM name → URI resolution is undocumented and version-dependent. Mirror as WS-routed commands (same path as `load_device_to_track`) since browser loading is Extension SDK territory. |
| LW-3 | **`live_set_track_property(track_index, mute/solo/arm)`** | Tiny gap. We have `rename_track` and `create_midi_track` but no mute/solo/arm. | **LOW RISK.** Pure LOM reads/writes, fits our TCP bridge. Adopt. |
| LW-4 | **`live_fire_scene(scene_index)`** | We have `fire_clip` but no scene fire. | **LOW RISK.** LOM `Scene.fire()`. Adopt. |
| LW-5 | **`live_set_clip_properties(track, clip, loop_start, loop_end, name, ...)`** | Today you can't resize a clip after `create_clip(4.0)`. | **MEDIUM RISK.** Live 12.4.5b7 grid-snap caveats (Category B in KNOWN_BUGS). Needs the same playhead-suspend trick our cue ops use. |
| LW-6 | **`live_session_overview()` composite read** | We have separate `get_session_info` / `get_track_list` / `get_scenes`. A single call is cheaper for agents that need a snapshot. | **LOW RISK.** Pure read, just a join. Adopt as a thin wrapper. |
| LW-7 | **M4L audio analysis** (`m4l_get_analysis`) | RMS/spectrum/transient per track. Requires M4L device on a track. | **OUT OF SCOPE.** Requires a M4L companion device. Our server is M4L-free. Defer. |
| LW-8 | **Vector + ref format serialization** (`__vector__`, `__ref__`) | Their protocol design for passing Live objects. | **OUT OF SCOPE.** Our path-id scheme (`track:N/device:N/param:N`) is already the contract. Changing serialization breaks every consumer. |

### From `AbletonBridge`

| # | Feature | Why it matters | Safety check before adopting |
|---|---|---|---|
| AB-1 | **`delete_clip(track_index, clip_index)`** | Today you can create + fire, but not delete. | **LOW RISK.** LOM `ClipSlot.delete_clip()`. One undo step. Adopt. |
| AB-2 | **`clear_clip_notes(track_index, clip_index)`** | Today `add_notes_to_clip` only appends. No way to clear without deleting the clip. | **LOW RISK.** LOM `Clip.remove_notes_extended(0, 128, 0, clip_length)`. One undo step. Adopt. |
| AB-3 | **`get_clip_info(track_index, clip_index)`** | Richer than `get_clip_summary` (start/end, loop, follow action, color). | **LOW RISK.** Read-only. Adopt. |
| AB-4 | **`add_notes_extended(notes, ...)` with mute/probability/velocity-deviation** | `add_notes_to_clip` accepts `mute:bool`. AbletonBridge has fuller tuple (probability, release velocity). | **MEDIUM RISK.** MIDI note spec fields are partially LOM-supported. Stage: add `probability` and `release_velocity` fields to our `NoteSpec` model — LOM ignores unknown fields silently, so safe to surface without binding. |
| AB-5 | **`create_clip_automation(...)` / `create_track_automation(...)`** | We have **zero** automation tools today. Big gap. | **HIGH RISK.** Automation lanes are notoriously fragile in Live (see known LOM bugs). Stage: implement Session clip automation only (simpler than track automation). Verify with deferred readback, not fire-and-forget. |
| AB-6 | **`snapshot_device_state` / `restore_device_snapshot` / `list_snapshots` (in-memory)** | We have `take_snapshot()` (whole Set). They snapshot individual devices, including **hidden** parameters (via M4L). | **OUT OF SCOPE.** Their snapshot uses M4L bridge to read hidden params. Without M4L, ours is just a list of the device's exposed parameters — already covered by `list_device_params`. Defer. |
| AB-7 | **`get_server_capabilities()`** | Reports server version, connections, feature set, tool count. | **LOW RISK.** Pure introspection, no LOM touch. Adopt. We already have `get_bridge_status` — extend it. |
| AB-8 | **M4L UDP/OSC bridge (port 9882)** | Reaches hidden parameters, rack chain internals, modulation matrix. | **OUT OF SCOPE.** Requires M4L. Defer. |
| AB-9 | **Web dashboard (HTTP 9880)** | Real-time tool metrics + server logs. | **OUT OF SCOPE.** Nice-to-have, not core. Defer. |
| AB-10 | **MCP resources (`ableton://session`, `ableton://tracks`, `ableton://capabilities`)** | Direct data access for MCP clients that prefer resource reads. | **MEDIUM RISK.** FastMCP supports resources. Stage: add 2-3 read-only resources. Pure serialization, no LOM mutation. |
| AB-11 | **MCP prompts (`create-beat`, `mix-track`, `sound-design`, `arrange-section`)** | Guided workflow templates for coding agents. | **MEDIUM RISK.** Prompts are not strictly needed if our tool docstrings are clear. Stage: add only if we see real agents struggling with multi-step workflows. Validate against our docstring discipline first. |
| AB-12 | **Browser cache (populate + persist + resolve URI)** | They cache the full browser tree on first request. Resolves `name → uri` offline. | **HIGH RISK.** Their cache is in `MCP_Server/cache/browser.py` with disk persistence. Adds operational complexity (stale cache, invalidation). Defer unless we see real friction with `load_device_to_track(uri=…)`. |
| AB-13 | **`search_browser(name)` / `load_browser_item(uri_or_name)`** | Today we have `get_browser_categories` only. No search. | **MEDIUM RISK → LOW.** Python LOM `application.browser` already used in `cmd_get_browser_categories` (line 533 of our Remote Script). Implement as TCP sync `cmd_*` handler. Stage: walk browser tree depth-first with limit clamp. |
| AB-14 | **Creative generators (Euclidean rhythm, chord progressions, arpeggios, drum patterns)** | Higher-level composition helpers. | **MEDIUM RISK.** Pure Python code, no LOM risk. But scope creep risk: every generator is its own test surface. Adopt **only** `generate_euclidean_rhythm` (most-cited, simplest, 1 test). Reject the rest for v0.4.0 — punt to v0.5.0. |
| AB-15 | **Grid notation (ASCII drum/melodic)** | Compact input format for MIDI patterns. | **MEDIUM RISK.** Pure parser. Adopt if we adopt AB-14, otherwise defer. |
| AB-16 | **MIDI CC maps for Arturia + NI plugins (76 JSON files)** | Pre-mapped parameter names for the popular proprietary plugins. | **OUT OF SCOPE.** Vendor-specific, large content, requires maintenance. Defer. |
| AB-17 | **`create_follow_action(...)` / scene follow actions** | Clip launch chaining. | **HIGH RISK.** LOM follow-action API is fiddly and undocumented. Defer. |
| AB-18 | **Arrangement clips / time editing** | Today `create_clip` only creates Session clips. | **HIGH RISK.** Arrangement operations compound with grid-snap (Category B in KNOWN_BUGS). Defer until v0.5.0 at earliest. |
| AB-19 | **Sidechain routing / modulation matrix** | M4L territory. | **OUT OF SCOPE.** M4L-required. Defer. |
| AB-20 | **Compound workflows (`create_instrument_track(track_name, instrument_name)`)** | One-call sugar over `create_midi_track` + `load_device_to_track`. | **LOW RISK.** Pure composition of existing tools. Adopt as `_`-prefixed internal helper, **NOT** as public MCP tool. Keeps the tool surface clean. |
| AB-21 | **Chunked async LiveAPI + chunked base64 response protocol** | Reliability pattern for large responses. | **LOW RISK.** Engineering hygiene. Adopt only if our existing `take_snapshot()` actually hits size limits in real Sets. We don't know yet — defer. |
| AB-22 | **Fire-and-forget writes (no readback)** | They deliberately skip readback on mutations to avoid crashes. | **OUT OF SCOPE.** Contradicts our deferred-mutation verification model (Category A in KNOWN_BUGS). Reject. |
| AB-23 | **Command-specific timeouts** | `freeze_track → 60s`, `load_instrument → 30s`. | **LOW RISK.** Already partly implemented via `request_timeout_seconds(command, params)` in `contracts.py`. Adopt: extend the work-units table for the new commands. |

## 3. Suggested v0.4.0 scope (implementer's starting point)

The implementing agent should **not exceed** this curated list. Each item is small enough to ship in one PR with full tests.

| Tool / change | Source | Backend | Notes |
|---|---|---|---|
| `delete_clip(track_index, clip_index)` | AB-1 | TCP/JSONL | `ALLOWED_MUTATIONS`, `_handle_delete_clip` |
| `clear_clip_notes(track_index, clip_index)` | AB-2 | TCP/JSONL | `ALLOWED_MUTATIONS`, `remove_notes_extended` |
| `get_clip_info(track_index, clip_index)` | AB-3 | TCP/JSONL | `READ_COMMANDS` |
| `set_track_property(track_index, property: "mute"|"solo"|"arm", value)` | LW-3 | TCP/JSONL | `ALLOWED_MUTATIONS` |
| `fire_scene(scene_index)` | LW-4 | TCP/JSONL | `ALLOWED_MUTATIONS` |
| `set_clip_properties(track_index, clip_index, loop_start?, loop_end?, name?)` | LW-5 | TCP/JSONL | Needs playhead-suspend pattern; deferred readback |
| `get_session_overview()` (composite) | LW-6 | TCP/JSONL | Joins existing reads; pure wrapper |
| `get_server_capabilities()` (extend `get_bridge_status`) | AB-7 | local | No LOM touch |
| `add_notes_extended(...)` (extended NoteSpec with `probability`, `release_velocity`) | AB-4 | TCP/JSONL | Extend `NoteSpec` model |
| `create_clip_automation(track_index, clip_index, parameter_name, automation_points)` | AB-5 (limited) | TCP/JSONL | Session clip only. Deferred readback. |
| `search_browser(query, category_type?)` | AB-13 | WS/JSON-RPC | New handler in `AbletonMCPServer_Extension/src/index.ts` |
| `_compound_create_instrument_track(name, instrument_uri)` | AB-20 | internal helper | NOT a public tool |
| Extend `request_timeout_seconds` work-units table | AB-23 | `contracts.py` | Per new command |

**Reject for v0.4.0** (explicit non-goals this round):

- Reflection primitives (LW-1) — needs a flag-off-by-default gate; design first.
- M4L bridges (LW-7, AB-8) — M4L-free server.
- Web dashboard (AB-9).
- Snapshots beyond device (AB-6).
- Automation beyond Session clips (AB-5 limited).
- Browser cache (AB-12) — premature.
- Creative generators beyond Euclidean (AB-14 limited).
- Arrangement operations (AB-18).
- Sidechain / modulation matrix (AB-19).
- MIDI CC maps (AB-16).
- Follow actions (AB-17).
- Vector/ref serialization (LW-8).

## 4. Architecture constraints (do not violate)

Our server already has the hybrid client (`ableton_mcp_server/ws_client.py`) routing WS-targeted commands. Use the same model:

1. **TCP vs WS routing** — browser-touching commands stay on WS 9889 (`load_device_to_track`, new `search_browser`). Everything else stays on TCP 9888.
2. **Allowlist enforcement** — every new mutation gets a row in `contracts.ALLOWED_MUTATIONS`. Don't add to a global allow-all dispatcher.
3. **Deferred verification** — new mutations must follow the existing generator-yield-readback-retry pattern from `AbletonMCPServer_RemoteScript/__init__.py`. **No fire-and-forget writes** (reject AB-22).
4. **Mutation verification gates** — every new mutation must pass against `ableton-mcp acceptance` runner with a disposable Set.
5. **Path-id stability** — adopt LW-8 paths (`__vector__`, `__ref__`) ONLY as informational fields, never as the canonical id. We are staying with `track:N/device:N/param:N`.
6. **Test discipline** — every new tool needs:
   - Unit test in `tests/test_server_tools.py` (mocked Remote Script).
   - Round-trip test against mock socket if it crosses the bridge.
   - Coverage check passes (`python scripts/coverage_check.py`).
   - Update `tests/test_packaging.py` count assertion (`len(PUBLIC_TOOL_NAMES) == N+1`).
7. **Concurrency** — Session-clip automation writes compete with MIDI note writes on the same `Clip`. Either serialize or document the contention. Prefer serialize.
8. **Vendor bridges** — neither live-wire nor AbletonBridge is a dependency. **Read their code, don't vendor it.** Cite in PR description.

## 5. Cross-cutting edits (one PR's worth)

If we ship the v0.4.0 curated list above, the PR will touch:

| file | change |
|---|---|
| `contracts.py` | Add ~6 names to `ALLOWED_MUTATIONS`, ~2 to `READ_COMMANDS`, work-units table updates |
| `AbletonMCPServer_RemoteScript/__init__.py` | New `_handle_*` functions; one underscore-named generator per deferred mutation |
| `ableton_mcp_server/server.py` | New `@mcp.tool()` registrations; `PUBLIC_TOOL_NAMES` updated |
| `ableton_mcp_server/models.py` | Extended `NoteSpec` (probability, release_velocity) |
| `AbletonMCPServer_Extension/src/index.ts` | New `handleSearchBrowser` JSON-RPC method |
| `tests/` | New test files for new commands; updated counts |
| `docs/TOOL_REFERENCE.md` | New entries (46 → ~58) |
| `CHANGELOG.md` | v0.4.0 entry citing live-wire and AbletonBridge |
| `prompts/REQUEST-2026-07-10-…md` | (this file) — close it once implemented |

Re-run `vendor_contracts.py` after every `contracts.py` edit (Category F in KNOWN_BUGS).

## 6. Out of scope (explicit non-goals)

1. Bundling a M4L device to expose hidden params (LW-7, AB-8).
2. Adding `create_device` / `delete_device` / `replace_device` (still blocked per LOM constraints — see `READ_ONLY_COMMANDS`).
3. Vendoring any of the competitor code (read, cite, rewrite).
4. Adding ElevenLabs voice tools (AB's optional 19).
5. Audio rendering tools (extension SDK doesn't expose post-FX).
6. Touching AbletonOSC / cue_point path (already works).
7. Touching `ableton-mcp-server` packages unrelated to this list.

## 7. Verification (before merge)

```powershell
python -m pytest -q --tb=line
python scripts\coverage_check.py
python -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests
python -m mypy --strict ableton_mcp_server
python -c "from ableton_mcp_server.server import mcp; print(len(mcp.list_tools()))"
# Expected: 46 + 8 = 54 tools (or whatever the curated count ends at)

cd AbletonMCPServer_Extension && npm install && npm run build

# Real-Live acceptance against a disposable Set:
.\.venv-win\Scripts\ableton-mcp.exe acceptance `
  --confirm-project-name TESTE_CODEX `
  --track-index 0 `
  --clip-index 3 `
  --fire-clip `
  --json
```

Plus per-tool round-trip tests with a fresh disposable Set for the new mutations.

## 8. Risks & mitigations (carry-overs from KNOWN_BUGS.md)

- **WSL ↔ Windows networking (K)** — verification must run on Windows Python.
- **3 control surfaces competing** — confirm `ableton-mcp-server` is the only one binding 9888/9889 before testing.
- **Ambiguous network failure (C)** — mutations must verify, never fire-and-forget.
- **`run_batch` abort semantics (D)** — if a new mutation goes into `run_batch`, document its failure boundary.
- **Cue grid snap (E)** — applies to any future arrangement ops; not relevant to this v0.4.0 scope, but flag for the next iteration.
- **Vendor contract drift (F)** — re-run `vendor_contracts.py` after every edit.
- **MIDI note API diff (H)** — `probability` and `release_velocity` may or may not round-trip through the Python LOM. Probe before promising.

## 9. Attribution

This request was scoped after a Discord scan on 2026-07-10. The implementing agent must:

- Cite **both** repos by URL and commit hash in the PR description.
- Mention them in `CHANGELOG.md` v0.4.0 entry as prior art.
- Not vendor any code from either.

## 10. Open questions for the implementing agent

1. `set_clip_properties.loop_end`: do we round to bar grid, or accept fractional beats and document the grid-snap caveat?
2. `create_clip_automation`: do we accept fractional parameter values, or normalize to device's quantization grid?
3. `search_browser`: do we cache results like AbletonBridge, or hit the Extension SDK every time?
4. `set_track_property`: do we accept all 3 of `mute|solo|arm` in one call, or 3 separate tools (mirroring LOM)?
5. `get_server_capabilities`: should it report Extension Host WS bridge availability, not just TCP?

If unsure, ask in the PR thread. Do not silently expand scope.