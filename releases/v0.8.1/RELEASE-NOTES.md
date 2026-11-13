# Release Notes

## v0.8.1

v0.8.1 ships the 97-tool server without the curated groove corpus in any distributed package. This stable release is bound to a guarded acceptance report with `release_ready=true`, run on Ableton Live 12.4.25b1 against a disposable Set on 2026-11-13: 71 tools passed in Live, 17 passed offline, none failed. The `v0.8.1-rc1` pre-release of 2026-10-31 carried the corpus change only; this release adds the changes listed below.

### Highlights

- **No bundled corpus**: the wheel, the source archive and the MCP bundle no longer contain the groove corpus. The server starts and exposes its 97 tools without one, and corpus-backed operations report that no corpus is configured instead of fetching one.
- **Optional private seed**: a local corpus is read from `%LOCALAPPDATA%\AbletonMCPServer\groove-seed` on Windows, `~/Library/Application Support/AbletonMCPServer/groove-seed` on macOS, or the path in `ABLETON_GROOVE_SEED_BUNDLE`. A missing seed and an invalid seed report different messages.
- **Import without a home directory**: the seed path is resolved when it is used, so the server imports on hosts with no home directory.
- **MCP Registry descriptor**: `server.json` describes the server for the official MCP Registry and pins the SHA-256 of the MCP bundle of this release.
- **Python 3.10 to 3.14**: continuous integration runs on all five versions.

### Artifacts

- `ableton_mcp_server-0.8.1-py3-none-any.whl` (sha256 `928dbe3f527de0be3658f46a2625caa590f2dac87b8fd95a461826b9e3620963`)
- `ableton_mcp_server-0.8.1.tar.gz` (sha256 `30453ec6ec0322dd820081f4ac5cc017a654337364ae49576798b3bf82331f3d`)
- `AbletonMCPServer_RemoteScript-0.8.1.zip` (sha256 `281341302c0ac16a41d83e8b4fb34e40ef2de2056d907458918a3989580ad508`)
- `AbletonMCPServer-Extension-0.8.1.ablx` (sha256 `6a4fa3181654031fb592970b1ea3781f1a59e43b5120f221e7bd93e3b74d620a`)
- `ableton-mcp-server-0.8.1.mcpb` (sha256 `64eed840cc0317f6af9e97f090c52d1d4441d7ada03c946cd1f2d39f2c2d3b41`)
- `acceptance-0.8.1.json`, the per-tool acceptance summary (sha256 `f3f177f8e8489bd527f7410dc858dcf43d66ac9fb586e6457e1138991b1d3bc8`)

The `manifest.json` of the release records the source commit and the SHA-256 of the full acceptance report, which stays private because it contains local paths of the test machine.
