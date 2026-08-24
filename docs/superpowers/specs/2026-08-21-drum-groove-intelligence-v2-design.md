# Drum Groove Intelligence V2 — Completion Design

## Goal

Complete the originally approved hybrid drum-groove system. The runtime must remain portable, offline, deterministic without a model, independent of the private source folder, and efficient for an MCP agent. An optional neural provider may refine results but cannot be required.

## Current gap

The existing system successfully inventories MIDI, packages 2,048 source artifacts, indexes facets/features/projections, exposes five MCP operations, and applies a selected artifact to Ableton. It does not yet encode the central musical intelligence: its grid assumes PPQ 480, source taxonomy is discarded, HVO/grammar comparison does not compare content, and deterministic generation copies the parent MIDI unchanged.

## Design

### 1. Canonical musical representation

- Quantize positions on a sixteenth-note grid computed from each file's PPQ.
- Store offsets and duration bins in canonical PPQ-480 ticks so projections are comparable across files.
- Derive meter, beats, bars, roles, dynamics, and microtiming from parsed SMF timing rather than fixed 4/4 assumptions.
- Expand GM drum roles enough to distinguish hats, cymbals, toms, auxiliary snare articulations, and percussion.
- Preserve declared SMF length as the clip loop length, including intentional silence after the final note.

### 2. Portable taxonomy

- Derive bounded, normalized labels from relative directory/file components during authorized build time.
- Store only safe labels and hierarchy—never absolute private paths.
- Expose collection, genre, subgenre, style, and section facets where supported by the source hierarchy, with an explicit taxonomy version and deterministic alias normalization.
- Preserve unmatched path components as bounded source-category facets instead of inventing genres.
- Make labels searchable through both facet filters and free text.

### 3. Musical similarity

- HVO distance compares occupied role/grid cells, normalized velocities, and canonical offsets.
- Grammar distance compares token/transition distributions, not projection availability.
- Feature distances are normalized by musical units instead of raw absolute subtraction.
- Comparison remains symmetric, bounded to `[0,1]`, deterministic, and small enough for MCP cards.

### 4. Hybrid deterministic generation

- A generation request may select one primary source and up to seven additional reference artifacts.
- Apply real seeded transforms to note events: density, syncopation, swing, microtiming, energy, and complexity.
- Recombine compatible bar/role material from references using deterministic bar and role selection.
- Emit a new valid SMF payload, rebuild projections/summary, record all parents and transformation lineage, and guarantee identical output for identical request/seed/bundle.
- Reject incompatible meter/PPQ/rights combinations explicitly instead of silently degrading.

### 5. Agent and Ableton workflow

The skill teaches a compact loop: inspect selected track/kit → search by genre/facets/features → compare up to eight candidates → generate or recombine → preview mapping → commit once → listen/compare. Kit mapping remains separate from groove selection so Superior Drummer, Ableton kits, or user-provided racks can be targeted.

## Data and compatibility

- Existing request fields remain valid; additional reference artifacts are optional.
- Projection/taxonomy/generator versions change when semantics change; the packaged seed is rebuilt atomically only after validation.
- SQLite remains the runtime index. Raw private paths, the complete catalog, and all 180k source files are excluded from the package.

## Acceptance

1. Equivalent rhythms encoded at PPQ 480 and PPQ 9600 have equivalent canonical HVO/grammar structure.
2. A 16-beat SMF with its last note ending earlier maps to a 16-beat clip.
3. Real corpus searches return explicit, inspectable genre/subgenre/style facets without private paths.
4. Different rhythmic content produces non-zero HVO/grammar distance; identical content produces zero.
5. Non-zero generation transforms change note events; multi-parent recombination records and uses all chosen parents; repeated runs are byte-identical.
6. Seed builds are deterministic, bounded, private-path-free, and pass the full test/lint/type suite.

