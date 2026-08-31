# Execution packet: groove-brain-extension-concept

## Target and authorization

- Project: ableton-mcp-server
- Authorized root: `C:\Users\Usuario\repos\ableton-mcp-server`
- Outcome: consolidate the Groove Brain product concept into one canonical design specification, obtain an independent critical review, and correct material inconsistencies without changing production code.
- Authorization evidence: the user explicitly requested one file describing the full concept and one spawned subagent to critique it.

## Repository context

- Authorized repository root: `C:\Users\Usuario\repos\ableton-mcp-server`
- Status: stale because the repository already contains unrelated tracked and untracked changes.
- Check command/evidence: Workflow Main bootstrap plus `git status --short --branch` on 2026-08-30.
- Changed paths when stale: existing Remote Script, groove-intelligence, resource, server, journey, scratch, and ingestion changes are outside this task and must be preserved.
- Curated files loaded: project guidance, Extension manifest/source/package metadata, bundled Extension SDK types and CLI documentation, existing groove-intelligence design documents, repository context maps, and current research evidence.
- Decision/limitations: use direct current evidence; do not refresh or rewrite broad repository context during this documentation-only task.

## Scope

- Included: one canonical product/architecture/training design; single-install `.ablx` packaging; fully local runtime; Ableton context and MIDI writeback; Drum Rack and Superior Drummer mapping; corpus preparation; retrieval and neural generation; user flows; safety; evaluation; risks; staged gates; read-only adversarial critique; corrections to the design.
- Excluded: production code, dependencies, model training, MIDI corpus mutation, cleanup of unrelated work, release, publishing, destructive Git operations, and claims of legal certification.
- User decisions already made: rhythm/drums only; fully local/offline; Ableton Extension as product shell; one `.ablx` installation; persistent web interface; direct Ableton integration; owned corpus of roughly 183,000 MIDI files; selected Live MIDI clip may be used as reference; prototypes may be replaced later if they do not support the final design.

## Known facts and unknowns

- Verified facts: the current Extension can run a process-lifetime loopback service; the SDK exposes MIDI clip notes, Live context, local UI, storage, and packaging includes; the corpus exists locally; existing research demonstrates local groove models, retrieval, infilling, and Ableton-hosted web interfaces.
- Unknowns that could change the result: whether the beta Extension host permits reliable execution of a bundled native inference helper across install/update paths; final `.ablx` size limits; external-browser launch behavior; exact Arrangement write semantics; cross-platform signing; and performance of the chosen model on the supported hardware range.

## Acceptance criteria

- [x] One canonical specification records the coherent product, UX, runtime, data, model, packaging, safety, verification, and delivery-gate decisions.
- [x] The specification makes `.ablx` the only required product installation and treats the current MCP/Remote Script path as non-core.
- [x] The specification clearly distinguishes verified SDK capability from packaging assumptions that require a spike.
- [x] A fresh read-only subagent critiqued the specification with line-specific, severity-ranked findings.
- [x] Material valid findings were incorporated as corrections, explicit limits, or binary gates.
- [x] Final owned Git diff contains only task-owned documentation paths; unrelated work remains untouched.

## Plan and routing

- Lead decisions: author and self-review the specification, then request a fresh independent audit and apply only evidence-backed corrections.
- Selected Sol Advisor route: `audit`
- Sonnet/worker tasks: one read-only final design critique; no implementation ownership.
- Premium escalation trigger: contradictions affecting product feasibility, `.ablx` single-install viability, data/model validity, Ableton safety, or offline security.
- Durable state: this task bundle under `tasks/groove-brain-extension-concept/`
- Legacy migration input: `Lunacy/runs/` is read-only

## Verification

- Commands/checks: inspect specification anchors and links; search for placeholders and contradictions; inspect exact Git diff/status; run repository documentation checks if available.
- Safety checks: no production code edits; no corpus reads or writes beyond already-authorized metadata inspection; no staging of unrelated paths; no network runtime dependency in the product design.

## Evidence and handoff

- Changed files: `docs/superpowers/specs/2026-08-30-groove-brain-extension-design.md` and this execution packet.
- Results: a fresh read-only reviewer returned `fix-first`; all twelve severity-ranked findings were incorporated into the revised design, including contextual-modal lifecycle, single-install Gate 0, safe writeback matrix, helper isolation, conservative mappings, lossless MIDI envelope, lineage-aware splits, challenger model selection, package budgets, compatibility contracts, reproducibility limits, and measurable promotion gates.
- Remaining risks: the concept is conditionally coherent, but `.ablx` resource discovery/helper execution and Extension lifecycle remain unproven until Gate 0; SDK is beta; SD3 profiles and lineage metadata still require audit.
- Next action: the user reviews the canonical specification and explicitly approves, rejects, or changes the design before any implementation plan or code work begins.
