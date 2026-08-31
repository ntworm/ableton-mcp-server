# Execution packet: music-brain-foundation-design

## Target

- Project: `ableton-mcp-server`
- Authorized root: `C:\Users\Usuario\repos\ableton-mcp-server`
- Outcome: consolidate research into a rights-safe architecture and staged program for training a serious symbolic-music model, without changing production code or starting training.

## Repository context

- Authorized repository root: `C:\Users\Usuario\repos\ableton-mcp-server`
- Status: stale; generated context predates local documentation and prototype changes.
- Check command/evidence: `repo_context.py check . --json` on 2026-08-30 reported `stale` with 65 changed paths.
- Changed paths when stale: local Remote Script, groove-intelligence, resource, server, journey, scratch, ingestion, task, and documentation paths.
- Curated files loaded: `AGENTS.md`, project bootstrap context, current Music Brain/Groove Brain source and tests, current Git evidence, corpus measurements, hardware evidence, and directly relevant design documents.
- Decision/limitations: use current source and narrow evidence; do not refresh the broad context map during this documentation-only task.

## Scope

- Included: product thesis; program decomposition; data rights; dataset contract; canonical MIDI representation; tokenization; model families; training stages; evaluation; serving; Ableton boundary; prototype triage; stop/go gates; research sources.
- Excluded: production code, dependency changes, model downloads, training runs, corpus mutation, branch merging, destructive cleanup, push, release, publication, and legal certification.
- User decisions already made: build a serious learned MIDI system; research and architecture before coding; broken prototypes may later be discarded; no launch or publication in this session; architecture direction accepted with “continua”.

## Known facts and unknowns

- Verified facts: public v0.6.0 contains deterministic Music Brain tools; the local tree contains unrelated prototype changes; the inspected corpus contains about 183 thousand short MIDI files with exact duplicates; the Toontrack EULA blocks AI training on its product components without written permission; local hardware has a 12 GB RTX 5070, about 64 GB RAM, and an i9-12900KS.
- Unknowns that could change the result: size and musical coverage of a rights-cleared replacement corpus; token count after canonicalization; cloud budget; target inference latency below the author's machine; final commercial distribution rights; viability of a single-file `.ablx` inference runtime.

## Acceptance criteria

- [x] One master specification records the recommended architecture and rejected alternatives.
- [x] Toontrack data and derivatives are explicitly quarantined from ML until written authorization exists.
- [x] Program is decomposed into independently testable workstreams and gates.
- [x] Existing reusable code and disposable prototypes are distinguished.
- [x] Training, evaluation, originality, and Ableton integration contracts are concrete enough to derive implementation plans.
- [x] No production code, model, corpus, branch, or remote state changes.

## Plan and routing

- Lead decisions: consolidate evidence, correct the earlier corpus-rights assumption, write the master specification, self-review, and request user review.
- Worker tasks: prior parallel research covered architecture and data/tokenization/evaluation; no implementation worker is authorized.
- Premium escalation trigger: rights conflict, architecture contradiction, or a plan that would train before provenance and leakage gates pass.
- Durable state: `tasks/music-brain-foundation-design/`
- Legacy transient state: `.agents/` and `Lunacy/runs/` remain preserved and outside this task.

## Verification

- Commands/checks: placeholder scan; contradiction scan; Markdown/reference inspection; exact Git diff; focused documentation/source test evidence where relevant.
- Safety checks: stage exact documentation paths only; preserve all unrelated dirty files; do not ingest or transform additional Toontrack files; do not push.

## Evidence and handoff

- Changed files: this packet, `docs/superpowers/specs/2026-08-30-music-brain-foundation-design.md`, and a rights correction to `docs/superpowers/specs/2026-08-30-groove-brain-extension-design.md`.
- Results: master architecture written; the prior Groove Brain rights assumption corrected; placeholder, contradiction, scope, and whitespace scans passed for the owned documentation.
- Remaining risks: rights-cleared data volume, budget, long-form model quality, and product packaging remain unproven until their gates run.
- Next action: user reviews the written specification; implementation-plan writing begins only after approval.
