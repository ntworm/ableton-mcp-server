# Ableton MCP Pre-publication Context Audit Implementation Plan

> Superseded on 2026-08-24 by
> `2026-08-24-repository-consolidation-audit.md` after the owner explicitly kept
> `wip/music-brain` local and authorized a committed main-worktree audit. Retained
> as historical planning evidence; do not execute its older no-commit scope.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align durable guidance with current local `main`, prove the safe offline
repository state, and produce a non-destructive pre-publication decision for local
commits, divergent branches, and orphaned worktree directories.

**Architecture:** Treat current source, tests, manifests, and Git topology as
authoritative. Update only human-owned guidance affected by verified drift, then
finalize deterministic repository context at the reviewed tree. Keep cleanup and
publication as explicit later gates rather than mutating branches, directories, or
remote state during the audit.

**Tech Stack:** Python 3.10+ through `.venv-win`, FastMCP/Pydantic repository,
PowerShell, Git, Ruff, MyPy, pytest, Workflow Main, and repo-context-loader v2.

**Spec:** `../workflow-main/tasks/ableton-mcp-prepublish-audit-20260823/EXECUTION.md`

## Global Constraints

- Authorized target root is `C:\Users\Usuario\repos\ableton-mcp-server` plus the
  selected Workflow Main packet/context needed for the same outcome.
- Do not fetch, push, merge, rebase, tag, release, delete branches/directories,
  install dependencies, control Ableton Live, or run Set-mutating acceptance.
- Preserve the clean target worktree and pre-existing untracked
  `C:\Users\Usuario\repos\workflow-main\Lunacy\` state.
- Do not ingest `.env`, sessions, vendored dependencies, release binaries, or the
  packaged Groove SQLite into model context.
- Keep stable instructions concise and prefer source-derived counts over prose that
  becomes stale.

---

### Task 1: Verify current contracts and define the owned guidance surface

**Files:**
- Inspect: `pyproject.toml`
- Inspect: `ableton_mcp_server/catalog.py`
- Inspect: `ableton_mcp_server/tool_counts.py`
- Inspect: `README.md`
- Inspect: `docs/TOOL_REFERENCE.md`
- Inspect: `.agent-context/*.md`
- Modify later: `AGENTS.md`
- Modify later: `.agent-context/*.md` only where current claims are affected

**Interfaces:**
- Consumes: package metadata, `TOOL_CATALOG`, count helpers, canonical commands,
  current Git topology, and existing curated context.
- Produces: an evidence list of exact stable facts and stale claims that Tasks 2–4
  use without re-reading the repository broadly.

- [ ] **Step 1: Record the pre-write Git boundary**

Run:

```powershell
git status --short --branch
git rev-parse HEAD
git rev-list --left-right --count origin/main...main
```

Expected: clean `main` plus a local-only ahead count; no file mutation.

- [ ] **Step 2: Verify version and public surface from source**

Run:

```powershell
.\.venv-win\Scripts\python.exe -c "from ableton_mcp_server.catalog import TOOL_CATALOG; from ableton_mcp_server.tool_counts import capability_counts; print(len(TOOL_CATALOG)); print(capability_counts())"
rg -n -e '^version\s*=' -e '"version"\s*:' pyproject.toml manifest.json AbletonMCPServer_Extension\package.json AbletonMCPServer_Extension\manifest.json
```

Expected: exact current version/count evidence, with all four release metadata
versions aligned.

- [ ] **Step 3: Locate stale durable claims narrowly**

Run:

```powershell
rg -n "v0\.5\.[0-9]|[0-9]+ public MCP tools|Registers the [0-9]+|asserted count|tool count|feature/music-brain|origin/main|repo-context-loader" AGENTS.md .agent-context README.md docs\TOOL_REFERENCE.md
```

Expected: a bounded list of claims requiring either correction or replacement with
a stable source-of-truth instruction.

### Task 2: Curate and attest current target repository context

**Files:**
- Modify: `AGENTS.md`
- Modify: `.agent-context/architecture.md` only if boundaries changed
- Modify: `.agent-context/conventions.md` only if commands/release rules changed
- Modify: `.agent-context/dependencies.md` only if dependency purpose changed
- Modify: `.agent-context/hot-files.md` only if coupling/entry points changed
- Modify: `.agent-context/risks.md` only if a verified failure mode changed
- Generated/ignored: `.agent-context/generated/*`

**Interfaces:**
- Consumes: Task 1 evidence and current source/tests/docs.
- Produces: concise stable instructions and repo-context-loader status `current`.

- [ ] **Step 1: Patch only verified stale guidance**

Use `apply_patch` to correct version-era text, current entry points, Groove
Intelligence boundaries, canonical verification commands, and branch/publication
warnings. Do not turn `AGENTS.md` into an inventory or changelog.

- [ ] **Step 2: Refresh deterministic evidence after semantic review**

Run:

```powershell
python C:\Users\Usuario\repos\workflow-main\.agents\skills\repo-context-loader\scripts\repo_context.py finalize . --json
python C:\Users\Usuario\repos\workflow-main\.agents\skills\repo-context-loader\scripts\repo_context.py check . --json
```

Expected: final check reports `status: current`; generated artifacts remain ignored.

- [ ] **Step 3: Inspect the owned diff**

Run:

```powershell
git diff --check
git diff -- AGENTS.md .agent-context docs\superpowers\plans\2026-08-23-ableton-mcp-prepublish-audit.md
git status --short --branch
```

Expected: only owned guidance/plan changes are visible.

### Task 3: Run the complete safe offline gate

**Files:**
- Inspect: `scripts/coverage_check.py`
- Inspect: `scripts/integration_check.py`
- No product source edits are authorized by this task.

**Interfaces:**
- Consumes: final target tree from Task 2 and repository-defined commands.
- Produces: fresh pytest, Ruff, MyPy, coverage, structural integration, and status
  evidence for the Workflow Main context and pre-publication decision.

- [ ] **Step 1: Confirm structural checks do not require Live mutation**

Run:

```powershell
rg -n "socket|127\.0\.0\.1|connect|Ableton|subprocess|pytest|ruff|mypy|coverage|main\(" scripts\coverage_check.py scripts\integration_check.py
```

Expected: establish which commands are safe offline; omit and report any command
that would contact or mutate Live.

- [ ] **Step 2: Run the repository test, lint, and type gates**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv-win\Scripts\python.exe -m pytest -q --tb=line -p no:cacheprovider
.\.venv-win\Scripts\python.exe -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests
.\.venv-win\Scripts\python.exe -m mypy --strict ableton_mcp_server
```

Expected: exit 0 for each command; report exact pass/skip/type counts.

- [ ] **Step 3: Run safe coverage and structural integration gates**

Run only the commands proven offline in Step 1:

```powershell
.\.venv-win\Scripts\python.exe scripts\coverage_check.py
.\.venv-win\Scripts\python.exe scripts\integration_check.py
```

Expected: exit 0 with exact reported coverage and integration counts. No Live Set
or bridge state changes.

- [ ] **Step 4: Reconfirm no test artifact changed tracked state**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected: tracked changes remain limited to the owned guidance/plan files.

### Task 4: Classify unpublished history, divergent branches, and orphan directories

**Files:**
- Inspect only: Git refs and `.worktrees/*/.git` marker files
- Create: `docs/reports/2026-08-23-prepublish-audit.md`

**Interfaces:**
- Consumes: local refs only, Task 3 gate evidence, branch ancestry, patch
  equivalence, and orphan marker targets.
- Produces: an exact keep/archive/remove/publish decision table without performing
  any branch, directory, tag, or remote mutation.

- [ ] **Step 1: Record unpublished main history from local refs**

Run:

```powershell
git rev-list --left-right --count origin/main...main
git log --oneline --decorate origin/main..main
git log -1 --format=fuller HEAD
```

Expected: exact locally known ahead/behind counts and commit boundary; explicitly
state that no fetch occurred.

- [ ] **Step 2: Compare divergent branches without merging**

Run:

```powershell
git branch -vv
git for-each-ref refs/heads --sort=-committerdate --format="%(refname:short)%09%(objectname:short)%09%(committerdate:short)%09%(subject)"
git cherry main feature/plugin-preset-tools
git cherry main wip/music-brain
git diff --stat main...feature/plugin-preset-tools
git diff --stat main...wip/music-brain
```

Expected: exact unique/subsumed commit evidence and a non-destructive recommendation
for each branch.

- [ ] **Step 3: Inventory orphan markers and bounded payload metadata**

For each immediate child of `.worktrees`, resolve only its `.git` marker target,
count files/bytes excluding `.git`, and list paths whose relative names do not
exist in current `main`. Do not open media, binaries, databases, dependencies, or
file contents and do not remove anything.

Expected: exact directory/file/byte counts, broken-target proof, and a conservative
archive/remove gate if unique relative paths exist.

- [ ] **Step 4: Write the pre-publication audit report**

Use `apply_patch` to create the report with: local ref boundary, full offline gate,
context status, branch table, orphan table, preserved unknowns, and the smallest
next separately authorized actions. Avoid any claim about current remote state.

### Task 5: Update Workflow Main and produce the final handoff

**Files:**
- Modify: `C:\Users\Usuario\repos\workflow-main\projects\ableton-mcp-server\CONTEXT.md`
- Modify: `C:\Users\Usuario\repos\workflow-main\tasks\ableton-mcp-prepublish-audit-20260823\EXECUTION.md`

**Interfaces:**
- Consumes: final target HEAD/diff, context check, Task 3 gate, and Task 4 report.
- Produces: current selected-project orientation and a resumable evidence-backed
  control-plane handoff.

- [ ] **Step 1: Replace stale project orientation with verified final facts**

Use `apply_patch` to record current HEAD/version/tool surface, exact safe gate,
current branch/worktree classification, prohibited actions, and next decision
gates. Do not copy the full audit report.

- [ ] **Step 2: Complete the execution packet**

Record exact changed files, commands/results, context statuses, preserved unrelated
state, unrun Live/remote gates, remaining risks, and the smallest next action.

- [ ] **Step 3: Verify both repositories and review final diffs**

Run:

```powershell
# in ableton-mcp-server
git diff --check
git status --short --branch
python C:\Users\Usuario\repos\workflow-main\.agents\skills\repo-context-loader\scripts\repo_context.py check . --json

# in workflow-main
python scripts\workflow_tool.py validate --json
git diff --check
git status --short --branch
```

Expected: target context `current`; Workflow Main structurally `valid`; only exact
owned files plus the pre-existing `Lunacy/` entry are present.

- [ ] **Step 4: Create coherent local commits only after identity/diff review**

Before each repository commit, verify effective human `user.name`/`user.email`,
stage exact owned paths, inspect the cached diff/check, and use short English
Conventional Commit subjects. Do not push. If identity or scope is unexpected,
leave exact files uncommitted and report the blocker.
