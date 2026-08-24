# v0.6.0 Release, Pages Recovery, and History Compaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a certified v0.6.0 GitHub Release and current Pages site while replacing `main` with eight verified release milestones.

**Architecture:** Keep the product surface unchanged at 96 tools. Generalize release tooling around repository-derived version identity and an acceptance-report gate, update current documentation content without redesigning the landing, then synthesize a compact history from verified milestone trees. Publish exact refs atomically with leases and monitor CI/Pages using actual remote evidence.

**Tech Stack:** Python 3.10+, pytest, Ruff, Mypy, PowerShell, TypeScript/npm, Git commit-tree/bundle, GitHub CLI/API, GitHub Pages.

---

### Task 1: Lock current release contracts with failing tests

**Files:**
- Modify: `tests/test_documentation_consistency.py`
- Modify: `tests/test_build_release_candidates.py`

- [ ] **Step 1: Add a version-identity and clean-install regression test**

```python
def test_release_identity_and_clean_install_are_catalog_driven() -> None:
    expected = __version__
    assert re.search(rf'^version = "{re.escape(expected)}"$', _text(ROOT / "pyproject.toml"), re.M)
    assert f'"version": "{expected}"' in _text(ROOT / "manifest.json")
    assert f'"version": "{expected}"' in _text(ROOT / "AbletonMCPServer_Extension" / "package.json")
    assert f'"version": "{expected}"' in _text(ROOT / "AbletonMCPServer_Extension" / "manifest.json")
    verifier = _text(ROOT / "scripts" / "verify_clean_install.ps1")
    assert "Expected 65 tools" not in verifier
    assert "len(TOOL_CATALOG)" in verifier
```

- [ ] **Step 2: Add stable-release builder tests**

Add tests that create a temporary project with `version = "9.8.7"`, supply a
real temporary Git commit and a JSON acceptance report, and assert:

```python
summary = build_release(
    root=project,
    output_directory=out,
    source_commit=head,
    stable=True,
    acceptance_report=report,
)
assert summary["version"] == "9.8.7"
assert summary["candidate"] is None
assert summary["live_certified"] is True
assert summary["promotion_ready"] is True
assert summary["artifacts"]["wheel"]["path"].startswith("ableton_mcp_server-9.8.7")
```

Also assert that `stable=True` rejects a missing report, a report with
`release_ready: false`, a tool count other than 96, and a report source commit
different from active HEAD.

- [ ] **Step 3: Run the new tests and verify RED**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_documentation_consistency.py tests\test_build_release_candidates.py -q --tb=short -p no:cacheprovider
```

Expected: failures for the literal 65-tool verifier and the missing stable
builder interface; no collection error.

### Task 2: Generalize release production and clean-install verification

**Files:**
- Modify: `scripts/build_release_candidates.py`
- Modify: `scripts/verify_clean_install.ps1`
- Test: `tests/test_build_release_candidates.py`
- Test: `tests/test_documentation_consistency.py`

- [ ] **Step 1: Read the project version from `pyproject.toml`**

Implement a Python-3.10-compatible parser at the release boundary:

```python
_PROJECT_VERSION_PATTERN = re.compile(r'^version\s*=\s*"([^"]+)"$', re.MULTILINE)

def _project_version(root: Path) -> str:
    match = _PROJECT_VERSION_PATTERN.search((root / "pyproject.toml").read_text(encoding="utf-8"))
    if match is None:
        raise ValueError("pyproject.toml does not declare project.version")
    return match.group(1)
```

Pass `version` explicitly to artifact-name, install-guide, release-note, and
manifest helpers. Remove current-release behavior derived from the stale
`VERSION = "0.5.1"` constant.

- [ ] **Step 2: Gate stable output on certification evidence**

Add:

```python
def _validated_acceptance_report(path: Path, *, source_commit: str, tool_count: int) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    certification = report.get("certification", report)
    if certification.get("release_ready") is not True:
        raise ValueError("stable release requires release_ready=true")
    if report.get("tool_count", certification.get("tool_count")) != tool_count:
        raise ValueError("acceptance report tool count does not match the catalog")
    if report.get("source_commit") not in (None, source_commit):
        raise ValueError("acceptance report source commit does not match HEAD")
    return report
```

Stable manifests set `candidate` to null and both certification flags to true;
candidate mode remains false/false for compatibility. Record the acceptance
report SHA-256 and filename in stable provenance.

- [ ] **Step 3: Make clean-install count catalog-driven**

Replace the inline fixed assertion with:

```python
from ableton_mcp_server.catalog import TOOL_CATALOG
from ableton_mcp_server.server import PUBLIC_TOOL_NAMES
assert len(PUBLIC_TOOL_NAMES) == len(TOOL_CATALOG), (
    f"Catalog/server mismatch: {len(TOOL_CATALOG)} != {len(PUBLIC_TOOL_NAMES)}"
)
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Task 1 command. Expected: all selected tests pass.

- [ ] **Step 5: Commit the tooling outcome**

Stage only the four owned paths and commit:

```text
fix(release): make artifacts version and certification aware
```

### Task 3: Promote the 96-tool surface to v0.6.0

**Files:**
- Modify: `pyproject.toml`
- Modify: `manifest.json`
- Modify: `AbletonMCPServer_Extension/package.json`
- Modify: `AbletonMCPServer_Extension/manifest.json`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `AGENTS.md`
- Modify: `.agent-context/architecture.md`
- Modify: `.agent-context/hot-files.md`
- Modify: `docs/TOOL_REFERENCE.md`
- Modify: `docs/index.html`
- Create: `releases/v0.6.0/RELEASE-NOTES.md`

- [ ] **Step 1: Bump all four identity files to 0.6.0**

Use exact `0.6.0` values. Do not touch package dependencies, tool contracts,
landing CSS, DOM layout, or JavaScript behavior.

- [ ] **Step 2: Promote changelog and current prose**

Keep an empty `## [Unreleased]` section, create
`## [0.6.0] - 2026-08-24`, and move the eight-tool material under it. README
must call v0.6.0 the current release while retaining 65/73/88 only in clearly
historical clauses.

- [ ] **Step 3: Update landing content only**

Set brand/footer to v0.6.0. Preserve all 96 catalog cards, bilingual pairs,
anchors, classes, layout, and interactions.

- [ ] **Step 4: Add stable release notes**

Document 96 tools, route counts, offline music/Groove additions, loopback-only
security, install surfaces, certification command, artifact list, and upgrade
notes. Do not claim CI, Pages, or certification before those gates run.

- [ ] **Step 5: Run consistency checks**

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_documentation_consistency.py tests\test_packaging.py tests\test_catalog.py tests\test_models.py tests\test_tool_registry.py -q --tb=short -p no:cacheprovider
```

Expected: all tests pass and derived counts remain 96.

- [ ] **Step 6: Commit the release identity outcome**

```text
release: prepare v0.6.0
```

### Task 4: Verify the release tree before rewriting history

**Files:**
- No source changes expected

- [ ] **Step 1: Run Python quality gates**

```powershell
.\.venv-win\Scripts\python.exe -m pytest -q --tb=line -p no:cacheprovider
.\.venv-win\Scripts\python.exe scripts\coverage_check.py
.\.venv-win\Scripts\python.exe -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests
.\.venv-win\Scripts\python.exe -m mypy --strict ableton_mcp_server
```

- [ ] **Step 2: Run build/install gates**

```powershell
Push-Location AbletonMCPServer_Extension
npm run build
Pop-Location
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_clean_install.ps1
```

- [ ] **Step 3: Recheck status, identity, diff, and WIP ref**

Require a clean `main`, human author/committer, no forbidden trailers,
`git diff --check`, and `wip/music-brain=9984e2614fb824ec10e8cf77e28173cbe71dfd74`.

### Task 5: Create verified backup and compact eight-milestone history

**Files:**
- Create outside repository: `C:/Users/Usuario/repos/_backups/ableton-mcp-server-pre-v0.6.0-20260824.bundle`
- Create Git ref: `refs/backup/ableton-mcp-pre-v060-20260824`

- [ ] **Step 1: Record exact old refs and create backup**

Record local HEAD, remote main, every local/remote tag object, and WIP SHA.
Create the backup ref, create `git bundle --all`, run `git bundle verify`, and
prove the old HEAD is present with `git bundle list-heads`.

- [ ] **Step 2: Build eight commits with `git commit-tree`**

Use source trees from the seven historical milestones plus the fully verified
release-preparation HEAD. Chain them linearly, preserve milestone dates, and use
the verified `ntworm <103321841+ntworm@users.noreply.github.com>` identity.

- [ ] **Step 3: Recreate annotated version tags**

Point v0.2.1 through v0.6.0 to their compact commits. Preserve the backup ref
and `wip/music-brain`; update only local `main` and exact version tags.

- [ ] **Step 4: Verify tree equivalence and count**

For every milestone run `git diff --exit-code <source> <compact>`. Require
`git rev-list --count main` to equal 8 and the final tree to equal the tested
pre-rewrite HEAD exactly.

### Task 6: Certify the final compact commit and build stable artifacts

**Files:**
- Generated outside tracked source: release output directory and acceptance JSON

- [ ] **Step 1: Repeat the full offline gates on compact HEAD**

Repeat Task 4. Any failure stops publication.

- [ ] **Step 2: Run guarded Live acceptance**

```powershell
.\.venv-win\Scripts\ableton-mcp.exe acceptance --profile baseline --fire-clip --confirm-project-name TESTE_CODEX --track-index 0 --clip-index 3 --audio-track-index 2 --audio-clip-index 0 --json
```

Capture the complete JSON without changing tracked source. Require 96 rows,
zero failures, and `release_ready: true`. Read and classify any failing row
before changing code.

- [ ] **Step 3: Build and inspect stable artifacts**

Run the generalized builder with final HEAD, `--stable`, the acceptance report,
and an external output directory. Verify wheel metadata, ZIP contents, `.ablx`
manifest/entry, SHA256SUMS, provenance source commit, and clean-install smoke.

### Task 7: Publish exact refs, release, and Pages

**Files:**
- GitHub refs and Release v0.6.0

- [ ] **Step 1: Re-read remote refs and account**

Require authenticated owner `ntworm`, remote repository
`ntworm/ableton-mcp-server`, and unchanged expected old refs.

- [ ] **Step 2: Atomic guarded publication**

Push only `main` and v0.2.1 through v0.6.0 in one atomic command. Use explicit
leases for every replaced public ref and require new tags to be absent. Never
push `wip/music-brain`, feature branches, or backup refs.

- [ ] **Step 3: Create GitHub Release v0.6.0**

Use the owner-authenticated GitHub CLI, tracked v0.6.0 notes, and all generated
artifacts. Verify tag, target commit, asset names/hashes, `draft=false`,
`prerelease=false`, owner attribution, and rendered URL.

- [ ] **Step 4: Autopilot CI/Pages loop**

Refresh remote state each pass. Read actual failing logs, fix only task-owned
causes, verify locally, and push one coherent correction. When checks run,
watch them rather than polling rapidly. Completion requires CI success, Pages
deployment success, remote main count 8, and public HTML markers v0.6.0 / 96.

### Task 8: Finalize durable context and handoff

**Files:**
- Modify: `.agent-context/architecture.md` and other affected curated context
- Modify: `C:/Users/Usuario/repos/workflow-main/projects/ableton-mcp-server/CONTEXT.md`
- Modify: `C:/Users/Usuario/repos/workflow-main/tasks/ableton-mcp-release-pages-history-20260824/EXECUTION.md`

- [ ] **Step 1: Finalize repository context**

Run `repo_context.py finalize . --json`, then require `check` status `current`.

- [ ] **Step 2: Record immutable remote evidence**

Record final local/remote SHAs, tags, release URL, asset hashes, CI/Pages URLs,
site markers, backup location/verification, and unchanged WIP SHA.

- [ ] **Step 3: Validate and commit Workflow Main owned paths only**

Preserve unrelated `projects/3d-gaussian-splatting/CONTEXT.md` and `Lunacy/`.
Run `python scripts/workflow_tool.py validate --json` and commit only the two
Ableton packet/context paths.

## Self-Review

Spec coverage: Tasks 1-8 cover versioning, landing content, release tooling,
offline/Live gates, compact history, guarded publication, GitHub Release,
Pages recovery, and durable handoff. No requirement is deferred.

Placeholder scan: no TBD, TODO, “implement later”, or undefined task exists.

Type consistency: `stable`, `acceptance_report`, `source_commit`, and the
manifest keys use one spelling across tests, implementation, CLI, and build.

Execution Consistency Audit evidence:

- PASS Test/implementation trace: Task 1 assertions map directly to Task 2 version parsing, certification validation, manifest flags, and catalog-derived verifier.
- PASS Per-task command executability: every command targets existing CLIs/scripts or functions created earlier in the plan.
- PASS File usage audit: every created release note is consumed by GitHub Release creation; generated artifacts are consumed by verification/upload.
- N/A Spec lifecycle audit: no long-lived application lifecycle or retained mutable state is introduced.
- PASS Time source audit: milestone dates use Git commit timestamps only; no runtime time comparison is added.
- N/A State scope audit: release helpers are stateless and receive paths/flags explicitly.
- PASS Environment audit: Live bridges remain loopback-only; GitHub/Pages are explicit public publication boundaries.
- N/A Browser event audit: landing interactions are unchanged; existing browser smoke and static contract tests cover content/navigation.
- PASS Lint/import audit: Python snippets use existing imports/types and are covered by Ruff and strict Mypy gates.
- PASS Non-obvious API audit: remote publication uses observable GitHub CLI/API reads, exact leases, workflow watches, and HTTP content checks.
