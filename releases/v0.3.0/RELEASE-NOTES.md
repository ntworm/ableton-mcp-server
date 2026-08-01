# Release notes — v0.3.0

**Date**: 2026-07-10
**Commit**: `38d6cdc` (merge) / `a2152c5` (last v0.3.0 feature commit)
**Tag**: `v0.3.0` (local-only, not pushed)
**Branch**: `main`
**Verified against**: Live 12.4.5b7 (Suite Beta), pytest suite, ruff clean, mypy --strict, `ableton-mcp doctor --json` round-trip.

---

## What ships

### Hybrid Dual-Bridge Architecture (new)
The MCP server now ships **two** Live-side adapters instead of one. Each command is routed by `ableton_mcp_server/client.py` based on `WEBSOCKET_TARGET_COMMANDS`:

- **TCP JSONL** (`127.0.0.1:9888`) → MIDI Remote Script → Live Python LOM. Same protocol as v0.2.x. Loopback-only.
- **WebSocket JSON-RPC** (`127.0.0.1:9889`) → TypeScript Extension Host → Live Node LOM. New. Loopback-only by intent (see `risks.md`).

The browser-touching commands (warp, device loading) and any other commands that require the Extension SDK go through the WS bridge. The Python Remote Script remains the source of truth for all transport/cue/clip/MIDI/track introspection.

### TypeScript Extension Host (new)
`AbletonMCPServer_Extension/` is a fresh repo subtree:

```text
AbletonMCPServer_Extension/
├── src/
│   ├── extension.ts   # activate/deactivate
│   ├── context.ts     # SDK context lifetime
│   └── index.ts       # WebSocket handlers + JSON-RPC dispatch
├── build.ts           # esbuild driver (bundles src/extension.ts → manifest entry)
├── manifest.json      # Ableton Extensions manifest (version 0.3.0)
├── package.json       # Node deps + build scripts
├── tsconfig.json
├── vendor/            # ableton-extensions-cli / -sdk pinned tarballs
└── dist/              # build output (gitignored)
```

WebSocket handlers exposed today: `get_warp_state`, `set_warp_state`, `load_device_to_track`. Build with `cd AbletonMCPServer_Extension && npm install && npm run build`.

### 46 MCP tools (was 37)
9 new tools land in this release:

| Tool | Verb | Source | Routing |
|---|---|---|---|
| `get_composition_structure` | READ | fresh | TCP/JSONL |
| `diagnose_midi_clip` | READ | fresh (note overlap, C-major detect, grid drift) | TCP/JSONL |
| `create_midi_track` | WRITE (96-track cap) | new track creation | TCP/JSONL |
| `rename_track` | WRITE | track/clip name | TCP/JSONL |
| `get_warp_state` | READ | AudioClip warping | WS/JSON-RPC |
| `set_warp_state` | WRITE (deferred) | AudioClip warping | WS/JSON-RPC |
| `load_device_to_track` | WRITE | browser insertion | WS/JSON-RPC |
| `scaffold_extension` | local | build pipeline | local |
| `build_extension` | local | compile pipeline | local |

Two error classes also land: `ExtensionUnavailableError` and `TrackLimitError`. See `docs/TOOL_REFERENCE.md` for the canonical surface listing.

### Repo context (new)
`AGENTS.md` + `.agent-context/{architecture,conventions,dependencies,hot-files,risks}.md` are now committed at the root. Generated evidence under `.agent-context/generated/` is gitignored. Future agents should `repo-context-loader check` first instead of broad-exploring the repo.

### v0.4.0 design docs (committed, not implemented)
Two proposals sit under `prompts/` as historical record:
- `prompts/REQUEST-2026-07-10-borrow-from-live-wire-and-ableton-bridge.md` (curated 12-tool list, explicit non-goals, attribution rules)
- `prompts/SPEC-2026-07-10-v0.4.0-borrow-specs.md` (1757-line engineering handbook: signatures, Pydantic models, handler sketches, test patterns)

The implementation track for these lives on `feature/v0.4.0-borrow-competitor-features` (see Distribution status below).

---

## What stays the same

- **Loopback-only bridge**: port 9888 (TCP) and port 9889 (WS). Both bound to `127.0.0.1` by intent. Documentation claims local-only; **WebSocket bind is not currently code-enforced loopback** (see `risks.md` §1). Do not expose either port externally.
- **`scripts/setup_windows.ps1` is the canonical installer.** Idempotent. Provisions `.venv-win/`, installs the package, deploys the Remote Script, prints the MCP stdio command. Re-run after upgrading.
- **Acceptance runner mutates a real Set** with `--project-name` confirmation and empty MIDI clip slot check. Use a disposable Set named per your test fixture.

---

## Install

1. **Bootstrap** (Windows PowerShell, from the repo root):

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
   ```

2. **Build the Extension Host**:

   ```powershell
   cd AbletonMCPServer_Extension
   npm install
   npm run build
   ```

3. **Open Live 12.4.5+ Suite Beta**. The `AbletonMCPServer` MIDI Remote Script auto-loads under Control Surfaces; load the Extension `.ablx` from `AbletonMCPServer_Extension/dist/` via Preferences → Extensions.

4. **Plug the printed `.exe` path into any MCP client**:

   ```
   command: C:\path\to\ableton-mcp-server\.venv-win\Scripts\ableton-mcp-server.exe
   env:
     ABLETON_MCP_SERVER_HOST: 127.0.0.1
     ABLETON_MCP_SERVER_PORT: "9888"
   ```

5. **Pre-flight**:

   ```powershell
   & 'C:\path\to\ableton-mcp-server\.venv-win\Scripts\ableton-mcp.exe' doctor --json
   ```

   Confirm `bridge_available: true` for both TCP and (if you need warp/devices) WS.

---

## Upgrade from v0.2.x

1. Pull `main` (or rebase your local work onto tag `v0.3.0`).
2. Re-run `scripts/setup_windows.ps1`.
3. Build and load the new Extension (step 2 above).
4. Restart Live so it picks up the new Remote Script payload + the new Extension.
5. Existing MCP clients keep working — the stdio command and port 9888 are unchanged.

The CHANGELOG entry below documents every concrete change since v0.2.2 — read it before filing an issue.

---

## Known caveats (carry-over + new)

- **WebSocket bind verification pending.** `WebSocketServer({ port: 9889 })` in `AbletonMCPServer_Extension/src/index.ts` does **not** explicitly bind `host: '127.0.0.1'`. Until the bind is code-enforced and a regression test added, do **not** expose port 9889 through any firewall, container port mapping, or tunnel.
- **Thread affinity**: Live's Python Object Model is not thread-safe. The MIDI Remote Script's socket thread enqueues work; `update_display()` advances handlers on Live's UI thread. Direct socket-thread LOM access can destabilize Live.
- **WSL clients must launch the Windows-native `.exe`** (`/mnt/c/.../.venv-win/Scripts/ableton-mcp-server.exe`) — WSL's `127.0.0.1` is not Windows loopback.
- **Ambiguous network failure → no replay.** Mutations are deliberately not replayed after an ambiguous disconnect; inspect current state before deciding whether to resend.
- **`run_batch` is grouped undo, not rollback.** First error aborts the batch; earlier successful commands remain applied inside one outer undo step. One user undo reverts the whole prefix.
- **Contracts drift risk.** Root `contracts.py` is canonical; `AbletonMCPServer_RemoteScript/_contracts.py` is vendored via `scripts/vendor_contracts.py`. Never hand-edit both. Re-run vendor after every `contracts.py` edit.
- **Session-local path IDs**. `track:2/device:1` is an index locator, not a durable handle. Re-list after structural edits; treat resolution failures as stale references.
- **Tests are part of the release contract.** `tests/test_packaging.py` asserts `len(PUBLIC_TOOL_NAMES) == 46`; bump it explicitly whenever you add a public MCP tool.

---

## Verification artifacts

| gate | result |
|---|---|
| `pytest` (test_server_tools, test_tool_registry, test_models, test_ws_client, test_composition, test_diagnostics_midi, test_contracts, test_packaging, remote_fakes) | passing |
| `ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests` | clean |
| `mypy --strict ableton_mcp_server` | clean |
| `python -c "from ableton_mcp_server.server import mcp; print(len(mcp.list_tools()))"` | `46` |
| `cd AbletonMCPServer_Extension && npm install && npm run build` | bundles successfully |
| `ableton-mcp doctor --json` | `bridge_available: true` (TCP); WS availability depends on Extension load |
| Acceptance runner (disposable Set `TESTE_CODEX`, track 0, clip slot 3) | `status: ok`, fire + cue round-trip |
| SHA256SUMS | `releases/v0.3.0/SHA256SUMS` (24 entries) |

---

## Distribution status

- Tag `v0.3.0` exists locally at `38d6cdc`. Not pushed.
- `main` is 9 commits ahead of `origin/main`. Not pushed.
- `releases/v0.3.0/*` artifacts are local-only.
- `feature/v0.3.0-super-bridge` was merged and deleted locally. The implementation track for the v0.4.0 REQUEST + SPEC pair starts at `feature/v0.4.0-borrow-competitor-features`.

To publish: review the diff (`git log 58c308a..v0.3.0`), verify SHA256SUMS against a fresh clone, then ask explicitly before any `git push` or `git push --tags`. The Extension Host's WebSocket bind should be code-enforced loopback before the first public release.
