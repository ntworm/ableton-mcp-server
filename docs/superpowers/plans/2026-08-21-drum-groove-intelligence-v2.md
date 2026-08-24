# Drum Groove Intelligence V2 Implementation Plan

> Approved continuation of the original hybrid retrieval/recombination/grammar objective. Execute autonomously on local `main`; no push.

## Task 1: Timing correctness

Files: `projections.py`, `mapping.py`, focused tests.

- Add RED tests for PPQ-invariant grids/microtiming and declared loop length.
- Introduce canonical PPQ conversion and meter-aware features/grammar.
- Use SMF timing length when building an apply mapping plan.
- Run focused tests, Ruff, and mypy.

## Task 2: Source taxonomy

Files: taxonomy/build/corpus/search modules and focused tests.

- Add RED tests for safe relative-path taxonomy and free-text/facet retrieval.
- Add a versioned bounded taxonomy extractor and carry labels through compile/index.
- Measure actual corpus hierarchy and publish genre/subgenre counts.
- Confirm no absolute/private paths enter artifacts, manifest, or SQLite.

## Task 3: Content similarity

Files: comparison/similarity modules and focused tests.

- Add RED tests for identity, symmetry, bounds, and distinct rhythmic content.
- Implement normalized feature, HVO, and grammar distances over stored projections.
- Keep MCP response bounded and deterministic.

## Task 4: Real deterministic generation

Files: MIDI writer, generation contracts/engine/store/index as required, focused tests.

- Add RED tests proving transforms change musical events and are reproducible.
- Add optional reference artifact IDs with bounded validation.
- Implement valid SMF emission, real transforms, compatible recombination, regenerated projections, and lineage.
- Preserve old single-parent requests and optional-neural fallback.

## Task 5: Portable rebuild and agent workflow

Files: resource bundle, skill/docs/tests.

- Locate/reuse the restartable private catalog or rebuild it read-only if unavailable.
- Build twice into a separate explicit directory; validate equal logical digests, limits, taxonomy coverage, privacy, and search quality.
- Replace packaged resources only after validation.
- Update skill/tool reference with the compact retrieve/compare/generate/preview/apply workflow.

## Task 6: Final verification and commits

- Run complete pytest, Ruff, strict mypy, deterministic bundle checks, privacy checks, and `git diff --check`.
- Review the full diff for protocol compatibility and unrelated edits.
- Commit coherent local milestones on `main`; do not push.
- Record exact corpus/taxonomy/capability results in the execution packet and final report.

