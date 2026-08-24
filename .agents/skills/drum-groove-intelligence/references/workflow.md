# Groove Intelligence V2 workflow

This reference is the detailed operating guide for the `drum-groove-intelligence`
skill. It documents the public MCP boundary, not the private corpus compiler.

## Contract boundary

Groove Intelligence is offline by default. `groove_search`, `groove_evidence`,
and `groove_compare` are deterministic reads; `groove_generate` writes only a
bounded content-addressed derived artifact; `groove_apply` is the only operation
that can cross into Live. The seed is portable: runtime use does not depend on
the source library or its paths, and public cards never expose local paths,
SQL, BLOBs, raw MIDI, or note arrays.

The deterministic generator needs no model. `provider="neural"` is optional and
bounded; a missing, unavailable, or invalid provider returns the equivalent
deterministic artifact with a stable fallback description. Do not treat neural
availability as a prerequisite for search, evidence, comparison, or generation.

Artifact IDs, seed-bundle IDs, query hashes, cursors, projection digests, and
receipts are opaque values. Store and pass them through; do not derive paths,
meaning, or persistence from their spelling. Examples below use visibly fake
placeholders rather than IDs from a seed.

## Efficient agent loop

Use the smallest useful read set and keep comparison bounded:

1. Inspect the selected Live track and kit. Resolve the intended drum track,
   device/rack, and any source track/channel scope before choosing a groove.
2. Call `groove_search` with the narrowest useful combination of free text,
   `facets`, `feature_constraints`, BPM/meter, and required projection IDs.
   Prefer explicit `genre`, `subgenre`, `style`, and `section` facets when known.
3. Call `groove_evidence` on promising results to inspect bounded provenance,
   matched facets, feature contributions, and projection digests. Do not seek
   raw MIDI from this tool.
4. Call `groove_compare` on at most eight candidates, using only compatible
   metrics/projections. Keep the best candidates and preserve their opaque IDs.
5. Call `groove_generate` with one primary source (or an inline search source),
   a deterministic seed, and optional `reference_artifact_ids` (zero to seven).
   Use the six transforms deliberately; the output is a new comparable artifact
   with all parents and lineage recorded.
6. Call `groove_apply(..., mode="preview")` to validate late kit mapping and
   inspect counts/warnings before any Live call.
7. After confirming the target and empty slot, call `groove_apply` once with
   `mode="commit"`; then listen in context and compare the result if needed.

Selection and mapping are separate. A groove can be valid while a kit profile,
source channel, or destination slot is not. Do not bypass a rejected preview by
changing unrelated fields or by retrying a possible mutation.

## Search, evidence, and comparison

`groove_search` accepts a V1 request envelope. Taxonomy facets are bounded and
normalized; the useful public axes are `collection`, `genre`, `subgenre`,
`style`, `section`, and `source_category` where the seed provides them. Common
aliases normalize deterministically (for example, `laid back` to `laid_back`).
Free text searches the same safe labels and card metadata. Feature constraints,
BPM ranges, meter, and required projections narrow the result without opening
Live. `limit` may be larger, but this workflow deliberately reviews no more
than eight candidates. Cursors are opaque and tied to the request, ranker, and
seed bundle; pass them back unchanged.

The current projection IDs are:

- `groove.hvo.v2` — canonical role/grid occupancy, velocity, and offsets;
- `groove.features.v2` — normalized musical features such as meter, PPQ, bars,
  density, dynamics, and timing;
- `groove.grammar.v2` — token and transition structure.

Evidence reports bounded digests and contributions. Comparison is deterministic,
symmetric, bounded to `[0, 1]`, and explicit about `compatible`, `incompatible`,
or `unavailable` projection/meter/PPQ conditions. It compares content, not just
whether a projection exists.

## Generation and multi-parent invariants

The request has one `source` (`artifact_id` or an inline search) and may include
up to seven additional `reference_artifact_ids`, for at most eight distinct
parents. The six transform axes are each bounded to `[-1, 1]`:
`density`, `syncopation`, `swing`, `microtiming`, `energy`, and `complexity`.
`bars` and `seed` are bounded integers; use `provider="deterministic"` unless
the optional neural path is intentionally requested.

The same request, seed, immutable bundle, and parent IDs produce byte-identical
generated output and the same reproducibility key. A generated card remains
searchable/evidenced/comparable and records every parent, relation, ordinal,
transform, provider resolution, and fallback state. Do not treat a generated
artifact as a source path or assume it can be applied: rights still govern
`apply`.

Generation rejects duplicate parents, incompatible PPQ, incompatible meter,
blocked/insufficient rights, and bounded-limit violations. It must not silently
resample, drop a reference, coerce a meter, or elevate rights. Re-run with an
explicitly corrected request only before any Live mutation.

## Preview, mapping, and commit

`groove_apply` requires `artifact_id`, destination `track_index` and
`clip_index`, a `kit_mapping_profile`, and `expected_empty_slot=true`. Use
`gm-drums-v1` for the explicit bounded GM profile (or
`native-compatible` where appropriate); keep kit mapping late and verify the
selected kit against the profile. If an artifact spans multiple
tracks/channels, provide `source_track_index` and `source_channel` together.

`mode="preview"` performs mapping only and returns a
`groove.apply.receipt.v1` with counts and warning/error codes; it does not call
Live. `mode="commit"` requires a fresh bridge capability and performs one
preconditioned `run_batch` for the empty slot. A successful receipt is
`committed`; mapping or precondition failures are `rejected`. `partial` and
`unknown` mean a mutation may have happened: inspect the destination clip and
recover deliberately, never retry automatically. `run_batch` is one grouped undo
step, not a rollback guarantee.

## Current JSON shapes

The wire envelopes are V1 even though the projection and runtime semantics are
V2. These examples are intentionally schematic: every `<>` value is a fake
opaque placeholder and must be replaced by an ID returned by the server. They
contain no local paths, source-library names, or real seed IDs.

### Search request and response

```json
{
  "schema_version": "groove.search.request.v1",
  "facets": {
    "genre": ["funk"],
    "subgenre": ["modern_funk"],
    "style": ["laid_back"],
    "section": ["groove"]
  },
  "feature_constraints": [{"name": "hits_per_bar", "op": "gte", "value": 4}],
  "meter": "4/4",
  "required_projection_ids": ["groove.hvo.v2", "groove.features.v2"],
  "projection_operator": "all",
  "limit": 8
}
```

```json
{
  "schema_version": "groove.search.response.v1",
  "items": [{
    "schema_version": "groove.card.artifact.v1",
    "artifact_id": "<opaque-artifact-id>",
    "kind": "source",
    "summary": {"meter": "4/4", "bars": 4},
    "facets": {"genre": ["funk"], "style": ["laid_back"]},
    "features": {"meter": "4/4", "ppq": 480},
    "projections": {
      "hvo": "groove.hvo.v2",
      "features": "groove.features.v2",
      "grammar": "groove.grammar.v2"
    },
    "rights_level": "full",
    "capabilities": {
      "evidence": {"allowed": true},
      "generate": {"allowed": true},
      "apply": {"allowed": true}
    },
    "provenance": {"corpus_id": "<opaque-corpus-id>"},
    "lineage": {}
  }],
  "total_hint": 1,
  "returned_count": 1,
  "omitted_count": 0,
  "truncated": false,
  "ranking": {
    "ranker_id": "groove-ranker-v2",
    "weights": {
      "text": 0.2,
      "facets": 0.25,
      "features": 0.4,
      "projection_coverage": 0.15
    },
    "projection_coverage_active": true
  },
  "provenance": {"seed_bundle_id": "<opaque-seed-bundle-id>"}
}
```

### Evidence request and response

```json
{
  "schema_version": "groove.evidence.request.v1",
  "artifact_id": "<opaque-artifact-id>",
  "include_projections": ["groove.hvo.v2", "groove.grammar.v2"]
}
```

```json
{
  "schema_version": "groove.evidence.response.v1",
  "artifact": {
    "schema_version": "groove.card.artifact.v1",
    "artifact_id": "<opaque-artifact-id>",
    "kind": "source",
    "summary": {"meter": "4/4", "bars": 4},
    "facets": {"genre": ["funk"]},
    "features": {"meter": "4/4", "ppq": 480},
    "projections": {
      "hvo": "groove.hvo.v2",
      "features": "groove.features.v2",
      "grammar": "groove.grammar.v2"
    },
    "rights_level": "full",
    "capabilities": {
      "evidence": {"allowed": true},
      "generate": {"allowed": true},
      "apply": {"allowed": true}
    },
    "provenance": {"corpus_id": "<opaque-corpus-id>"},
    "lineage": {}
  },
  "card": {
    "schema_version": "groove.card.evidence.v1",
    "artifact_id": "<opaque-artifact-id>",
    "matched_facets": {"genre": ["funk"]},
    "feature_contributions": [{"name": "hits_per_bar", "observed": 8, "weight": 0.0, "distance": 0.0}],
    "projection_digests": {
      "groove.hvo.v2": "<opaque-projection-digest>",
      "groove.grammar.v2": "<opaque-projection-digest>"
    },
    "provenance_digest": "<opaque-provenance-digest>",
    "limitations": [],
    "confidence": 1.0,
    "references": [],
    "truncated": false
  },
  "provenance": {"seed_bundle_id": "<opaque-seed-bundle-id>"}
}
```

### Multi-parent deterministic generation

```json
{
  "schema_version": "groove.generate.request.v1",
  "source": {"artifact_id": "<opaque-primary-parent-id>"},
  "reference_artifact_ids": [
    "<opaque-reference-a>",
    "<opaque-reference-b>"
  ],
  "transforms": {
    "density": 0.2,
    "syncopation": 0.1,
    "swing": 0.35,
    "microtiming": 0.0,
    "energy": 0.15,
    "complexity": 0.05
  },
  "bars": 4,
  "seed": 17,
  "provider": "deterministic"
}
```

```json
{
  "schema_version": "groove.generate.response.v1",
  "artifact": {
    "schema_version": "groove.card.artifact.v1",
    "artifact_id": "<opaque-generated-artifact-id>",
    "kind": "generated",
    "summary": {"meter": "4/4", "bars": 4, "generator": "groove-deterministic-v2"},
    "facets": {"genre": ["funk"]},
    "features": {"meter": "4/4", "ppq": 480},
    "projections": {
      "hvo": "groove.hvo.v2",
      "features": "groove.features.v2",
      "grammar": "groove.grammar.v2"
    },
    "rights_level": "full",
    "capabilities": {
      "evidence": {"allowed": true},
      "generate": {"allowed": true},
      "apply": {"allowed": true}
    },
    "provenance": {"corpus_id": "<opaque-corpus-id>"},
    "lineage": {
      "parent_artifact_ids": ["<opaque-primary-parent-id>", "<opaque-reference-a>", "<opaque-reference-b>"],
      "relations": ["recombination", "recombination", "recombination"],
      "ordinals": [0, 1, 2]
    }
  },
  "card": {
    "schema_version": "groove.card.generation.v1",
    "artifact_id": "<opaque-generated-artifact-id>",
    "parent_artifact_ids": ["<opaque-primary-parent-id>", "<opaque-reference-a>", "<opaque-reference-b>"],
    "generator_id": "groove-deterministic-v2",
    "generator_version": "2",
    "transforms": {"density": 0.2, "syncopation": 0.1, "swing": 0.35, "microtiming": 0.0, "energy": 0.15, "complexity": 0.05},
    "seed": 17,
    "provider_requested": "deterministic",
    "provider_resolved": "deterministic",
    "fallback": false,
    "deterministic": true,
    "reproducibility_key": "<opaque-reproducibility-key>",
    "summary": {},
    "mapping_summary": {},
    "lineage": {},
    "warnings": []
  },
  "provenance": {"seed_bundle_id": "<opaque-seed-bundle-id>"}
}
```

### Compare and apply preview

```json
{
  "schema_version": "groove.compare.request.v1",
  "artifact_ids": ["<opaque-primary-parent-id>", "<opaque-generated-artifact-id>"],
  "metrics": ["facets", "features", "hvo", "grammar"],
  "normalize": true
}
```

```json
{
  "schema_version": "groove.apply.request.v1",
  "artifact_id": "<opaque-generated-artifact-id>",
  "track_index": 3,
  "clip_index": 0,
  "kit_mapping_profile": "gm-drums-v1",
  "source_track_index": 1,
  "source_channel": 9,
  "mode": "preview",
  "expected_empty_slot": true
}
```

```json
{
  "schema_version": "groove.apply.receipt.v1",
  "state": "preview",
  "receipt_id": "<opaque-receipt-id>",
  "artifact_id": "<opaque-generated-artifact-id>",
  "bridge_stage": "none",
  "selected_count": 32,
  "emitted_count": 32,
  "exact_count": 32,
  "fallback_count": 0,
  "unmapped_count": 0,
  "skipped_count": 0
}
```
