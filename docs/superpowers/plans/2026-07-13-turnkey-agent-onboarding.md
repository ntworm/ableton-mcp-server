# Turnkey Agent Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an unfamiliar agent clone the repository, install both required Ableton components without Node.js, diagnose the runtime, discover 125 truthful capabilities, and complete a safe read-only inspection using only exposed MCP guidance.

**Architecture:** Package a prebuilt Extension payload beside the Remote Script, expose one idempotent setup/doctor flow, and derive MCP instructions/resources/prompts plus tool documentation from the canonical catalog. Add an internal Extension health RPC so diagnostics never need a clip/device fixture merely to prove WebSocket availability.

**Tech Stack:** Python 3.10+, FastMCP resources/prompts/instructions, Hatchling wheel data, PowerShell setup, Ableton Extension JSON-RPC, pytest, TypeScript/node:test for development builds only.

**Verified FastMCP API:** Installed FastMCP 3.4 exposes `FastMCP(name, instructions=...)`, `@mcp.resource(uri, ...)`, `@mcp.prompt(...)`, async `list_resources/read_resource/list_prompts/get_prompt`, and the existing `@mcp.tool` API. Tests use these public methods rather than private component registries.

---

## File map

- Create `ableton_mcp_server/instructions.py`: server-level agent rules.
- Create `ableton_mcp_server/resources.py`: five resource implementations/registration.
- Create `ableton_mcp_server/prompts.py`: five prompt implementations/registration.
- Create `ableton_mcp_server/guides/`: packaged installation, safety, and troubleshooting text.
- Create `ableton_mcp_server/extension_install.py`: prebuilt Extension discovery, hash status, install.
- Create `ableton_mcp_server/setup.py`: unified idempotent installation orchestration.
- Create `scripts/generate_tool_reference.py`: catalog-driven reference generator/checker.
- Create `scripts/verify_clean_install.ps1` updates: assert runtime install needs no Node.
- Create `docs/verification/125-tool-certification.json`: promoted final evidence only after acceptance.
- Modify Extension dispatcher for internal `get_extension_status`.
- Modify `diagnostics.py`, `cli.py`, `server.py`, setup script, package metadata, README/docs/tests.

### Task 1: Enrich the catalog and generate tool reference data

**Files:**
- Modify: `ableton_mcp_server/catalog.py`
- Create: `scripts/generate_tool_reference.py`
- Create: `tests/test_tool_reference_generation.py`
- Modify: `docs/TOOL_REFERENCE.md`

- [ ] **Step 1: Write failing catalog-quality and drift tests**

```python
def test_every_catalog_entry_has_agent_metadata() -> None:
    for item in TOOL_CATALOG:
        assert item.summary.strip()
        assert item.prerequisites
        assert item.cleanup in {"none", "readback", "undo", "explicit", "manual"}


def test_generated_reference_is_current() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/generate_tool_reference.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
```

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_tool_reference_generation.py -q`

Expected: metadata fields/generator are absent.

- [ ] **Step 3: Extend immutable catalog metadata**

Add these fields to `ToolSpec`:

```python
summary: str
prerequisites: tuple[str, ...]
cleanup: str
minimum_live: str | None = None
```

Populate all 125 entries. Use `("tcp_bridge",)` for TCP tools,
`("websocket_bridge",)` for Extension tools, and explicit local prerequisites
such as `("local_audio_file",)` or `("node_development_runtime",)`. Summaries
are one sentence and must describe the observable result, not restate the name.

- [ ] **Step 4: Implement deterministic Markdown/JSON rendering**

```python
def render_reference(specs: tuple[ToolSpec, ...]) -> str:
    lines = ["# Tool Reference", "", f"Public tools: {len(specs)}", ""]
    for spec in sorted(specs, key=lambda item: (item.domain, item.name)):
        lines.extend(
            [
                f"## `{spec.name}`",
                "",
                spec.summary,
                "",
                f"- Domain: `{spec.domain}`",
                f"- Route: `{spec.route.value}`",
                f"- Risk: `{spec.risk.value}`",
                f"- Acceptance: `{spec.acceptance.value}`",
                f"- Prerequisites: {', '.join(f'`{p}`' for p in spec.prerequisites)}",
                f"- Cleanup: `{spec.cleanup}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
```

The script writes `docs/TOOL_REFERENCE.md` by default. `--check` renders in
memory, compares exact UTF-8 text, prints the target path on drift, and exits 1
without writing.

- [ ] **Step 5: Generate and run GREEN**

Run:

```powershell
.\.venv-win\Scripts\python.exe scripts\generate_tool_reference.py
.\.venv-win\Scripts\python.exe -m pytest tests\test_tool_reference_generation.py tests\test_catalog.py -q
```

Expected: generated reference contains 125 unique headings and `--check` exits 0.

- [ ] **Step 6: Commit**

Commit subject: `docs: generate reference from capability catalog`.

### Task 2: Add global FastMCP agent instructions

**Files:**
- Create: `ableton_mcp_server/instructions.py`
- Modify: `ableton_mcp_server/server.py`
- Modify: the module that instantiates `CountableFastMCP`
- Create: `tests/test_instructions.py`

- [ ] **Step 1: Write a failing instructions test**

```python
def test_server_instructions_encode_safe_agent_boot_sequence() -> None:
    assert mcp.instructions == SERVER_INSTRUCTIONS
    for phrase in (
        "get_bridge_status",
        "refresh selectors after structural changes",
        "never blindly retry a mutation",
        "run_batch",
        "disposable Set",
    ):
        assert phrase.casefold() in SERVER_INSTRUCTIONS.casefold()
```

- [ ] **Step 2: Run RED**

Expected: current FastMCP instance has no instructions.

- [ ] **Step 3: Add the complete instruction string at construction time**

```python
SERVER_INSTRUCTIONS = """You control Ableton Live through two loopback bridges.
Start every task with get_bridge_status. Inspect the session before choosing
indexes, and refresh selectors after structural changes. Read before writing and
verify the observed response after every mutation. A lost connection after a
mutation is ambiguous: never blindly retry a mutation. Use run_batch only when
one grouped undo step is intended; a failed batch does not roll back its
successful prefix. Use destructive tools only in an explicitly confirmed
disposable Set. If TCP or WebSocket is unavailable, read the installation and
troubleshooting resources and run the diagnose_installation prompt. Warp markers
are read-only on the supported Extension SDK."""
```

Instantiate `CountableFastMCP("AbletonMCPServer", instructions=SERVER_INSTRUCTIONS)`.

- [ ] **Step 4: Run GREEN and tool-count regression**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_instructions.py tests\test_tool_registry.py -q`

Expected: instructions test passes and tool count remains 125.

- [ ] **Step 5: Commit**

Commit subject: `feat: teach agents the safe Ableton workflow`.

### Task 3: Add five MCP resources

**Files:**
- Create: `ableton_mcp_server/resources.py`
- Create: `ableton_mcp_server/guides/__init__.py`
- Create: `ableton_mcp_server/guides/installation.md`
- Create: `ableton_mcp_server/guides/safety.md`
- Create: `ableton_mcp_server/guides/troubleshooting.md`
- Create: `tests/test_resources.py`
- Modify: `ableton_mcp_server/server.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing public FastMCP resource tests**

```python
@pytest.mark.asyncio
async def test_five_resources_are_public_and_readable() -> None:
    resources = await mcp.list_resources()
    assert {str(item.uri) for item in resources} == {
        "ableton://server/capabilities",
        "ableton://server/installation",
        "ableton://server/safety",
        "ableton://server/troubleshooting",
        "ableton://live/session-summary",
    }
    result = await mcp.read_resource("ableton://server/capabilities")
    payload = json.loads(result.contents[0].content)
    assert payload["tool_count"] == 125
```

Add a session-summary test that mocks the composed read and another that returns
a structured `status:error` payload when Live is offline.

- [ ] **Step 2: Run RED**

Expected: resource listing is empty.

- [ ] **Step 3: Implement pure resource functions**

Register with public decorators:

```python
def register_resources(mcp: FastMCP) -> None:
    mcp.resource(
        "ableton://server/capabilities",
        name="capabilities",
        mime_type="application/json",
        description="The canonical 125-tool routing and safety catalog.",
    )(capabilities_resource)
    # register the remaining four functions with their exact URIs
```

`capabilities_resource()` serializes catalog metadata plus
`ableton_mcp_server/_certification.json` when the promoted release evidence is
present; before promotion it reports `certification_status: "not_promoted"`.
Installation/safety/troubleshooting read the three packaged UTF-8 guide files
through `importlib.resources.files("ableton_mcp_server.guides")`, never
checkout-only relative paths. Add this wheel rule:

```toml
"ableton_mcp_server/guides" = "ableton_mcp_server/guides"
```

The installation guide contains fresh-clone, restart, Control Surface, MCP
executable, and WSL instructions. The safety guide contains selector, readback,
undo, retry, and destructive-operation rules. The troubleshooting guide covers
Python/package, TCP 9888, WS 9889, versions, logs, and repair order. Session
summary calls the composed read once and catches `BridgeError` into JSON; it
never mutates Live.

- [ ] **Step 4: Register once and run GREEN**

Import/call `register_resources(mcp)` from the composition root after tool
registration. Run resource, packaging, and registry tests. Expected: five
resources, 125 tools.

- [ ] **Step 5: Commit**

Commit subject: `feat: expose Ableton guidance as MCP resources`.

### Task 4: Add five diagnostic/workflow prompts

**Files:**
- Create: `ableton_mcp_server/prompts.py`
- Create: `tests/test_prompts.py`
- Modify: `ableton_mcp_server/server.py`

- [ ] **Step 1: Write failing prompt listing/content tests**

```python
@pytest.mark.asyncio
async def test_five_agent_prompts_are_registered() -> None:
    prompts = await mcp.list_prompts()
    assert {item.name for item in prompts} == {
        "diagnose_installation", "inspect_live_set", "safe_session_edit",
        "debug_midi_clip", "build_arrangement",
    }
    prompt = await mcp.get_prompt("diagnose_installation")
    assert prompt is not None
    assert "TCP 9888" in prompt.description
```

- [ ] **Step 2: Run RED**

Expected: prompt listing is empty.

- [ ] **Step 3: Implement prompts as deterministic instruction text**

Each function returns a string and has explicit parameters only when useful:

```python
def diagnose_installation() -> str:
    return """Run get_bridge_status. Check Python/package identity, Remote Script
hashes and Control Surface selection, TCP 9888, Extension manifest/payload and
WS 9889, then read Ableton logs. Do not modify the Set while diagnosing. Report
the first failed boundary and its repair action."""


def debug_midi_clip(track_index: int, clip_index: int) -> str:
    return f"""Inspect track {track_index}, clip slot {clip_index}: clip type,
notes, mute/velocity/loop bounds, playing state, devices, parameter enablement,
routing, monitoring, arm state, and track/main mixer. Read first; propose a
mutation only after identifying the silent boundary."""
```

The other three prompts encode the approved read-plan-write-readback-cleanup
flows. None instructs an agent to bypass guards or execute arbitrary code.

Register each function with an explicit public description so prompt discovery
does not depend on a function docstring:

```python
def register_prompts(mcp: FastMCP) -> None:
    mcp.prompt(
        name="diagnose_installation",
        description="Diagnose Python, TCP 9888, Extension WS 9889, versions, and logs.",
    )(diagnose_installation)
    # register the other four named functions with equally explicit descriptions
```

- [ ] **Step 4: Register once and run GREEN**

Run prompt tests and full listing regression. Expected: five prompts, five
resources, 125 tools.

- [ ] **Step 5: Commit**

Commit subject: `feat: add diagnostic and safe-edit MCP prompts`.

### Task 5: Add an internal Extension health method

**Files:**
- Modify: `AbletonMCPServer_Extension/src/rpc.ts`
- Modify: `AbletonMCPServer_Extension/src/index.ts`
- Create/modify: Extension TypeScript tests
- Modify: `ableton_mcp_server/diagnostics.py`
- Modify: `tests/test_diagnostics.py`

- [ ] **Step 1: Write failing health-probe tests**

Assert JSON-RPC `get_extension_status` requires no params/Live fixture and
returns:

```json
{
  "status": "ok",
  "extension_version": "0.5.0",
  "api_version": "1.0.0",
  "host": "127.0.0.1",
  "port": 9889,
  "methods": ["...sorted method names..."]
}
```

Python diagnostics must set `extension_host_available` true only after this real
round trip, not after a port-open check.

- [ ] **Step 2: Run RED**

Expected: method not found and diagnostics leaves availability `None`.

- [ ] **Step 3: Implement health handler from compile-time constants**

Keep `EXTENSION_VERSION`, `API_VERSION`, host, and port in one TypeScript module
used by server construction and status response. Method names come from sorted
dispatcher keys. Add the internal method to the dispatcher but not the public
MCP catalog, request-model map, or 125 count.

- [ ] **Step 4: Probe WS from diagnostics with bounded timeout**

Keep the existing synchronous TCP-only `bridge_status` for compatibility and add
`async def full_bridge_status(client, ...)`. It calls TCP session info and awaits
`client.call_ws("get_extension_status", {}, timeout=2.0)` independently so output
can represent `tcp_only`, `ws_only`, `both`, or `neither`. Change the public MCP
`get_bridge_status` wrapper to async and make the synchronous CLI call
`asyncio.run(full_bridge_status(...))`. Preserve typed errors and repair hints
for each boundary; never call `asyncio.run` from inside the MCP event loop.

- [ ] **Step 5: Run GREEN, npm tests/build, and commit**

Expected: health tests, diagnostics tests, npm test, and production build pass.

Commit subject: `feat: add fixture-free Extension health probe`.

### Task 6: Package and install the prebuilt Extension without Node.js

**Files:**
- Create: `ableton_mcp_server/extension_install.py`
- Create: `tests/test_extension_install.py`
- Modify: `.gitignore`
- Modify: `pyproject.toml`
- Build/track: `AbletonMCPServer_Extension/dist/extension.js`
- Package: `AbletonMCPServer_Extension/manifest.json`

- [ ] **Step 1: Write failing checkout/wheel install tests**

Tests create temporary checkout and wheel layouts, call source discovery,
install into a temporary Extensions root, modify one installed byte, and assert
statuses `installed`, `current`, then `stale`. They also assert no subprocess or
Node executable is invoked.

- [ ] **Step 2: Run RED**

Expected: extension installer module is absent.

- [ ] **Step 3: Build once as a developer and track only the runtime payload**

Run `npm run build:prod` in `AbletonMCPServer_Extension`. Add `.gitignore`
exceptions:

```gitignore
!AbletonMCPServer_Extension/dist/
!AbletonMCPServer_Extension/dist/extension.js
```

Do not track source maps, `node_modules`, or npm caches.

- [ ] **Step 4: Force-include the payload in wheels**

```toml
[tool.hatch.build.targets.wheel.force-include]
"contracts.py" = "contracts.py"
"AbletonMCPServer_RemoteScript" = "ableton_mcp_server/_remote_script"
"AbletonMCPServer_Extension/manifest.json" = "ableton_mcp_server/_extension/manifest.json"
"AbletonMCPServer_Extension/dist/extension.js" = "ableton_mcp_server/_extension/dist/extension.js"
```

- [ ] **Step 5: Implement hash-verified source/status/install**

Use constants:

```python
EXTENSION_FOLDER = "ntworm.abletonmcpserver-extension"
EXTENSION_FILES = ("manifest.json", "dist/extension.js")
```

Checkout source is `package.parent / "AbletonMCPServer_Extension"`; wheel source
is `package / "_extension"`. Windows destination defaults to
`%LOCALAPPDATA%\Ableton\Extensions`. Copy only the two approved files, create
parent directories, and verify SHA-256 after copying. Never delete the whole
Extensions root.

- [ ] **Step 6: Run GREEN and clean-wheel inspection**

Run installer tests, build a wheel, inspect its archive for both payload files,
and execute `scripts/verify_clean_install.ps1` with `PATH` temporarily lacking
`node`/`npm`. Expected: installation/import/status succeed.

- [ ] **Step 7: Commit**

Commit subject: `feat: ship prebuilt Ableton Extension payload`.

### Task 7: Add unified idempotent setup and comprehensive doctor

**Files:**
- Create: `ableton_mcp_server/setup.py`
- Create: `tests/test_setup.py`
- Modify: `ableton_mcp_server/cli.py`
- Modify: `ableton_mcp_server/diagnostics.py`
- Modify: `scripts/setup_windows.ps1`
- Modify: `tests/test_cli.py`, `tests/test_diagnostics.py`, `tests/test_packaging.py`

- [ ] **Step 1: Write failing setup/doctor matrix tests**

Cover healthy, missing, stale, version-mismatched, TCP-only, WS-only, and neither
states. Assert default doctor performs no copy/write. Assert `setup` and
`doctor --fix` install only local Remote Script/Extension files and never call
save/quit or a mutating Live command.

- [ ] **Step 2: Run RED**

Expected: CLI lacks unified commands and Extension status.

- [ ] **Step 3: Implement idempotent setup orchestration**

```python
def setup_runtime(
    remote_source: Path,
    remote_root: Path,
    extension_source: Path,
    extension_root: Path,
) -> dict[str, object]:
    remote = install_remote_script(remote_source, remote_root)
    extension = install_extension(extension_source, extension_root)
    return {
        "status": "installed",
        "remote_script": remote,
        "extension": extension,
        "restart_required": True,
    }
```

Second execution must produce the same hashes/destinations and no duplicate
folder. `restart_required` means Live must be restarted if it was already open;
the command does not attempt to close it.

- [ ] **Step 4: Add CLI commands while preserving compatibility aliases**

Public CLI:

```text
ableton-mcp setup [--json]
ableton-mcp install [--json]          # alias of setup
ableton-mcp status [--json]
ableton-mcp doctor [--fix] [--json]
ableton-mcp install-script            # retained compatibility command
ableton-mcp install-status            # retained compatibility command
```

Doctor output contains executable/package versions, source kinds, both artifact
hash statuses, Live/Control Surface probe, TCP status, WS health response,
catalog/tool/resource/prompt counts, and ordered repair actions. Exit `0` only
when runtime-ready; missing optional Node is reported under
`development_ready:false` and does not fail runtime readiness.

- [ ] **Step 5: Make PowerShell bootstrap call the unified installer**

After venv/package install, execute `ableton-mcp setup --json` and then
`ableton-mcp status --json`. Print exact MCP executable and the instruction to
restart Live/select `AbletonMCPServer_RemoteScript`. Do not call npm.

- [ ] **Step 6: Run GREEN and clean-install gate**

Run setup/CLI/diagnostic/packaging tests twice, then run the PowerShell script in
a temporary HOME/LOCALAPPDATA fixture. Expected: idempotent hashes, no Node call,
no Ableton Set mutation.

- [ ] **Step 7: Commit**

Commit subject: `feat: add one-command Ableton MCP setup and doctor`.

### Task 8: Produce certification evidence and first-clone documentation

**Files:**
- Create: `docs/verification/125-tool-certification.json`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/KNOWN_BUGS.md`
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`
- Modify: `ableton_mcp_server/__init__.py`
- Modify: `manifest.json`
- Modify: `AbletonMCPServer_RemoteScript/__init__.py`
- Modify: `AbletonMCPServer_Extension/package.json`
- Modify: `AbletonMCPServer_Extension/manifest.json`
- Rebuild: `AbletonMCPServer_Extension/dist/extension.js`
- Modify: `tests/test_packaging.py`, resource tests

- [ ] **Step 1: Write failing release-document assertions**

Assert README begins with fresh-clone setup, Ableton restart/Control Surface
selection, Extension location, doctor, MCP executable, and first read-only call.
Assert docs say 125 tools, five resources, five prompts, two loopback bridges,
and excluded integrations. Assert packaged certification has 125 unique rows,
zero failed/unclassified, `captured_at_unix_ms` as an integer Unix epoch value,
and the current server/Live/SDK versions.

- [ ] **Step 2: Run RED**

Expected: docs/evidence are missing or stale.

- [ ] **Step 3: Run full automated and guarded Live certification**

Set the release-candidate version to `1.0.0` in Python package metadata, root
manifest, Python `__version__`, Extension package/manifest, and documentation.
Set `REMOTE_SCRIPT_RUNTIME_VERSION = "core-complete-1"`. Extend packaging tests
to require exact agreement, rebuild the tracked production Extension payload,
and reinstall both artifacts. Then run every gate from the master plan. Run all non-destructive Live profiles
against `TESTE_CODEX`. Run destructive Arrangement time tests only after an
explicit disposable confirmation. Run `quit_ableton` last under its manual flag;
after reopening Live, merge its manual result into the report.

Certification timestamp uses `int(time.time() * 1000)` (Unix epoch
milliseconds). Promote the generated report to
`docs/verification/125-tool-certification.json` only if every catalog name has
one allowed status and no `failed` status.

Add the promoted report to the wheel at the path consumed by the capability
resource:

```toml
"docs/verification/125-tool-certification.json" = "ableton_mcp_server/_certification.json"
```

- [ ] **Step 4: Write the concise first-clone path**

README order:

```text
1. requirements: Windows, supported Ableton Live, Python; no Node for use
2. clone and run scripts/setup_windows.ps1
3. restart Live and select AbletonMCPServer_RemoteScript
4. configure the printed ableton-mcp-server.exe in the MCP client
5. run ableton-mcp doctor --json
6. agent calls get_bridge_status, then inspect_live_set
7. development-only Extension build instructions
8. safety, WSL, verification, architecture, license
```

Commit the complete `1.0.0` release-candidate code, generated Extension payload,
documentation, and pre-smoke certification report:

```powershell
git add pyproject.toml ableton_mcp_server/__init__.py manifest.json AbletonMCPServer_RemoteScript/__init__.py AbletonMCPServer_Extension/package.json AbletonMCPServer_Extension/manifest.json AbletonMCPServer_Extension/dist/extension.js README.md docs/ARCHITECTURE.md docs/KNOWN_BUGS.md docs/TOOL_REFERENCE.md docs/verification/125-tool-certification.json CHANGELOG.md tests/test_packaging.py
git commit -m "release: prepare v1.0.0 core-complete candidate"
```

- [ ] **Step 5: Perform the unfamiliar-agent smoke test**

In a fresh temporary clone of the release-candidate commit and a new venv, give
the worker only README plus MCP discovery.
Observable pass criteria: setup reports both installed artifacts, doctor reports
both bridges, resources/prompts list correctly, `get_bridge_status` succeeds,
and `ableton://live/session-summary` returns the disposable Set name without any
mutation. Record commands/results in the certification JSON evidence section.

- [ ] **Step 6: Run final drift/gate checks**

```powershell
$py = ".\.venv-win\Scripts\python.exe"
& $py scripts\generate_tool_reference.py --check
& $py -m pytest -q --tb=line
& $py scripts\coverage_check.py
& $py -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests
& $py -m mypy --strict ableton_mcp_server
powershell -ExecutionPolicy Bypass -File .\scripts\verify_clean_install.ps1
Push-Location AbletonMCPServer_Extension
npm test
npm run build:prod
npm audit --audit-level=high
Pop-Location
git diff --check
git status --short
```

Expected: all commands pass; status shows only the intended documentation and
certification evidence update produced by the fresh-clone smoke.

- [ ] **Step 7: Commit**

```powershell
git add docs/verification/125-tool-certification.json
git commit -m "test: record fresh-clone v1.0.0 certification"
```

Do not push, merge, tag, or publish after this commit. Hand the branch, fresh
verification output, and certification report to the owner for approval.

## Self-Review

Spec coverage: catalog metadata/reference, instructions, five resources, five
prompts, internal WS health, prebuilt no-Node Extension installation, unified
setup/doctor, certification evidence, and first-clone smoke test cover every
Slice 3 requirement.

Execution Consistency Audit evidence:

- PASS Test/implementation trace: each test assertion maps to a concrete metadata field, decorator registration, health response, installer function, CLI result, or documentation/evidence step.
- PASS Per-task command executability: generator exists before `--check`; resources/prompts are registered before listing; clean install uses the payload created in Task 6; final smoke runs after setup/doctor exist.
- PASS File usage audit: packaged docs are loaded by resources, Extension payload by installer/hatch, certification JSON by capability resource/tests, and generated reference by README/release checks.
- PASS Spec lifecycle audit: setup installs and reports restart-required without closing Live; doctor is read-only unless `--fix`; Extension health survives ordinary connect/disconnect through its process-lifetime dispatcher.
- PASS Time source audit: certification uses Unix epoch milliseconds from `time.time() * 1000`; it is never compared to monotonic timeout clocks.
- PASS State scope audit: resource/prompt registration is process-lifetime immutable; setup has no cache; each doctor/certification report is owned by one invocation.
- PASS Environment audit: all advertised bridge URLs are desktop-only `127.0.0.1`; no phone/LAN URL or QR code is produced.
- N/A Browser event audit: no web UI, DOM event, or gesture path is introduced.
- PASS Lint/import audit: Python snippets are 3.10-compatible; FastMCP APIs were inspected in installed 3.4; Extension types/build/tests use vendored SDK and existing tsconfig.
- PASS Non-obvious API audit: FastMCP constructor/decorators/list/read APIs were verified by runtime signatures; SDK health method is project-owned; readiness uses real TCP/WS round trips with bounded timeouts rather than sleeps.
