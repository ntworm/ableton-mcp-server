# R4 — Capability matrix via `bridge_status`

> **Status update (2026-08-09):** The original prohibition on a generated
> `docs/api_capability_matrix.md` is superseded by the 75-tool documentation
> update. The shipped generator consumes the canonical wire-facing
> `bridge_status` payload and does not join `TOOL_CATALOG`, `contracts.*`, or
> the public registry independently. The runtime payload remains the source of
> truth; the Markdown file is a tested projection for human readers.

**Status:** proposed (Wave-4 of `docs/ABLETON_AGENT_HUB_REFACTORING.md` §Fase 1)
**Date:** 2026-08-01
**Repo:** `ableton-mcp-server` (v0.5.1, branch `feature/v0-5-1-refactor-r1r3`)
**Scope:** single source of truth for what the server can do, consumed at runtime by
agents and at CI by a regression guard. **No new markdown file is canonical.**
**Non-goal:** no new tools, no allowlist changes, no contract regeneration.

## 1. Problem

Three audiences need a machine-checkable answer to "what can this server do today?":

1. **AI agent discovering capabilities at runtime.** Today it must trial-and-error
   every tool, or rely on the hand-written `docs/TOOL_REFERENCE.md`. Trial mutates
   state; markdown is not enumerable from the wire. The agent has no machine-readable
   view of route, risk, or acceptance mode before invoking.
2. **Human evaluating server coverage.** `TOOL_REFERENCE.md` lists 65 tools and
   `KNOWN_BUGS.md` documents quirks, but no single artefact answers "what is
   supported, experimental, blocked" in matrix form. The §R4 directive to copy the
   remote hub's `docs/api_capability_matrix.md` would create a third hand-written
   file — drift from the catalog becomes a CI hazard.
3. **CI detecting drift.** `tests/test_catalog.py:6-23` covers 65 names, route/risk
   alignment, and the WS set, but does not assert the cross-counts (65 / 55 / 3 / 5
   / 5) that `AGENTS.md` documents, nor route ↔ WS-method overlap, nor read-only
   inclusion in `READ_COMMANDS ∪ ALLOWED_MUTATIONS`.

The local repo already has a strictly better primitive than the upstream's
`api_capability_matrix.md`: `TOOL_CATALOG` in `ableton_mcp_server/catalog.py:121-189`
(single source of truth) + `bridge_status` in `diagnostics.py:103-162` (already on
the wire). R4 enriches `bridge_status` with a derived capability view instead of
creating a third persisted artefact.

## 2. Proposed form

Two artefacts, both additive:

**(a) `bridge_status` gains a `tools` list** — one dict per `ToolSpec`. Each dict has
exactly six fields: `name`, `domain`, `route`, `risk`, `acceptance`, `reversible`
(plain Python `dict[str, Any]`, not Pydantic — consumer is the MCP wire). The list
is derived at call time by iterating `TOOL_CATALOG`. No persisted JSON, no
module-level cache. Adding a tool requires no edits here.

**(b) `tests/test_capability_matrix.py` (new)** — eight pytest cases, §5.

`docs/TOOL_REFERENCE.md` stays as human narrative. The upstream's
`docs/api_capability_matrix.md` is **not reproduced**: any script that emits a third
markdown file is out of scope and would recreate the drift R4 exists to prevent.

## 3. Wire-shape change

`bridge_status` today returns `endpoint`, `runtime`, `server_version`, `tool_count`,
`ws_endpoint`, `extension_host_available`, `ws_methods_registered`, `python_runtime`,
`source_kind`, `source`, `python_executable`, `features`, `status`, `bridge_available`,
`live`, `error`, `hint`. New keys added alongside, none renamed, none removed:

- `tools`: `list[dict]` — one entry per `ToolSpec`, schema per §2(a). Always present,
  populated before the live probe (observable when Live is down).
- `capability_counts`: `dict[str, int]` — `public_tools` (65), `routed_commands` (55),
  `websocket_targets` (3), `read_only_blocked` (5), `feature_flags` (5),
  `live_required_tools` (59 = 65 − 6 `LOCAL_READS`).
- `capability_source`: `dict[str, str]` — provenance per count
  (`"catalog": "ableton_mcp_server.catalog:TOOL_CATALOG"`,
  `"routed_commands": "contracts:READ_COMMANDS|ALLOWED_MUTATIONS"`,
  `"websocket_targets": "contracts:WEBSOCKET_TARGET_COMMANDS"`,
  `"read_only": "contracts:READ_ONLY_COMMANDS"`,
  `"features": "ableton_mcp_server.diagnostics.bridge_status:features"`).

`tool_count` is **kept** (existing consumers may parse it). It is now redundant
with `capability_counts.public_tools`; §5 case 8 enforces agreement. The five
`features` entries are the same hand-curated list at `diagnostics.py:126-132`; R4
does not add or remove any.

## 4. Compatibility

Yes — every new key is additive. `tool_count`, `features`, `ws_methods_registered`,
`bridge_available` consumers continue to work byte-for-byte. `tests/test_diagnostics.py`
asserts on `features`/`ws_methods_registered` shape; both survive.
`tests/test_extension_loopback.py` exercises `bridge_status` against the loopback TCP
probe; new keys are populated before the probe, observable when the probe fails. The
65-entry `tools` list grows the response by ~5 KB — one-shot read at MCP startup, no
hot-path impact. No MCP schema change, no `isError` envelope change, no `contracts.py`
edit (`git diff --stat _contracts.py` must remain empty after
`python scripts/vendor_contracts.py`).

## 5. Minimal new test cases

`tests/test_capability_matrix.py` (new, eight cases):

1. `test_bridge_status_tools_length_is_65` — assert `len(result["tools"]) == 65`.
2. `test_bridge_status_tool_dict_schema` — six §2(a) fields present per entry,
   correct types, `name` unique.
3. `test_capability_counts_match_invariants` — `public_tools == 65`,
   `routed_commands == 55`, `websocket_targets == 3`, `read_only_blocked == 5`,
   `feature_flags == 5`, `live_required_tools == 59`.
4. `test_websocket_targets_match_catalog_route` — names with `route == "websocket"`
   equal `contracts.WEBSOCKET_TARGET_COMMANDS`.
5. `test_routed_commands_cover_reads_and_mutations` —
   `routed_commands == len(READ_COMMANDS) + len(ALLOWED_MUTATIONS) == 55`.
6. `test_read_only_blocked_are_subset_of_total` —
   `READ_ONLY_COMMANDS ⊆ {READ_COMMANDS ∪ ALLOWED_MUTATIONS}`.
7. `test_features_list_is_frozen` — `features` equals the literal at
   `diagnostics.py:126-132`; any drift fails.
8. `test_tool_count_agrees_with_capability_counts` —
   `result["tool_count"] == result["capability_counts"]["public_tools"]`.

Existing `tests/test_server_tools.py`, `tests/test_tool_registry.py`,
`tests/test_models.py`, `tests/test_diagnostics.py`, `tests/test_extension_loopback.py`,
`tests/test_catalog.py`, `tests/test_vendoring.py` must pass unmodified.

## 6. Acceptance criteria

1. `python -c "from ableton_mcp_server.server import mcp; print(len(mcp.list_tools()))"`
   returns `65`.
2. `python -m pytest -q --tb=line` passes; the eight new cases are green.
3. `python -m ruff check` + `python -m mypy --strict ableton_mcp_server` pass.
4. `git diff --stat _contracts.py` is empty after `python scripts/vendor_contracts.py`.
5. `bridge_status(bridge_client)` returns the three new top-level keys alongside
   every key it returned before; existing assertions on old keys pass byte-for-byte.
6. `test_capability_counts_match_invariants` catches a synthetic drift: shrinking
   `READ_COMMANDS` by one must drop the count and fail with a clear message.
7. **No `docs/api_capability_matrix.md` is created or shipped.** A generation script
   that emits a markdown file would re-introduce drift; the spec forbids it.
   Verification: `find docs -name 'api_capability_matrix.md'` prints nothing.
8. `docs/TOOL_REFERENCE.md` gets a one-line cross-reference to `bridge_status` near
   the existing "List of tools" anchor. No section rewrite.

## 7. Risks

1. **Drift between `TOOL_CATALOG` and `bridge_status` output.** A future change
   adding a key computed independently from `TOOL_CATALOG` can diverge silently.
   Mitigation: §3 fixes every key as derived from `TOOL_CATALOG` and `contracts.*`
   at call time, no module-level caches. `test_capability_counts_match_invariants`
   guards the largest source (count arithmetic).
2. **`bridge_status` payload size.** ~5 KB growth per MCP startup. Mitigation:
   plain `dict`s, one `json.dumps` over a flat list. Acceptable. A future
   `?summary=1` flag may drop the list — out of scope for R4.
3. **Re-introduction of `docs/api_capability_matrix.md`.** A future contributor may
   notice the upstream doc and copy it. Mitigation: §6.7 makes "file does not
   exist" an acceptance criterion; `find docs -name 'api_capability_matrix.md'`
   in verification catches any regression.
4. **Schema drift in `ToolSpec`.** Adding a field to `ToolSpec` requires no edits
   to `bridge_status` (built from explicit field access, not `__dict__`).
   Mitigation: §2(a) lists the six fields by name, so additions are deliberate,
   reviewed changes.
5. **Cat-G drift in capability counts.** Wrong count (e.g., 64 instead of 65) is
   silent and breaks cross-tool consumers. Mitigation: §5 cases 3, 6, 8 are three
   independent assertions on the same arithmetic.

## 8. Out of scope

R1 `resolved` envelope (Wave-3, shipped). R2 `dry_run`, R3 SHA-256, R5 limits
summary, R6 `-DryRun` (Fase 2). E1 stable IDs, E2 UDP, E3 M4L, E4 focused clients,
E5 sample index, E6 doctor dry-run (Fase 4 / deferred). Any change to `contracts.py`
/ `_contracts.py`. A `docs/api_capability_matrix.md` regeneration script — if a
future spec wants a regenerated markdown, it must source from `bridge_status` via
the MCP wire, not from a parallel hand-written file. R4 explicitly forecloses this.
New tools, routes, allowlist entries, or features.

## 9. Implementation plan

Two commits in `feature/v0-5-1-refactor-r1r3`, gated on owner explicit
authorization per `AGENTS.md` §"Safety".

**Commit 1 — spec (this file).** Just
`docs/superpowers/specs/2026-08-01-r4-capability-matrix.md`. No code change.

**Commit 2 — implementation + tests.**
`feat(diagnostics): expose capability matrix via bridge_status`. Touch list:

- `ableton_mcp_server/diagnostics.py` — `bridge_status` (lines 103-162) gains the
  three new keys. `tools` is built by iterating `TOOL_CATALOG` from
  `ableton_mcp_server.catalog` (new import). `capability_counts` and
  `capability_source` are small dict literals. No existing key renamed or removed.
- `tests/test_capability_matrix.py` — new module with the eight cases in §5.
- `docs/TOOL_REFERENCE.md` — one-line cross-reference added near the existing
  "List of tools" anchor; no section rewrite.

**Verification sequence** (per `AGENTS.md`):

```
python -m pytest -q --tb=line
python scripts\coverage_check.py
python -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests
python -m mypy --strict ableton_mcp_server
python scripts/vendor_contracts.py && git diff --stat _contracts.py
python -c "from ableton_mcp_server.server import mcp; print(len(mcp.list_tools()))"
find docs -name 'api_capability_matrix.md'   # MUST print nothing
```

Last command must print `65`. `git diff --stat _contracts.py` must be empty.
`find docs -name 'api_capability_matrix.md'` must print nothing (R4 forbids the
file).

## 10. Open questions

None blocking. Two judgement calls are explicit and reversible:

- **List of dicts over Pydantic model.** §2(a) uses plain `dict[str, Any]` because
  the consumer is the MCP wire, not internal Python code. A future revision may
  promote to a Pydantic model if a typed client emerges; the change is mechanical
  and does not affect the wire shape.
- **`capability_counts` as flat dict over named constants.** §3 lists six keys;
  future additions land as one more dict entry, not a breaking restructure. The
  shape is intentional.
