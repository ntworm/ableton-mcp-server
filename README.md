# ableton-mcp-server

[**:globe_with_meridians: Live Landing Page & Interactive 97-Tool Catalog**](https://ntworm.github.io/ableton-mcp-server/) <!-- TOOL_COUNT: active_total --> · [**Architecture Diagram**](docs/ARCHITECTURE.md) · [**Agent Playbook**](docs/AGENT_PLAYBOOK.md) · [**Tool Index**](docs/TOOL_REFERENCE.md)

An open **Model Context Protocol (MCP)** server that enables AI agents (Antigravity, Gemini, Codex) and audio developers to query, analyze, drive, and automate a running Ableton Live 12 Set.

The current tool surface is 97 tools over TCP, WebSockets, composed routes, and local execution <!-- TOOL_COUNT: active_total --> (with primary device resolution via device_name, track_index, and clip_index); the current v0.8.1 release ships 97 tools. Historical milestones exposed 65 certified tools in v0.5.2 <!-- HISTORICAL_TOOL_COUNT: 65; baseline=v0.5.2 -->, 88 tools in the v0.5.6 source milestone <!-- HISTORICAL_TOOL_COUNT: 88; baseline=v0.5.6 -->, 96 tools in the v0.6.0 release <!-- HISTORICAL_TOOL_COUNT: 96; baseline=v0.6.0 -->, and v0.7.0 with journey planning and realtime UDP. v0.8.0 modularizes the Remote Script into 17 domain modules, adds chain-order-safe device insertion (`load_device_to_track`), and introduces preflight clean-set verification. v0.8.1 removes the curated groove corpus from every distributed package. Groove retrieval, evidence, generation, and comparison stay offline; only the guarded apply path reaches Live. A FastMCP server in Python communicates with a MIDI Remote Script on TCP `127.0.0.1:9888` and an Extension Host bridge over WebSockets on `127.0.0.1:9889`.

Groove Intelligence is offline by default. Its deterministic generator needs no
provider installation; an optional neural provider is isolated behind a fixed
allowlist, bounded local IPC, resource limits, and signed laboratory gates.
Provider failures always return the equivalent deterministic artifact, and no
provider receives corpus paths, raw MIDI, notes, SQL, credentials, or network
access. See [the provider laboratory contract](docs/groove_intelligence/provider-lab.md).
The curated corpus no longer ships inside the wheel or any other distributed
package. An optional private seed is read from
`%LOCALAPPDATA%\AbletonMCPServer\groove-seed` (on macOS from
`~/Library/Application Support/AbletonMCPServer/groove-seed`), or from the
path given in `ABLETON_GROOVE_SEED_BUNDLE`, while derived artifacts stay in
the same per-user folder.
Groove retrieval, evidence, comparison, and deterministic generation are
portable and do not depend on the private source library. A generation request can use one
primary groove plus up to seven references; incompatible PPQ, meter, or rights
are rejected explicitly. Within the Groove Intelligence surface, the only Live
mutation is guarded `groove_apply`, which must be previewed against an explicit
target and empty slot before one commit.

## Evidence

Measured on 2026-11-11 with Live 12.4.25b1, on a disposable Set reopened from
disk before each run. Data and commands are in [`docs/reports/`](docs/reports/).

**Writes read back from Live.** `ableton-mcp acceptance` drove the 97 catalogued
tools: 70 `live_passed`, 17 `offline_passed`, none `failed`. Of the 70, 30 are
mutations the runner read back from the Set after the write (for example
`create_cue_point`, then `get_locators` for that name and time), 2 are
mutations certified by their own reply (`run_batch`, `create_clip_automation`),
3 are mutations that pass when the call returns without error, with no check of
the reply or the Set (`create_clip_automation_curve`, `add_notes_pattern`,
`set_arrangement_clip_properties`), and 35 are reads that returned a valid
answer. The `groove_apply` row among the 17 offline ones checks the preview
contract only (`acceptance/probes/groove_apply.py`), not a tool call. The other
10 rows: 5 track move and group operations that Live does not
expose, refused with `CAPABILITY_UNAVAILABLE`; 3 that need a plugin or a Rack in
the Set; `save_set` and `quit_ableton`, which need the owner. The per-tool list,
with how each mutation was certified, is in
[`2026-11-acceptance-readback.json`](docs/reports/2026-11-acceptance-readback.json);
the probe function that backs each row is named in
[`scripts/summarize_acceptance.py`](scripts/summarize_acceptance.py). The runner
records the same fixed evidence string for every row that passes through its
common recorder, so the report does not carry the values read back.
To rerun: `ableton-mcp acceptance --confirm-project-name <Set> --track-index <midi>
--clip-index <empty slot> --audio-track-index <audio> --audio-clip-index <clip>
--fire-clip --json > raw.json`, then `python scripts/summarize_acceptance.py raw.json
--live-version <version> --set-name <Set> --date <date> --out report.json`.

**Batch cost.** One scenario, the same end state in Live: 8 MIDI tracks created and
renamed, a 4-beat clip with 16 notes on each, 8 cue points, one scene launch.

| Variant | Tool calls | Argument chars | Result chars | Context chars | Tokens (estimate) |
|---|---|---|---|---|---|
| One call per operation | 42 | 9,433 | 7,360 | 2,708,741 | 677,185 |
| `run_batch` and `bulk_create_cue_points` | 4 | 10,626 | 8,205 | 275,207 | 68,801 |

Each tool call is one agent turn. The context figures assume a client that sends
the full tool list (here 64,094 characters) with every model turn, which is the
common setup; a client that caches or trims the list pays less, and the call
count holds either way. Context chars are `calls x 64,094 + argument chars +
result chars`; tokens are that divided by 4, an estimate, while the call count is
exact. After the Live run of the batched variant the Set held the 8 cue points
and the 16 notes on the last created track, written by the batch's last command;
the script now also fails a Live run whose batch completes fewer commands than
it sent. The batched variant sends slightly more per call and creates the
cue points in one undo step instead of 8. Details in
[`2026-11-batch-cost.md`](docs/reports/2026-11-batch-cost.md);
`python scripts/measure_batch_cost.py` reproduces the call counts without Live.

**No outbound network.** `tests/test_no_outbound_network.py` runs the real bridge
client against loopback TCP and WebSocket servers and calls `tools/list`, one TCP
read, one WebSocket read and the offline tools through the MCP layer, while an
audit hook and the asyncio connection path record every destination. It fails on
any address other than `127.0.0.1`, `::1` or `localhost`, and also if either
recorder misses its bridge. Static checks cover the Python packages, the bundled
Extension sources and the telemetry defaults: no OpenTelemetry SDK is installed
by default, and the server sets `OTEL_SDK_DISABLED`, `FASTMCP_TELEMETRY_DISABLED`
and `MCP_TELEMETRY_DISABLED` to `true` unless the user already set them. Not
covered by the runtime test: `build_extension`, which runs `npm install` and
reaches the npm registry; the five `groove_*` tools, which need a seed the
repository does not ship (their package is in the static check); the child
process of the optional neural provider; and
`AbletonMCPServer_Extension/groove-brain-gate0/`, a laboratory that is not
bundled and calls `fetch`.

---

## ⚡ What is Model Context Protocol (MCP) & How Agents Use It

**Model Context Protocol (MCP)** is an open standard for secure, local communication between Large Language Models (LLMs) and desktop applications.

> **Local IPC / stdio (Not a Cloud Service):**  
> `ableton-mcp-server` runs locally on your host OS over standard input/output (`stdio`) or IPC loopback. The AI agent spawns the `ableton-mcp-server.exe` process directly. There are no external cloud endpoints or API keys required, guaranteeing zero network latency and maximum privacy.

### How AI Agents Interact with Ableton Live:
1. **Tool Discovery (`tools/list`)**: When an MCP client (Antigravity, Cursor, Windsurf) launches the server, it automatically discovers all 97 tool schemas <!-- TOOL_COUNT: active_total -->.
2. **Tool Execution (`tools/call`)**: When the LLM decides to manipulate Ableton Live, it issues JSON-RPC messages (e.g. `set_tempo(tempo=128.0)` or `create_clip(...)`).
3. **Write-Then-Verify Loop**: The server writes to Live's local socket and verifies object model state before returning a result.
4. **Self-Correcting Error Taxonomy**: If an error occurs, the server returns structured codes (`CAPABILITY_UNAVAILABLE`, `AMBIGUOUS_MATCH`, `VERIFICATION_FAILED`), enabling the agent to reason and adapt.

### Recommended System Prompt for AI Agents:
```text
You have direct access to an active Ableton Live Set via ableton-mcp-server (97 tools) <!-- TOOL_COUNT: active_total -->.
1. Always start by inspecting the project state using `get_session_overview()` or `get_track_list()`.
2. To modify track properties, resolve the target track index using `live_find_track(name_pattern)` first.
3. For parameter adjustments, query parameters via `get_device_list()` and `get_parameter_value()`, then apply changes using `set_parameter_value()`.
4. When executing multiple operations, bundle them using `run_batch(commands)`; a successful prefix persists if a later command fails. Live closes an undo step at the end of every UI tick, so Arrangement edits and other commands that finish in one tick share a Ctrl+Z, while each command read back on a later tick (tempo, loop, colours, cue points) takes its own.
5. Respect the error taxonomy: if you receive `AMBIGUOUS_MATCH` or `VERIFICATION_FAILED`, inspect track context and retry.
```

---

## 🛠️ Use It

License is **MIT**. Copy, fork, ship — see [LICENSE](LICENSE).

### Windows Install (one-shot):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
```

Install the release wheel from the project's GitHub Releases page (the
downloaded `.whl` file). There is no PyPI install for this server: the public
`ableton-mcp-server` name on PyPI belongs to an unrelated project.

Preview the exact Remote Script copy plan without creating `.venv-win`, installing
dependencies, or writing to Ableton's User Library:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1 -DryRun
```

If the environment already exists, the equivalent CLI preview is:

```powershell
.\.venv-win\Scripts\ableton-mcp.exe install-script --dry-run
```

Then restart Live, select `AbletonMCPServer` under `Preferences -> Link, Tempo & MIDI -> Control Surfaces`, and verify the installation:

```powershell
.\.venv-win\Scripts\ableton-mcp.exe doctor --json
```

### Verify Install

You can verify your installation integrity using either the built-in CLI tool or direct SHA-256 hash comparison:

#### 1. CLI Remote Script Status

Run `install-status` to compare installed Remote Script files against the bundled source:

```powershell
.\.venv-win\Scripts\ableton-mcp.exe install-status --json
```

A healthy, up-to-date installation returns `"status": "current"`:

```json
{
  "status": "current",
  "source": "C:\\path\\to\\ableton-mcp-server\\AbletonMCPServer_RemoteScript",
  "target": "C:\\Users\\<user>\\Documents\\Ableton\\User Library\\Remote Scripts\\AbletonMCPServer_RemoteScript",
  "missing_files": [],
  "mismatched_files": []
}
```

#### 2. SHA-256 Checksum Audit

During setup, `setup_windows.ps1` automatically verifies and prints the Remote Script's SHA-256 hash:

```text
Remote Script verification:
  algorithm: SHA256
  hash: 3E3504D661FA2DCE7582F50C56F0C71EB79892F7A4520BD3F1B8571EEDBB14DE
  path: C:\Users\<user>\Documents\Ableton\User Library\Remote Scripts\AbletonMCPServer_RemoteScript\__init__.py
```

To manually compute and verify the SHA-256 checksum of the installed `__init__.py` at any time:

- **Windows (PowerShell):**
  ```powershell
  Get-FileHash "$HOME\Documents\Ableton\User Library\Remote Scripts\AbletonMCPServer_RemoteScript\__init__.py" -Algorithm SHA256
  ```
- **macOS / Linux:**
  ```bash
  shasum -a 256 "$HOME/Music/Ableton/User Library/Remote Scripts/AbletonMCPServer_RemoteScript/__init__.py"
  ```

The Remote Script spans several modules, so `ableton-mcp install-status --json` is the check that compares every installed file.

### Agent Configuration (`mcp.json`):

```json
{
  "mcpServers": {
    "ableton": {
      "command": "C:\\path\\to\\ableton-mcp-server\\.venv-win\\Scripts\\ableton-mcp-server.exe",
      "args": []
    }
  }
}
```

If you operate from **WSL2**, point the MCP client at the Windows binary so loopback stays in the host network namespace:

```text
/path/to/ableton-mcp-server/.venv-win/Scripts/ableton-mcp-server.exe
```

### MCP Bundle (`.mcpb`)

`scripts/build_mcpb.py` packs the server as an [MCP Bundle](https://github.com/modelcontextprotocol/mcpb) for Windows. The bundle carries the wheel and a locked launcher project; on first launch the host's `uv` installs Python and the dependencies from PyPI. It contains the server only, so the Remote Script and the Extension still install as described above.

```powershell
.\.venv-win\Scripts\python.exe scripts\build_mcpb.py build --out-dir dist\mcpb
.\.venv-win\Scripts\python.exe scripts\build_mcpb.py smoke dist\mcpb\ableton-mcp-server-<version>.mcpb
```

`build` needs `uv`, Node.js (`npx` runs the pinned `@anthropic-ai/mcpb` CLI), and network access. `smoke` extracts the bundle, launches it over stdio, and checks `initialize`, `tools/list` against the catalog, and one offline tool, without Ableton Live.

### Optional private groove seed

The curated groove corpus is **not** part of this wheel, the MCP bundle, or any
other distributed package. No groove corpus is downloaded at install time or later.
The server starts normally and exposes all 97 tools without a corpus; only the
corpus-backed operations need one.

When you have a licensed local copy, point the server at it with either:

- `%LOCALAPPDATA%\AbletonMCPServer\groove-seed` — the default location on
  Windows.
- `~/Library/Application Support/AbletonMCPServer/groove-seed` — the default
  location on macOS.
- `ABLETON_GROOVE_SEED_BUNDLE` — an explicit path that overrides the default
  location.

Without a configured seed the corpus operations (`groove_search`,
`groove_evidence`, `groove_compare`, and `groove_generate` from a corpus
source) answer with an explicit error instead of fetching anything. The two
messages are literal:

```text
No groove corpus configured: no seed bundle at <bundle>. Set ABLETON_GROOVE_SEED_BUNDLE, or place a licensed seed there.
Invalid groove seed at <bundle>: <cause>. Set ABLETON_GROOVE_SEED_BUNDLE to a valid seed bundle.
```

---

## 📦 What It Does (97 MCP Tools) <!-- TOOL_COUNT: active_total -->

> v0.6.0 extends the certified 65-tool v0.5.2 baseline <!-- HISTORICAL_TOOL_COUNT: 65; baseline=v0.5.2 -->. v0.5.3 introduced colour writes, clip-target diagnostics, and five hierarchy tools that validate then return `CAPABILITY_UNAVAILABLE`; v0.6.0 adds offline music generation, Groove retrieval, and guarded apply. See [the offline music reference](docs/TOOL_REFERENCE.md#offline-music-generation).

The 97 MCP tools are grouped into operational domains <!-- TOOL_COUNT: active_total -->:

- **Transport & Session**: `get_session_info`, `set_tempo`, `start_playback`, `stop_playback`, `get_loop_settings`, `set_loop`, `set_loop_start`, `set_loop_length`, `set_current_song_time`, `get_song_length`, `get_session_overview`, `get_scenes`, `get_scene_state`, `fire_scene`, `fire_clip`.
- **Tracks & Devices**: `get_track_list`, `live_find_track`, `live_find_device`, `live_find_clip`, `get_track_state`, `get_device_list`, `list_device_params`, `get_parameter_value`, `get_plugin_presets`, `set_plugin_preset`, `get_clip_summary`, `set_parameter_value`, `create_clip`, `get_clip_notes`, `add_notes_to_clip`, `delete_clip`, `clear_clip_notes`, `set_clip_properties`, `get_clip_info`, `set_track_property`, `set_track_color`, `set_clip_color`, `diagnose_clip_targets`, `create_midi_track`, `create_audio_track`, `rename_track`, `move_track`, `reorder_tracks`, `move_track_to_group`, `ungroup_track`, `merge_groups`, `get_routing`, `diff_snapshots_tool`, `take_snapshot`, `get_selected_context`, `get_composition_structure`, `diagnose_midi_clip`, `search_browser`, `load_device_to_track`, `get_warp_state`, `set_warp_state`.
- **Lifecycle & Automation**: `lifecycle_status`, `save_set`, `quit_ableton`, `live_fade`, `create_clip_automation`.
- **Offline Mix Analysis**: `analyze_audio`, `find_frequency_masking`, `analyze_mix`, `extract_single_cycle` (LUFS-I, True Peak, dynamic range, spectral collision).
- **Groove Intelligence (offline by default)**: `groove_search`, `groove_evidence`, `groove_generate`, `groove_compare`, `groove_apply` (genre/subgenre/style/section taxonomy, V2 projections, deterministic multi-parent generation, late kit mapping, and one guarded Live commit).
- **Inspection & Batch Execution**: `run_batch`, `get_locators`, `create_cue_point`, `delete_cue_point`, `bulk_create_cue_points`, `get_control_surfaces`, `get_browser_categories`, `get_project_metadata`, `get_ableton_logs`, `get_bridge_status`.

### Offline Music Generation

| Inventory | Tools | Live boundary |
|---|---|---|
| Deterministic music generation | `music_generate_drum_groove`, `music_generate_bass`, `music_plan_production` | Offline by default; only an explicit `apply` request reaches Live. |

---

## 💡 Inspiration & Prior Art

This project builds on design insights from seminal open-source projects:

- [`pnomolos/live-wire`](https://github.com/pnomolos/live-wire) — TCP JSONL Remote Script layout, typed error envelopes, per-tick verification loop.
- [`hidingwill/AbletonBridge`](https://github.com/hidingwill/AbletonBridge) — `run_batch` transaction semantics and attribute verification.
- [`ideoforms/AbletonOSC`](https://github.com/ideoforms/AbletonOSC) — OSC command naming and Extension Host bridge conventions.
- [`ideoforms/pylive`](https://github.com/ideoforms/pylive) — Python LOM introspection reference.
- [`Simon-Kansara/ableton-live-mcp-server`](https://github.com/Simon-Kansara/ableton-live-mcp-server) — Tool boundary design (Remote Script for transport/devices vs WebSocket Extension for warping/browser loading).

Full notes in [docs/INSPIRATION.md](docs/INSPIRATION.md).

---

## ⚠️ Known Bugs

Live's Object Model exposes a number of traps (path-id drift, undo semantics, WSL loopback, protocol drift, allowlist surprises) that an AI agent can hit without warning. Each one has a known workaround in the codebase; every trap is documented in [docs/KNOWN_BUGS.md](docs/KNOWN_BUGS.md). Read the executive summary at the top of that file before relying on track indexes, `run_batch`, or a TCP loopback to Live.

---

## 📜 License

**MIT** — Copyright (c) 2026 Gabriel Worm (ntworm). See [LICENSE](LICENSE).
