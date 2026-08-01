# ableton-mcp-server

[**:globe_with_meridians: Live Landing Page & Interactive 65-Tool Catalog**](https://ntworm.github.io/ableton-mcp-server/) · [**Architecture Diagram**](docs/ARCHITECTURE.md) · [**Tool Index**](docs/TOOL_REFERENCE.md)

An open **Model Context Protocol (MCP)** server that enables AI agents (Claude, Antigravity, Gemini, Codex) and audio developers to query, analyze, drive, and automate a running Ableton Live 12 Set.

Version 0.5.1 exposes 65 tools over TCP and WebSockets (with primary device resolution via device_name, track_index, and clip_index). A FastMCP server in Python communicates with a MIDI Remote Script on TCP `127.0.0.1:9888` and an Extension Host bridge over WebSockets on `127.0.0.1:9889`.

---

## ⚡ What is Model Context Protocol (MCP) & How Agents Use It

**Model Context Protocol (MCP)** is an open standard developed by Anthropic for secure, local communication between Large Language Models (LLMs) and desktop applications.

> **Local IPC / stdio (Not a Cloud Service):**  
> `ableton-mcp-server` runs locally on your host OS over standard input/output (`stdio`) or IPC loopback. The AI agent spawns the `ableton-mcp-server.exe` process directly. There are no external cloud endpoints or API keys required, guaranteeing zero network latency and maximum privacy.

### How AI Agents Interact with Ableton Live:
1. **Tool Discovery (`tools/list`)**: When an MCP client (Claude Desktop, Antigravity, Cursor) launches the server, it automatically discovers all 65 tool schemas.
2. **Tool Execution (`tools/call`)**: When the LLM decides to manipulate Ableton Live, it issues JSON-RPC messages (e.g. `set_tempo(tempo=128.0)` or `create_clip(...)`).
3. **Write-Then-Verify Loop**: The server writes to Live's local socket and verifies object model state before returning a result.
4. **Self-Correcting Error Taxonomy**: If an error occurs, the server returns structured codes (`CAPABILITY_UNAVAILABLE`, `AMBIGUOUS_MATCH`, `VERIFICATION_FAILED`), enabling the agent to reason and adapt.

### Recommended System Prompt for AI Agents:
```text
You have direct access to an active Ableton Live Set via ableton-mcp-server (65 tools).
1. Always start by inspecting the project state using `get_session_overview()` or `get_track_list()`.
2. To modify track properties, resolve the target track index using `live_find_track(name_pattern)` first.
3. For parameter adjustments, query parameters via `get_device_list()` and `get_parameter_value()`, then apply changes using `set_parameter_value()`.
4. When executing multiple operations, bundle them using `run_batch(operations)` to ensure atomic execution.
5. Respect the error taxonomy: if you receive `AMBIGUOUS_MATCH` or `VERIFICATION_FAILED`, inspect track context and retry.
```

---

## 🛠️ Use It

License is **MIT**. Copy, fork, ship — see [LICENSE](LICENSE).

### Windows Install (one-shot):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
```

Then restart Live, select `AbletonMCPServer` under `Preferences -> Link, Tempo & MIDI -> Control Surfaces`, and verify the installation:

```powershell
.\.venv-win\Scripts\ableton-mcp.exe doctor --json
```

### Verify Install

Run the Remote Script status check after installation:

```powershell
.\.venv-win\Scripts\ableton-mcp.exe install-status --json
```

A current installation reports `"status": "current"`. The setup script also prints the
installed Remote Script's SHA-256 `algorithm`, `hash`, and `path` for auditing.

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

## 📦 What It Does (65 MCP Tools)

The 65 MCP tools are grouped into 5 operational domains:

- **Transport & Session**: `get_session_info`, `set_tempo`, `start_playback`, `stop_playback`, `get_loop_settings`, `set_loop`, `set_loop_start`, `set_loop_length`, `set_current_song_time`, `get_song_length`, `get_session_overview`, `get_scenes`, `get_scene_state`, `fire_scene`, `fire_clip`.
- **Tracks & Devices**: `get_track_list`, `live_find_track`, `get_track_state`, `get_device_list`, `get_parameter_value`, `get_clip_summary`, `set_parameter_value`, `create_clip`, `get_clip_notes`, `add_notes_to_clip`, `delete_clip`, `clear_clip_notes`, `set_clip_properties`, `get_clip_info`, `set_track_property`, `create_audio_track`, `get_routing`, `diff_snapshots_tool`, `take_snapshot`, `get_selected_context`, `search_browser`, `load_device_to_track`, `get_warp_state`.
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

## 📜 License

**MIT** — Copyright (c) 2026 Gabriel Worm (ntworm). See [LICENSE](LICENSE).
