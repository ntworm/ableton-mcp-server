# Core-Complete Capability Program Design

## Purpose

Turn `ableton-mcp-server` from a promising 65-tool development build into a
turnkey, agent-friendly Ableton control surface whose advertised capabilities
are truthful, installable from a fresh clone, and proven against both automated
tests and a disposable Live Set.

“Complete” in this program means complete for the supported, dependency-light
core: the Ableton Python Remote Script, the existing Ableton Extension, and the
local Python MCP process. It does not mean exposing every Live internal or
matching another repository's tool count. A capability is part of the supported
core only when it has a stable schema, bounded behavior, structured errors,
documentation, automated coverage, and an explicit verification status.

## Approved constraints

- Preserve the existing hybrid architecture: FastMCP over stdio, the Python
  Remote Script on loopback TCP `127.0.0.1:9888`, and the existing Ableton
  Extension on loopback WebSocket `127.0.0.1:9889`.
- Require no Max for Live device, MIDI CC port, OSC/UDP bridge, ElevenLabs
  account, web dashboard, second MCP server, or separately managed background
  process.
- Do not add vendor-specific controller mappings or a generic remote-code or
  reflection primitive.
- Python packages already required by the existing 65 tools must be declared
  and installed automatically by the normal package install. They must not
  require a separate manual setup flow.
- Prefer a smaller typed capability to multiple near-duplicate tools. The
  target public surface is 125 tools: the existing 65 plus 60 high-value tools.
- Continue binding every bridge to loopback. LAN exposure is not part of the
  supported product.
- Preserve explicit mutation allowlists, no automatic mutation retry after an
  ambiguous connection failure, deferred Live readback, and grouped undo.
- Do not push, merge, tag, or publish without separate owner authorization.

## Delivery slices

The program is one architecture with three independently reviewable delivery
slices. Each slice must leave the repository installable and testable.

1. **Stabilize and certify the existing 65 tools.** Fix confirmed defects,
   reconcile packaging and versions, introduce a machine-readable capability
   catalog, and produce per-tool evidence.
2. **Reach core capability completeness.** Add 60 tools in coherent domain
   groups, using only the existing Remote Script and Extension runtimes.
3. **Make first-clone operation turnkey.** Add MCP instructions, resources,
   prompts, one-command Windows setup, comprehensive diagnostics, generated
   reference documentation, and guarded Live acceptance profiles.

The implementation work must follow this order. Capability expansion cannot
hide failures in the original surface, and onboarding cannot claim support for
uncertified tools.

## Architecture

### Runtime routing

The public MCP layer remains the only interface seen by agents. It validates
arguments, applies safety metadata, and routes each command to one of four
explicit execution targets:

1. `local` for filesystem diagnostics, snapshots, extension scaffolding, and
   offline audio analysis;
2. `tcp` for Python Live Object Model operations that need the Remote Script UI
   thread, deferred ticks, and grouped undo;
3. `websocket` for operations natively supported by the official Extensions
   SDK, especially devices, racks, Simpler samples, and audio-clip warp state;
4. `composed` for an MCP operation implemented by orchestrating existing reads
   or mutations while preserving one public contract.

No third bridge will be added. When both Live runtimes expose an operation, the
Extension SDK is preferred when it offers a direct typed setter; the Remote
Script remains authoritative for transport, undo, and operations that must run
on Live's main thread. `get_bridge_status` reports the selected route and host
support for every capability group.

### Tool modules and catalog

The current `ableton_mcp_server/server.py` is already too large to accept 60
more decorated functions safely. It becomes a small composition root while
domain modules register tools for session, tracks, scenes, clips, arrangement,
automation, devices/browser, diagnostics, and analysis.

A single Python capability catalog owns public metadata for every tool:

- public name and domain;
- route (`local`, `tcp`, `websocket`, or `composed`);
- read/mutation classification and destructive-risk level;
- required Live object type and minimum runtime capability;
- automatic, guarded, or manual acceptance mode;
- reversibility and cleanup strategy;
- concise agent-facing purpose.

`PUBLIC_TOOL_NAMES`, tool-count checks, generated documentation, MCP resources,
diagnostic output, and acceptance coverage are derived from this catalog. The
wire command allowlists remain in `contracts.py` because that file is vendored
into Live, but tests require an exact mapping between catalog routes and wire
contracts so the two cannot drift silently.

New Remote Script handlers are organized by domain. Existing handlers are
extracted only when touched by a fix or shared by a new capability; this avoids
a high-risk rewrite before the baseline is stable. Compatibility imports keep
current tests and installed script entry points working throughout migration.

### Stable selectors and identity

Public selectors use typed index/path selectors and always return the observed
index/path after mutation. Python `id()` values and object proxy identity are
never used as persistent or cross-enumeration identity. After structural edits,
the handler re-enumerates Live collections and identifies results through the
requested insertion index, collection delta, stable LOM properties, or SDK
handles available within one request. Agents are told to refresh path selectors
after any structural edit.

## Slice 1: stabilize and certify the current 65

### Confirmed corrections

1. `create_audio_track` must name and return the newly created track rather
   than relying on Python proxy identity across LOM enumerations.
2. `search_browser` must traverse known categories without using unstable
   proxy identity and must find canonical built-ins such as `Operator` and
   `Utility` on the tested Live build.
3. `load_device_to_track` must accept the actual SDK contract (`device_name`)
   and retain a deprecated `device_uri` alias for one compatibility cycle. The
   response reports the resolved name, track, and inserted device index.
4. `set_warp_state` must expose only writable SDK fields. Warp markers remain
   readable through `get_warp_state`; attempts to write them return a structured
   `CAPABILITY_UNAVAILABLE` error instead of a false success.
5. `find_frequency_masking` must detect narrow tonal overlap as well as
   broadband masking. Its algorithm and thresholds are covered by deterministic
   synthesized tone, noise, silence, sample-rate, and duration cases.
6. Package metadata must resolve in a clean environment: FastMCP and
   `websockets` ranges are compatible, existing `numpy`/`soundfile` imports are
   declared, and a wheel/sdist dry install succeeds.
7. Mypy failures in project-owned code are corrected. Third-party typing gaps
   are isolated by targeted stubs or configuration, not global suppression.
8. Root version, Python package version, Remote Script runtime identity,
   Extension `package.json`, Extension manifest, and generated documentation
   must agree. Packaging tests cover all of them.
9. Installation status compares the working tree or installed wheel selected by
   the running executable and reports that source explicitly, preventing a stale
   site-packages copy from masquerading as the checkout.
10. Architecture and tool-reference documents are regenerated or corrected so
    historical tool counts cannot remain in current-state prose.

### Certification model

Every one of the 65 baseline tools receives a catalog entry and one of these
verification outcomes:

- `offline_passed`: schema, error envelope, and local or fake bridge behavior
  passed, but the tool does not require Live;
- `live_passed`: the operation and its readback passed in the disposable Set;
- `manual_passed`: an intentionally disruptive operation passed with an owner
  confirmation, such as quitting Live;
- `host_unavailable`: the installed Live build does not expose the operation;
  the tool returned the documented structured fallback;
- `environment_unavailable`: an explicitly development-only existing tool,
  such as `build_extension`, is missing its documented developer runtime;
- `failed`: the tool is not release-ready, with the failing stage and evidence.

A release report contains all 65 rows. Missing rows fail the release. A tool may
remain public with `host_unavailable` only if its contract is explicitly a
capability probe/fallback; it may not claim successful mutation.
`environment_unavailable` is permitted only for catalog entries marked
development-only and does not affect normal Ableton control.

## Slice 2: 60 new core tools

The additions below intentionally use coarse, typed operations where many
fine-grained names would only inflate discovery. Existing general setters are
expanded when that produces a clearer contract than another alias.

### Session and transport — 10

- `get_transport_state`
- `set_metronome`
- `set_recording_state`
- `set_punch`
- `continue_playback`
- `tap_tempo`
- `undo`
- `redo`
- `stop_all_clips`
- `re_enable_automation`

`set_recording_state` uses explicit optional fields for Arrangement record,
Session record, and overdub, returning the observed state for every requested
field. `set_punch` similarly groups punch-in, punch-out, and count-in because
they form one transport configuration rather than separate capabilities.

### Tracks, mixer, and routing — 11

- `delete_track`
- `duplicate_track`
- `create_return_track`
- `delete_return_track`
- `get_mixer_state`
- `set_track_mixer`
- `set_main_mixer`
- `set_track_send`
- `set_track_monitoring`
- `set_track_routing`
- `get_playing_clips`

Track selectors explicitly distinguish normal, return, and main tracks. Mixer
setters group volume, pan, mute, solo, arm, and crossfade assignment when legal
for the selected type. Routing setters accept only values returned by routing
reads; free-form routing strings are rejected.

### Scenes — 5

- `create_scene`
- `delete_scene`
- `duplicate_scene`
- `set_scene_properties`
- `capture_and_insert_scene`

Scene properties include name, color, tempo, time signature, and supported
follow settings. Unsupported properties fail before any partial mutation.

### Session clips and MIDI editing — 10

- `duplicate_session_clip`
- `move_session_clip`
- `stop_clip`
- `stop_track_clips`
- `replace_clip_notes`
- `remove_clip_notes`
- `transform_clip_notes`
- `quantize_clip_notes`
- `set_clip_loop_region`
- `set_clip_launch`

`transform_clip_notes` covers transpose, velocity scaling/offset, time shift,
duration scaling, and bounded humanization in one deterministic operation. A
seed is mandatory when humanization is requested. Native quantization remains a
separate tool because its grid and amount semantics are Live-specific. Note
mutations return counts and a compact before/after summary.

### Arrangement and time editing — 8

- `get_arrangement_clips`
- `get_arrangement_clip_info`
- `duplicate_clip_to_arrangement`
- `move_arrangement_clip`
- `delete_arrangement_clip`
- `set_arrangement_clip_properties`
- `insert_arrangement_time`
- `delete_arrangement_time`

Arrangement selectors are refreshed after every edit. Time-edit operations are
marked destructive, require positive bounded beat ranges, run inside one undo
step, and are excluded from default acceptance profiles.

### Devices, racks, and samples — 9

- `delete_device`
- `duplicate_device`
- `set_device_enabled`
- `get_rack_chains`
- `create_rack_chain`
- `delete_rack_chain`
- `duplicate_rack_chain`
- `get_drum_pad`
- `replace_simpler_sample`

Rack tools operate only on SDK objects positively identified as racks. Drum-pad
and Simpler tools return `WRONG_TYPE` for other devices. Sample replacement
accepts a local path validated by the Extension SDK and does not introduce an
audio import service or file watcher.

### Automation — 5

- `get_clip_automation`
- `clear_clip_automation`
- `list_automated_parameters`
- `create_arrangement_automation`
- `clear_arrangement_automation`

Automation targets use the same typed mixer/device parameter selector as
parameter reads and writes. Points are sorted, bounded to the target envelope,
and read back. Arrangement automation is implemented only where a real
Arrangement clip exposes a writable envelope; absence returns
`CAPABILITY_UNAVAILABLE` and never falls back to a hidden Max for Live bridge.

### Browser — 2

- `load_browser_item`
- `preview_browser_item`

`load_browser_item` extends the corrected bounded search contract to supported
devices, presets, and samples and requires an explicit target. It never guesses
the first search hit when results are ambiguous. `preview_browser_item` uses an
`action` enum (`start` or `stop`) so preview lifecycle is one capability.

## Slice 3: turnkey agent onboarding

### FastMCP instructions

The server receives global instructions that tell an agent:

1. call `get_bridge_status` first;
2. inspect the current session before selecting indexes;
3. refresh selectors after structural changes;
4. use reads before mutations and verify observed results;
5. treat connection loss after a mutation as ambiguous and never blindly retry;
6. use `run_batch` only when grouped undo is desired;
7. reserve destructive tools for a disposable or explicitly confirmed Set;
8. use diagnostics and installation resources when either bridge is absent.

### MCP resources

- `ableton://server/capabilities` — generated catalog with route, risk,
  prerequisites, and verification status.
- `ableton://server/installation` — canonical Windows, WSL, Remote Script, and
  Extension setup instructions.
- `ableton://server/safety` — mutation, undo, selector, timeout, and recovery
  rules.
- `ableton://server/troubleshooting` — structured decision tree for TCP, WS,
  packaging, version, and Live host failures.
- `ableton://live/session-summary` — fresh composed read of the active Set,
  available only when Live is connected.

### MCP prompts

- `diagnose_installation` — walk from Python/package state through Remote Script,
  TCP, Extension, WS, versions, logs, and a read-only Live probe.
- `inspect_live_set` — gather a compact session, routing, device, and playback
  overview without mutation.
- `safe_session_edit` — plan, execute, read back, and summarize reversible
  Session changes.
- `debug_midi_clip` — inspect clip type, notes, loop bounds, devices, routing,
  and common silent-output causes.
- `build_arrangement` — construct Arrangement edits with explicit time ranges,
  risk confirmation, and post-write verification.

These prompts guide agents but never bypass tool validation or safety guards.

### Installation and diagnostics

`scripts/setup_windows.ps1` becomes the canonical fresh-clone entry point. It
creates the Windows virtual environment, installs the package and its declared
dependencies, installs the Remote Script, installs a versioned prebuilt
Extension payload shipped with the repository/release, and prints the exact MCP
executable/configuration. Each stage is idempotent and reports its destination.
Node.js is not required to run or install the MCP. It is required only for
developers changing Extension TypeScript; `build_extension` reports that
optional prerequisite explicitly instead of failing as an opaque shell error.

The CLI gains a unified `setup`/`install` path and an expanded `doctor` that
checks:

- supported Python and package versions;
- dependency resolution and executable identity;
- Remote Script source, destination, hashes, runtime identity, and port 9888;
- Extension payload, manifest/version, installed files, and port 9889;
- Live version, Control Surface presence, and actual TCP/WS round trips;
- registered catalog size and MCP instructions/resources/prompts;
- concise repair actions for every failed stage.

Diagnostics are read-only by default. An explicit `--fix` may reinstall local
artifacts but never starts, saves, closes, or modifies an Ableton Set.

## Error and safety model

All public failures use stable codes and structured details. The existing
taxonomy remains, with these additions:

- `CAPABILITY_UNAVAILABLE`: the installed Live/SDK does not expose a documented
  optional host capability;
- `AMBIGUOUS_MATCH`: a selector or Browser query has multiple legal targets;
- `VERIFICATION_FAILED`: Live accepted a write but readback did not reach the
  requested state;
- `ACCEPTANCE_GUARD_FAILED`: a live test refused to run because the Set or target
  was not disposable and empty as required.

Mutations validate the complete request before the first write. Multi-step
operations return the observed successful prefix and `rolled_back: false` on
failure unless they can prove no mutation occurred. Automatic reconnect/retry
remains read-only. Destructive operations are cataloged and omitted from default
agent workflows and acceptance profiles.

## Verification strategy

### Automated gates

Every production change follows red-green-refactor. The release gate runs:

- focused contract and regression tests for each change;
- the full Python test suite and coverage thresholds;
- Ruff and strict mypy over project-owned Python;
- vendored-contract byte comparison;
- tool catalog, registered tools, resources, prompts, and generated-doc drift
  checks;
- Extension TypeScript typecheck, production build, and audit;
- wheel and sdist builds plus installation into a fresh temporary environment;
- CLI `doctor` fixture tests for healthy, missing, stale, mismatched, and partial
  TCP/WS installations.

Tests for mutations must prove the regression test fails against the pre-fix
implementation and passes after the change. Fakes model proxy recreation so
identity bugs cannot be hidden by stable Python test objects.

### Guarded real-Live acceptance

Acceptance runs only against a Set whose name exactly matches the confirmation
argument. Test artifacts use a reserved `__MCP_ACCEPTANCE__` prefix. Profiles
separate `read`, `session`, `mixer`, `arrangement`, `device`, `browser`, and
`destructive` capabilities. Default profiles snapshot relevant state, execute,
read back, and clean up; cleanup is independently verified and leftovers are
reported with exact selectors.

`save_set`, `quit_ableton`, Arrangement time deletion, and other disruptive
operations require dedicated flags. `quit_ableton` can be certified only in the
manual profile because its success necessarily terminates the host connection.

The output is a JSON certification report keyed by all catalog tools. A final
release claim requires zero `failed` or unclassified tools. `host_unavailable`
is acceptable only for explicitly capability-gated behavior and must include the
observed Live/SDK version and fallback result.
`environment_unavailable` is acceptable only for development-only tools and
must name the optional developer prerequisite.

## Documentation and release readiness

`docs/TOOL_REFERENCE.md` and the capability resource are generated from the same
catalog. The README leads with a fresh-clone quickstart, Ableton configuration,
the two bridge indicators, a first read-only agent call, and `doctor`. Architecture
and known-quirks documents describe current behavior rather than historical
counts.

The program is ready for a stable release only when:

1. clean install and all automated gates pass;
2. all 65 original tools are classified with no failures;
3. all 60 additions have contract coverage and required Live acceptance;
4. catalog, registered surface, generated docs, instructions, resources, and
   prompts agree exactly;
5. the guarded disposable-Set acceptance report has no unexpected leftovers;
6. an agent following only the README and exposed MCP guidance can diagnose both
   bridges and complete a read-only session inspection from a fresh clone.

## Explicit non-goals

- Max for Live devices, rack analyzers, hidden-parameter access, or M4L UDP
  bridges;
- MIDI CC, `mido`, `python-rtmidi`, controller maps, or vendor plug-in maps;
- ElevenLabs, speech generation, API keys, or a second MCP server;
- OSC, realtime UDP control, LAN/mobile access, or unauthenticated remote use;
- web dashboards and custom Live webviews;
- audio capture, cross-track spectrum streams, or DSP analysis inside Live;
- writable warp markers until the installed official SDK exposes a setter;
- generic LOM reflection, arbitrary Python/JavaScript execution, or silent
  fallback to undocumented behavior;
- tool-count parity with AbletonBridge or aliases added solely to increase the
  advertised number.
