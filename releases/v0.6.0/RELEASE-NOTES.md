# Release Notes

## v0.6.0

v0.6.0 publishes the complete 96-tool Ableton MCP Server surface. It adds
three deterministic offline music-generation tools and five Groove
Intelligence tools to the 88-tool v0.5.6 source milestone.

### Highlights

- 96 catalogued MCP tools: 75 TCP, 3 WebSocket, 5 composed, and 13 local or
  headless routes.
- Deterministic drum-groove, bass, and production-plan generation.
- Offline Groove search, evidence, generation, and comparison, plus one
  explicit guarded apply route.
- Plugin preset inspection/write support and clearer Configure-gate diagnostics.
- Loopback-only TCP (`127.0.0.1:9888`) and WebSocket (`127.0.0.1:9889`)
  bridges.
- Version-aware release artifacts with SHA-256 checksums and source-commit
  provenance.

### Artifacts

- `ableton_mcp_server-0.6.0-py3-none-any.whl`
- `AbletonMCPServer_RemoteScript-0.6.0.zip`
- `AbletonMCPServer-Extension-0.6.0.ablx`
- `SHA256SUMS`
- `manifest.json`
- `INSTALL.md`
- guarded acceptance report

### Installation

Install the wheel, extract the Remote Script into Ableton's User Library, and
install the `.ablx` Extension. Restart Ableton Live, select
`AbletonMCPServer` as a Control Surface, then run:

```powershell
.\.venv-win\Scripts\ableton-mcp.exe install-status --json
.\.venv-win\Scripts\ableton-mcp.exe doctor --json
```

Stable promotion requires the full offline gate set and a guarded baseline
acceptance run against a disposable Set with all 96 tool rows present,
zero failures, and `release_ready: true`.
