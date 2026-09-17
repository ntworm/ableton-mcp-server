# Release Notes

## v0.7.0

v0.7.0 publishes the expanded 97-tool Ableton MCP Server surface. It introduces
`plan_user_journey`, an updated retrieval seed v3 with per-collection SD3 and General MIDI
articulation maps, a high-speed UDP realtime control channel, and deterministic
polyrhythm transformations.

### Highlights

- 97 catalogued MCP tools: 75 TCP, 3 WebSocket, 5 composed, and 14 local or
  headless routes.
- New `plan_user_journey` tool providing structured four-stage planning (discover,
  await confirmation, apply, verify).
- Dedicated UDP realtime control channel on port `9890` (`contracts.REALTIME_UDP_PORT`)
  with guarded message draining.
- Regenerated retrieval seed v3 with 4,000 curated grooves across 266 collections,
  Superior Drummer 3 and General MIDI articulation mappings, 85.8% genre coverage,
  and tempo/bpm indexing.
- Polyrhythm transformation axis support for deterministic groove generation.
- Loopback-only TCP (`127.0.0.1:9888`) and WebSocket (`127.0.0.1:9889`) bridges.
- Version-aware release artifacts with SHA-256 checksums and source-commit provenance.

### Artifacts

- `ableton_mcp_server-0.7.0-py3-none-any.whl`
- `AbletonMCPServer_RemoteScript-0.7.0.zip`
- `AbletonMCPServer-Extension-0.7.0.ablx`
- `SHA256SUMS`
- `manifest.json`
- `INSTALL.md`

### Installation

Install the wheel, extract the Remote Script into Ableton's User Library, and
install the `.ablx` Extension. Restart Ableton Live, select
`AbletonMCPServer` as a Control Surface, then run:

```powershell
.\.venv-win\Scripts\ableton-mcp.exe install-status --json
.\.venv-win\Scripts\ableton-mcp.exe doctor --json
```
