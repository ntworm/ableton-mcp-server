# Install & WSL Incompatibility Report — 2026-07-09

**Author**: broc (assistant), testing session with worm
**Repo**: `ableton-mcp-server` @ commit `a88dd1f` ("feat: rewrite Ableton MCP server")
**Env**: Windows 11 host + WSL2 (Ubuntu), Live 12.4.5b7, hermes MCP client (in-process stdio)

---

## TL;DR

Install, deploy, and registration all worked. **Server cannot connect to the Live Remote Script when run from WSL** because of two design choices that assume the server runs on the Windows host. `hermes mcp test` reports "36 tools" successfully but **does not actually exercise the Live bridge** — see Finding F1. Worm's request to "switch MCP server to ableton-mcp-server" is blocked by this. No workarounds were applied; user wants CODEX to fix the root cause.

---

## What was done

| step | command / action | result |
|---|---|---|
| 1 | `cd /mnt/c/.../ableton-mcp-server && python3 -m venv .venv` | venv created (Linux, not Windows — see Finding F2) |
| 2 | `.venv/bin/python3.11 -m pip install -e ".[dev]"` | timeout on first run; completed on retry; all deps including `fastmcp 3.4.4` installed |
| 3 | `python scripts/vendor_contracts.py` | OK; `_contracts.py` regenerated with vendor diff = header only |
| 4 | `cp -r AbletonMCPServer_RemoteScript/ /mnt/c/Users/<username>/Documents/Ableton/User Library/Remote Scripts/AbletonMCPServer_RemoteScript/` | OK; md5 verified; `__pycache__` purged |
| 5 | Old `AbletonDebuggerMCP_RemoteScript/` deleted from User Library | OK |
| 6 | `[Environment]::SetEnvironmentVariable('ABLETON_MCP_SERVER_VERBOSE', '1', 'User')` in PowerShell | set; persists across reboots |
| 7 | Live closed via PowerShell | OK |
| 8 | User reopened Live; AbletonMCPServer auto-loaded as `MidiRemoteScript 3` per `Log.txt` | confirmed via `get_ableton_logs` |
| 9 | `hermes mcp remove ableton-debugger` (the old, 12-tool server) | OK |
| 10 | `hermes mcp add ableton-mcp-server --command /mnt/c/.../.venv/bin/python3.11 --args -m ableton_mcp_server.server --env PYTHONPATH=... ABLETON_MCP_SERVER_HOST=127.0.0.1 ABLETON_MCP_SERVER_PORT=9888` | first attempt: `Connection closed` (likely warm-up race); second attempt (accepted "save anyway"): **36 tools discovered** |
| 11 | `hermes mcp test ableton-mcp-server` | "Connected (12750ms), 36 tools" |
| 12 | Direct repro: `Client(host='127.0.0.1', port=9888).call('get_session_info', {})` from WSL python | **`ConnectionRefusedError [Errno 111]`** |
| 13 | PowerShell `Get-NetTCPConnection -LocalPort 9888` | 127.0.0.1:9888 LISTENING, PID 46396 (Live) |
| 14 | WSL python `socket.create_connection(('127.0.0.1', 9888))` | refused |
| 15 | WSL python `socket.create_connection(('192.168.100.9', 9888))` | refused (Remote Script binds loopback only, no route from WSL) |
| 16 | `Client(host='192.168.100.9', port=9888)` constructor | `ValueError: Ableton bridge host must be loopback 127.0.0.1` (intentional hard guard) |

**Conclusion**: server cannot be exercised end-to-end from a WSL-launched hermes subprocess. The Remote Script is up; the MCP server is up; but the bridge socket is unreachable across the WSL↔Windows loopback boundary and the Client refuses non-loopback hosts.

---

## Findings

### F1 — `hermes mcp test` does not validate the Live bridge

**Severity**: high (false-positive verification)
**File**: `ableton_mcp_server/server.py:82-88` (interaction with `hermes` MCP client)

`hermes mcp test` reports "36 tools" because `CountableFastMCP.list_tools()` (`server.py:82`) is a **pure in-memory enumeration** of `PUBLIC_TOOL_NAMES` — it never opens the `Client` socket. So "✓ Connected, ✓ 36 tools" only proves the Python entrypoint imports cleanly and FastMCP is wired up. **It does NOT prove the server can talk to Live.**

Repro: after `mcp add` + `mcp test` both succeeded with 36 tools, the very next direct call `Client(...).call('get_session_info', {})` raised `ConnectionRefusedError`. The MCP client's "list tools" handshake is decoupled from the per-tool RPC path.

**Suggested fix**: add an integration test that calls a real read tool (e.g. `get_session_info`) against a mock Remote Script, and surface a clear `LIVE_UNAVAILABLE` error in `list_tools()` (or in the MCP server's `health`/`ping` mechanism) when the bridge socket can't be opened at startup. The current `hermes mcp test` command should fail or warn when the bridge is unreachable.

### F2 — venv was created in WSL instead of Windows

**Severity**: medium (downstream of F3 — caused by CODEX's deployment instructions being silent on WSL)
**File**: install flow (no `setup.py` / no `Makefile` target for Windows venv)

The `.venv/` created by `python3 -m venv` in this WSL shell is a Linux venv (`bin/python3.11`, no `Scripts/python.exe`). Installed deps via the Linux pip, so `.venv/bin/python3.11` is the only working interpreter for that venv.

The **previous** debugger server (`ableton-debugger-mcp`) was registered with a Windows venv at `.venv/Scripts/python.exe`, which `hermes` resolves via the WSL mount — that worked. So there's an existing pattern of "use Windows venv for hermes MCP servers". CODEX's prompt and `README.md` should explicitly state which interpreter is expected. If WSL Linux python is acceptable, the docs need to address Finding F3.

### F3 — `Client` hard-rejects non-loopback hosts; WSL loopback ≠ Windows loopback

**Severity**: **blocker** (cannot ship as-is for the user's hermes-Windows-WSL workflow)
**File**: `ableton_mcp_server/client.py:20-39`, specifically lines 28-29:

```python
def __init__(
    self,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    reconnect: bool = True,
    max_retries: int = 3,
    backoff_factor: float = 0.05,
) -> None:
    if host != DEFAULT_HOST:
        raise ValueError("Ableton bridge host must be loopback 127.0.0.1")
```

The hard guard forces `host == "127.0.0.1"`. This is intentional (security: don't expose Live API to LAN). But it makes the server **Windows-host-only**. WSL Python connects to `127.0.0.1` and gets the **WSL loopback**, not the Windows loopback where the Remote Script is bound. Same-host WSL↔Windows loopback is not bridged by default in WSL2.

Workarounds the user explicitly forbade:
- `wsl --exec` style: not available across hermes subprocess boundary
- `localhostAlias` / `0.0.0.0` rebind: would defeat the security intent of the guard
- `--add-interface=...` WSL settings: not portable, fragile

**What needs to change**:

Option A (minimum): allow the Client to accept the Windows host IP (e.g. `192.168.100.x`) when the env var `ABLETON_MCP_SERVER_HOST` resolves to a private RFC1918 address, and have the Remote Script also bind `0.0.0.0` instead of `127.0.0.1`. Both ends need to change together.

Option B (cleaner): ship a Windows venv explicitly via `pyproject.toml` `[project.scripts]` + a `setup-windows-venv.ps1` script, document it as the only supported install path for hermes-on-Windows. WSL users would launch the hermes subprocess with a `.exe` Python that runs on the Windows side, so loopback matches.

Option C (cleanest): make the Remote Script bind both `127.0.0.1` **and** the LAN interface, and let the Client take any host (no hard guard) but require an opt-in env var (`ABLETON_MCP_SERVER_ALLOW_REMOTE=1`) to leave loopback. Document the security tradeoff explicitly.

I'd recommend **Option C** — it's the smallest behaviour change for the WSL case, preserves the loopback-only default, and matches the user's existing practice of running things from WSL against Windows-host services (e.g. setlist-bridge already does this on `0.0.0.0:4444`).

### F4 — `get_ableton_logs` uses `os.environ.get("APPDATA")` which is Windows-only

**Severity**: low (will silently return `None` and the tool will surface a graceful "not found" if implemented correctly, but worth knowing)
**File**: `ableton_mcp_server/server.py:108-121` (`find_ableton_log_path`)

```python
def find_ableton_log_path() -> Path | None:
    if not appdata:
        return None
    ...
```

`APPDATA` is a Windows env var. On WSL Linux it doesn't exist (unless explicitly exported from Windows). So `get_ableton_logs` will return `None`/empty when the server is launched from WSL. If the fix to F3 keeps the server on WSL, this tool needs an alternate path resolution (e.g. translate `~/.hermes/profiles/broc` → `/mnt/c/Users/<username>/AppData/Roaming`, or read the env from the parent hermes process and re-export).

### F5 — verbose env var does not appear in `Log.txt`

**Severity**: low (cosmetic)
**File**: `AbletonMCPServer_RemoteScript/__init__.py` (no `ABLETON_MCP_SERVER_VERBOSE` handler)

I set `ABLETON_MCP_SERVER_VERBOSE=1` in the user environment before Live launched. The `Log.txt` shows the Remote Script loaded (`MidiRemoteScript 3 [Control Surface="AbletonMCPServer_RemoteScript"`) but **no `[MCP-Server]` lines** appear. Either the Remote Script's `__init__.py` doesn't read this env var, or it uses a different prefix (e.g. `ABLETON_MCP_VERBOSE`), or the logger isn't pointed at Live's `Log.txt`. Test queries (before the MCP swap) returned data correctly, so the bridge works — the debug output just isn't surfacing.

Suggest reading the env var in `RemoteScript.__init__` and calling `self.log_message(f"[MCP-Server] …")` for command receipts and bridge state transitions.

---

## Test evidence (kept for the record)

```
$ hermes mcp list
  Name                  Transport                      Tools  Status
  filesystem            npx -y --prefer-offline        all    ✓ enabled
  playwright            npx -y --prefer-offline        all    ✓ enabled
  sequential-thinking   npx -y --prefer-offline        all    ✓ enabled
  ableton-mcp-server    /mnt/c/.../.venv/bin/python…   all    ✓ enabled

$ hermes mcp test ableton-mcp-server
  Transport: stdio → /path/to/ableton-mcp-server/.venv/bin/python3.11
  Auth: none
  ✓ Connected (12750ms)
  ✓ Tools discovered: 36

$ /mnt/c/.../venv/bin/python3.11 -c "from ableton_mcp_server.client import Client; Client().call('get_session_info', {})"
  ConnectionError: Command 'get_session_info' failed at 127.0.0.1:9888:
                    [Errno 111] Connection refused

$ /mnt/c/.../venv/bin/python3.11 -c "from ableton_mcp_server.client import Client; Client(host='192.168.100.9', port=9888)"
  ValueError: Ableton bridge host must be loopback 127.0.0.1

$ powershell Get-NetTCPConnection -LocalPort 9888
  LocalAddress  LocalPort  State    OwningProcess
  127.0.0.1     9888       Listen   46396        ← Live

$ /mnt/c/.../venv/bin/python3.11 -c "import socket; socket.create_connection(('127.0.0.1', 9888)).close()"
  ConnectionRefusedError: [Errno 111] Connection refused

$ /mnt/c/.../venv/bin/python3.11 -c "import socket; socket.create_connection(('192.168.100.9', 9888)).close()"
  ConnectionRefusedError: [Errno 111] Connection refused
```

The "old" `ableton-debugger-mcp` server worked in this same environment because its `Client` did not have the loopback guard — it connected to `192.168.100.9:9888` directly. That's why worm's tests earlier in the session showed `get_session_info` returning data successfully **via the old 12-tool server** while the new 36-tool server, despite being registered, returns nothing.

---

## What I did NOT do (user explicitly forbade workarounds)

- Did NOT add `wsl --exec`-style invocations to bypass the loopback guard.
- Did NOT rebind the Remote Script to `0.0.0.0` from outside (no write access to Remote Script logic from hermes anyway, but I also didn't ask CODEX for a stopgap patch — the user wants the proper fix).
- Did NOT register a side-by-side MCP server to keep the old one alive.
- Did NOT use `PYTHONPATH` magic to coerce the WSL Python to find the Windows-side loopback (impossible; the OS routes it differently).
- Did NOT touch `ableton_mcp_server/` source. The `git status` is clean (per Finding F2 the `.venv/` is untracked, which is correct).

---

## What the user (worm) wants from CODEX

1. Pick one of F3 Options A/B/C (recommend C) and ship it. The `ValueError` guard cannot stay as-is for the hermes-on-WSL workflow.
2. Update `README.md` install steps to specify Windows venv explicitly (Option B) **or** document the host-IP allowance + security caveat (Option C).
3. Decide whether `hermes mcp test` should probe the Live bridge; if yes, ship the F1 fix.
4. Verify `ABLETON_MCP_SERVER_VERBOSE` actually logs to `Log.txt`, or remove the env var to avoid misleading users.
5. Confirm the new venv path expectations are aligned with `pyproject.toml`'s `[project.scripts]` entry (if any) so future installs don't re-trip F2.

---

## Files referenced (no edits made)

- `ableton_mcp_server/client.py` (lines 20-39)
- `ableton_mcp_server/server.py` (lines 75-121, 124-184)
- `AbletonMCPServer_RemoteScript/__init__.py` (verbose handler missing)
- `~/.hermes/profiles/broc/config.yaml` (server entry; CODEX does not own this — but note the previous `ableton-debugger` used `host='192.168.100.9'` and worked)

## End of report