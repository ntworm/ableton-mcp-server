# Final Acceptance Certification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the two remaining false-green paths, regenerate and install a provenance-bound v0.5.1-rc1, and fast-forward the verified feature branch into local `main`.

**Architecture:** Treat `save_set` as a strict response state machine and split reversible cleanup from structural track creation. Preserve the existing 65-tool catalog and two-commit release provenance model.

**Tech Stack:** Python 3.11, pytest, Ruff, Mypy strict, Ableton Remote Script Python, TypeScript Extension, npm, PowerShell, Git worktrees.

---

### Task 1: Make `save_set` contract-strict

**Files:**
- Modify: `tests/test_acceptance_runner_integration.py`
- Modify: `tests/_strict_fake.py`
- Modify: `ableton_mcp_server/acceptance.py`

- [ ] **Step 1: Add failing contract tests**

Add focused tests that call `run_live_acceptance(..., profiles=("mutations",))`
and assert:

```python
{"saved": True, "api_available": False, "song_save_available": True}
# -> save_set.status == "failed"

{"saved": False, "api_available": False, "gui_workflow": {}}
# -> save_set.status == "failed"

{"saved": False, "api_available": False,
 "gui_workflow": {"save": ["File -> Save"]}}
# -> save_set.status == "manual_required"
```

Also cover missing `api_available`, malformed workflow entries, valid API save,
and `saved=true` followed by `is_dirty=true`.

- [ ] **Step 2: Verify RED**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest -q `
  tests\test_acceptance_runner_integration.py -k "save_set" --tb=short
```

Expected: the contradictory and empty-workflow cases fail because current code
records them as `live_passed`/`manual_required`.

- [ ] **Step 3: Implement the strict state machine**

Remove `song_save_available` handling from `run_save_set`. Accept only exact
boolean `saved`/`api_available` combinations, validate `gui_workflow["save"]`,
and keep the existing dirty-state readback for the successful API path. Change
the StrictFake default to:

```python
{"saved": True, "api_available": True, "result": None}
```

- [ ] **Step 4: Verify GREEN**

Run the command from Step 2 and require all selected tests to pass.

### Task 2: Restore before structural track creation

**Files:**
- Modify: `tests/test_acceptance_runner_integration.py`
- Modify: `ableton_mcp_server/acceptance.py`

- [ ] **Step 1: Add failing duplicate-name and ordering tests**

Create a StrictFake Set where track 0 and a return track share the same name
but have opposite mute/solo/arm values. Assert the complete original state is
preserved after the runner. Add a timeline assertion proving both track-create
commands happen after the last cleanup/readback command.

- [ ] **Step 2: Verify RED**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest -q `
  tests\test_acceptance_runner_integration.py `
  -k "duplicate_name or structural_creation" --tb=short
```

Expected: current code reports green while leaving the duplicate-named regular
track changed, or shows structural creation before cleanup.

- [ ] **Step 3: Implement phase ordering**

Keep `_run_track_creation` as a local helper, but do not call it inside the
reversible-mutation `try`. Remove `_cur_idx` and the unused artifact callback.
The `finally` block restores original indexes directly. After cleanup:

```python
if cleanup_failures:
    record both create-track rows as failed without calling the bridge
else:
    await _record_call(... create_audio_track ...)
    await _record_call(... create_midi_track ...)
```

Ensure exception paths still classify all 65 tools exactly once.

- [ ] **Step 4: Verify GREEN and adversarial state**

Run the Step 2 tests and the full acceptance integration module. Require the
duplicate-name baseline fields to match exactly and `release_ready` to reflect
the actual row statuses.

### Task 3: Align documentation and persistent context

**Files:**
- Modify: `README.md`
- Modify: `docs/CERTIFICATION.md`
- Modify: `.agent-context/architecture.md`
- Modify: `.agent-context/hot-files.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Correct the acceptance command and policy language**

Include `--audio-track-index 2 --audio-clip-index 0` in the README command.
Document both permitted manual lifecycle rows consistently. Attribute baseline
safety to preflight `is_dirty=false`, not to an unavailable save API.

- [ ] **Step 2: Correct repository metadata**

Replace stale 46-tool claims with the current 65-tool catalog, compute current
remote command counts from `contracts.py`, remove the broken ignored-summary
read-order entry from `AGENTS.md`, and call `source_commit` a full Git commit
object ID rather than SHA-256.

- [ ] **Step 3: Run documentation regressions**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest -q tests\test_packaging.py --tb=short
rg -n "46 public tools|single documented exception|source_commit.*SHA-256" `
  AGENTS.md README.md docs .agent-context
```

Expected: tests pass and the search returns no stale current-state claims.

### Task 4: Run complete offline gates

**Files:** no intended source changes.

- [ ] **Step 1: Windows gates**

Run full pytest, coverage, Ruff, Mypy strict, `vendor_contracts.py`, and
`verify_clean_install.ps1` using `.venv-win`.

- [ ] **Step 2: WSL gates**

Run full pytest, coverage, Ruff, and Mypy strict using `.venv`.

- [ ] **Step 3: Extension gates**

Run `npm ci`, `npm run build:prod`, and `npm audit --audit-level=high`.

- [ ] **Step 4: Source-tree checks**

Require `git diff --check`, 65 public tools, synchronized 0.5.1 versions, and
only intended files in `git status --short`.

### Task 5: Commit source and regenerate candidates

**Files:**
- Modify: `releases/v0.5.1-rc1/*`

- [ ] **Step 1: Commit source**

Commit code, tests, docs, spec, and plan as one auditable implementation commit.

- [ ] **Step 2: Generate from exact source commit**

Pass the full `git rev-parse HEAD` value to
`scripts/build_release_candidates.py` and output to `releases/v0.5.1-rc1`.

- [ ] **Step 3: Verify candidate provenance**

Check artifact hashes/bytes against `manifest.json` and `SHA256SUMS`; confirm
`source_commit` exists and equals the implementation commit. Keep
`live_certified=false` and `promotion_ready=false`.

- [ ] **Step 4: Commit candidates separately**

Require the candidate commit to touch only `releases/v0.5.1-rc1/**` and leave
the feature worktree clean.

### Task 6: Install, integrate, and hand off

**Files:** external Ableton installation plus local `main` worktree.

- [ ] **Step 1: Install with Live closed**

Force-reinstall the candidate wheel into `.venv-cert`, copy/install the exact
`.ablx`, install the Remote Script, and compare installed hashes/content to the
manifest artifacts.

- [ ] **Step 2: Fast-forward local main**

Verify both worktrees are clean, fast-forward `main` to the feature branch, and
run a focused post-merge pytest plus Git checks in the main worktree. Do not
pull, push, tag, publish, or delete the feature worktree/branch.

- [ ] **Step 3: Stop before Live acceptance**

Report installed hashes and ask the user to open Live on `TESTE_CODEX`. The next
agent must run read-only preflight before the single guarded acceptance command.

## Self-Review

Execution Consistency Audit evidence:
- PASS Test/implementation trace: every new assertion maps to the strict save state machine or post-cleanup structural phase.
- PASS Per-task command executability: all commands target files, venvs, CLIs, and scripts already present in the checkout.
- PASS File usage audit: every modified document/source/test is consumed by repository instructions, pytest, packaging, or runtime acceptance.
- PASS Spec lifecycle audit: clean preflight, mutation, cleanup, structural additions, installation, and final Live handoff have explicit state transitions.
- N/A Time source audit: this plan introduces no clocks or timestamps in runtime behavior.
- PASS State scope audit: acceptance artifacts and cleanup failures remain per-run local state; StrictFake state remains per-test instance.
- PASS Environment audit: Windows Live bridges remain loopback-only; WSL is used only for offline gates and Git.
- N/A Browser event audit: no browser or UI event handling is introduced.
- PASS Lint/import audit: all Python changes are gated by Ruff and Mypy strict; Extension changes are not expected but build:prod remains mandatory.
- PASS Non-obvious API audit: `save_set` behavior is derived from the existing Remote Script response contract and observable metadata readback.

