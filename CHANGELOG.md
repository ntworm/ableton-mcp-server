# Changelog

All notable changes to this project are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

The canonical certification policy that governs the promotion decision
(see `ableton-mcp acceptance --profile baseline` below) lives in
[`docs/CERTIFICATION.md`](docs/CERTIFICATION.md).

## [0.5.3] - 2026-08-04

Adds 8 tools to the 65-tool v0.5.2 baseline (73 total). Track hierarchy and
colour are now readable; colours are writable; moving/grouping tracks is
proven impossible through any public API and refuses accordingly.

### Added — track hierarchy reads and track colour

- `set_track_color(track_index, color_index=None, color=None)` writes Live's
  `Track.color_index` (70-swatch palette) or `Track.color` (packed
  `0x00rrggbb`) in one undo step, confirmed by readback, never retried.
- `get_track_list` / `get_track_state` now report `color`, `color_index`,
  `is_group_track` (`Track.is_foldable`), `is_grouped`, `group_track_index`,
  `group_track_id`, `is_visible` and `fold_state`. A Group Track has no MIDI
  input, so `type` still reads `audio` for it — `is_group_track` is the only
  correct group test. Properties a host does not expose are `null`, never
  invented. Mixer state stays on `get_track_state` only.

### Added — clip colour

- `set_clip_color(track_index, clip_index, scope="session", color_index=None,
  color=None)`. `Clip.color` and `Clip.color_index` are `getsetobserve` in the
  LOM and `Track.arrangement_clips` exists since Live 11, so **both** the
  Session and the Arrangement lane are genuinely writable. Single undo step,
  written once, confirmed by readback, no retry.
- `diagnose_clip_targets(track_index=None)` — read-only sweep reporting which
  clips `set_clip_color` can reach, with an explicit `inaccessible` list and a
  reason per entry. A host without `Track.arrangement_clips` is reported as
  `arrangement_supported: false` rather than as "zero Arrangement clips".

### Added — track hierarchy tools that refuse honestly

- `move_track`, `reorder_tracks`, `move_track_to_group`, `ungroup_track` and
  `merge_groups` are registered, documented and fully validated — and they
  always refuse, because no public API can perform them. Validation runs
  first (bad index → `INVALID_PARAMS`, return/main track → `WRONG_TYPE`,
  non-permutation order / cycle / self-nesting / `delete_empty_source=True` →
  `BAD_INPUT`), then a well-formed request returns `CAPABILITY_UNAVAILABLE`
  carrying the API evidence. No undo step is opened and nothing in the Set
  changes; tests assert clips, devices, notes, automation, mixer values,
  routing, colours, fold state and track order are byte-identical afterwards.
- Error envelopes gained an optional `details` object
  (`protocol.Response.details`, `errors.BridgeError.details`) so the refusal
  can carry machine-readable evidence instead of prose only.
- `get_bridge_status()` gained `capability_gaps` and a
  `capability_counts.capability_unavailable` entry, so the gap is discoverable
  without triggering a refusal.
- New certification status `capability_unavailable`: the expected steady state
  for those tools, and — unlike `host_unavailable` — it does not block a
  release. A hierarchy tool that ever *succeeds* is recorded as `failed`.
- Evidence, for the record. LOM `Song` exposes `create_audio_track(index)`,
  `create_midi_track(index)`, `duplicate_track(index)`, `delete_track(index)`
  and `move_device(...)`, with no reposition call; `song.tracks` and
  `song.visible_tracks` are get/observe and `Track.group_track` is get-only.
  Extension SDK 1.0.0-beta.0 has `songCreateMidiTrack`, `songCreateAudioTrack`,
  `songDuplicateTrack`, `songDeleteTrack` and `trackGetGroupTrack` — no move,
  no grouping, and its create calls take no index. Duplicate + delete cannot
  reorder at all (the copy always lands immediately after the original) and
  would destroy the original track.

### Documented

- `#` at the start of a track name is Live's native auto-numbering token, so
  `# DRUMS` is displayed and read back as `1 DRUMS`. This is Live behaviour,
  not a bridge bug; the LOM exposes no escape syntax and no separate display
  name, so the bridge sends names through unchanged instead of hiding the
  substitution. See `docs/KNOWN_BUGS.md` §Category P.

## [0.5.2] - 2026-08-01

### Added

- `ableton-mcp-server` `R3` — `setup_windows.ps1` now invokes
  `ableton-mcp install-status --json`, prints the SHA-256 of the installed
  `AbletonMCPServer_RemoteScript/__init__.py`, and surfaces the algorithm,
  hash, and path. JSON parse, exit code, and target presence are validated
  before the hash is computed, so partial installs and bad JSON no longer
  fail with cryptic PowerShell errors.
- `ableton-mcp-server` `R5` — `docs/KNOWN_BUGS.md` opens with a 5-bullet
  "Don't try these yet" executive summary pointing at categories G, H, K,
  F, and I. A new "## ⚠️ Known Bugs" section in `README.md` links to the
  full document so AI agents surface the constraints before relying on
  track indexes, `run_batch`, or a TCP loopback to Live.
- `ableton-mcp-server` `R1` — every successful mutation from
  `set_parameter_value`, `create_clip`, `set_tempo`, and
  `load_device_to_track` now returns a `resolved` sub-object. The shape
  is canonical across all four tools: `kind`, the location keys, and the
  name keys that were actually observed (`track_name` and
  `device_name` are omitted when the LOM returned an empty value, not
  emitted as empty strings). The transport shape is documented in
  `docs/superpowers/specs/2026-08-01-r1-resolved-field.md`.
- `ableton-mcp-server` `R4` — `get_bridge_status` now returns a
  capability matrix alongside the existing transport diagnostics:
  `tools` (65 entries with `name`, `route`, `risk`, and `acceptance`),
  `capability_counts` (6 named invariants), and `capability_source`
  (5 pointers to the canonical modules that hold each invariant). The
  full design lives in
  `docs/superpowers/specs/2026-08-01-r4-capability-matrix.md`. The
  narrative `docs/TOOL_REFERENCE.md` remains the hand-curated source of
  truth for human readers; the matrix is the machine-checkable mirror.

### Changed

- `test_build_extension.py::test_build_extension_propagates_subprocess_failure`
  was replaced by `test_build_extension_surfaces_nonzero_returncode`,
  which exercises the real `build_extension` failure path: a non-zero
  returncode is now asserted against the JSON payload that the function
  actually returns (`{"status": "error", "steps": [...]}`). The
  exception-propagation path is now covered separately by
  `test_build_extension_propagates_subprocess_exception`.
- `test_resolved_envelope.py::test_resolved_omitted_keys_when_name_unavailable`
  now drives the real `cmd_create_clip` against a `FakeSong` whose
  track name is empty, instead of mocking the client. The canonical
  signal — `track_name` key absent from `resolved` — is asserted
  end-to-end through the Remote Script and a sanity case confirms
  the key is present when the name is non-empty.

### Fixed

- `setup_windows.ps1` no longer crashes with an unhandled JSON parse
  error when `install-status` exits non-zero with a non-JSON payload.
- `setup_windows.ps1` no longer crashes with an unhandled
  `Get-FileHash` error when the Remote Script install target directory
  is missing the expected `__init__.py`.

## [0.5.1] - 2026-07-13

### Added

- `ableton_mcp_server.catalog` exposes the canonical 65-tool `TOOL_CATALOG`
  (`ToolSpec` with `Route`, `Risk`, `AcceptanceMode`). `PUBLIC_TOOL_NAMES`
  is now derived from the catalog — the catalog is the single source of
  truth.
- `ableton_mcp_server.certification` provides an immutable `Verification`
  record and a per-run `CertificationReport` aggregator with the statuses
  `offline_passed`, `live_passed`, `manual_passed`, `host_unavailable`,
  `environment_unavailable`, and `failed`.
- `scripts/verify_clean_install.ps1` — isolated wheel install probe that
  succeeds without Node.js.

### Changed

- `load_device_to_track` takes a primary `device_name` argument; the
  `device_uri` alias is retained for one release cycle. Only the resolved
  name travels over the WebSocket bridge.
- `set_warp_state` no longer accepts `warp_markers`. Marker writes are
  rejected at the model layer; `get_warp_state` keeps returning the
  read-only marker array.
- Browser search in the Remote Script now tracks visited nodes by URI and
  ordinal path rather than `id()`, so the traversal stays stable across
  Live's LOM proxy wrappers.
- `create_audio_track` now identifies the newly-created track by counting
  the regular-track collection before and after the mutation; proxy
  identity is no longer trusted.
- `find_frequency_masking` switches from per-bin log means to STFT power
  and trims both signals to a shared sample count before the band
  comparison.
- Both bridges (TCP Remote Script and WebSocket Extension) now share a
  stable error taxonomy: `CAPABILITY_UNAVAILABLE`, `AMBIGUOUS_MATCH`,
  `VERIFICATION_FAILED`, `ACCEPTANCE_GUARD_FAILED`.

### Diagnostics

- `bridge_status` reports `source_kind` (`checkout` vs `wheel`),
  `source`, and resolved `python_executable` so an unfamiliar agent can
  confirm which tree is running.

### Safety

- All TCP and WebSocket mutations stay on their originating runtime
  thread; no automatic retry after connection loss.
- The Release Blockers gate now runs every tool through
  `CertificationReport.finish()`; a single `failed` row blocks the
  release.

## [0.5.0] - 2026-07-13

### Added

- Nine public tools, bringing the FastMCP surface to 65:
  - Set lifecycle: `lifecycle_status` (read-only probe of save/quit API availability), `save_set` (conditional `Song.save()`), `quit_ableton` (save-then-quit with scheduled GUI fallback), `live_fade` (smoothstep/linear interpolation distributed across `duration` via `time.monotonic`; yields between steps; never blocks the Live main thread).
  - Track creation: `create_audio_track` (mirrors `create_midi_track`, zero-touch).
  - Offline mix analysis: `analyze_audio` (LUFS-I, true-peak, RMS, per-band energy), `find_frequency_masking` (target/reference band-level delta), `analyze_mix` (up to 16 stems with pair-wise masking), `extract_single_cycle` (pitch detection plus single-cycle buffer).
- New `ableton_mcp_server.analysis` package — dependency-free of Live and the bridge; reads local audio through `soundfile`.
- Runtime identity tag in `get_bridge_status` payload (e.g. `set-lifecycle-and-fade-1`) so consumers can distinguish which feature set a given server is running.
- Contract vendoring: `live_fade` 60-second timeout override; `lifecycle_status` listed in `READ_COMMANDS`.
- `time.sleep` removed from `live_fade_steps` per repo invariant (no blocking on Live main thread); steps execute inside `Song.update_display` ticks.

### Changed

- Public tool registry: `PUBLIC_TOOL_FUNCTIONS` is now assembled at the end of `server.py` after the v0.5.0 mix analysis wrappers are defined; the upstream portion is exposed as `PUBLIC_TOOL_FUNCTIONS_HEAD` for readability.

### Safety

- All new Python LOM work remains on Live's UI-thread queue; one undo step; no automatic replay after ambiguous network failure.
- Mix analysis is dependency-free of Live, the Remote Script, and the bridge — it cannot touch the Set.

### Attribution

- No third-party code vendored; design notes referenced from prior in-repo specs under `docs/superpowers/specs/`.

## [0.4.0] - 2026-07-11

### Added

- Ten public tools, bringing the FastMCP surface to 56:
  - `set_parameter_value` with bounds, enabled-state, close-name suggestions, deferred readback, and batch support.
  - `get_clip_info`, `get_session_overview`, and bounded TCP `search_browser` reads.
  - `delete_clip`, `clear_clip_notes`, `fire_scene`, `set_track_property`, and `set_clip_properties` Session operations.
  - Capability-gated `create_clip_automation` for Session clip parameter envelopes.
- Optional MIDI note `probability`, `release_velocity`, and `velocity_deviation` fields.
- Backward-compatible server version, tool count, WebSocket method, runtime, and feature metadata in `get_bridge_status`.
- Command-specific deadlines and bounded work-unit scaling for device loading, Browser search, clip properties, note clearing, and automation.

### Changed

- `load_device_to_track` remains the existing WebSocket-routed tool and now has explicit 30-second timeout coverage; it was not duplicated.
- Optional MIDI expression fields are omitted from legacy wire payloads unless requested.
- Browser search uses the Remote Script's existing `application.browser` access and does not require the Extension.

### Safety

- All new Python LOM work remains on Live's UI-thread queue. Mutations use the explicit allowlist, one undo step, and no automatic replay after ambiguous network failure.
- Browser traversal is bounded by depth, per-node children, visited nodes, and results. Automation is limited to Session clips and fails explicitly when host APIs are absent.

### Attribution

- Design inspiration: `pnomolos/live-wire` at `7fc8b06` — https://github.com/pnomolos/live-wire
- Design inspiration: `hidingwill/AbletonBridge` at `01c31c4e` — https://github.com/hidingwill/AbletonBridge

## [0.3.0] - 2026-07-10

### Added
- Hybrid Dual-Bridge Architecture: support for routing transport/MIDI commands to Remote Script (TCP `9888`) and warping/device commands to Extension Host (WebSocket `9889`).
- Node.js/TypeScript Extension Host bridge component (`AbletonMCPServer_Extension`).
- Pydantic models and FastMCP tool interfaces for 9 new tools:
  - `get_composition_structure` (full track layout metadata).
  - `diagnose_midi_clip` (note overlap detection, C-major scale matching, and grid timing drift analysis).
  - `create_midi_track` (guarded with 96-track safety limit).
  - `rename_track` (renaming tracks/clips).
  - `get_warp_state` & `set_warp_state` (reading and writing audio clip warping properties via WebSocket).
  - `load_device_to_track` (loading native instruments/devices via WebSocket).
  - `scaffold_extension` & `build_extension` (scaffolding and compiling native Ableton Extensions).
- `ExtensionUnavailableError` and `TrackLimitError` error classes.
- Unit tests for WSClient, composition queries, track mutations, and MIDI diagnostics.

## [0.2.2] - 2026-07-10

### Changed

- Cue toggles and cue renames are observed across up to ten Live UI ticks before a result is reported.
- Playhead and state writes now tolerate up to ten transitional UI ticks.
- JSONL deadlines use a shared 20-second base and scale with bulk/batch work instead of using conflicting client/server constants.
- Bulk cue creation holds the working cursor and restores the original cursor once after all items.

### Fixed

- Empty list results retain structured `[]` data and an explicit text fallback across FastMCP clients.
- Expected bridge errors become typed MCP error results instead of escaping as framework exceptions and tracebacks.
- Idle persistent JSONL connections stay open; the socket timeout now polls for shutdown rather than closing a healthy client.
- Windows socket failures become typed `LIVE_UNAVAILABLE` errors and keep mutation retry decisions explicit.
- Delayed cue toggles no longer race cursor restoration and leave default-name markers at the restored position.
- Cue names are verified and idempotently retried when Live drops a name write.
- Cue operations no longer write `Song.start_time`; the official LOM defines it as the playback start position rather than the cue cursor.
- Live 12 Beta Arrangement-grid snapping is detected transactionally. An unintended off-grid cue creation or deletion is reversed and returned as `CUE_SNAPPED_TO_GRID` instead of leaking or corrupting a locator.

## [0.2.1] - 2026-07-09

### Added

- Native Windows bootstrap, packaged Remote Script installer, installation status, and bridge doctor commands.
- A guarded real-Live acceptance runner that refuses to mutate unless the disposable Set name, MIDI track, and empty clip slot all match.
- `get_bridge_status`, bringing the public FastMCP surface to 37 tools.
- Cross-platform Ableton log discovery with an explicit `ABLETON_MCP_LOG_PATH` override.

### Changed

- WSL uses the native Windows MCP executable to reach Live's loopback listener; the listener remains bound to `127.0.0.1:9888`.
- Live mutations now advance and verify across `update_display` ticks without sleeping on Live's UI thread.
- Batches execute deferred child operations inside one outer undo step, abort at the first error, and report the exact successful prefix.

### Fixed

- Embedded Python note insertion now constructs `Live.Clip.MidiNoteSpecification` objects instead of passing Max-for-Live-style dictionaries.
- Transport and loop results are verified only after Live has had a UI tick to apply each write.
- Cue creation/deletion moves and restores both `current_song_time` and `start_time`, preventing misplaced toggles and false failures.
- Verbose diagnostics use a consistent `[MCP-Server]` prefix and emit a startup endpoint record.
- Wheel builds include the canonical contracts module and installable Remote Script assets.

### Security

- The bridge remains loopback-only. WSL compatibility does not expose port 9888 on the LAN.

## [0.2.0] - 2026-07-09

### Added

- Greenfield `ableton_mcp_server` package and MIDI Remote Script.
- Thirty-six documented FastMCP tools.
- TCP JSONL protocol on `127.0.0.1:9888` with typed error envelopes.
- Dependency-free canonical contracts with deterministic vendoring.
- Session path-ids, typed bridge errors, Pydantic request models, snapshots, and diffs.
- Verified transport setters, idempotent cue-point handling, clip creation/firing, MIDI note insertion, and grouped batch execution.
- Stateful mock Remote Script, socket integration check, and test suite runnable without Live.
- Opt-in `[PROBE]` logging through `ABLETON_MCP_SERVER_VERBOSE=1`.

### Changed

- Debug-relevant mutations are explicitly allowed instead of being blocked by command-name prefixes.
- Mutations are not automatically retried after ambiguous connection failures.
- Batch errors preserve the already-applied prefix in a single undo step rather than claiming automatic rollback.

### Removed

- `set_song_length`, because `Song.song_length` is read-only in the Live Object Model.
- Prefix-based mutation blocking and duplicated protocol constants.

### Fixed

- Transport verification now reads an explicit attribute after every write; it never compares lambda identity.
- Cue deletion uses `set_or_delete_cue` after a verified playhead move.
- Cue beat-time objects are cast to `float` before comparison.
- `create_clip`, `fire_clip`, and `add_notes_to_clip` are no longer incorrectly blocked.
