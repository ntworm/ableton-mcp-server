# Repository Audit — 2026-08-24

## Scope and exclusions

This audit covers the committed local `main` worktree for the Ableton MCP
Server, its durable repository guidance, the landing page, the documentation
consistency checks, and the selected Workflow Main context/task packet. It does
not change product source, contracts, manifests, release artifacts, branches,
tags, remotes, worktrees, Ableton Live Sets, Push devices, or external services.

The following gates were intentionally not run: Live/bridge round trips,
Push access, remote refresh/fetch, publication, release, and destructive cleanup.
`scripts/integration_check.py` is a real TCP round-trip to the Live Remote Script,
not an offline structural check, so it remains an explicitly unrun Live gate.

## Git classification and preservation

The audited starting point was local `main` at `1e73be8` (`docs: plan
repository consolidation audit`). Local refs reported `origin/main...main` as
`0 66`; no fetch or other remote operation was performed.

- `main`: authorized local documentation/context audit; preserve local commits
  and do not publish them in this task.
- `feature/plugin-preset-tools`: local ref at `10c6807`; `git cherry main
  feature/plugin-preset-tools` returned 18 rows, all `-`, so its patches are
  already represented in `main` and it remains unmerged/unmodified.
- `wip/music-brain`: unchanged at
  `9984e2614fb824ec10e8cf77e28173cbe71dfd74`; it remains local-only and
  unmerged. Its `main...wip/music-brain` diff is five files, 126 insertions,
  and 16 deletions. It is not staged, edited, or merged.

Five ignored `.worktrees` directories retain broken `.git` markers. Metadata
inventory (the marker itself excluded) found no non-cache unique source path:

| directory | marker target | files | bytes | unique non-cache source paths |
|---|---:|---:|---:|---:|
| `probes-composed-quit` | missing | 203 | 2,373,703 | 0 |
| `probes-mutations` | missing | 203 | 2,557,933 | 0 |
| `probes-offline` | missing | 209 | 2,568,399 | 0 |
| `probes-tcp-reads` | missing | 228 | 24,547,239 | 0 |
| `probes-websocket-reads` | missing | 265 | 3,606,809 | 0 |

Cache/bytecode metadata was not treated as source payload, and no orphan was
removed or archived. Workflow Main's pre-existing modified
`projects/3d-gaussian-splatting/CONTEXT.md` and untracked `Lunacy/` were
preserved unchanged.

## Public surface and documentation review

Source-derived facts:

```text
96
ToolCountSnapshotV1(active_total=96, headless_total=13, live_required_total=83, certified_total=18, acceptance_total=96, route_counts={'composed': 5, 'local': 13, 'tcp': 75, 'websocket': 3})
35 38 5 3
```

The landing page now identifies stdio backed by loopback TCP/WebSocket bridges,
shows v0.5.6 in the brand and footer, preserves exactly the catalog's 96 card
names and unique IDs, pairs all `data-en`/`data-pt` attributes, and uses
`artefato` in Portuguese. README distinguishes current 96 from published v0.5.6
88 and names the three deterministic music-generation plus five Groove tools;
it includes the Offline Music Generation inventory row. CHANGELOG has an
undated Unreleased section for the current 96 surface and keeps the published
post-v0.5.3 material under `[0.5.6] - 2026-08-18`, with historical 88/73 counts.
AGENTS and curated context now state 96 total, 13 local/headless, 83 may require
Live, the four version identity files, `.venv-win` commands, no normal
`npm install` during offline verification, and verified WS loopback binding.

## Risk review

The tracked-source audit command searched `except Exception`, subprocess use,
shell/system execution, sleeps, retry paths, bind calls, and TODO/FIXME/
NotImplemented markers. It returned 38 `except Exception` matches, 129
`subprocess` matches, 9 `sleep(` matches, 105 `retry` matches, 3 `bind(`
matches, and 3 marker matches. The matches were classified as follows:

- safe-by-contract: loopback binds in the Remote Script, mock server, and
  loopback regression fixture; bounded Live UI-tick readback retries; client
  reconnect/backoff for reads only; and historical plan/prompt text.
- covered defensive boundary: acceptance probes/cleanup/reporting catch and
  record environment failures; transport and diagnostics translate bridge
  failures; Groove corpus/index/resource boundaries return bounded failure
  states; and neural provider process cleanup is isolated and resource-limited.
- covered security boundary: extension build and neural-provider subprocesses
  use argument lists and `shell=False`; focused tests cover subprocess failure,
  no-shell invocation, resource limits, process protocol, loopback binding, and
  no mutation retry.
- finding: none. No product behavior edit was needed.

Focused safety evidence:

```text
66 passed in 4.45s
```

## Offline verification evidence

The documentation consistency/catalog/model/registry/server/acceptance/loopback
focus passed:

```text
119 passed in 1.62s
```

Final offline gates:

```text
pytest: 885 passed, 2 skipped in 68.10s
ruff: All checks passed!
mypy: Success: no issues found in 66 source files
coverage: TOTAL: 5622/6568 (85.6%); 885 passed, 2 skipped; exit 0
extension: npm run build; tsc --noEmit and tsx build.ts; exit 0
```

The target repository context was finalized and checked as `current` with
`repo_context.py finalize . --json` followed by `check . --json`. Workflow Main
validation returned `{"drift": [], "errors": [], "status": "valid"}` before
its owned packet/context update.

## Landing browser smoke

Using a temporary local server bound to `127.0.0.1:8765` only, the in-app
browser observed: visible v0.5.6, one `All (96)` control, 96 initial cards,
five cards after searching `groove` (`groove_search`, `groove_evidence`,
`groove_generate`, `groove_compare`, `groove_apply`), changed Portuguese
heading/copy after PT-BR toggle, eight internal links with no missing targets,
equal `scrollWidth`/`clientWidth` at 1265 px in both tested language states,
and zero console errors. The temporary server was stopped after the smoke.

## Remaining gates

Live/Push behavior, real bridge TCP/WS round trips, disposable-Set acceptance,
remote freshness, publication, release, branch deletion, and orphan cleanup
remain separately authorized owner gates. No external action was taken.
