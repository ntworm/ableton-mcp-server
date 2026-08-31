# Execution packet: groove-brain-gate0-plan

## Target and authorization

- Project: `ableton-mcp-server`
- Authorized root: `C:\Users\Usuario\repos\ableton-mcp-server`
- Outcome: write an executable, TDD-oriented implementation plan for Groove Brain Gate 0 without changing production code.
- Authorization evidence: after reviewing the consolidated concept, the user authorized continuing with the next steps.

## Repository context

- Authorized repository root: `C:\Users\Usuario\repos\ableton-mcp-server`
- Status: stale and concurrently changed; main is ahead of origin and the worktree contains unrelated tracked/untracked prototype changes.
- Check command/evidence: Workflow Main change bootstrap, `git status --short --branch`, and current `git log` on 2026-08-30.
- Concurrent evidence: commit `ecbf5e2` added a separate Music Brain foundation and rights correction after the Groove Brain architecture commit; preserve it and avoid corpus/training work in Gate 0.
- Curated files to load: current Extension sources, manifest, build/package scripts, vendored SDK/CLI surfaces, Extension-focused tests, packaging tests, and the two current design specifications.
- Decision/limitations: plan only the single-install Extension feasibility gate; do not plan model training, corpus ingestion, broad repository cleanup, or Music Brain composition work.

## Scope

- Included: contextual Extension action, modal local UI, bundled Windows helper probe, authenticated loopback protocol, lifecycle/failure handling, safe Session clip create/write/readback probe, `.ablx` inventory, machine-clean/offline evidence, compatibility matrix, and stop/go result.
- Excluded: production implementation in this turn; model weights; ONNX inference; corpus use; full dashboard; Arrangement writeback; SD3 mapping; MCP/Remote Script product dependency; push/release/publication; unrelated dirty work.
- User decisions already made: one `.ablx` installation, local/offline runtime, direct Ableton integration, web-based control surface, and no hidden separate installer.

## Acceptance criteria

- [x] One plan is saved under `docs/superpowers/plans/` with the required Writing Plans header.
- [x] Every task names exact files, tests, commands, expected failures/passes, code, and commit boundaries.
- [x] Plan begins with Gate 0 and has an explicit stop condition before any model/data implementation.
- [x] Plan accounts for the beta SDK's contextual/modal lifecycle instead of assuming a persistent global panel.
- [x] All ten Execution Consistency Audit checks are recorded in the plan.
- [x] Only this task packet and the plan document are selected for this planning commit; unrelated work remains untouched.

## Plan and routing

- Lead decisions: create one plan for Gate 0; later workstreams receive separate plans only after this gate passes.
- Selected route: `solo` plan authoring; no implementation delegation.
- Durable state: `tasks/groove-brain-gate0-plan/`

## Verification

- Commands/checks: placeholder/conflict scan; spec-to-task coverage matrix; signature/type consistency scan; exact staged diff; documentation anchors; all ten execution-audit statements present.
- Safety checks: no production code edits; no corpus operations; no runtime downloads; no staging of concurrent work.

## Evidence and handoff

- Changed files: `docs/superpowers/plans/2026-08-30-groove-brain-gate0-implementation.md` and this execution packet.
- Results: 10 implementation tasks and 61 checkbox steps, with a hard stop before corpus/model work, a spec coverage matrix, and all ten Execution Consistency Audit checks recorded.
- Verification evidence: structural plan verifier, placeholder/conflict scan, balanced code fences, ordered task numbering, required anchor scan, exact staged `git diff --cached --check`, and staged-path inspection. The repository-wide check still reports whitespace in unrelated pre-existing prototype edits, which remain untouched.
- Remaining risks: Extension SDK/host beta behavior, developer Node 24.13.1 versus the vendored CLI's documented 24.14.1 minimum, native resource execution from `.ablx`, modal lifecycle, safe Live mutation, clean-machine offline operation, and orphan-free shutdown. These are Gate 0 test subjects, not assumed capabilities.
- Next action: owner reviews the plan and authorizes either subagent-driven implementation (recommended) or inline execution. No product implementation begins before that choice.
