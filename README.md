# ableton-mcp-server

[**:globe_with_meridians: Live Landing Page & Interactive 65-Tool Catalog**](https://ntworm.github.io/ableton-mcp-server/) · [**Architecture Diagram**](docs/ARCHITECTURE.md) · [**Tool Index**](docs/TOOL_REFERENCE.md)

An MCP server that lets an AI agent drive a running Ableton Live Set.

Version 0.5.1 exposes 65 tools. A FastMCP server in Python talks to a MIDI
Remote Script on TCP `127.0.0.1:9888` and to an Extension Host bridge over
WebSockets on `127.0.0.1:9889`. Live runs on Windows; the WSL client runs
the Windows binary so the loopback stays in the right network namespace.
Verify a clean install with `scripts/verify_clean_install.ps1`.

## Why this exists

This is a working tool, not a clean-room reference implementation. It exists
because one person writes, performs and debugs Live Sets with an agent in the
loop, and the off-the-shelf pieces didn't cover the workflow — the live
session lifecycle (save, quit, fade between tracks), offline mix analysis,
and a WSL topology that actually works against a Windows Live install.

The contract layout borrows from a few predecessors. The code is written
from scratch. See [Inspiration & prior art](docs/INSPIRATION.md) for the
full attribution and the projects that shaped this codebase.

## Projects I read while building this

- `pnomolos/live-wire` — the TCP JSONL bridge shape and the per-tick
  write-then-verify loop.
- `hidingwill/AbletonBridge` — group `run_batch` semantics with
  `rolled_back: false` on partial failure.
- `ideoforms/AbletonOSC` — the Open Sound Control command conventions used
  by the Extension Host bridge.
- `ideoforms/pylive` — Python LOM reference for the introspection surface.
- `Simon-Kansara/ableton-live-mcp-server` — anchors the decision to keep
  transport, clips, tracks and devices on the Python Remote Script path
  and route warping and device loading through the WebSocket Extension.

Full notes in [docs/INSPIRATION.md](docs/INSPIRATION.md).

## Use it

License is MIT. Copy, fork, ship — see [LICENSE](LICENSE).

Windows install (one-shot):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
```

Then restart Live, select `AbletonMCPServer` under `Preferences -> Link,
Tempo & MIDI -> Control Surfaces`, and use the CLI:

```powershell
.\.venv-win\Scripts\ableton-mcp.exe doctor --json
```

If you're on WSL, point the MCP client at the Windows binary:

```text
/mnt/c/Users/Usuario/repos/ableton-mcp-server/.venv-win/Scripts/ableton-mcp-server.exe
```

Native Linux Python inside WSL NAT won't reach the Live loopback. Don't
expose or forward port `9889` to a LAN — the JSONL protocol has no auth.
The cross-bridge error taxonomy is documented in `ableton_mcp_server.errors`
and includes `CAPABILITY_UNAVAILABLE`, `AMBIGUOUS_MATCH`,
`VERIFICATION_FAILED`, and `ACCEPTANCE_GUARD_FAILED`.

## What it does

65 MCP tools grouped by area:

- Transport and session: `get_session_info`, `set_tempo`, `start_playback`,
  `stop_playback`, `get_loop_settings`, `set_loop`, `set_loop_start`,
  `set_loop_length`, `set_current_song_time`, `get_song_length`,
  `get_session_overview`, `get_scenes`, `get_scene_state`, `fire_scene`,
  `fire_clip`.
- Tracks and devices: `get_track_list`, `live_find_track`, `get_track_state`,
  `get_device_list`, `get_parameter_value`, `get_clip_summary`,
  `set_parameter_value`, `create_clip`, `get_clip_notes`, `add_notes_to_clip`,
  `delete_clip`, `clear_clip_notes`, `set_clip_properties`, `get_clip_info`,
  `set_track_property`, `create_audio_track`, `get_routing`, `diff_snapshots_tool`,
  `take_snapshot`, `get_selected_context`, `search_browser`,
  `load_device_to_track` accepts `device_name` (primary) or `device_uri`
  (deprecated alias). `get_warp_state` is read-only; `set_warp_state` rejects
  marker writes at the model layer.
- Lifecycle: `lifecycle_status`, `save_set`, `quit_ableton`, `live_fade`,
  `create_clip_automation`.
- Offline mix analysis: `analyze_audio`, `find_frequency_masking`,
  `analyze_mix`, `extract_single_cycle`. Input is a file path; no Live
  required; LUFS-I, true peak, single-cycle extraction.
- Test/inspection: `run_batch`, `get_locators`, `create_cue_point`,
  `delete_cue_point`, `bulk_create_cue_points`, `get_control_surfaces`,
  `get_browser_categories`, `get_project_metadata`, `get_ableton_logs`,
  `get_bridge_status`.

WSL-safe executable path is the canonical deployment, not an afterthought.
A guarded acceptance runner lives at `ableton-mcp acceptance --profile
baseline` and is gated to a disposable Set called `TESTE_CODEX`.

## Stability

The 65-tool catalog is the immutable surface for the v0.5.x line. Per-tool
status reports drive release decisions; see
[docs/CERTIFICATION.md](docs/CERTIFICATION.md) for the policy.

## Changelog

[CHANGELOG.md](CHANGELOG.md) tracks the public surface.

## License

MIT — Copyright (c) 2026 ntworm. See [LICENSE](LICENSE).
