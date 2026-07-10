# Release notes — v0.2.1

**Date**: 2026-07-09
**Commit**: `72e590c` (merge) / `60b0cd2` (feature)
**Tag**: `v0.2.1` (local-only, not pushed)
**Branch**: `main`
**Verified**: Live 12.4.5b7, pytest 168, ruff clean, mypy --strict, doctor end-to-end against disposable set `TESTE_CODEX`.

---

## What ships

### Acceptance runner (new)
`ableton-mcp-server` ships a guarded real-Live smoke test that refuses to mutate the project unless the disposable Set name, MIDI track index, and empty clip slot all match what you pass in. Restore-on-failure is guaranteed for tempo, loop, and playhead; the disposable clip is left behind by design.

Run from PowerShell after opening a disposable Live Set named e.g. `TESTE_CODEX`:

```powershell
& 'C:\Users\Usuario\repos\ableton-mcp-server\.venv-win\Scripts\ableton-mcp.exe' acceptance --project-name TESTE_CODEX --track-index 0 --clip-index 3
```

The CLI refuses to run without an explicit `--project-name` and exits non-zero if the loaded Set does not match.

### Windows bootstrap (new)
The repository now ships `scripts/setup_windows.ps1`, which provisions a Windows-native virtualenv at `.venv-win\`, installs the package in editable mode, deploys the Remote Script to Live's User Library, and prints the exact stdio command line to plug into any MCP client.

```powershell
powershell -ExecutionPolicy Bypass -File 'C:\Users\Usuario\repos\ableton-mcp-server\scripts\setup_windows.ps1'
```

### Bridge doctor (new)
`ableton-mcp doctor` reports runtime, endpoint reachability, and bridge state in either JSON or human format. Exit code is non-zero when the bridge is unavailable. Use this as the pre-flight check before plugging the server into an MCP client.

### 37 tools (was 36)
`get_bridge_status` is the new tool. Total surface: 37 FastMCP tools, all wired through the loopback JSONL protocol on `127.0.0.1:9888`. See `docs/TOOL_REFERENCE.md` for the full list.

### WSL compatibility
The Live Remote Script binds `127.0.0.1:9888` only; on WSL, hermes launches the Windows-side `ableton-mcp-server.exe` from the `.venv-win` bootstrap so the MCP process shares Live's Windows loopback network. No LAN exposure, no firewall changes, no `0.0.0.0` rebind.

---

## Install

1. Run `scripts/setup_windows.ps1` from PowerShell.
2. Open Live. The `AbletonMCPServer` MIDI Remote Script auto-loads under Control Surfaces.
3. Plug the printed `.exe` path into your MCP client's stdio config. For hermes:

```
command: C:\Users\Usuario\repos\ableton-mcp-server\.venv-win\Scripts\ableton-mcp-server.exe
env:
  ABLETON_MCP_SERVER_HOST: 127.0.0.1
  ABLETON_MCP_SERVER_PORT: "9888"
```

For a WSL hermes client, the same path is reachable via `/mnt/c/Users/Usuario/repos/ableton-mcp-server/.venv-win/Scripts/ableton-mcp-server.exe`.

---

## Upgrade from v0.2.0

1. Pull this branch.
2. Re-run `scripts/setup_windows.ps1` (it is idempotent and will reinstall the Remote Script and bump the package version in-place).
3. Restart Live so it picks up the new Remote Script payload.
4. Re-register the MCP entry in your client (the `command` path does not change).

---

## Known caveats

- The bridge remains loopback-only. Do not change the bind address; do not expose port 9888 on the LAN.
- The `ABLETON_MCP_SERVER_VERBOSE` environment variable now produces lines prefixed with `[MCP-Server]` in Live's `Log.txt`. Set to `1` in the user environment to enable.
- The Remote Script's installer uses `setup_windows.ps1` and refuses to operate outside the repository root.
- The acceptance runner mutates the loaded Set (creates a 4-beat clip with 4 MIDI notes in the target slot, creates and deletes a cue point) and leaves the clip behind by design. Use a disposable Set.

---

## Verification artifacts

| gate | result |
|---|---|
| `pytest` | 168 passed |
| `ruff check` | All checks passed |
| `mypy --strict` (13 source files) | Success: no issues found |
| `ableton-mcp doctor` | `bridge_available=true`, `status=ok` |
| `run_live_acceptance(confirm='TESTE_CODEX', track=0, clip=3)` | `status=ok`, `cue_round_trip=true`, `notes_added=4`, batch `completed=2, aborted_at=2, rolled_back=false` (expected — slot already occupied by acceptance's own previous step) |
| SHA256SUMS | `releases/v0.2.1/SHA256SUMS` (16 entries) |

---

## Distribution status

- Tag `v0.2.1` exists locally at `72e590c`. Not pushed.
- `main` is 6 commits ahead of `origin/main`. Not pushed.
- All release artifacts in this directory are local-only.

To publish: review the diff (`git log a88dd1f..72e590c`), verify SHA256SUMS, then ask explicitly before any `git push` or `git push --tags`.