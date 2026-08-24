# Repository Consolidation and Audit Design

**Date:** 2026-08-24

## Objective

Leave local `main` internally consistent, documented, verified, and committed. The
work covers Git classification, the complete public MCP surface, supporting Python
and TypeScript code, canonical documentation, the bilingual landing page, and the
persistent agent context. It does not publish anything or control Ableton Live.

## Current Evidence

- `main` is 64 commits ahead of the locally stored `origin/main` ref and has one
  pre-existing untracked audit plan.
- `feature/plugin-preset-tools` has divergent ancestry, but `git cherry` reports
  every one of its 19 commits as patch-equivalent to work already present on
  `main`. No content merge is required.
- `wip/music-brain` contains one deliberately parked commit. The current `main`
  already has completed implementations of the three music tools from that line.
  The remaining Push 3 declaration is unimplemented, and the parked WebSocket
  retry contradicts the no-replay rule for ambiguous mutations.
- Five ignored `.worktrees/probes-*` directories have broken Git metadata. Their
  only paths absent from `main` are disposable Ruff/Mypy/bytecode caches, not
  unique source files.
- Package metadata is `0.5.6`, the source catalog contains 96 public tools, and
  the landing page still displays older `v0.5.1` and `v0.5.3` labels in two places.
- Repository context is stale and Workflow Main still describes an older branch,
  tool-count, and release state.

## Settled Git Policy

`main` remains the only integration target for this task. Do not merge or modify
`wip/music-brain`; keep it as a local pending branch for later completion. Do not
create a content-free merge for `feature/plugin-preset-tools`, because its changes
are already represented on `main` and such a merge would add history without an
observable result.

Do not delete branches, remove orphan directories, fetch, push, rebase, tag,
release, or rewrite history. The locally stored `origin/main` ref is evidence only
and must not be described as current remote state.

## Review Architecture

### Public surface and contracts

Use `ableton_mcp_server.catalog.TOOL_CATALOG` as the inventory root. Prove that
every catalog entry has the required request model, public registration, routing,
certification/capability representation, documentation entry, and tests required
by its route and risk. Derive counts from source rather than copying fragile prose.

Review all executable Python and TypeScript through repository-wide static and
test gates. Manual inspection concentrates on the boundaries where automated
checks cannot establish intent: mutation replay, TCP/WS routing, Live UI-thread
ownership, validation before writes, path-id lifetime, generated contracts,
subprocess/file access, and catalog/registry synchronization. Fix only defects
supported by current evidence and add a focused regression test for each behavior
change.

### Documentation and landing page

Reconcile `README.md`, `CHANGELOG.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`,
`docs/TOOL_REFERENCE.md`, `docs/KNOWN_BUGS.md`, the capability matrix, and the
landing page with the final source. Historical counts remain labeled as historical;
current counts and versions must agree with manifests and the catalog.

For `docs/index.html`, verify English and Brazilian Portuguese copy, version/tool
labels, tool-card inventory, internal anchors, external links, HTML structure,
JavaScript filtering/language behavior, responsive rendering, and absence of stale
claims. The page remains a static artifact with no new framework or dependency.

### Persistent context and Workflow Main

Update only stale curated claims in `AGENTS.md` and `.agent-context/*.md`, then
finalize and recheck the context map. Exclude ignored orphan worktrees from durable
source evidence so generated freshness reflects the real repository rather than
abandoned probe copies.

Update the existing Workflow Main Ableton project context and execution packet with
the final Git classification, verification evidence, exact changed files, preserved
WIP branch, and remaining external gates. Preserve the unrelated modified
`projects/3d-gaussian-splatting/CONTEXT.md` and untracked `Lunacy/` tree.

## Error and Safety Behavior

- Never retry a mutation after an ambiguous transport failure.
- Never touch the Live Python Object Model outside the Remote Script UI thread.
- Expected bridge failures remain typed results rather than framework crashes.
- No test may contact or mutate a real Live Set unless separately authorized.
- No Push 3 SSH/preferences feature is added in this task.
- No secret, local credential, `.env`, packaged database, vendored dependency, or
  release binary is read into task artifacts.
- If a proposed fix changes a public contract, network boundary, dependency,
  persistence rule, or release identity, stop and return the decision to the owner.

## Verification

The final tree must pass the repository-defined safe offline gates using the
existing Windows virtual environment:

1. full pytest suite without cache artifacts;
2. Ruff over package, Remote Script, scripts, and tests;
3. strict Mypy over `ableton_mcp_server`;
4. coverage and structural integration scripts after confirming they are offline;
5. Extension TypeScript/build gate using the already installed dependencies;
6. focused catalog/model/registry/documentation and landing-page consistency checks;
7. `git diff --check`, context-loader `current`, and clean staged-diff inspection;
8. Workflow Main structural validation and exact preservation of unrelated dirt.

Live connectivity, Set-mutating acceptance, Push hardware behavior, remote
freshness, publication, and CI remain explicit user-run or separately authorized
gates.

## Commit Strategy and Acceptance

Use the repository's verified human identity and short English Conventional Commit
subjects. Commit the approved design first. Commit the audited Ableton source/docs
outcome as one coherent unit unless a discovered product fix is independently
reviewable and reversible. Commit Workflow Main context separately in its own
repository, staging only the selected Ableton packet/context paths.

The task is accepted when the public surface is internally consistent, safe offline
verification is green, current documentation and landing content match source,
persistent context reports `current`, owned work is committed on local `main`, the
parked Music Brain branch is unchanged, and all unrun external gates are named.
