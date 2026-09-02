# Groove Seed V3 Regeneration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the shipped retrieval seed onto the per-collection articulation map and give it the genre and tempo axes the vendor databases supply, so the product searches on real drum lanes instead of a junk bucket.

**Architecture:** Additive, not a swap. The regenerated index keeps `groove.hvo.v2` exactly as it is and gains `groove.hvo.v3` alongside it, so anything reading v2 keeps working and rollback is a file copy. The `kit` facet moves to v3 because that is the whole point, and `genre` and `bpm` — axes the taxonomy already declares and never populates — get filled from the vendor labels.

**Tech Stack:** The product package and its `.venv-win` environment. No lab dependency ships; the articulation map is derived data already committed.

---

## Why this is worth doing now

The neural programme closed on 2026-09-01 with gate G5 failing: retrieval beat
the trained model. **Retrieval is the product.** Which makes this measurement the
most expensive open defect in the repository:

| Measure | Value |
|---|---|
| Corpus note mass in `other_percussion` under the shipped v2 map | **24.34%** |
| Same, under the v3 articulation map | **6.48%** |
| Hi-hat note mass under v2 | 5.67% |
| Hi-hat note mass under v3 | **21.95%** |

The shipped `index.sqlite` derives its `kit` facet from `groove.hvo.v2`. So today
`groove_search` filtering by hi-hat searches a lane that mostly is not there, and
`groove_compare` measures HVO distance across lanes that hold the wrong
instruments. Every one of those is a product bug, live, with no model involved.

Separately, `_TAXONOMY_AXES` in `taxonomy.py:33` already lists `genre` and
`subgenre`. They are never populated, because `classify_path_facets` cannot get
genre from a folder name. The vendor databases give genre for 103,096 files and
a tempo for 97.8% of them. The axis exists; only the source was missing.

## Blocking owner decisions

### S1 — the uncommitted 500-item seed in the working tree

`ableton_mcp_server/resources/groove_seed/index.sqlite` and `manifest.json` are
**modified and uncommitted**: they hold a 500-item experiment, while `HEAD` holds
the promoted 1,685-item seed. Regenerating writes to those exact paths.

Task 1 backs both files up before anything else, and nothing is overwritten until
that backup is verified. But the owner should say whether the 500-item build is
still wanted at all; if it is disposable, say so and the backup is just insurance.

### S2 — how many representatives the new seed carries

Retrieval quality is now the product's quality, and it scales with how much of the
corpus ships. Measured reference points:

| Representatives | Approximate `index.sqlite` size |
|---|---|
| 1,685 (current `HEAD`) | 27 MB |
| 4,000 | ~64 MB |
| 8,000 | ~128 MB |

A Python wheel carrying 128 MB of data is a different product decision from one
carrying 27 MB. **The plan builds at the current 1,685 unless the owner names a
different number**, so the change under test is the articulation map and the
labels, not the size.

### S3 — the 66 collections that fail gate G1

66 of 278 collections still leave more than 10% of their note mass unresolved
after the articulation map, mostly latin percussion whose instruments have no
lane in the 18-role ontology. They were excluded from *training*. For
*retrieval* they are still perfectly playable MIDI that a user might want.

**The plan keeps them and records their unresolved share per artifact**, so
search can rank them down rather than pretend they do not exist. Say so if you
would rather they were dropped.

## The coupling this change actually has

`derive_hvo` is called from four places, and getting this wrong means the index
and the runtime disagree about what a lane is:

| Call site | What it feeds | What this plan does |
|---|---|---|
| `build.py:122` | the stored projection in the index | adds v3 beside v2 |
| `corpus.py:312` | the curated bundle facets | derives `kit` from v3 |
| `deterministic.py:473` | runtime generation and transforms | must match the index |
| `fallback.py:341` | provider candidate validation | must match the index |

A user's own clip pasted in from Ableton has no collection, so `resolve_role`
falls through to General MIDI, which is correct: the articulation map describes
the vendor libraries, not arbitrary user MIDI. That fallback is already the
behaviour of `articulation.resolve_role` and is covered by an existing test.

## File Structure

| Path | Responsibility |
|---|---|
| `ableton_mcp_server/groove_intelligence/constants.py` | Version identifiers |
| `ableton_mcp_server/groove_intelligence/projections.py` | v3 already exists; unchanged |
| `ableton_mcp_server/groove_intelligence/taxonomy.py` | `kit` from v3, `genre` and `bpm` from labels |
| `ableton_mcp_server/groove_intelligence/build.py` | Store both projections |
| `ableton_mcp_server/groove_intelligence/corpus.py` | Pass the collection through |
| `ableton_mcp_server/groove_intelligence/vendor_labels.py` | Load the label sidecar |
| `scripts/regenerate_seed.py` | The regeneration entry point |
| `tests/test_groove_seed_v3.py` | Behaviour this change must not break, and what it must change |

---

### Task 1: Freeze what exists before touching it

**Files:**
- Create: `tests/test_groove_seed_v3.py`

Nothing is regenerated until the current behaviour is pinned and the working
tree is backed up. This task changes no product code.

- [ ] **Step 1: Back up the uncommitted seed**

Run:

```bash
mkdir -p "$LOCALAPPDATA/AbletonMCPServer/seed-backup-20260901"
cp ableton_mcp_server/resources/groove_seed/index.sqlite "$LOCALAPPDATA/AbletonMCPServer/seed-backup-20260901/"
cp ableton_mcp_server/resources/groove_seed/manifest.json "$LOCALAPPDATA/AbletonMCPServer/seed-backup-20260901/"
sha256sum ableton_mcp_server/resources/groove_seed/* | tee "$LOCALAPPDATA/AbletonMCPServer/seed-backup-20260901/SHA256SUMS"
```

Expected: two files copied and two digests recorded. Do not continue until this
prints both digests — decision S1 depends on the backup existing.

- [ ] **Step 2: Write the pinning test**

Create `tests/test_groove_seed_v3.py`:

```python
"""What the v3 seed must change, and what it must not.

Written before the regeneration so the difference is a decision rather than a
surprise. The v2 projection is the shipped contract for everything already using
the seed; the v3 projection and the kit facet are what this change is for.
"""

from __future__ import annotations

import numpy as np
import pytest

from ableton_mcp_server.groove_intelligence.articulation import resolve_role
from ableton_mcp_server.groove_intelligence.constants import (
    HVO_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION_V3,
)
from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf
from ableton_mcp_server.groove_intelligence.projections import derive_hvo, derive_hvo_v3

SUPERIOR = "Drums Groove MIDI/000011@SUPERIOR_DRUMMER_3"
LATIN = "Drums Groove MIDI/07@EZX_LATIN_PERCUSSION"


def _chunk(tag: bytes, body: bytes) -> bytes:
    return tag + len(body).to_bytes(4, "big") + body


# Pitch 0x16 is 22: a hi-hat articulation in the vendor libraries, outside the
# General MIDI percussion range, and therefore junk under v2.
BAND_SMF = _chunk(b"MThd", b"\x00\x01\x00\x01\x01\xe0") + _chunk(
    b"MTrk",
    b"\x00\x99\x16\x64\x00\x99\x24\x64"
    b"\x81\x70\x89\x16\x00\x00\x89\x24\x00"
    b"\x00\xff\x2f\x00",
)


def test_v2_still_calls_the_band_junk() -> None:
    # This is the defect being fixed, pinned so the fix is visible in the diff.
    hvo = derive_hvo(parse_smf(BAND_SMF))
    assert hvo.schema_version == HVO_SCHEMA_VERSION
    assert "other_percussion" in {cell.role for cell in hvo.cells}


def test_v3_puts_the_band_in_a_hi_hat_lane() -> None:
    hvo = derive_hvo_v3(parse_smf(BAND_SMF), SUPERIOR)
    assert hvo.schema_version == HVO_SCHEMA_VERSION_V3
    roles = {cell.role for cell in hvo.cells}
    assert "other_percussion" not in roles
    assert roles & {"hat_closed", "hat_open", "hat_pedal"}


def test_a_clip_with_no_collection_falls_back_to_general_midi() -> None:
    # A user's own clip pasted from Ableton has no collection. The articulation
    # map describes the vendor libraries, not arbitrary MIDI, so General MIDI is
    # the correct answer and not a degradation.
    assert resolve_role("", 36) == "kick"
    assert resolve_role("", 22) == "other_percussion"


def test_the_same_pitch_still_differs_by_library() -> None:
    assert resolve_role(SUPERIOR, 60) != resolve_role(LATIN, 60)
```

- [ ] **Step 3: Run it**

Run:

```bash
.\.venv-win\Scripts\python.exe -m pytest tests/test_groove_seed_v3.py -q
```

Expected: PASS, 4 tests. All four describe behaviour that already exists; they
are here so the regeneration cannot quietly change the wrong half.

- [ ] **Step 4: Commit**

```bash
git add tests/test_groove_seed_v3.py
git commit -m "test(groove): pin the v2 and v3 role behaviour before regenerating"
```

---

### Task 2: Load the vendor labels inside the product

**Files:**
- Create: `ableton_mcp_server/groove_intelligence/vendor_labels.py`
- Test: `tests/test_groove_vendor_labels.py`

The labels are a sidecar produced by `scripts/build_vendor_labels.py` and living
outside the repository. The product reads it at build time only; nothing at
runtime depends on it existing.

- [ ] **Step 1: Write the failing test**

Create `tests/test_groove_vendor_labels.py`:

```python
from __future__ import annotations

import json

from ableton_mcp_server.groove_intelligence.vendor_labels import (
    VendorLabels,
    genre_facet,
    tempo_facet,
)


def _write(tmp_path, records: list[dict]) -> str:
    path = tmp_path / "vendor_labels.jsonl"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return str(path)


def test_missing_sidecar_is_not_an_error(tmp_path) -> None:
    labels = VendorLabels.load(str(tmp_path / "absent.jsonl"))
    assert labels.for_path("anything") == {}


def test_a_label_is_found_by_corpus_path(tmp_path) -> None:
    path = _write(tmp_path, [{"path": "a/b.mid", "genre": "Metal", "tempo": 140}])
    labels = VendorLabels.load(path)
    assert labels.for_path("a/b.mid")["genre"] == "Metal"


def test_genre_becomes_a_normalised_facet_value() -> None:
    assert genre_facet({"genre": "Pop/Rock/Country"}) == ("pop_rock_country",)
    assert genre_facet({"genre": "Metal"}) == ("metal",)
    assert genre_facet({}) == ()


def test_tempo_becomes_a_coarse_bucket_not_a_raw_number() -> None:
    # A facet is a search axis, not a measurement. The exact tempo stays in the
    # features projection; the facet is what a user can browse by.
    assert tempo_facet({"tempo": 92}) == ("bpm_80_99",)
    assert tempo_facet({"tempo": 140}) == ("bpm_140_159",)
    assert tempo_facet({}) == ()
    assert tempo_facet({"tempo": 0}) == ()
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
.\.venv-win\Scripts\python.exe -m pytest tests/test_groove_vendor_labels.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named ...vendor_labels`.

- [ ] **Step 3: Write the module**

Create `ableton_mcp_server/groove_intelligence/vendor_labels.py`:

```python
"""Genre and tempo from the vendor MIDI databases, used only at build time.

``_TAXONOMY_AXES`` has always declared ``genre`` and ``subgenre``; nothing ever
filled them, because a folder name does not carry a genre. The vendor databases
do, for 103,096 files, along with a tempo for 97.8% of them.

The sidecar lives outside the repository and is optional. A build without it
produces a seed with no genre facet, which is exactly what ships today, so its
absence degrades nothing.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_SIDECAR = (
    r"C:\Users\Usuario\AppData\Local\AbletonMCPServer\groove-vendor-labels"
    r"\vendor_labels.jsonl"
)

# Coarse enough to browse, fine enough to be useful. A facet is a search axis;
# the exact tempo stays in the features projection.
_TEMPO_BUCKETS = (
    (60, 79, "bpm_60_79"),
    (80, 99, "bpm_80_99"),
    (100, 119, "bpm_100_119"),
    (120, 139, "bpm_120_139"),
    (140, 159, "bpm_140_159"),
    (160, 179, "bpm_160_179"),
    (180, 260, "bpm_180_plus"),
)


@dataclass(frozen=True)
class VendorLabels:
    by_path: dict[str, dict[str, Any]]

    @classmethod
    def load(cls, path: str | Path = DEFAULT_SIDECAR) -> VendorLabels:
        source = Path(path)
        if not source.exists():
            return cls(by_path={})
        records: dict[str, dict[str, Any]] = {}
        with source.open(encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                key = record.get("path")
                if isinstance(key, str):
                    records[key] = record
        return cls(by_path=records)

    def for_path(self, relative_path: str) -> dict[str, Any]:
        return self.by_path.get(relative_path, {})


def genre_facet(record: Mapping[str, Any]) -> tuple[str, ...]:
    genre = record.get("genre")
    if not isinstance(genre, str) or not genre:
        return ()
    normalised = genre.lower().replace("/", "_").replace(" ", "_").replace("-", "_")
    return (normalised,)


def tempo_facet(record: Mapping[str, Any]) -> tuple[str, ...]:
    tempo = record.get("tempo")
    if not isinstance(tempo, int | float) or not tempo:
        return ()
    for low, high, name in _TEMPO_BUCKETS:
        if low <= tempo <= high:
            return (name,)
    return ()


__all__ = ["VendorLabels", "genre_facet", "tempo_facet"]
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
.\.venv-win\Scripts\python.exe -m pytest tests/test_groove_vendor_labels.py -q
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add ableton_mcp_server/groove_intelligence/vendor_labels.py tests/test_groove_vendor_labels.py
git commit -m "feat(groove): read vendor genre and tempo labels at build time"
```

---

### Task 3: Facets from v3 and from the labels

**Files:**
- Modify: `ableton_mcp_server/groove_intelligence/taxonomy.py:558-584`
- Test: `tests/test_groove_taxonomy.py`

`classify_facets` currently derives `kit` from whichever HVO it is handed. It
does not need to know about v3; the caller decides. What it does need is a way to
accept the vendor record.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_groove_taxonomy.py`:

```python
def test_kit_follows_whichever_hvo_it_is_given() -> None:
    from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf
    from ableton_mcp_server.groove_intelligence.projections import (
        derive_features,
        derive_hvo,
        derive_hvo_v3,
    )
    from ableton_mcp_server.groove_intelligence.taxonomy import classify_facets
    from tests.test_groove_seed_v3 import BAND_SMF, SUPERIOR

    parsed = parse_smf(BAND_SMF)
    v2 = derive_hvo(parsed)
    v3 = derive_hvo_v3(parsed, SUPERIOR)

    v2_kit = classify_facets(derive_features(parsed, v2), v2).values["kit"]
    v3_kit = classify_facets(derive_features(parsed, v3), v3).values["kit"]
    assert "other_percussion" in v2_kit
    assert "other_percussion" not in v3_kit


def test_vendor_labels_populate_genre_and_bpm() -> None:
    from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf
    from ableton_mcp_server.groove_intelligence.projections import (
        derive_features,
        derive_hvo,
    )
    from ableton_mcp_server.groove_intelligence.taxonomy import classify_facets
    from tests.test_groove_seed_v3 import BAND_SMF

    parsed = parse_smf(BAND_SMF)
    hvo = derive_hvo(parsed)
    facets = classify_facets(
        derive_features(parsed, hvo),
        hvo,
        vendor_record={"genre": "Metal", "tempo": 140},
    )
    assert facets.values["genre"] == ("metal",)
    assert facets.values["bpm"] == ("bpm_140_159",)


def test_no_vendor_record_leaves_the_axes_absent() -> None:
    from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf
    from ableton_mcp_server.groove_intelligence.projections import (
        derive_features,
        derive_hvo,
    )
    from ableton_mcp_server.groove_intelligence.taxonomy import classify_facets
    from tests.test_groove_seed_v3 import BAND_SMF

    parsed = parse_smf(BAND_SMF)
    hvo = derive_hvo(parsed)
    facets = classify_facets(derive_features(parsed, hvo), hvo)
    assert "genre" not in facets.values
    assert "bpm" not in facets.values
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
.\.venv-win\Scripts\python.exe -m pytest tests/test_groove_taxonomy.py -q
```

Expected: FAIL — `classify_facets` has no `vendor_record` parameter, and `bpm` is
not an allowed axis.

- [ ] **Step 3: Extend the taxonomy**

In `taxonomy.py`, add `"bpm"` to `_ALLOWED_AXES` on line 34:

```python
_ALLOWED_AXES = _TAXONOMY_AXES + ("feel", "density", "microtiming", "kit", "license", "bpm")
```

Then extend `classify_facets` to accept and use the vendor record. Replace its
signature and the `values` assembly:

```python
def classify_facets(
    features: FeaturesProjectionV1,
    hvo: HvoProjectionV1,
    *,
    relative_path: str | None = None,
    redistribution: Redistribution = "full",
    vendor_record: Mapping[str, object] | None = None,
) -> FacetSetV1:
    """Combine rhythmic facets with optional taxonomy and vendor labels.

    ``kit`` follows whichever HVO projection the caller passes, which is how the
    articulation map reaches the index: hand it ``derive_hvo_v3`` and the hi-hats
    stop being ``other_percussion``.
    """

    hits_per_bar = _value(features, "hits_per_bar") or 0.0
    offset_mean = _value(features, "offset_mean") or 0.0
    offset_std = _value(features, "offset_std") or 0.0
    density = "sparse" if hits_per_bar < 8 else "dense" if hits_per_bar > 20 else "medium"
    feel = "laid_back" if offset_mean > 3 else "pushed" if offset_mean < -3 else "straight"
    microtiming = "tight" if offset_std <= 3 else "loose" if offset_std >= 12 else "human"
    roles = tuple(sorted({cell.role for cell in hvo.cells}))
    values: dict[str, tuple[str, ...]] = {
        "feel": (feel,),
        "density": (density,),
        "microtiming": (microtiming,),
        "kit": roles or (ROLES[-1],),
        "license": (redistribution,),
    }
    if relative_path is not None:
        values.update(classify_path_facets(relative_path).values)
    if vendor_record:
        genre = genre_facet(vendor_record)
        tempo = tempo_facet(vendor_record)
        if genre:
            values["genre"] = genre
        if tempo:
            values["bpm"] = tempo
    return FacetSetV1(values)
```

Add the import at the top of `taxonomy.py`:

```python
from .vendor_labels import genre_facet, tempo_facet
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
.\.venv-win\Scripts\python.exe -m pytest tests/test_groove_taxonomy.py -q
```

Expected: PASS, including the three new tests and every pre-existing one. If an
existing test fails, the change has altered behaviour for callers that pass no
vendor record, which it must not.

- [ ] **Step 5: Commit**

```bash
git add ableton_mcp_server/groove_intelligence/taxonomy.py tests/test_groove_taxonomy.py
git commit -m "feat(groove): derive kit from the given HVO and add genre and bpm facets"
```

---

### Task 4: Store both projections and pass the collection through

**Files:**
- Modify: `ableton_mcp_server/groove_intelligence/build.py:122`
- Modify: `ableton_mcp_server/groove_intelligence/corpus.py:312`
- Test: `tests/test_groove_build.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_groove_build.py` a test asserting that a built artifact
carries both projection versions and that the v2 blob is byte-identical to what
the current code produces:

```python
def test_an_artifact_carries_both_hvo_versions(tmp_path) -> None:
    from ableton_mcp_server.groove_intelligence.constants import (
        HVO_SCHEMA_VERSION,
        HVO_SCHEMA_VERSION_V3,
    )
    from ableton_mcp_server.groove_intelligence.build import build_artifact
    from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf
    from tests.fixtures.groove_smf import MINIMAL_TYPE1_SMF

    artifact = build_artifact(
        MINIMAL_TYPE1_SMF, collection="Drums Groove MIDI/000011@SUPERIOR_DRUMMER_3"
    )
    versions = {projection.version for projection in artifact.projections}
    assert HVO_SCHEMA_VERSION in versions
    assert HVO_SCHEMA_VERSION_V3 in versions
```

Read `build.py` around line 100 to 140 first and match the real construction
API — the assertion is what matters, the call shape must follow the code that is
there.

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
.\.venv-win\Scripts\python.exe -m pytest tests/test_groove_build.py -q
```

Expected: FAIL — only one HVO projection is stored.

- [ ] **Step 3: Store both**

In `build.py`, keep the existing `derive_hvo(parsed)` call and its stored
projection untouched, and add a second projection from `derive_hvo_v3(parsed,
collection)` when a collection is known. In `corpus.py`, thread the collection —
which is the stratum already available on the catalog row — into that call, and
pass the v3 projection to `classify_facets` so `kit` comes from it.

The v2 projection must remain byte-identical: everything already reading the seed
depends on it, and Task 1 pinned it.

- [ ] **Step 4: Run the whole groove suite**

Run:

```bash
.\.venv-win\Scripts\python.exe -m pytest tests/ -k groove -q
```

Expected: every groove test passes. A digest test failing here means the v2 blob
moved, which is the one thing this task must not do.

- [ ] **Step 5: Commit**

```bash
git add ableton_mcp_server/groove_intelligence/build.py ableton_mcp_server/groove_intelligence/corpus.py tests/test_groove_build.py
git commit -m "feat(groove): store the v3 projection beside v2 and key kit to it"
```

---

### Task 5: Version bump across the coupled files

**Files:**
- Modify: `ableton_mcp_server/groove_intelligence/constants.py`

The `kit` facet changes meaning and two axes appear. That is a new index, not a
patch of the old one, and `AGENTS.md` requires the coupled identifiers to move
together.

- [ ] **Step 1: Bump the identifiers**

In `constants.py`:

```python
SEED_SCHEMA_VERSION = "groove.seed.v3"
INDEX_SCHEMA_VERSION = "groove.index.v3"
SQLITE_USER_VERSION = 3
TAXONOMY_VERSION = "groove-taxonomy-v3"
```

Leave `HVO_SCHEMA_VERSION` at `groove.hvo.v2` and `HVO_SCHEMA_VERSION_V3` at
`groove.hvo.v3`: both projections ship, so both identifiers stay meaningful.
Leave `FEATURES_SCHEMA_VERSION` and `GRAMMAR_SCHEMA_VERSION` alone — neither
changed.

- [ ] **Step 2: Find everything that asserted the old values**

Run:

```bash
grep -rn "groove.index.v2\|groove.seed.v2\|groove-taxonomy-v2\|SQLITE_USER_VERSION" ableton_mcp_server tests docs --include=*.py --include=*.md
```

Update each hit to the new identifier, or to read the constant instead of
repeating the string. Do not leave a literal `"groove.index.v2"` anywhere that
should have moved.

- [ ] **Step 3: Run the full suite**

Run:

```bash
.\.venv-win\Scripts\python.exe -m pytest -q --tb=line
```

Expected: the four known prototype failures and nothing else new.

- [ ] **Step 4: Commit**

```bash
git add ableton_mcp_server/groove_intelligence/constants.py tests docs
git commit -m "feat(groove): bump the index, seed and taxonomy versions to v3"
```

---

### Task 6: Regenerate

**Files:**
- Create: `scripts/regenerate_seed.py`

- [ ] **Step 1: Write the entry point**

Create `scripts/regenerate_seed.py` mirroring `scripts/ingest_private_corpus.py`
but writing to a staging directory rather than over the package resources, taking
`--representatives` (default 1,685, per decision S2) and `--out`, loading
`VendorLabels`, and printing the facet coverage of what it built: how many
artifacts carry a genre, how many carry a bpm bucket, and the share of note mass
still in `other_percussion`.

Building to a staging path is not caution for its own sake: the package resource
is the file the product loads, and overwriting it before the new bundle has been
inspected would leave no working seed if the build is wrong.

- [ ] **Step 2: Build to staging**

Run:

```bash
.\.venv-win\Scripts\python.exe scripts\regenerate_seed.py --out "$env:LOCALAPPDATA\AbletonMCPServer\seed-v3-staging"
```

Expected: an `index.sqlite` and `manifest.json` under the staging directory, and
a printed coverage summary.

- [ ] **Step 3: Inspect before promoting**

Run:

```bash
.\.venv-win\Scripts\python.exe -c "import sqlite3,json,collections; c=sqlite3.connect('file:%LOCALAPPDATA%/AbletonMCPServer/seed-v3-staging/index.sqlite?mode=ro',uri=True); print('artifacts', c.execute('select count(*) from artifacts').fetchone()[0]); print('projections', c.execute('select version, count(*) from projections group by version').fetchall()); print('axes', c.execute('select axis, count(*) from facets group by axis order by 2 desc').fetchall())"
```

Check three things:

1. both `groove.hvo.v2` and `groove.hvo.v3` appear in `projections`;
2. `genre` and `bpm` appear in `facets` with a non-trivial count;
3. the artifact count matches decision S2.

If the `kit` axis still shows `other_percussion` on most artifacts, the v3
projection is not reaching `classify_facets` and Task 4 is incomplete.

- [ ] **Step 4: Promote**

Only after Step 3 passes, and only with the Task 1 backup verified:

```bash
cp "$LOCALAPPDATA/AbletonMCPServer/seed-v3-staging/index.sqlite" ableton_mcp_server/resources/groove_seed/
cp "$LOCALAPPDATA/AbletonMCPServer/seed-v3-staging/manifest.json" ableton_mcp_server/resources/groove_seed/
```

- [ ] **Step 5: Run the full suite against the promoted seed**

Run:

```bash
.\.venv-win\Scripts\python.exe -m pytest -q --tb=line
.\.venv-win\Scripts\python.exe -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests
.\.venv-win\Scripts\python.exe -m mypy --strict ableton_mcp_server
```

Expected: the four known prototype failures and nothing else; Ruff and Mypy clean
apart from the same prototypes.

- [ ] **Step 6: Commit**

```bash
git add scripts/regenerate_seed.py ableton_mcp_server/resources/groove_seed/
git commit -m "feat(groove): regenerate the retrieval seed on the v3 articulation map"
```

---

### Task 7: Say what changed, where users read it

**Files:**
- Modify: `docs/TOOL_REFERENCE.md`
- Modify: `docs/superpowers/specs/2026-08-30-groove-brain-extension-design.md`
- Create: `docs/superpowers/plans/2026-09-01-groove-seed-v3-regeneration-result.md`

- [ ] **Step 1: Document the new axes**

In `docs/TOOL_REFERENCE.md`, wherever `groove_search` facets are listed, add
`genre` and `bpm` with their value vocabularies, and note that `kit` now reflects
the per-collection articulation map rather than General MIDI alone.

- [ ] **Step 2: Correct the product design document**

Section 13.5 of the extension design says the folder hierarchy carries genre.
Measured, it does not: `genre` came from the vendor databases and the folder
names never produced it. Replace that claim with the measured source and
coverage.

- [ ] **Step 3: Write the result document**

Record: the artifact count, the note mass in `other_percussion` before and after,
the hi-hat mass before and after, genre and bpm coverage, the new manifest
digests, and the backup location of the previous seed.

- [ ] **Step 4: Verify**

Run:

```bash
git diff --check
.\.venv-win\Scripts\python.exe -m pytest -q --tb=line
```

- [ ] **Step 5: Commit**

```bash
git add docs
git commit -m "docs: record the v3 seed regeneration and its new facets"
```

---

## What this plan does not do

It does not change how search ranks. Adding `genre` and `bpm` makes them
filterable; whether the ranker should weight them is a separate decision with its
own evidence.

It does not drop the 66 collections that fail gate G1. Unresolved lanes make a
collection hard to search by kit; they do not make its MIDI unplayable, and
retrieval is now the product.

It does not touch the Extension, the Remote Script, or the provider. The seed is
data the product reads.

## Stop condition

Done when the promoted seed carries both HVO projections, `kit` reflects the
articulation map, `genre` and `bpm` are populated, the full suite is at its known
state, and the result document records the before and after figures.

If the regenerated seed does not reduce `other_percussion` mass close to the
6.48% the corpus measurement predicts, stop and find out why before promoting.
A seed that ships the v3 label while still holding v2 lanes would be worse than
the one it replaced, because it would look fixed.
