# Core-Complete Capability Program Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a truthful, dependency-light, 125-tool Ableton MCP server that installs from a fresh clone and exposes enough guidance for an unfamiliar agent to diagnose and use it safely.

**Architecture:** Execute three release slices in strict order: certify the existing 65 tools, add 60 core tools through the current TCP/WebSocket bridges, then ship turnkey installation and MCP guidance. The capability catalog introduced in Slice 1 is the shared source for registration, routing, safety, documentation, and acceptance evidence.

**Tech Stack:** Python 3.10+, FastMCP 3.x, Pydantic 2, Ableton Python Remote Script LOM, Ableton Extensions SDK 1.0.0 beta, TypeScript 5.9, WebSockets/JSON-RPC, pytest 9, Ruff, mypy strict, npm.

---

## Source of truth

- Approved design: `docs/superpowers/specs/2026-07-13-core-complete-capability-program-design.md`
- Slice 1: `docs/superpowers/plans/2026-07-13-stabilize-and-certify-65-tools.md`
- Slice 2: `docs/superpowers/plans/2026-07-13-expand-to-125-tools.md`
- Slice 3: `docs/superpowers/plans/2026-07-13-turnkey-agent-onboarding.md`

The worker must not execute Slice 2 until every Slice 1 automated gate passes and
the baseline Live acceptance report contains no `failed` or unclassified tool.
The worker must not execute Slice 3 until the registered tool surface is exactly
125 and all Slice 2 automated gates pass.

## Global execution rules

- Work in a dedicated branch/worktree created from commit `ff880a8` or a newer
  commit that contains the approved spec and this plan pack.
- At the start of each task, run `git status --short`. Stop if unrelated changes
  overlap files named by that task.
- Follow RED–GREEN–REFACTOR for every behavior change. Record the expected
  failing assertion before editing production code.
- Edit root `contracts.py`, then run
  `.\.venv-win\Scripts\python.exe scripts\vendor_contracts.py`; never edit the
  vendored Remote Script `_contracts.py` directly.
- Never automatically replay a TCP or WebSocket mutation after connection loss.
- Keep every server bound to `127.0.0.1`; do not add a LAN mode.
- Run Live mutations only against the disposable `TESTE_CODEX` Set (or another
  exact name supplied through `--confirm-project-name`).
- Do not push, merge, tag, publish, or create a release without owner approval.

## Milestone gates

### Gate A — certified baseline

Run from repository root:

```powershell
$py = ".\.venv-win\Scripts\python.exe"
& $py -m pytest -q --tb=line
& $py scripts\coverage_check.py
& $py -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests
& $py -m mypy --strict ableton_mcp_server
Push-Location AbletonMCPServer_Extension
npm run build:prod
npm audit --audit-level=high
Pop-Location
```

Expected: every command exits `0`; the public catalog contains 65 entries; the
baseline certification report has no missing row.

### Gate B — complete core surface

Run the Gate A commands plus:

```powershell
& $py -m pytest tests\test_tool_registry.py tests\test_catalog.py -q
& $py -m ableton_mcp_server.cli acceptance `
  --confirm-project-name TESTE_CODEX `
  --profile read --profile session --profile mixer --profile device --json
```

Expected: the registry, request-model map, and catalog each contain exactly 125
names; guarded profiles finish with verified cleanup.

### Gate C — turnkey release candidate

Run the Gate B commands plus:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_clean_install.ps1
& $py -m ableton_mcp_server.cli doctor --json
& $py scripts\generate_tool_reference.py --check
& $py -m pytest tests\test_resources.py tests\test_prompts.py tests\test_setup.py -q
```

Expected: clean install succeeds without Node.js, both loopback bridges answer,
generated documentation is current, and the MCP lists 125 tools, five resources,
and five prompts.

## Handoff checkpoint template

After each plan task, the worker reports:

```text
Task: <number and title>
RED: <command and expected failure observed>
GREEN: <focused command and pass count>
REGRESSION: <broader command and pass count>
COMMIT: <hash and subject>
RISKS/LEFTOVERS: <none or exact file/tool>
```

## Self-Review

Spec coverage: the three linked slice plans map directly to stabilization,
capability expansion, and turnkey onboarding in the approved design. No program
requirement is assigned to more than one authoritative slice.

Execution Consistency Audit evidence:

- PASS Test/implementation trace: each slice contains its own assertion-to-code steps; this index adds no production behavior.
- PASS Per-task command executability: Gate A uses existing commands; Gates B and C are run only after the slice that creates their CLI/profile/scripts.
- PASS File usage audit: every linked plan is consumed by the stated execution order and every gate command targets a named repository entry point.
- PASS Spec lifecycle audit: connection loss remains non-retrying for mutations and each slice preserves that invariant.
- PASS Time source audit: this index introduces no timestamp fields.
- PASS State scope audit: this index introduces no mutable runtime state.
- PASS Environment audit: all Live bridge endpoints remain desktop-only `127.0.0.1`.
- N/A Browser event audit: the program contains no browser UI or gesture test.
- PASS Lint/import audit: the commands use the repository's Python environment and current Ruff/mypy/npm configurations.
- PASS Non-obvious API audit: SDK-specific operations are assigned to Slice 2, where the vendored declarations and capability fallbacks are cited explicitly.

