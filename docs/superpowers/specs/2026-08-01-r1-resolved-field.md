# R1 — `resolved` field on mutation envelopes

**Status:** proposed (Wave-3 of `docs/ABLETON_AGENT_HUB_REFACTORING.md` §Fase 1)
**Date:** 2026-08-01
**Repo:** `ableton-mcp-server` (v0.5.1, branch `feature/v0-5-1-refactor-r1r3`)
**Scope:** success-envelope shape for the four mutation tools named in R1.
**Non-goal:** no new tools, no transport changes, no allowlist changes.

## 1. Problem

Three of the four mutation tools called out by R1 hide the difference between what the
client asked for and what Live actually carried out:

- `set_parameter_value` returns `{target, value, is_quantized}`
  (`AbletonMCPServer_RemoteScript/__init__.py:611-615`). No track or device identity.
- `create_clip` returns `{created, clip_id, length_beats}` (`__init__.py:1270-1274`).
  `clip_id` is the path-id `track:N/clipslot:M/clip`, which `docs/ARCHITECTURE.md`
  §"Path-Id Scheme" declares to be a session-local locator, not a handle.
- `set_tempo` returns `{tempo}` only — observed BPM with no Set anchor.
- `load_device_to_track` returns `{status, track_index, device_name, device_index}`
  (`AbletonMCPServer_Extension/src/index.ts:169-174`); `track.name` is **not** captured.

`LoadDeviceToTrackRequest.resolved_name` (`ableton_mcp_server/models.py:513-516`) is a
Pydantic **property** that returns `self.device_name` after the input validator coerces
`device_uri` → `device_name`. It is **client-side**, not a server echo, and does not
solve R1. `docs/KNOWN_BUGS.md` §"Category G" applies: path-ids are session-local
locators and a success log carrying only `track:0/clipslot:1/clip` does not tell a
human which track that was two minutes later in the session.

## 2. Canonical `resolved` envelope

`resolved` is a **sub-object** at the top level of the success payload (not a flat key
per field), so future fields (cue name, scene name) extend the same object without
breaking struct equality for existing consumers.

```json
{
  "status": "ok",
  "result": {
    "<existing fields preserved verbatim>",
    "resolved": { "kind": "device | clip | tempo", "<per-kind sub-fields>" }
  }
}
```

`kind` is mandatory. `resolved` is **absent** in error envelopes (no `result` to
extend) and **absent** for the 61 tools not in R1, whose JSON is byte-for-byte
unchanged.

### 2.1 Per-tool sub-fields

| Tool | `kind` | Required sub-fields |
|---|---|---|
| `set_parameter_value` | `device` | `track_index`, `device_index`, `parameter_name`, `track_name`, `device_name` |
| `create_clip` | `clip` | `track_index`, `clip_index`, `track_name`, `clip_id` |
| `set_tempo` | `tempo` | `tempo` (observed; may be clamped by 20..999) |
| `load_device_to_track` | `device` | `track_index`, `device_index`, `track_name`, `device_name` |

`load_device_to_track` may carry `device_uri` when the request used the deprecated
alias. `clip_id` is the **post-mutation** path-id (input and observation coincide for
`create_clip`; the rule is "echo what is now in Live"). `track_index` and
`device_index` are resolved Live indexes, never path-ids.

### 2.2 "I don't have this info" signalling

The canonical signal is **key absent**. A tool that fails to resolve a name does not
emit `"track_name": ""`; it omits the key. The exception is `device_name` for
`load_device_to_track`: the Extension guarantees the handle exists, so an empty
`device.name` is reported as `"device_name": ""` — matching `get_device_list`
(`__init__.py:271`). Tests assert `key in result["resolved"]`, not equality with a
non-empty value.

### 2.3 Source of truth per tool

| Tool | Source | Readback needed? |
|---|---|---|
| `set_parameter_value` | `_set_parameter_value_steps` (`__init__.py:565-620`) captures `track` and `device` LOM references. Read `track.name` and `device.name` from the same references. | No extra read. |
| `create_clip` | `cmd_create_clip` (`__init__.py:1260-1274`) captures `track` before `slot.create_clip(length)`. Read `track.name` from the same reference. | No extra read. |
| `set_tempo` | Routes via `_verified_numeric_steps` (`__init__.py:2253-2262`) returning `{tempo: <observed>}`. No identity to add. | No read. |
| `load_device_to_track` | Extension captures `device.name` at `src/index.ts:172` and `track_index` at lines 149-150. `track.name` is **not** captured today and must be added after `await track.insertDevice(...)`. | Yes — one new attribute read on the Extension track. |

Python-shaped handlers gain read-by-reference only; the Extension gains one new
attribute read.

## 3. Compatibility with existing clients

Yes — the key is purely additive inside the existing `result` dict:

1. `set_parameter_value` callers asserting `result["value"] == 0.75` still pass.
2. `create_clip` callers asserting `result["clip_id"] == "track:0/clipslot:1/clip"`
   still pass.
3. `load_device_to_track` callers asserting `result["device_name"] == "Operator"`
   still pass — the Extension already returns the resolved name at the top level.

`tests/test_server_tools.py:208-240` exercises the WS payload and JSON return; it
keeps passing unmodified when `resolved` is added next to the existing keys. No MCP
schema change, no `isError` envelope change, and `client.py:103-128` (`call`) returns
`response.result` directly so the new key travels through transparently.

## 4. Minimal new test cases

`tests/test_resolved_envelope.py` (new):

1. `test_set_parameter_value_resolved_sub_object` — mock `client.call` to attach
   `resolved={kind:"device", ...}`; assert all keys present.
2. `test_create_clip_resolved_sub_object` — attach `resolved={kind:"clip", ...}`.
3. `test_set_tempo_resolved_sub_object` — attach `resolved={kind:"tempo", tempo:128.0}`.
4. `test_load_device_to_track_resolved_sub_object` — mock `client.call_ws` to attach
   `resolved={kind:"device", ...}`.
5. `test_resolved_absent_on_error` — force a `BridgeError` `INVALID_PARAMS`; assert no
   `resolved` key in the error envelope.
6. `test_resolved_omitted_keys_when_name_unavailable` — patch `_safe` to return `""`
   for `track.name`; assert `track_name` is **absent**.
7. `test_legacy_clients_ignore_resolved` — snapshot the existing top-level keys for
   the four tools before and after the change; assert zero diff on every
   non-`resolved` key.

Existing `tests/test_server_tools.py`, `tests/test_tool_registry.py`,
`tests/test_models.py`, `tests/test_vendoring.py` must pass unmodified.

## 5. Acceptance criteria

1. `python -c "from ableton_mcp_server.server import mcp; print(len(mcp.list_tools()))"`
   returns `65` (coupled-change rule from `AGENTS.md`).
2. `python -m pytest -q --tb=line` passes; the seven new cases are green.
3. `python -m ruff check` + `python -m mypy --strict ableton_mcp_server` pass.
4. The four tools keep every existing top-level assertion not referencing `resolved`
   passing byte-for-byte; the 61 tools outside the four return the same JSON as the
   pre-change build.
5. `git diff --stat _contracts.py` is empty after
   `python scripts/vendor_contracts.py`. R1 adds no command, route, or allowlist
   entry; `contracts.py` is untouched.
6. `docs/TOOL_REFERENCE.md` is updated for the four tools.
7. `AGENTS.md` gains one bullet under "Coupled-change rules" noting the `resolved`
   convention applies to the four R1 tools and any future tool that adopts it.

## 6. Risks

1. **Cat-G drift.** `resolved` must reflect the Live object that was actually mutated,
   not the request path-id. Mitigation: per-tool spec says "resolved indexes, not
   path-id"; §4.6 forces omission when the name cannot be read; `clip_id` is allowed
   only for `create_clip` and only as the post-mutation observation.
2. **Extension surface drift.** The Extension handler must add `track.name` after the
   insert. Mitigation: `npm run build` in `AbletonMCPServer_Extension` must succeed
   and `tests/test_extension_loopback.py` must pass.
3. **Mock script drift.** `scripts/mock_remote_script.py` returns legacy envelopes for
   `set_tempo` (line 238), `create_clip` (line 316-318); `set_parameter_value` is not
   mocked. Implementation PR updates the mock to mirror the new shapes.
4. **Tests that pattern-match the whole result.** None exist today (verified against
   `tests/test_server_tools.py`, `tests/test_tool_registry.py`,
   `tests/test_models.py`), but §4.7 adds a regression guard.
5. **MCP boundary mismatch.** If a future change folds `resolved` into a `wrap_result`
   envelope, the format visible to clients drifts. Mitigation: `resolved` lives inside
   the `result` dict only; `_explicit_json_result` (`server.py:87`) is untouched.

## 7. Out of scope

- R2 `dry_run` flag (Wave-3, separate spec).
- R6 `setup_windows.ps1 -DryRun` (Fase 2).
- New `find_device` / `find_clip` tools (Fase 3 / E1).
- Any change to `contracts.py` / `_contracts.py`.
- `resolved` entries for the 61 tools not enumerated in R1. The plan §R1 says
  "3–4 tools"; we cap at exactly four and document that as a deliberate decision.
- Stable Live Object IDs as a contract (E1) — explicitly deferred.

## 8. Implementation plan

Three commits, all in `feature/v0-5-1-refactor-r1r3`, all gated on owner explicit
authorization per `AGENTS.md` §"Safety".

**Commit 1 — spec (this file).** Just the addition of
`docs/superpowers/specs/2026-08-01-r1-resolved-field.md`. No code change.

**Commit 2 — implementation.** `feat(bridge): add resolved envelope to
set_parameter_value, create_clip, set_tempo, load_device_to_track`. Touch list:

- `AbletonMCPServer_RemoteScript/__init__.py` — `cmd_create_clip` (line 1260),
  `_set_parameter_value_steps` (line 565), and the `set_tempo` route (line 2253) so
  each returns the `resolved` sub-object alongside the existing fields.
- `AbletonMCPServer_Extension/src/index.ts` — `load_device_to_track` handler (around
  lines 149-175) gains a `track.name` read after `insertDevice`.
- `scripts/mock_remote_script.py` — `set_tempo` (line 236), `create_clip` (line 296),
  and a new `set_parameter_value` branch return the new envelope.
- `ableton_mcp_server/server.py` — no body change; `_remote` / `_remote_ws`
  (`server.py:108-128`) pass the new key through automatically.
- `docs/TOOL_REFERENCE.md` — update the four tool sections.
- `AGENTS.md` — one bullet under "Coupled-change rules".

**Commit 3 — tests.** `test(bridge): cover resolved envelope across four mutation
tools`. Add `tests/test_resolved_envelope.py` with the seven cases in §4.

**Verification sequence** (per `AGENTS.md`):

```
python -m pytest -q --tb=line
python scripts\coverage_check.py
python -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests
python -m mypy --strict ableton_mcp_server
python scripts/vendor_contracts.py && git diff --stat _contracts.py
python -c "from ableton_mcp_server.server import mcp; print(len(mcp.list_tools()))"
cd AbletonMCPServer_Extension && npm run build
```

The last command must report `65`. `git diff --stat _contracts.py` must be empty.

## 9. Open questions

None blocking. Two judgement calls are explicit and reversible: sub-object over
flat keys (§2) and omission rule for unavailable names (§2.2). Both flip via
one-line changes inside the bridge handlers if a future spec chooses otherwise.
