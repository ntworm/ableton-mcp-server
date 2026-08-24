# v0.6.0 Release, Pages Recovery, and History Compaction Design

## Outcome

Publish `ableton-mcp-server` v0.6.0 as the first complete GitHub Release for
the current 96-tool surface, serve the existing landing-page interface with
current content, and replace the 208-commit local `main` / 141-commit remote
`main` with a compact eight-commit release-milestone history.

## Verified starting state

- Local `main` is clean at `062b259`, 67 commits ahead of remote
  `ad42ea6`.
- GitHub Pages builds `main:/docs`; the latest build succeeded and deployment
  failed because GitHub's Pages deployment API returned HTTP 503.
- The currently served page is the previous successful deployment and still
  shows v0.5.1 / 75 tools.
- GitHub has no Release objects. The remote has only the historical tags
  `v0.2.1`, `v0.5.1`, and `v0.5.2`.
- The current source exposes 96 tools. `doctor` succeeds against the open Live
  bridge, and the owner has authorized the guarded baseline run against the
  disposable `TESTE_CODEX` Set.
- The release builder is hardcoded to v0.5.1-rc1, while
  `scripts/verify_clean_install.ps1` still asserts 65 tools.

## Release identity and documentation

The next release is v0.6.0 because eight backwards-compatible public tools
were added after the 88-tool v0.5.6 source milestone: three deterministic
offline music tools and five Groove Intelligence tools. Update all four
version identity files, promote the Unreleased changelog material to v0.6.0,
and update current-version prose. Historical counts remain explicitly marked
as historical.

The landing-page layout, styles, navigation, cards, search, and bilingual
interaction remain unchanged. Only version and current-surface content may
change. Automated consistency tests continue to require exactly the catalog's
96 cards, resolved anchors, unique IDs, and paired English/Portuguese copy.

## Release tooling

Generalize `scripts/build_release_candidates.py` so release identity is read
from the target repository rather than a stale constant. Stable output is
allowed only when supplied a real acceptance report whose source commit is the
active HEAD and whose certification says `release_ready: true`. The builder
produces a wheel, Remote Script ZIP, Extension `.ablx`, SHA256SUMS, install
guide, release notes, and a provenance manifest. Tests prove dynamic versioning,
stable certification gating, exact source-commit binding, artifact naming, and
stale-artifact removal.

The clean-install verifier derives the public tool count from the installed
catalog instead of asserting a historical literal.

## Certification and verification

Run the offline suite, coverage floor, Ruff, strict Mypy, Extension build,
clean-install smoke, documentation consistency tests, and the guarded baseline
acceptance against `TESTE_CODEX` with `--fire-clip`. A final release requires
the generated report to cover all 96 tools and return `release_ready: true`.
The acceptance run may mutate the disposable Set in memory; its built-in
restore/cleanup evidence is authoritative, and the Set is not saved as part of
this task.

## Compact history

Before rewriting any ref, create and verify both a local backup ref and a Git
bundle containing the original repository refs. Record the exact old/new ref
table. Construct a new linear `main` with eight human-authored commits whose
trees reproduce these milestones:

1. v0.2.1
2. v0.3.0
3. v0.4.0
4. v0.5.0
5. v0.5.1
6. v0.5.2
7. v0.5.6
8. v0.6.0

Recreate the corresponding annotated tags on those compact commits. Verify
each milestone tree against its source tree and verify the final tree against
the fully tested pre-rewrite HEAD. Preserve `wip/music-brain` exactly at
`9984e261` and never publish it.

Publish only the exact `main` and version tags with one atomic push. Existing
remote refs use explicit `--force-with-lease=<ref>:<old-object>` guards; new
tags must still be absent. No branch deletion or orphan-worktree cleanup is in
scope.

## GitHub publication and recovery loop

Create the v0.6.0 GitHub Release through the directly authenticated `ntworm`
CLI session, attach all generated artifacts plus hashes and provenance, and
verify rendered release metadata. Then monitor CI and the dynamic Pages
workflow. Read actual logs before any correction. Do not weaken workflows to
make checks pass. Completion requires remote `main` and v0.6.0 to match local
refs, CI green, Pages deployment successful, and the public site serving v0.6.0
with 96 tools.

## Safety and rollback

- The original graph remains recoverable from the verified local bundle and
  backup ref.
- The force update is protected by exact leases and atomic publication.
- A failure before the atomic push leaves GitHub unchanged.
- A failure after the push is repaired from the compact line or, if necessary,
  restored from the recorded backup using a new explicit lease.
- No AI authorship, trailers, release credits, or public attribution are added.

## Acceptance criteria

- `main` contains eight release-milestone commits and is clean.
- v0.6.0 versions, docs, landing content, and 96-tool contracts agree.
- Offline gates and real Live acceptance are green.
- Release artifacts are reproducible, hashed, and bound to final HEAD.
- GitHub Release v0.6.0 exists and is not a draft or prerelease.
- CI and Pages are successful; the public landing serves v0.6.0 / 96 tools.
- `wip/music-brain` remains local and unchanged.
