# Repository Consolidation and Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Leave local `main` documented, internally consistent, fully verified offline, and committed while preserving the parked Music Brain branch unchanged.

**Architecture:** Treat `TOOL_CATALOG`, request-model registration, the public server registry, manifests, and current tests as executable sources of truth. Add deterministic documentation/landing contracts, correct verified drift, perform a risk-focused source audit, then attest repository context and update Workflow Main without absorbing unrelated dirt.

**Tech Stack:** Python 3.14 in the existing `.venv-win`, FastMCP, Pydantic v2, pytest, Ruff (`E,F,I,UP,B,SIM`, line length 100, target py310), strict Mypy, TypeScript 5.9, Node 24+, esbuild, static HTML/CSS/JavaScript, PowerShell, Git, Workflow Main, and repo-context-loader v2.

**Spec:** `docs/superpowers/specs/2026-08-24-repository-consolidation-audit-design.md`

---

## Execution Boundary and File Map

Execute on the authorized local `main` worktree because the outcome is specifically
to consolidate and attest that worktree. Do not create another `.worktrees` copy;
five abandoned probe directories already exist there and are preserved unchanged.

Owned Ableton paths:

- Create: `tests/test_documentation_consistency.py`
- Create: `docs/reports/2026-08-24-repository-audit.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `AGENTS.md`
- Modify: `docs/index.html`
- Modify only when a verified stale claim exists: `docs/ARCHITECTURE.md`,
  `docs/TOOL_REFERENCE.md`, `docs/api_capability_matrix.md`, `docs/KNOWN_BUGS.md`
- Modify: `.agent-context/architecture.md`
- Modify: `.agent-context/conventions.md`
- Modify only when evidence requires it: `.agent-context/dependencies.md`,
  `.agent-context/hot-files.md`, `.agent-context/risks.md`
- Modify: `docs/superpowers/plans/2026-08-23-ableton-mcp-prepublish-audit.md`
- Preserve and commit this plan: `docs/superpowers/plans/2026-08-24-repository-consolidation-audit.md`

Owned Workflow Main paths:

- Modify: `C:/Users/Usuario/repos/workflow-main/projects/ableton-mcp-server/CONTEXT.md`
- Modify: `C:/Users/Usuario/repos/workflow-main/tasks/ableton-mcp-prepublish-audit-20260823/EXECUTION.md`

Explicit exclusions:

- No edit or merge of `wip/music-brain`.
- No content-free merge of `feature/plugin-preset-tools`.
- No product behavior change without a new failing regression test and a plan
  amendment naming the responsible function.
- No fetch, push, tag, release, branch deletion, orphan-directory removal,
  dependency installation, Live connection, Set mutation, Push 3 access, or history
  rewrite.
- Preserve Workflow Main's unrelated modified
  `projects/3d-gaussian-splatting/CONTEXT.md` and untracked `Lunacy/` tree.

### Task 1: Freeze the Git and runtime baseline

**Files:**

- Inspect: Git refs, manifests, catalog, models, server registry, contracts
- No file modifications

- [ ] **Step 1: Record exact repository ownership and identity**

Run:

```powershell
git status --short --branch
git config --get user.name
git config --get user.email
git rev-parse HEAD
git branch --all --verbose --no-abbrev
git worktree list --porcelain
```

Expected: `main` at or after design commit `3bbd780`, human identity `ntworm
<103321841+ntworm@users.noreply.github.com>`, the older 2026-08-23 plan remains the
only pre-existing untracked Ableton path, and `wip/music-brain` remains at
`9984e26`.

- [ ] **Step 2: Re-prove branch classification without mutation**

Run:

```powershell
git rev-list --left-right --count main...feature/plugin-preset-tools
git cherry main feature/plugin-preset-tools
git rev-list --left-right --count main...wip/music-brain
git cherry main wip/music-brain
```

Expected: every feature-branch patch is prefixed `-`; the WIP branch has one `+`
commit and is neither merged nor changed.

- [ ] **Step 3: Record the executable inventory**

Run:

```powershell
.\.venv-win\Scripts\python.exe -c "from ableton_mcp_server import __version__; from ableton_mcp_server.catalog import TOOL_CATALOG; from ableton_mcp_server.models import TOOL_REQUEST_MODELS; from ableton_mcp_server.server import PUBLIC_TOOL_FUNCTIONS; from ableton_mcp_server.tool_counts import build_tool_count_snapshot; print(__version__); print(len(TOOL_CATALOG), len(TOOL_REQUEST_MODELS), len(PUBLIC_TOOL_FUNCTIONS)); print(build_tool_count_snapshot())"
.\.venv-win\Scripts\python.exe -c "import contracts; print(len(contracts.READ_COMMANDS), len(contracts.ALLOWED_MUTATIONS), len(contracts.UNAVAILABLE_COMMANDS), len(contracts.WEBSOCKET_TARGET_COMMANDS))"
```

Expected: version `0.5.6`; inventory `96 96 96`; snapshot `active_total=96`,
`headless_total=13`, `live_required_total=83`, routes `composed=5`, `local=13`,
`tcp=75`, `websocket=3`; contracts `35 38 5 3`.

### Task 2: Add executable documentation and landing-page contracts

**Files:**

- Create: `tests/test_documentation_consistency.py`

- [ ] **Step 1: Write the failing consistency tests**

Create the file with exactly this implementation:

```python
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from ableton_mcp_server import __version__
from ableton_mcp_server.catalog import TOOL_CATALOG


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_COUNT_PATHS = (
    ROOT / "README.md",
    ROOT / "docs" / "ARCHITECTURE.md",
    ROOT / "docs" / "TOOL_REFERENCE.md",
    ROOT / "docs" / "index.html",
)


class LandingContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.internal_targets: list[str] = []
        self.missing_translation_pairs: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(str(values["id"]))
        href = values.get("href")
        if href and href.startswith("#"):
            self.internal_targets.append(href[1:])
        has_en = "data-en" in values
        has_pt = "data-pt" in values
        if has_en != has_pt:
            self.missing_translation_pairs.append(
                f"{tag}:{values.get('id') or values.get('class') or 'anonymous'}"
            )


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_active_tool_count_markers_match_catalog() -> None:
    active_count = str(len(TOOL_CATALOG))
    for path in ACTIVE_COUNT_PATHS:
        marked_lines = [
            line for line in _text(path).splitlines() if "TOOL_COUNT: active_total" in line
        ]
        assert marked_lines, f"{path} has no active tool-count markers"
        assert all(active_count in line for line in marked_lines), path


def test_landing_version_catalog_and_translations_are_current() -> None:
    html = _text(ROOT / "docs" / "index.html")
    catalog_names = {item.name for item in TOOL_CATALOG}
    card_names = re.findall(r"\{ name: '([^']+)'", html)

    assert f'<span class="brand-tag">v{__version__}</span>' in html
    assert f"<strong>ableton-mcp-server v{__version__}</strong>" in html
    assert len(card_names) == len(catalog_names)
    assert set(card_names) == catalog_names

    parser = LandingContractParser()
    parser.feed(html)
    assert len(parser.ids) == len(set(parser.ids))
    assert set(parser.internal_targets) <= set(parser.ids)
    assert parser.missing_translation_pairs == []


def test_current_guidance_and_changelog_name_the_current_surface() -> None:
    agents = _text(ROOT / "AGENTS.md")
    readme = _text(ROOT / "README.md")
    changelog_head = _text(ROOT / "CHANGELOG.md").split("## [0.5.3]", maxsplit=1)[0]

    assert re.search(r"server\.py.*96 public MCP tools", agents)
    assert "Offline Music Generation" in readme
    assert "## [Unreleased]" in changelog_head
    assert "## [0.5.6] - 2026-08-18" in changelog_head
    assert "96" in changelog_head


def test_every_public_tool_is_present_in_canonical_user_docs() -> None:
    tool_reference = _text(ROOT / "docs" / "TOOL_REFERENCE.md")
    landing = _text(ROOT / "docs" / "index.html")
    for item in TOOL_CATALOG:
        assert f"`{item.name}" in tool_reference, item.name
        assert f"name: '{item.name}'" in landing, item.name
```

- [ ] **Step 2: Run the new tests and prove the stale state**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_documentation_consistency.py -q --tb=short -p no:cacheprovider
```

Expected: FAIL because the landing still contains `v0.5.1`/`v0.5.3`, `AGENTS.md`
still says 75 public tools, the README lacks the `Offline Music Generation`
inventory heading, and the changelog has no released `0.5.6` section/current 96-tool
Unreleased summary.

### Task 3: Correct canonical product documentation and landing copy

**Files:**

- Modify: `docs/index.html`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `AGENTS.md`
- Modify only for verified mismatches: `docs/ARCHITECTURE.md`,
  `docs/TOOL_REFERENCE.md`, `docs/api_capability_matrix.md`, `docs/KNOWN_BUGS.md`
- Modify: `tests/test_acceptance_runner_integration.py`

- [ ] **Step 1: Correct the known landing defects**

Apply these exact semantic replacements in `docs/index.html`:

```html
<meta name="description" content="Local MCP server exposing 96 typed tools over stdio, backed by loopback TCP and WebSocket bridges for Ableton Live 12."> <!-- TOOL_COUNT: active_total -->
...
<span class="brand-tag">v0.5.6</span>
...
<strong>ableton-mcp-server v0.5.6</strong> — Source available under MIT License.
```

Correct the Brazilian Portuguese Groove description from `artifacto` to
`artefato`. Preserve the static single-file implementation, all existing styles,
and the 96-card JavaScript inventory.

- [ ] **Step 2: Reconcile README current-line claims**

Keep the published/current distinction and replace the current-line summary with:

```markdown
The current development surface is 96 tools <!-- TOOL_COUNT: active_total -->.
The published v0.5.6 release contains 88 tools
<!-- HISTORICAL_TOOL_COUNT: 88; baseline=v0.5.6 -->; the current branch adds three
deterministic offline music tools and five Groove Intelligence tools. A FastMCP
server in Python communicates with a MIDI Remote Script on TCP `127.0.0.1:9888`
and an Extension Host bridge over WebSockets on `127.0.0.1:9889`.
```

Add this inventory row immediately before Groove Intelligence:

```markdown
- **Offline Music Generation**: `music_generate_drum_groove`,
  `music_generate_bass`, `music_plan_production` (deterministic note generation
  and production planning; only explicit `apply=True` reaches Live).
```

- [ ] **Step 3: Repair the changelog chronology**

Replace the existing top `Unreleased` header with a concise current section:

```markdown
## [Unreleased]

### Added

- Three deterministic music tools for drum grooves, root-only bass generation,
  and production-section planning.
- Five Groove Intelligence tools for bounded search/evidence, deterministic or
  gated-provider generation, comparison, and guarded apply.
- Packaged curated Groove seed data with restartable corpus/index tooling and
  explicit rights, resource, precondition, and receipt gates.

### Changed

- The current development surface contains 96 public tools, including 13
  headless/local tools and 83 tools that may require Live.

## [0.5.6] - 2026-08-18
```

Retain the existing plugin-preset, live-find, dry-run, and capability-matrix notes
under `0.5.6`, and correct their final counts from the stale `77 tools / 62
commands` wording to the released `88 tools / 73 remote commands` evidence.

- [ ] **Step 4: Replace stale durable guidance in AGENTS.md**

Make these facts explicit and remove the old 75-tool statements:

```markdown
`ableton-mcp-server` has package version 0.5.6 and a current development surface
of 96 public MCP tools. Thirteen tools are headless/local; 83 may require Ableton
Live. The published v0.5.6 release contained 88 tools, while the current branch
adds the three deterministic Music Brain tools and five Groove Intelligence tools.
```

The critical-path row must read:

```markdown
| `ableton_mcp_server/server.py` | Registers the 96 public MCP tools. |
```

Use `.\.venv-win\Scripts\python.exe` in canonical Windows verification commands,
remove `npm install` from normal verification, include all four aligned version
files, and replace the obsolete “unresolved WebSocket bind” warning with the
verified loopback rule covered by `tests/test_extension_loopback.py`.

- [ ] **Step 5: Rename the stale count-bearing test name**

In `tests/test_acceptance_runner_integration.py`, change only:

```python
def test_fake_runner_returns_one_row_per_catalog_tool() -> None:
```

Keep the dynamic assertions unchanged.

- [ ] **Step 6: Inspect all canonical documentation for remaining active drift**

Run:

```powershell
rg -n "75 public|75-function|75 tools|77 public|77-tool|v0\.5\.1|v0\.5\.3|artifacto|unresolved WebSocket" AGENTS.md .agent-context README.md CHANGELOG.md docs
rg -n "TOOL_COUNT: active_total" README.md docs\ARCHITECTURE.md docs\TOOL_REFERENCE.md docs\index.html
```

Expected: matches for `v0.5.3` remain only as explicitly historical release
documentation; no current 75/77 claim, stale landing version, typo, or unresolved
loopback statement remains. If a match is ambiguous rather than demonstrably
historical/current, record it in the audit report and do not rewrite it by guesswork.

- [ ] **Step 7: Run the focused tests to green**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_documentation_consistency.py tests\test_acceptance_runner_integration.py tests\test_catalog.py tests\test_models.py tests\test_tool_registry.py tests\test_server_tools.py -q --tb=short -p no:cacheprovider
```

Expected: all selected tests pass; catalog, request models, and registry remain
96/96/96.

- [ ] **Step 8: Run a real local-browser landing smoke**

Start the static site without opening a visible terminal window:

```powershell
$landingServer = Start-Process -FilePath ".\.venv-win\Scripts\python.exe" -ArgumentList "-m","http.server","8765","--directory","docs","--bind","127.0.0.1" -WindowStyle Hidden -PassThru
```

Use the in-app browser against `http://127.0.0.1:8765/`. Verify the visible brand
is `v0.5.6`, the All filter shows 96, searching for `groove` leaves the five Groove
cards, switching to Portuguese changes the visible navigation/description copy,
the Architecture and Tools anchors scroll to real sections, desktop and narrow
mobile widths do not create horizontal overflow, and the browser console has no
JavaScript error. Then stop only the captured server process:

```powershell
Stop-Process -Id $landingServer.Id
```

Expected: each interaction produces the named observable DOM change and the local
server process exits; no external URL is opened.

### Task 4: Curate and attest persistent repository context

**Files:**

- Modify: `.agent-context/architecture.md`
- Modify: `.agent-context/conventions.md`
- Modify: `.agent-context/hot-files.md`
- Modify only if current evidence changed: `.agent-context/dependencies.md`,
  `.agent-context/risks.md`
- Generated/ignored: `.agent-context/generated/*`

- [ ] **Step 1: Update exact stale context facts**

Record these source-derived invariants:

```text
public tools: 96
headless/local: 13
may require Live: 83
routes: 75 TCP, 3 WebSocket, 5 composed, 13 local
contracts: 35 reads, 38 allowed mutations, 5 unavailable commands
metadata version: 0.5.6 in all four release manifests
```

State that `server.py` owns the 96-function registry, `tool_counts.py` derives
current counts, and five Groove tools plus three deterministic music tools are
post-v0.5.6 current-line work. Use the repo venv in verification commands. Do not
copy the full tool catalog into context.

- [ ] **Step 2: Finalize after semantic review**

Run:

```powershell
git status --short --branch
python C:\Users\Usuario\.agents\skills\repo-context-loader\scripts\repo_context.py finalize . --json
python C:\Users\Usuario\.agents\skills\repo-context-loader\scripts\repo_context.py check . --json
git status --short --branch
```

Expected: final check reports `status: current`; `.worktrees/` remains ignored and
unchanged; generated evidence remains ignored; tracked changes are limited to the
owned surface.

### Task 5: Perform the complete code/risk audit and offline gate

**Files:**

- Inspect: all tracked Python and TypeScript source plus test/config entry points
- Create: `docs/reports/2026-08-24-repository-audit.md`

- [ ] **Step 1: Audit high-risk function boundaries**

Run:

```powershell
rg -n "except Exception|subprocess\.|shell=True|os\.system|asyncio\.sleep|time\.sleep|max_retries|retry|127\.0\.0\.1|0\.0\.0\.0|TODO|FIXME|NotImplemented" ableton_mcp_server AbletonMCPServer_RemoteScript AbletonMCPServer_Extension\src scripts --glob "!**/_contracts.py"
.\.venv-win\Scripts\python.exe -m pytest tests\test_transport_retry.py tests\test_remote_threading.py tests\test_extension_loopback.py tests\test_write_guard.py tests\test_contracts.py tests\test_protocol.py tests\test_groove_preconditions.py tests\test_groove_resource_limits.py tests\test_groove_provider_process.py -q --tb=short -p no:cacheprovider
```

Inspect every search match in its owning function and classify it in the report as
`safe-by-contract`, `covered-defensive-boundary`, or `finding`. A `finding` stops
this task before edits: add a concrete failing regression test and amend this plan
with the exact responsible function, expected behavior, and minimal implementation.
Do not perform opportunistic source cleanup.

- [ ] **Step 2: Run the complete safe offline gate**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv-win\Scripts\python.exe -m pytest -q --tb=line -p no:cacheprovider
.\.venv-win\Scripts\python.exe -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests
.\.venv-win\Scripts\python.exe -m mypy --strict ableton_mcp_server
.\.venv-win\Scripts\python.exe scripts\coverage_check.py
.\.venv-win\Scripts\python.exe scripts\integration_check.py
Push-Location AbletonMCPServer_Extension
npm run build
Pop-Location
```

Expected: pytest remains at least the established baseline of `881 passed, 2
skipped`; Ruff exits 0; Mypy reports no issues in 66 source files; coverage exits 0
at or above its configured threshold; integration reports zero failures; TypeScript
and esbuild exit 0. Generated `dist/` output stays ignored.

- [ ] **Step 3: Write the audit report from terminal evidence**

The report must contain:

```markdown
# Repository Audit — 2026-08-24

## Scope and exclusions
## Git classification
## Public surface evidence
## High-risk boundary review
## Documentation and landing review
## Offline verification
## Preserved work and residual gates
```

Record exact commands/results, the unchanged `wip/music-brain` commit, feature
patch equivalence, the five orphan worktree metadata findings, catalog/model/registry
counts, each reviewed risk category, final test/lint/type/coverage/integration/build
results, and the unrun Live/Push/remote/publication gates. Do not claim a fetch,
hardware test, or remote verification occurred.

### Task 6: Supersede the older plan and commit the Ableton outcome

**Files:**

- Modify: `docs/superpowers/plans/2026-08-23-ableton-mcp-prepublish-audit.md`
- Include all exact owned Ableton files from Tasks 2–5

- [ ] **Step 1: Mark the older untracked plan as preserved historical input**

Insert immediately below its title:

```markdown
> Superseded on 2026-08-24 by
> `2026-08-24-repository-consolidation-audit.md` after the owner explicitly kept
> `wip/music-brain` local and authorized a committed main-worktree audit. Retained
> as historical planning evidence; do not execute its older no-commit scope.
```

- [ ] **Step 2: Inspect the complete Ableton diff and branch preservation**

Run:

```powershell
git diff --check
git status --short --branch
git diff --stat
git diff
git rev-parse wip/music-brain
git cherry main feature/plugin-preset-tools
```

Expected: only owned audit/docs/tests/context paths changed; WIP still resolves to
`9984e2614fb824ec10e8cf77e28173cbe71dfd74`; feature patches remain equivalent;
no product source, release binary, build output, cache, or orphan worktree is staged.

- [ ] **Step 3: Stage exact owned paths and commit**

Run `git add --` with the explicit changed-file list from `git status`, excluding
every unowned/generated path, then:

```powershell
git diff --cached --check
git diff --cached --stat
git diff --cached
git commit -m "docs: reconcile repository guidance and audit"
git show --format=fuller --no-patch HEAD
git log -1 --format=%B
```

Expected: a coherent local commit authored and committed by `ntworm`, with no AI
attribution or trailers. Do not push.

### Task 7: Update Workflow Main and close the handoff

**Files:**

- Modify: `C:/Users/Usuario/repos/workflow-main/projects/ableton-mcp-server/CONTEXT.md`
- Modify: `C:/Users/Usuario/repos/workflow-main/tasks/ableton-mcp-prepublish-audit-20260823/EXECUTION.md`

- [ ] **Step 1: Replace stale selected-project evidence**

Record the final Ableton HEAD, version `0.5.6`, current 96-tool surface and route
counts, exact gate results, context `current`, feature patch equivalence, unchanged
WIP commit, preserved orphan directories, local-only origin boundary, and next
external gates. Remove the stale statement that `main` is aligned with
`origin/main` and the retired `feature/music-brain` description.

- [ ] **Step 2: Complete the existing execution packet**

Update scope, decisions, acceptance checkboxes, changed files, verification evidence,
commit IDs, unrelated state preserved, and final next action. The packet must say
that publication, Live acceptance, branch/orphan deletion, and WIP completion were
not performed.

- [ ] **Step 3: Validate and commit only the two owned Workflow Main files**

Run:

```powershell
python scripts\workflow_tool.py validate --json
git diff --check
git status --short --branch
git diff -- projects/ableton-mcp-server/CONTEXT.md tasks/ableton-mcp-prepublish-audit-20260823/EXECUTION.md
git add -- projects/ableton-mcp-server/CONTEXT.md tasks/ableton-mcp-prepublish-audit-20260823/EXECUTION.md
git diff --cached --check
git diff --cached
git commit -m "docs(ableton-mcp-server): record repository audit"
git show --format=fuller --no-patch HEAD
```

Expected: validation reports structurally valid; the commit contains only those two
paths; `projects/3d-gaussian-splatting/CONTEXT.md` and `Lunacy/` remain unstaged and
unchanged.

- [ ] **Step 4: Run the final cross-repository acceptance sample**

In Ableton:

```powershell
git status --short --branch
python C:\Users\Usuario\.agents\skills\repo-context-loader\scripts\repo_context.py check . --json
.\.venv-win\Scripts\python.exe -m pytest tests\test_documentation_consistency.py tests\test_catalog.py tests\test_transport_retry.py tests\test_extension_loopback.py -q --tb=short -p no:cacheprovider
```

In Workflow Main:

```powershell
python scripts\workflow_tool.py validate --json
git status --short --branch
```

Expected: Ableton has no loose owned work and context is `current`; Workflow Main
contains only the explicitly preserved unrelated dirt; all acceptance tests and
structural validation exit 0.

## Self-Review

Spec coverage: every accepted outcome is mapped to Tasks 1–7; the parked Music
Brain decision is enforced in the boundary, Git checks, report, and handoff.

Placeholder scan: the plan contains no deferred implementation marker; any newly
discovered product defect has a fail-closed amendment protocol rather than an
unspecified repair step.

Type consistency: the plan uses current names from source (`TOOL_CATALOG`,
`TOOL_REQUEST_MODELS`, `PUBLIC_TOOL_FUNCTIONS`, `build_tool_count_snapshot`, and
the current contract sets) and the new test imports only installed/project modules.

Execution Consistency Audit evidence:

- PASS Test/implementation trace: Task 2 assertions map to the exact landing,
  README, changelog, AGENTS, and test-name replacements in Task 3.
- PASS Per-task command executability: every Python/Node/script target exists in
  the current tree; the existing `.venv-win` and Extension `node_modules` were
  observed before planning.
- PASS File usage audit: the new test is discovered by pytest; the static landing
  is the existing GitHub Pages artifact; both reports/plans are linked from the
  final audit/handoff surface.
- N/A Spec lifecycle audit: no runtime connect/resume/disconnect/eviction behavior
  changes; existing transport lifecycle is audit-only.
- N/A Time source audit: no timestamp-producing runtime code is added; the report
  uses a fixed calendar date.
- N/A State scope audit: no mutable runtime state is added.
- PASS Environment audit: every Live bridge URL remains explicit loopback;
  Live/Push/remote publication gates are excluded and named as unrun.
- PASS Browser event audit: Task 3 Step 8 types into the production search input,
  clicks the production language control and anchors, and requires observable card,
  copy, scroll-target, layout, and console results.
- PASS Lint/import audit: the new Python test uses stdlib plus project imports and
  is covered by the repository Ruff configuration and full Ruff gate.
- PASS Non-obvious API audit: no undocumented framework hook is introduced;
  readiness claims rely on observable command exit codes and parsed artifacts.
