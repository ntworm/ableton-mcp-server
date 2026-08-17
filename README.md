# ableton-mcp-server

[**:globe_with_meridians: Live Landing Page & Interactive 88-Tool Catalog**](https://ntworm.github.io/ableton-mcp-server/) · [**Architecture Diagram**](docs/ARCHITECTURE.md) · [**Agent Playbook**](docs/AGENT_PLAYBOOK.md) · [**Tool Index**](docs/TOOL_REFERENCE.md)

An open **Model Context Protocol (MCP)** server that enables AI agents (Claude, Antigravity, Gemini, Codex) and audio developers to query, analyze, drive, and automate a running Ableton Live 12 Set.

Version 0.5.3 exposes 88 tools over TCP and WebSockets (with primary device resolution via device_name, track_index, and clip_index), up from the 65 certified in v0.5.2. A FastMCP server in Python communicates with a MIDI Remote Script on TCP `127.0.0.1:9888` and an Extension Host bridge over WebSockets on `127.0.0.1:9889`.

---

## ⚡ What is Model Context Protocol (MCP) & How Agents Use It

**Model Context Protocol (MCP)** is an open standard developed by Anthropic for secure, local communication between Large Language Models (LLMs) and desktop applications.

> **Local IPC / stdio (Not a Cloud Service):**  
> `ableton-mcp-server` runs locally on your host OS over standard input/output (`stdio`) or IPC loopback. The AI agent spawns the `ableton-mcp-server.exe` process directly. There are no external cloud endpoints or API keys required, guaranteeing zero network latency and maximum privacy.

### How AI Agents Interact with Ableton Live:
1. **Tool Discovery (`tools/list`)**: When an MCP client (Claude Desktop, Antigravity, Cursor) launches the server, it automatically discovers all 88 tool schemas.
2. **Tool Execution (`tools/call`)**: When the LLM decides to manipulate Ableton Live, it issues JSON-RPC messages (e.g. `set_tempo(tempo=128.0)` or `create_clip(...)`).
3. **Write-Then-Verify Loop**: The server writes to Live's local socket and verifies object model state before returning a result.
4. **Self-Correcting Error Taxonomy**: If an error occurs, the server returns structured codes (`CAPABILITY_UNAVAILABLE`, `AMBIGUOUS_MATCH`, `VERIFICATION_FAILED`), enabling the agent to reason and adapt.

### Recommended System Prompt for AI Agents:
```text
You have direct access to an active Ableton Live Set via ableton-mcp-server (88 tools).
1. Always start by inspecting the project state using `get_session_overview()` or `get_track_list()`.
2. To modify track properties, resolve the target track index using `live_find_track(name_pattern)` first.
3. For parameter adjustments, query parameters via `get_device_list()` and `get_parameter_value()`, then apply changes using `set_parameter_value()`.
4. When executing multiple operations, bundle them using `run_batch(commands)` for one grouped undo step; a successful prefix persists if a later command fails.
5. Respect the error taxonomy: if you receive `AMBIGUOUS_MATCH` or `VERIFICATION_FAILED`, inspect track context and retry.
```

---

## 🛠️ Use It

License is **MIT**. Copy, fork, ship — see [LICENSE](LICENSE).

### Windows Install (one-shot):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
```

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

### Agent Configuration (`claude_desktop_config.json` / `mcp.json`):

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

---

## 📦 What It Does (88 MCP Tools)

> The current line adds 10 tools to the certified 65-tool v0.5.2 baseline. v0.5.3 introduced colour writes, clip-target diagnostics, and five hierarchy tools that validate then return `CAPABILITY_UNAVAILABLE`; the latest update adds `live_find_device` and `live_find_clip` for fresh session-local locators. See [docs/KNOWN_BUGS.md](docs/KNOWN_BUGS.md) §Category O.

The 88 MCP tools are grouped into 5 operational domains:

- **Transport & Session**: `get_session_info`, `set_tempo`, `start_playback`, `stop_playback`, `get_loop_settings`, `set_loop`, `set_loop_start`, `set_loop_length`, `set_current_song_time`, `get_song_length`, `get_session_overview`, `get_scenes`, `get_scene_state`, `fire_scene`, `fire_clip`.
- **Tracks & Devices**: `get_track_list`, `live_find_track`, `live_find_device`, `live_find_clip`, `get_track_state`, `get_device_list`, `list_device_params`, `get_parameter_value`, `get_plugin_presets`, `set_plugin_preset`, `get_clip_summary`, `set_parameter_value`, `create_clip`, `get_clip_notes`, `add_notes_to_clip`, `delete_clip`, `clear_clip_notes`, `set_clip_properties`, `get_clip_info`, `set_track_property`, `set_track_color`, `set_clip_color`, `diagnose_clip_targets`, `create_midi_track`, `create_audio_track`, `rename_track`, `move_track`, `reorder_tracks`, `move_track_to_group`, `ungroup_track`, `merge_groups`, `get_routing`, `diff_snapshots_tool`, `take_snapshot`, `get_selected_context`, `get_composition_structure`, `diagnose_midi_clip`, `search_browser`, `load_device_to_track`, `get_warp_state`, `set_warp_state`.
- **Lifecycle & Automation**: `lifecycle_status`, `save_set`, `quit_ableton`, `live_fade`, `create_clip_automation`.
- **Offline Mix Analysis**: `analyze_audio`, `find_frequency_masking`, `analyze_mix`, `extract_single_cycle` (LUFS-I, True Peak, dynamic range, spectral collision).
- **Inspection & Batch Execution**: `run_batch`, `get_locators`, `create_cue_point`, `delete_cue_point`, `bulk_create_cue_points`, `get_control_surfaces`, `get_browser_categories`, `get_project_metadata`, `get_ableton_logs`, `get_bridge_status`.

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
