# Release notes — v0.5.2

**Date**: 2026-08-01
**Branch**: `feature/v0-5-1-refactor-r1r3`
**Base**: local `main` at `7e4c8d0`
**Head**: `3622a44` (merge commit into `main`)
**Tag**: to be created as annotated `v0.5.2`, local-only; no push has been performed
**Direction document**: `docs/ABLETON_AGENT_HUB_REFACTORING.md` (403 lines)
**Wave handoff**: `tasks/v0-5-1-refactor-r1r3/HANDOFF.md` (147 lines)

## What ships

v0.5.2 is a comparison-driven refactor release. The direction document
contrasts `ableton-mcp-server` (local, 65 tools) with the public
`8309/ableton-agent-hub` project (v0.1.0-alpha, Max for Live + UDP), then
selects the **R1, R3, R4, R5** items as small, testable, contract-safe
ports. R2 (`dry_run`), R6 (install dry-run), and E1–E6 (architecture
reopens) are explicitly **out of scope** and recorded as such in
`AGENTS.md` and `tasks/v0-5-1-refactor-r1r3/HANDOFF.md` so they are not
silently re-introduced.

Four coordinated changes ship:

- **R1 — `resolved` sub-object on mutation responses**
  `set_parameter_value`, `create_clip`, `set_tempo`, and
  `load_device_to_track` now return a `resolved` field that exposes the
  canonical kind, the location keys, and the observed name keys
  (`track_name`, `device_name`). Names that the LOM returned as empty
  are **omitted** (key absent), never emitted as empty strings. Spec:
  `docs/superpowers/specs/2026-08-01-r1-resolved-field.md` (210 lines).
  Transport shape unchanged for all other tools.

- **R3 — Install verification on Windows**
  `scripts/setup_windows.ps1` now invokes `ableton-mcp install-status
  --json`, prints the SHA-256 of the installed Remote Script
  (`AbletonMCPServer_RemoteScript/__init__.py`), and surfaces the
  algorithm, hash, and path. JSON parse, exit code, and target
  presence are validated **before** the hash is computed, so partial
  installs and bad JSON no longer fail with cryptic PowerShell errors.

- **R4 — Capability matrix via `get_bridge_status`**
  `bridge_status()` now returns a 65-entry `tools` array (each entry
  carries `name`, `domain`, `route`, `risk`, `acceptance`,
  `reversible`) plus `capability_counts` (6 named invariants) and
  `capability_source` (5 pointers to the canonical modules that hold
  each invariant). All values are computed at call time from
  `ableton_mcp_server.catalog.TOOL_CATALOG` and `contracts.*`; nothing
  is cached at module level and adding a tool requires no edits here.
  Spec: `docs/superpowers/specs/2026-08-01-r4-capability-matrix.md`
  (205 lines). The narrative `docs/TOOL_REFERENCE.md` remains the
  hand-curated source of truth for human readers; the matrix is the
  machine-checkable mirror.

- **R5 — Executive summary of known bugs**
  `docs/KNOWN_BUGS.md` opens with a 5-bullet "Don't try these yet"
  summary pointing at categories G (session-local path-ids), H
  (`run_batch` is undo grouping, not rollback), K (WSL loopback is
  NAT, not Windows loopback), F (vendored protocol constants), and I
  (explicit allowlist, not prefix heuristic). A new "## ⚠️ Known
  Bugs" section in `README.md` links to the full document so AI
  agents surface the constraints before relying on track indexes,
  `run_batch`, or a TCP loopback to Live.

A post-wave cold audit surfaced 3 issues that were fixed in
`3c12a94` before tag creation:

- `setup_windows.ps1` no longer crashes with an unhandled JSON parse
  error when `install-status` exits non-zero with a non-JSON payload.
- `setup_windows.ps1` no longer crashes with an unhandled
  `Get-FileHash` error when the Remote Script install target
  directory is missing `__init__.py`.
- `test_resolved_envelope.py::test_resolved_omitted_keys_when_name_unavailable`
  now drives the real `cmd_create_clip` against a `FakeSong` whose
  track name is empty, instead of mocking the client. The canonical
  signal (`track_name` key absent from `resolved`) is asserted
  end-to-end through the Remote Script, and a sanity case confirms
  the key is present when the name is non-empty.

## Safety and compatibility

- All Python LOM access remains on Live's UI-thread queue.
- New `resolved` output is **additive**: it does not change the
  existing error envelope, does not touch `contracts.py`, and does not
  require regenerating `_contracts.py`.
- The transport shape and the JSONL framing are unchanged.
- `run_batch` semantics are unchanged (Category H in
  `docs/KNOWN_BUGS.md` still applies).
- Session path-IDs remain session locators, not stable handles
  (Category G still applies).
- The capability matrix is computed at call time; module-level state
  is not added.

## Known drift (non-blocking, documented)

The R4 spec records `live_required_tools = 59` as the expected
value. The code computes `57` because `scaffold_extension` and
`build_extension` are also classified as `Route.LOCAL` in the
catalog (alongside the four LOCAL_READS and the two other
LOCAL_WRITES that the spec anticipates). This is a counting
discrepancy in the spec, not a bug in the matrix; the spec is the
item to reconcile. No action required for v0.5.2.

## Automated verification

| Gate | Result |
|---|---|
| `python -m pytest -q --tb=line` | 507 passed, 1 skipped (was 280 at v0.5.1; +227 from R1, R4, and R3 build_extension coverage) |
| `python scripts/coverage_check.py` | passed (per AGENTS.md) |
| `python -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests` | All checks passed |
| `python -m mypy --strict ableton_mcp_server` | Success: no issues found in 31 source files |
| `python3 scripts/vendor_contracts.py` | idempotent (no diff in `AbletonMCPServer_RemoteScript/_contracts.py`) |
| public FastMCP count | 65 |
| routed remote commands | 55 (26 reads, 29 mutations permitted, 5 blocked, 3 WS targets) |
| `live_required_tools` | 57 (spec 59; non-blocking drift, see above) |

## Required owner acceptance before tag/push

Automated tests do not prove connectivity to Ableton Live or real
undo behaviour. Before approving the tag and any push, run against
a disposable Live Set on Windows:

1. `ableton-mcp doctor --json` for a real TCP round trip; confirm
   `tools[].length == 65` and `capability_counts.live_required_tools
   == 57` in the response.
2. R3 — `setup_windows.ps1` on a clean install and a re-install;
   confirm the SHA-256 line prints without error and the algorithm
   is `SHA256`.
3. R5 — open `docs/KNOWN_BUGS.md`; confirm the "Don't try these yet"
   bullets render and link to the correct category sections.
4. R1 — `set_tempo(120.0)`; confirm the response carries
   `resolved.kind == "tempo"` and no empty-string name keys.
5. R1 — `create_clip(0, 1, 4.0)` against a track with an empty name
   in a `FakeSong`; confirm `resolved.track_name` is **absent** (not
   `""`).
6. R1 — `set_parameter_value(0, 0, "Device On", True)`; confirm
   `resolved.track_name` and `resolved.device_name` are present and
   non-empty.
7. R1 — `load_device_to_track(0, "Auto Filter")`; confirm the
   response carries `resolved.kind == "device"` with a `device_index`
   key.
8. R4 — `get_bridge_status`; confirm `tools` is a 65-entry array and
   every entry has the 6 documented fields. `capability_source`
   should point at `ableton_mcp_server.catalog:TOOL_CATALOG` and
   `contracts.READ_COMMANDS` (etc.).
9. R4 — add a temporary 66th tool in a feature branch, restart, and
   confirm `tools[].length == 66` without any edit in
   `diagnostics.py` (proves call-time derivation).
10. Audit-fixes — invoke `ableton-mcp build-extension` against a
    broken `npm` setup; confirm a non-zero returncode produces
    `{"status": "error", ...}` and does not raise.

After owner approval: tag `v0.5.2` is already annotated and
local-only. Push of `main`, the `feature/v0-5-1-refactor-r1r3`
branch, and the `v0.5.2` tag each require separate owner
authorization.
