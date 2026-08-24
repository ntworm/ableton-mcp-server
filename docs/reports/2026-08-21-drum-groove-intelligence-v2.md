# Drum Groove Intelligence V2 documentation report

Date: 2026-08-21

This report records the documentation alignment for the implemented V2 groove
runtime. This documentation change did not modify source, tests, or seed
resources.

## Public contract

The five-tool taxonomy is:

| Tool | Boundary | Purpose |
| --- | --- | --- |
| `groove_search` | offline read | Retrieve cards by normalized taxonomy, text, features, meter, BPM, or projections. |
| `groove_evidence` | offline read | Inspect bounded provenance, facet matches, features, and projection digests. |
| `groove_generate` | local derived write | Create a deterministic/reproducible artifact from one source plus optional references. |
| `groove_compare` | offline read | Compare up to eight cards by facets/features/HVO/grammar with explicit compatibility. |
| `groove_apply` | guarded Live mutation | Preview mapping, then commit once to an explicit empty clip slot. |

The wire envelopes remain V1. The current projection IDs are
`groove.hvo.v2`, `groove.features.v2`, and `groove.grammar.v2`.

## V2 invariants captured

- The seed is portable and does not require the private source library at
  runtime; public cards do not expose local paths, SQL, BLOBs, raw MIDI, or
  note arrays.
- The deterministic core is offline and complete. Neural generation is optional;
  missing or failed providers return the deterministic artifact with a stable
  fallback state.
- Generation accepts one primary source and up to seven distinct references.
  `density`, `syncopation`, `swing`, `microtiming`, `energy`, and `complexity`
  are the six bounded transform axes. Seeded transforms, parent IDs, and the
  immutable bundle determine reproducible output and lineage.
- PPQ, meter, rights, duplicate-parent, mapping, and capability incompatibility
  are explicit refusals. The runtime does not silently drop a reference, coerce
  timing, or elevate rights.
- Apply is target- and slot-explicit. Preview is offline; commit uses one guarded
  batch. `partial` and `unknown` receipts require inspection and must not be
  retried automatically.

## Agent workflow

The skill now teaches: inspect selected track/kit → search by
genre/subgenre/style/section/features → inspect evidence → compare no more than
eight candidates → generate/recombine → preview mapping → commit once →
listen/compare. Kit mapping remains late and separate from groove selection.

The complete workflow and schematic JSON envelopes use fake opaque placeholders
and are maintained in
[the skill reference](../../.agents/skills/drum-groove-intelligence/references/workflow.md).

## Verification

The documentation validation record is maintained with the task handoff. The
required checks are the skill creator quick validator, link/search checks, and
`git diff --check`; Ruff is not applicable to this documentation-only change.
