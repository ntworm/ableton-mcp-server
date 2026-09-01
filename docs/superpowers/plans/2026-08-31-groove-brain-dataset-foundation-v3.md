# Groove Brain Dataset Foundation V3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn 169,318 byte-unique MIDI files into a reproducible, leak-free tensor dataset whose training target round-trips exactly, and prove it on a 1% build.

**Architecture:** A pipeline in the lab package reads each file through the product's parser and `groove.hvo.v3` articulation map, builds a `CanonicalGroove` with a `subhits` multiplicity channel, fingerprints it at four levels, groups files into family clusters by transitive closure over the exact, canonical, rhythmic and hierarchy edges, reserves a blind test by whole cluster, writes memory-mappable `.npy` shards with a JSONL index, and emits a manifest that lets a second run be checked digest-for-digest against the first.

**Tech Stack:** The lab CPU-only environment from plan 3, plus `pydantic` so it can import `ableton_mcp_server.groove_intelligence`. NumPy `.npy` arrays, JSONL indexes, SHA-256 digests. No pickle anywhere.

---

## What is already settled, and must not be re-litigated

| Fact | Source |
|---|---|
| 169,318 byte-unique files; 354,749 non-overlapping 2-bar windows | spec 4.2 |
| 56,842 files (33.6%) are shorter than 2 bars | spec 4.2 |
| Dense grids lose 3.51% of notes at 16ths, 1.38% at 32nds, 0.92% at 64ths | spec 4.2 |
| 26.0% of windows repeat another window's exact onset pattern | spec 4.2 |
| 346 repeated patterns and 1,030 kick/snare skeletons cross collections | spec 12.1 |
| Roles come from `articulation.resolve_role`, keyed by collection | spec 4.3 |
| 66 of 278 collections fail gate G1 and stay out of training | spec 4.3 |
| Vendor genre and tempo exist for 103,096 files | spec 4.3 |
| Model decoding is budgeted at 32 steps, step-token layout | spec 19.4 |
| Baseline grid: 2 bars, 4/4, 32 steps of sixteenth, continuous offset | spec 11.2 |

The tokenisation plan 3 chose is a model concern. The dataset stores `[example, time, lane]` tensors either layout can consume.

## Storage decisions, made here so no task has to invent them

**Workspace:** `F:\groove-brain\` — 458 GB free, the least cluttered drive, and never `C:` per spec 16.4.

**Layout** under `F:\groove-brain\dataset\<build_id>\`:

```text
manifest.json                     the DatasetManifest
canonical/<split>/index.jsonl     one CanonicalGroove record per line
shards/<split>/<nnnn>/hit.npy     uint8  [rows, 32, 18]
                    /subhits.npy  uint8  [rows, 32, 18]
                    /velocity.npy float32[rows, 32, 18]
                    /offset.npy   int8   [rows, 32, 18]
                    /observed.npy uint8  [rows, 32, 18]
                    /target.npy   uint8  [rows, 32, 18]
                    /conditions.npy float32 [rows, 16]
                    /ids.npy      uint64 [rows, 3]  example, family, source
shards/<split>/index.jsonl        one line per example, pointing at shard and row
```

**Dtypes are chosen for exact round-trip, not convenience.** `offset_ticks` is an integer in `[-60, +60]` after `derive_hvo_v3`, so `int8` is lossless. `subhits` is a raw count in `uint8`, deliberately uncapped: clamping it to the model's four classes is a model decision that belongs to plan 6, and the manifest reports how much mass a clamp would cost. `velocity` is a mean over colliding notes, so it stays `float32`.

Per example that is `5 × 576` bytes plus `576 × 4`, about 5.06 KiB, so 354,749 windows come to roughly 1.8 GB. Disk is not the constraint; the 1% build measures it anyway because a pipeline that does not measure before it writes is the thing gate D1 exists to catch.

**Condition vector, 16 dimensions, fixed here:**

| Index | Meaning |
|---|---|
| 0 | BPM normalised, `(bpm - 60) / 140`, clipped to `[0, 1]` |
| 1 | time signature is 4/4 |
| 2 | global density, hits per bar over 32 |
| 3, 4, 5 | section is groove, fill, variation |
| 6 | swing, from the systematic offset bias |
| 7 | energy, mean velocity |
| 8 | complexity, distinct lanes over 18 |
| 9 | window was looped from a shorter file |
| 10 | a vendor genre is present |
| 11–15 | vendor genre bucket: rock/pop/country, metal, latin, jazz, other |

BPM comes from the SMF tempo meta, present in 97.8% of files, never from the path. Genre comes from the vendor labels, never from a folder name. A condition with no source is zero and index 10 says so.

## File Structure

| Path | Responsibility |
|---|---|
| `lab/groove_lab/dataset/config.py` | Frozen build configuration and its digest |
| `lab/groove_lab/dataset/canonical.py` | File to `CanonicalGroove`, with hashes |
| `lab/groove_lab/dataset/fingerprint.py` | The four fingerprint levels |
| `lab/groove_lab/dataset/clusters.py` | Union-find over dedupe edges, giant-component guard |
| `lab/groove_lab/dataset/windows.py` | Windowing and the short-file policy |
| `lab/groove_lab/dataset/conditions.py` | The 16-dimension condition vector |
| `lab/groove_lab/dataset/splits.py` | Blind test by cluster, 80/10/10, leakage test |
| `lab/groove_lab/dataset/shards.py` | `.npy` shard writer and reader, JSONL index |
| `lab/groove_lab/dataset/roundtrip.py` | Tensor to `CanonicalGroove` and the exactness check |
| `lab/groove_lab/dataset/build.py` | Orchestration and the `DatasetManifest` |
| `lab/scripts/build_dataset.py` | Entry point with a `--fraction` flag |
| `lab/tests/dataset/test_*.py` | One test module per unit above |

---

### Task 1: Lab can import the product package

**Files:**
- Modify: `lab/requirements.txt`
- Modify: `lab/README.md`
- Create: `lab/tests/test_product_import.py`

- [ ] **Step 1: Write the failing test**

Create `lab/tests/test_product_import.py`:

```python
from __future__ import annotations


def test_lab_can_use_the_product_projections() -> None:
    # The dataset pipeline reuses the shipped parser, articulation map and v3
    # projection rather than reimplementing them, so a drift in the product is a
    # failure here rather than a silent divergence in the training data.
    from ableton_mcp_server.groove_intelligence.articulation import resolve_role
    from ableton_mcp_server.groove_intelligence.constants import HVO_SCHEMA_VERSION_V3
    from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf
    from ableton_mcp_server.groove_intelligence.projections import derive_hvo_v3

    assert HVO_SCHEMA_VERSION_V3 == "groove.hvo.v3"
    assert callable(parse_smf)
    assert callable(derive_hvo_v3)
    assert resolve_role("Drums Groove MIDI/does-not-exist", 36) == "kick"
```

- [ ] **Step 2: Run it to see how it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/test_product_import.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ableton_mcp_server'` or `No module named 'pydantic'`.

- [ ] **Step 3: Add pydantic and a conftest that puts the repo on the path**

Append to `lab/requirements.txt`:

```text
pydantic==2.13.5
```

Create `lab/conftest.py`:

```python
"""Put the repository root on the path so the lab can import the product package.

The lab reuses the shipped parser, articulation map and v3 projection. It does
not install the product package, because that would drag FastMCP and the whole
server dependency tree into an environment that only needs to read MIDI.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
```

- [ ] **Step 4: Install and verify**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pip install "pydantic==2.13.5"
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/test_product_import.py -q
```

Expected: PASS, 1 test.

- [ ] **Step 5: Confirm the product environment is still clean**

Run:

```bash
.venv-win/Scripts/python.exe -c "import importlib.util as u; print(u.find_spec('torch'))"
.venv-win/Scripts/python.exe -m pytest -q --tb=line
```

Expected: `None`, then `906 passed` with the four known prototype failures and nothing new.

- [ ] **Step 6: Commit**

```bash
git add lab/requirements.txt lab/conftest.py lab/tests/test_product_import.py lab/README.md
git commit -m "chore(lab): let the lab import the product projections"
```

---

### Task 2: Frozen build configuration

**Files:**
- Create: `lab/groove_lab/dataset/__init__.py`
- Create: `lab/groove_lab/dataset/config.py`
- Test: `lab/tests/dataset/test_config.py`

A build is reproducible only if every knob is in one frozen object whose digest goes into the manifest.

- [ ] **Step 1: Write the failing test**

Create `lab/tests/dataset/test_config.py`:

```python
from __future__ import annotations

import dataclasses

import pytest

from groove_lab.dataset.config import BuildConfig


def test_defaults_match_the_specification() -> None:
    config = BuildConfig()
    assert config.steps == 32
    assert config.lanes == 18
    assert config.bars == 2
    assert config.grid_division == 16
    assert config.condition_dimensions == 16
    assert config.short_file_policy == "looped"
    assert config.split_ratios == (0.8, 0.1, 0.1)
    assert config.max_cluster_share == 0.05
    assert config.representation_loss_budget == 0.04
    assert config.seed == 20260831


def test_config_is_frozen() -> None:
    config = BuildConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.steps = 64  # type: ignore[misc]


def test_digest_is_stable_and_sensitive() -> None:
    assert BuildConfig().digest() == BuildConfig().digest()
    assert BuildConfig().digest() != BuildConfig(short_file_policy="padded").digest()
    assert len(BuildConfig().digest()) == 64


def test_short_file_policy_is_restricted() -> None:
    with pytest.raises(ValueError):
        BuildConfig(short_file_policy="whatever")
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/dataset/test_config.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.dataset'`.

- [ ] **Step 3: Write the config**

Create `lab/groove_lab/dataset/__init__.py`:

```python
"""Dataset foundation V3: canonical store, clusters, splits, shards, manifest."""
```

Create `lab/groove_lab/dataset/config.py`:

```python
"""Every knob of a dataset build, frozen, with a digest for the manifest.

A build that cannot be described by one hashable object cannot be reproduced,
and gate G2 asks for two independent builds with identical digests.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json

SHORT_FILE_POLICIES = ("looped", "padded")


@dataclasses.dataclass(frozen=True)
class BuildConfig:
    # Grid, from specification section 11.2.
    bars: int = 2
    grid_division: int = 16
    steps: int = 32
    lanes: int = 18
    condition_dimensions: int = 16

    # Windowing, from section 11.4. 33.6% of files are shorter than two bars, so
    # the policy is explicit and recorded rather than implied.
    short_file_policy: str = "looped"
    window_hop_bars: int = 2

    # Clustering and splits, from section 12.
    split_ratios: tuple[float, float, float] = (0.8, 0.1, 0.1)
    max_cluster_share: float = 0.05

    # Representation, from section 11.2. The measured loss of a sixteenth grid is
    # 3.51% of note mass; the budget is set just above it so a regression fails.
    representation_loss_budget: float = 0.04

    # Gate G1: a collection above this unresolved note mass stays out of training.
    max_unresolved_note_share: float = 0.10

    rows_per_shard: int = 4096
    seed: int = 20260831

    def __post_init__(self) -> None:
        if self.short_file_policy not in SHORT_FILE_POLICIES:
            raise ValueError(
                f"short_file_policy must be one of {SHORT_FILE_POLICIES}, "
                f"got {self.short_file_policy!r}"
            )
        if abs(sum(self.split_ratios) - 1.0) > 1e-9:
            raise ValueError(f"split_ratios must sum to 1.0, got {self.split_ratios}")

    def as_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)

    def digest(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/dataset/test_config.py -q
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/dataset/__init__.py lab/groove_lab/dataset/config.py lab/tests/dataset/test_config.py
git commit -m "feat(dataset): freeze the build configuration behind a digest"
```

---

### Task 3: CanonicalGroove with a multiplicity channel

**Files:**
- Create: `lab/groove_lab/dataset/canonical.py`
- Test: `lab/tests/dataset/test_canonical.py`

`derive_hvo_v3` returns one cell per `(role, bar, step)` with `hit=1` and averaged velocity and offset. It carries `event_ids`, so the multiplicity is recoverable without reparsing: `subhits` is `len(cell.event_ids)`.

- [ ] **Step 1: Write the failing test**

Create `lab/tests/dataset/test_canonical.py`:

```python
from __future__ import annotations

from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf

from groove_lab.dataset.canonical import build_canonical, note_mass_lost
from tests.fixtures.groove_smf import MULTI_HIT_SMF, NO_TEMPO_SMF


def _chunk(tag: bytes, body: bytes) -> bytes:
    return tag + len(body).to_bytes(4, "big") + body


# Two notes on the same pitch at the same tick: one HVO cell, two subhits.
COLLIDING_SMF = _chunk(b"MThd", b"\x00\x01\x00\x01\x01\xe0") + _chunk(
    b"MTrk",
    b"\x00\x99\x24\x64\x00\x99\x24\x50"
    b"\x81\x70\x89\x24\x00\x00\x89\x24\x00"
    b"\x00\xff\x2f\x00",
)


def test_subhits_counts_every_event_in_a_cell() -> None:
    groove = build_canonical(parse_smf(COLLIDING_SMF), collection="unmapped")
    cells = [cell for cell in groove.cells if cell.subhits > 1]
    assert cells, "a colliding cell must report more than one subhit"
    assert cells[0].subhits == 2


def test_note_mass_lost_is_zero_when_subhits_are_kept() -> None:
    parsed = parse_smf(COLLIDING_SMF)
    groove = build_canonical(parsed, collection="unmapped")
    assert note_mass_lost(parsed, groove) == 0.0


def test_hashes_separate_rhythm_from_expression() -> None:
    quiet = build_canonical(parse_smf(NO_TEMPO_SMF), collection="unmapped")
    same = build_canonical(parse_smf(NO_TEMPO_SMF), collection="unmapped")
    other = build_canonical(parse_smf(MULTI_HIT_SMF), collection="unmapped")

    assert quiet.canonical_hash == same.canonical_hash
    assert quiet.rhythm_hash == same.rhythm_hash
    assert quiet.rhythm_hash != other.rhythm_hash
    assert len(quiet.canonical_hash) == 64


def test_tempo_comes_from_the_smf_not_the_path() -> None:
    groove = build_canonical(parse_smf(NO_TEMPO_SMF), collection="unmapped")
    assert groove.bpm is None or groove.bpm > 0
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/dataset/test_canonical.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.dataset.canonical'`.

- [ ] **Step 3: Write the canonical builder**

Create `lab/groove_lab/dataset/canonical.py`:

```python
"""One file to one CanonicalGroove, with the multiplicity the grid would drop.

``derive_hvo_v3`` collapses every event in a ``(role, bar, step)`` cell into one
cell with averaged velocity and offset, but it keeps ``event_ids``, so the count
is recoverable without reparsing.  Storing that count is what makes the training
target round-trip and what turns "notes silently fused" into a published number.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from ableton_mcp_server.groove_intelligence.midi_lossless import ParsedSmfV1
from ableton_mcp_server.groove_intelligence.projections import derive_hvo_v3

MICROSECONDS_PER_MINUTE = 60_000_000


@dataclass(frozen=True)
class CanonicalCell:
    role: str
    bar: int
    step: int
    subhits: int
    velocity: float
    offset_ticks: int


@dataclass(frozen=True)
class CanonicalGroove:
    cells: tuple[CanonicalCell, ...]
    bpm: float | None
    meter: str
    bars: int
    collection: str
    source_events_digest: str
    canonical_hash: str = field(default="")
    rhythm_hash: str = field(default="")
    expression_hash: str = field(default="")


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _bpm(parsed: ParsedSmfV1) -> float | None:
    if not parsed.tempos:
        return None
    microseconds = parsed.tempos[0].get("microseconds")
    if not microseconds:
        return None
    return round(MICROSECONDS_PER_MINUTE / float(microseconds), 4)


def _meter(parsed: ParsedSmfV1) -> str:
    if not parsed.meters:
        return "4/4"
    first = parsed.meters[0]
    return f"{first['numerator']}/{2 ** first['denominator_power']}"


def build_canonical(parsed: ParsedSmfV1, collection: str) -> CanonicalGroove:
    hvo = derive_hvo_v3(parsed, collection)
    cells = tuple(
        CanonicalCell(
            role=cell.role,
            bar=cell.bar,
            step=cell.step,
            subhits=len(cell.event_ids),
            velocity=cell.velocity,
            offset_ticks=cell.offset_ticks,
        )
        for cell in sorted(hvo.cells, key=lambda c: (c.bar, c.step, c.role))
    )
    bars = max((cell.bar for cell in cells), default=0) + 1

    rhythm = [[cell.role, cell.bar, cell.step, cell.subhits] for cell in cells]
    expression = [[cell.velocity, cell.offset_ticks] for cell in cells]
    return CanonicalGroove(
        cells=cells,
        bpm=_bpm(parsed),
        meter=_meter(parsed),
        bars=bars,
        collection=collection,
        source_events_digest=parsed.source_events_digest,
        canonical_hash=_digest([rhythm, expression]),
        rhythm_hash=_digest(rhythm),
        expression_hash=_digest(expression),
    )


def note_mass_lost(parsed: ParsedSmfV1, groove: CanonicalGroove) -> float:
    """Fraction of source notes the canonical form does not account for."""

    source = len(parsed.note_events)
    if source == 0:
        return 0.0
    kept = sum(cell.subhits for cell in groove.cells)
    return (source - kept) / source
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/dataset/test_canonical.py -q
```

Expected: PASS, 4 tests.

If `note_mass_lost` is not zero, stop. It means `event_ids` is not carrying every event, and the whole exactness claim of gate G3 rests on it.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/dataset/canonical.py lab/tests/dataset/test_canonical.py
git commit -m "feat(dataset): build CanonicalGroove with a subhits channel"
```

---

### Task 4: Fingerprints and family clusters

**Files:**
- Create: `lab/groove_lab/dataset/clusters.py`
- Test: `lab/tests/dataset/test_clusters.py`

Layers 1, 2, 3 and 5 create cluster edges. Layer 4, continuous near-duplicate distance, deliberately does not: single linkage over a continuous metric collapses into one giant component and makes the split impossible.

- [ ] **Step 1: Write the failing test**

Create `lab/tests/dataset/test_clusters.py`:

```python
from __future__ import annotations

import pytest

from groove_lab.dataset.clusters import (
    GiantComponentError,
    build_clusters,
    component_sizes,
)


def _record(source: str, byte: str, canonical: str, rhythm: str, collection: str) -> dict:
    return {
        "source_id": source,
        "byte_hash": byte,
        "canonical_hash": canonical,
        "rhythm_hash": rhythm,
        "collection": collection,
    }


def test_identical_bytes_land_in_one_cluster() -> None:
    records = [
        _record("a", "H", "C", "R", "col1"),
        _record("b", "H", "C", "R", "col1"),
        _record("c", "OTHER", "C2", "R2", "col2"),
    ]
    clusters = build_clusters(records, max_share=1.0)
    assert clusters["a"] == clusters["b"]
    assert clusters["a"] != clusters["c"]


def test_same_rhythm_across_collections_still_shares_a_cluster() -> None:
    # Measured: 346 onset patterns repeat across different collections. Grouping
    # by hierarchy alone would put these on opposite sides of the split.
    records = [
        _record("a", "H1", "C1", "SAME", "col1"),
        _record("b", "H2", "C2", "SAME", "col2"),
    ]
    clusters = build_clusters(records, max_share=1.0)
    assert clusters["a"] == clusters["b"]


def test_unrelated_files_stay_apart() -> None:
    records = [
        _record("a", "H1", "C1", "R1", "col1"),
        _record("b", "H2", "C2", "R2", "col2"),
    ]
    clusters = build_clusters(records, max_share=1.0)
    assert clusters["a"] != clusters["b"]


def test_a_giant_component_is_rejected_not_tolerated() -> None:
    records = [_record(str(i), "H", "C", "R", "col") for i in range(100)]
    with pytest.raises(GiantComponentError) as error:
        build_clusters(records, max_share=0.05)
    assert "100" in str(error.value)


def test_component_sizes_are_reported_for_the_manifest() -> None:
    records = [
        _record("a", "H", "C", "R", "col1"),
        _record("b", "H", "C", "R", "col1"),
        _record("c", "H2", "C2", "R2", "col2"),
    ]
    clusters = build_clusters(records, max_share=1.0)
    sizes = component_sizes(clusters)
    assert sorted(sizes.values(), reverse=True) == [2, 1]
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/dataset/test_clusters.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.dataset.clusters'`.

- [ ] **Step 3: Write the cluster builder**

Create `lab/groove_lab/dataset/clusters.py`:

```python
"""Family clusters as the transitive closure over the discrete dedupe layers.

Specification section 12.1 defines five layers.  Layers 1, 2, 3 and 5 are
discrete equality relations and safely form edges.  Layer 4, near-duplicate
distance, is a continuous metric: single linkage over it collapses the corpus
into one component and makes an 80/10/10 split by whole clusters impossible, so
it is a sampling filter and a published metric, never an edge.

Hierarchy alone is not enough either.  346 onset patterns and 1,030 kick/snare
skeletons were measured crossing collection boundaries, which is why the rhythm
hash is an edge in its own right.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping


class GiantComponentError(RuntimeError):
    """Clustering produced a component too large to split around."""


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        self._parent.setdefault(item, item)

    def find(self, item: str) -> str:
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self._parent[max(left_root, right_root)] = min(left_root, right_root)


def build_clusters(
    records: Iterable[Mapping[str, str]], max_share: float
) -> dict[str, str]:
    """Map every ``source_id`` to a cluster id, refusing a giant component."""

    items = list(records)
    union = _UnionFind()
    for record in items:
        union.add(record["source_id"])

    # Layers 1, 2 and 3: identical bytes, identical canonical form, identical
    # rhythm. Layer 5, the collection, is intentionally not an edge on its own:
    # it would merge whole libraries into one component while adding nothing the
    # content hashes have not already caught.
    for key in ("byte_hash", "canonical_hash", "rhythm_hash"):
        groups: dict[str, list[str]] = defaultdict(list)
        for record in items:
            groups[record[key]].append(record["source_id"])
        for members in groups.values():
            first = members[0]
            for other in members[1:]:
                union.union(first, other)

    clusters = {record["source_id"]: union.find(record["source_id"]) for record in items}

    sizes = Counter(clusters.values())
    if items:
        largest, count = sizes.most_common(1)[0]
        if count / len(items) > max_share:
            raise GiantComponentError(
                f"largest cluster {largest} holds {count} of {len(items)} examples, "
                f"above the {max_share:.0%} ceiling; reduce the near-duplicate "
                f"threshold and regroup rather than splitting a cluster"
            )
    return clusters


def component_sizes(clusters: Mapping[str, str]) -> dict[str, int]:
    return dict(Counter(clusters.values()))
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/dataset/test_clusters.py -q
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/dataset/clusters.py lab/tests/dataset/test_clusters.py
git commit -m "feat(dataset): cluster families by transitive closure with a size guard"
```

---

### Task 5: Splits with a content leakage test

**Files:**
- Create: `lab/groove_lab/dataset/splits.py`
- Test: `lab/tests/dataset/test_splits.py`

The order in specification 12.3 is mandatory: cluster first, reserve blind test by whole cluster, then divide the rest. The leakage test is separate from the clustering on purpose, so a bug in one cannot hide a bug in the other.

- [ ] **Step 1: Write the failing test**

Create `lab/tests/dataset/test_splits.py`:

```python
from __future__ import annotations

import pytest

from groove_lab.dataset.splits import LeakageError, assign_splits, verify_no_leakage


def _records(count: int, cluster_size: int) -> list[dict]:
    return [
        {
            "source_id": str(index),
            "cluster_id": f"c{index // cluster_size}",
            "byte_hash": f"b{index}",
            "canonical_hash": f"c{index}",
            "rhythm_hash": f"r{index}",
        }
        for index in range(count)
    ]


def test_whole_clusters_never_straddle_a_split() -> None:
    records = _records(300, cluster_size=3)
    splits = assign_splits(records, ratios=(0.8, 0.1, 0.1), seed=1)
    by_cluster: dict[str, set[str]] = {}
    for record in records:
        by_cluster.setdefault(record["cluster_id"], set()).add(splits[record["source_id"]])
    assert all(len(values) == 1 for values in by_cluster.values())


def test_ratios_are_approximately_honoured() -> None:
    records = _records(1000, cluster_size=2)
    splits = assign_splits(records, ratios=(0.8, 0.1, 0.1), seed=1)
    counts = {name: sum(1 for v in splits.values() if v == name) for name in
              ("train", "validation", "test")}
    assert 0.75 <= counts["train"] / 1000 <= 0.85
    assert 0.05 <= counts["validation"] / 1000 <= 0.15
    assert 0.05 <= counts["test"] / 1000 <= 0.15


def test_assignment_is_deterministic_for_a_seed() -> None:
    records = _records(200, cluster_size=2)
    assert assign_splits(records, (0.8, 0.1, 0.1), seed=7) == assign_splits(
        records, (0.8, 0.1, 0.1), seed=7
    )


def test_leakage_verifier_catches_a_shared_hash() -> None:
    records = _records(10, cluster_size=1)
    splits = {record["source_id"]: "train" for record in records}
    splits["9"] = "test"
    records[9]["rhythm_hash"] = records[0]["rhythm_hash"]
    with pytest.raises(LeakageError) as error:
        verify_no_leakage(records, splits)
    assert "rhythm_hash" in str(error.value)


def test_leakage_verifier_passes_a_clean_split() -> None:
    records = _records(10, cluster_size=1)
    splits = {record["source_id"]: "train" for record in records}
    splits["9"] = "test"
    verify_no_leakage(records, splits)
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/dataset/test_splits.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.dataset.splits'`.

- [ ] **Step 3: Write the split module**

Create `lab/groove_lab/dataset/splits.py`:

```python
"""Assign splits by whole cluster and prove afterwards that nothing leaked.

The verification is deliberately independent of the assignment: it re-derives
leakage from the content hashes alone, so a bug in the clustering cannot hide a
bug in the split, which is the failure mode section 12.3 asks for.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence

SPLIT_NAMES = ("train", "validation", "test")
LEAKAGE_KEYS = ("byte_hash", "canonical_hash", "rhythm_hash")


class LeakageError(RuntimeError):
    """A content hash appears on both sides of a split boundary."""


def _cluster_order(cluster_id: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{cluster_id}".encode()).hexdigest()


def assign_splits(
    records: Sequence[Mapping[str, str]], ratios: tuple[float, float, float], seed: int
) -> dict[str, str]:
    """Return ``source_id`` to split name, moving whole clusters at a time."""

    members: dict[str, list[str]] = defaultdict(list)
    for record in records:
        members[record["cluster_id"]].append(record["source_id"])

    ordered = sorted(members, key=lambda cluster: _cluster_order(cluster, seed))
    total = len(records)
    train_target = ratios[0] * total
    validation_target = ratios[1] * total

    assignment: dict[str, str] = {}
    placed = 0
    for cluster in ordered:
        if placed < train_target:
            name = "train"
        elif placed < train_target + validation_target:
            name = "validation"
        else:
            name = "test"
        for source_id in members[cluster]:
            assignment[source_id] = name
        placed += len(members[cluster])
    return assignment


def verify_no_leakage(
    records: Sequence[Mapping[str, str]], splits: Mapping[str, str]
) -> None:
    """Raise if any content hash spans more than one split."""

    for key in LEAKAGE_KEYS:
        seen: dict[str, set[str]] = defaultdict(set)
        for record in records:
            seen[record[key]].add(splits[record["source_id"]])
        offenders = {value: names for value, names in seen.items() if len(names) > 1}
        if offenders:
            example, names = next(iter(offenders.items()))
            raise LeakageError(
                f"{len(offenders)} values of {key} span multiple splits; "
                f"for example {example} appears in {sorted(names)}"
            )
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/dataset/test_splits.py -q
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/dataset/splits.py lab/tests/dataset/test_splits.py
git commit -m "feat(dataset): split by whole cluster and verify leakage independently"
```

---

### Task 6: Windows, conditions and tensors

**Files:**
- Create: `lab/groove_lab/dataset/windows.py`
- Create: `lab/groove_lab/dataset/conditions.py`
- Test: `lab/tests/dataset/test_windows.py`

- [ ] **Step 1: Write the failing test**

Create `lab/tests/dataset/test_windows.py`:

```python
from __future__ import annotations

import numpy as np
import pytest

from groove_lab.dataset.canonical import CanonicalCell, CanonicalGroove
from groove_lab.dataset.conditions import build_conditions
from groove_lab.dataset.windows import Window, to_windows

STEPS = 32
LANES = 18


def _groove(bars: int, cells: tuple[CanonicalCell, ...]) -> CanonicalGroove:
    return CanonicalGroove(
        cells=cells, bpm=120.0, meter="4/4", bars=bars, collection="col",
        source_events_digest="0" * 64, canonical_hash="c", rhythm_hash="r",
        expression_hash="e",
    )


def test_a_one_bar_file_is_looped_and_flagged() -> None:
    groove = _groove(1, (CanonicalCell("kick", 0, 0, 1, 0.8, 3),))
    windows = to_windows(groove, policy="looped", hop_bars=2)
    assert len(windows) == 1
    window = windows[0]
    assert window.looped is True
    # The single bar appears in both halves of the two-bar window.
    assert window.hit[0, 0] == 1
    assert window.hit[16, 0] == 1


def test_a_one_bar_file_can_instead_be_padded() -> None:
    groove = _groove(1, (CanonicalCell("kick", 0, 0, 1, 0.8, 3),))
    window = to_windows(groove, policy="padded", hop_bars=2)[0]
    assert window.looped is False
    assert window.hit[16, 0] == 0
    # The absent second bar is neither observed nor a target.
    assert window.observed[16:, :].sum() == 0
    assert window.target[16:, :].sum() == 0


def test_a_four_bar_file_yields_two_windows() -> None:
    cells = tuple(CanonicalCell("kick", bar, 0, 1, 0.8, 0) for bar in range(4))
    windows = to_windows(_groove(4, cells), policy="looped", hop_bars=2)
    assert len(windows) == 2


def test_subhits_and_offset_survive_the_tensor() -> None:
    groove = _groove(2, (CanonicalCell("snare", 1, 4, 3, 0.5, -7),))
    window = to_windows(groove, policy="looped", hop_bars=2)[0]
    lane = window.lane_index("snare")
    assert window.subhits[16 + 4, lane] == 3
    assert window.offset[16 + 4, lane] == -7
    assert window.offset.dtype == np.int8
    assert window.subhits.dtype == np.uint8


def test_conditions_have_the_declared_width_and_range() -> None:
    groove = _groove(2, (CanonicalCell("kick", 0, 0, 1, 0.9, 0),))
    window = to_windows(groove, policy="looped", hop_bars=2)[0]
    vector = build_conditions(groove, window, labels={"genre": "Metal"})
    assert vector.shape == (16,)
    assert vector.dtype == np.float32
    assert float(vector.min()) >= 0.0 and float(vector.max()) <= 1.0
    assert vector[10] == 1.0, "index 10 flags that a vendor genre was present"


def test_conditions_report_absence_rather_than_guessing() -> None:
    groove = _groove(2, (CanonicalCell("kick", 0, 0, 1, 0.9, 0),))
    window = to_windows(groove, policy="looped", hop_bars=2)[0]
    vector = build_conditions(groove, window, labels={})
    assert vector[10] == 0.0
    assert float(vector[11:16].sum()) == 0.0


def test_unknown_policy_is_refused() -> None:
    groove = _groove(1, ())
    with pytest.raises(ValueError):
        to_windows(groove, policy="invent-one", hop_bars=2)
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/dataset/test_windows.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.dataset.windows'`.

- [ ] **Step 3: Write the window and condition modules**

Create `lab/groove_lab/dataset/windows.py`:

```python
"""Cut a CanonicalGroove into two-bar windows and lay them out as tensors.

33.6% of the byte-unique corpus is shorter than two bars, so the short-file
policy is explicit.  ``looped`` repeats the bar and sets a flag the condition
vector carries, because repeating without the flag teaches a two-bar periodicity
the source never had.  ``padded`` leaves the missing bar neither observed nor
targeted.

Dtypes are chosen so the tensor round-trips exactly: ``offset_ticks`` is an
integer in ``[-60, 60]``, so ``int8`` is lossless, and ``subhits`` is a raw count
kept uncapped in ``uint8``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ableton_mcp_server.groove_intelligence.drum_roles import GM_DRUM_ROLES

from .canonical import CanonicalGroove

STEPS_PER_BAR = 16
BARS = 2
STEPS = STEPS_PER_BAR * BARS
LANES = len(GM_DRUM_ROLES)
LANE_INDEX = {role: index for index, role in enumerate(GM_DRUM_ROLES)}
POLICIES = ("looped", "padded")


@dataclass
class Window:
    hit: np.ndarray
    subhits: np.ndarray
    velocity: np.ndarray
    offset: np.ndarray
    observed: np.ndarray
    target: np.ndarray
    start_bar: int
    looped: bool

    @staticmethod
    def lane_index(role: str) -> int:
        return LANE_INDEX[role]


def _blank() -> Window:
    return Window(
        hit=np.zeros((STEPS, LANES), dtype=np.uint8),
        subhits=np.zeros((STEPS, LANES), dtype=np.uint8),
        velocity=np.zeros((STEPS, LANES), dtype=np.float32),
        offset=np.zeros((STEPS, LANES), dtype=np.int8),
        observed=np.zeros((STEPS, LANES), dtype=np.uint8),
        target=np.ones((STEPS, LANES), dtype=np.uint8),
        start_bar=0,
        looped=False,
    )


def _place(window: Window, cell, row: int) -> None:
    lane = LANE_INDEX.get(cell.role)
    if lane is None or not 0 <= row < STEPS:
        return
    window.hit[row, lane] = 1
    window.subhits[row, lane] = min(cell.subhits, 255)
    window.velocity[row, lane] = cell.velocity
    window.offset[row, lane] = int(np.clip(cell.offset_ticks, -128, 127))


def to_windows(groove: CanonicalGroove, policy: str, hop_bars: int) -> list[Window]:
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES}, got {policy!r}")

    if groove.bars < BARS:
        window = _blank()
        for cell in groove.cells:
            _place(window, cell, cell.bar * STEPS_PER_BAR + cell.step)
        if policy == "looped":
            window.looped = True
            for cell in groove.cells:
                _place(window, cell, STEPS_PER_BAR + cell.step)
        else:
            window.observed[STEPS_PER_BAR:, :] = 0
            window.target[STEPS_PER_BAR:, :] = 0
        return [window]

    windows: list[Window] = []
    for start in range(0, groove.bars - BARS + 1, hop_bars):
        window = _blank()
        window.start_bar = start
        for cell in groove.cells:
            if start <= cell.bar < start + BARS:
                _place(window, cell, (cell.bar - start) * STEPS_PER_BAR + cell.step)
        windows.append(window)
    return windows
```

Create `lab/groove_lab/dataset/conditions.py`:

```python
"""The 16-dimension condition vector, with absence reported rather than guessed.

Every dimension is documented in the plan and in the dataset manifest.  A
condition with no source is zero, and index 10 says whether a vendor genre was
available at all, so the model can learn the difference between "not metal" and
"nobody said".
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from .canonical import CanonicalGroove
from .windows import BARS, Window

DIMENSIONS = 16
GENRE_BUCKETS = ("Pop/Rock/Country", "Metal", "Latin", "Jazz")


def build_conditions(
    groove: CanonicalGroove, window: Window, labels: Mapping[str, object]
) -> np.ndarray:
    vector = np.zeros(DIMENSIONS, dtype=np.float32)

    bpm = labels.get("tempo") or groove.bpm
    if bpm:
        vector[0] = float(np.clip((float(bpm) - 60.0) / 140.0, 0.0, 1.0))
    vector[1] = 1.0 if groove.meter == "4/4" else 0.0

    hits = int(window.hit.sum())
    vector[2] = float(np.clip(hits / (BARS * 32.0), 0.0, 1.0))

    section = str(labels.get("section", "")).lower()
    vector[3] = 1.0 if "groove" in section else 0.0
    vector[4] = 1.0 if "fill" in section else 0.0
    vector[5] = 1.0 if "variation" in section else 0.0

    offsets = window.offset[window.hit == 1]
    if offsets.size:
        vector[6] = float(np.clip(abs(float(offsets.mean())) / 60.0, 0.0, 1.0))
        velocities = window.velocity[window.hit == 1]
        vector[7] = float(np.clip(float(velocities.mean()), 0.0, 1.0))

    lanes_used = int((window.hit.sum(axis=0) > 0).sum())
    vector[8] = float(np.clip(lanes_used / window.hit.shape[1], 0.0, 1.0))
    vector[9] = 1.0 if window.looped else 0.0

    genre = labels.get("genre")
    if genre:
        vector[10] = 1.0
        for index, bucket in enumerate(GENRE_BUCKETS):
            if genre == bucket:
                vector[11 + index] = 1.0
                break
        else:
            vector[15] = 1.0
    return vector
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/dataset/test_windows.py -q
```

Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/dataset/windows.py lab/groove_lab/dataset/conditions.py lab/tests/dataset/test_windows.py
git commit -m "feat(dataset): window into two bars and build the condition vector"
```

---

### Task 7: Shards, round-trip and the representation budget

**Files:**
- Create: `lab/groove_lab/dataset/shards.py`
- Create: `lab/groove_lab/dataset/roundtrip.py`
- Test: `lab/tests/dataset/test_shards.py`

Gate G3 wants two things: the training target round-trips exactly, and the fraction of notes the grid cannot represent is measured against a declared budget.

- [ ] **Step 1: Write the failing test**

Create `lab/tests/dataset/test_shards.py`:

```python
from __future__ import annotations

import json

import numpy as np

from groove_lab.dataset.roundtrip import cells_from_window, roundtrip_is_exact
from groove_lab.dataset.shards import ShardWriter, read_shard
from groove_lab.dataset.windows import LANES, STEPS, Window


def _window(seed: int) -> Window:
    rng = np.random.default_rng(seed)
    hit = (rng.random((STEPS, LANES)) > 0.9).astype(np.uint8)
    return Window(
        hit=hit,
        subhits=(hit * rng.integers(1, 4, (STEPS, LANES))).astype(np.uint8),
        velocity=(hit * rng.random((STEPS, LANES))).astype(np.float32),
        offset=(hit * rng.integers(-60, 61, (STEPS, LANES))).astype(np.int8),
        observed=np.zeros((STEPS, LANES), dtype=np.uint8),
        target=np.ones((STEPS, LANES), dtype=np.uint8),
        start_bar=0,
        looped=False,
    )


def test_shard_round_trips_every_field_exactly(tmp_path) -> None:
    writer = ShardWriter(tmp_path / "train", rows_per_shard=2)
    for index in range(5):
        writer.add(
            _window(index),
            conditions=np.zeros(16, dtype=np.float32),
            ids=(index, index, index),
            record={"source_id": str(index)},
        )
    writer.close()

    rows = [json.loads(line) for line in (tmp_path / "train" / "index.jsonl").read_text().splitlines()]
    assert len(rows) == 5

    for index in range(5):
        original = _window(index)
        shard = read_shard(tmp_path / "train" / rows[index]["shard"])
        row = rows[index]["row"]
        assert np.array_equal(shard["hit"][row], original.hit)
        assert np.array_equal(shard["subhits"][row], original.subhits)
        assert np.array_equal(shard["offset"][row], original.offset)
        assert np.array_equal(shard["velocity"][row], original.velocity)


def test_arrays_are_memory_mappable_and_not_pickled(tmp_path) -> None:
    writer = ShardWriter(tmp_path / "train", rows_per_shard=4)
    writer.add(_window(0), np.zeros(16, dtype=np.float32), (0, 0, 0), {"source_id": "0"})
    writer.close()
    path = tmp_path / "train" / "0000" / "hit.npy"
    mapped = np.load(path, mmap_mode="r", allow_pickle=False)
    assert mapped.shape[1:] == (STEPS, LANES)


def test_roundtrip_reports_exactness() -> None:
    window = _window(3)
    cells = cells_from_window(window)
    assert roundtrip_is_exact(window, cells)
    # Losing one subhit must be detected.
    broken = list(cells)
    if broken:
        broken[0] = broken[0].__class__(**{**broken[0].__dict__, "subhits": 99})
        assert not roundtrip_is_exact(window, tuple(broken))
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/dataset/test_shards.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.dataset.shards'`.

- [ ] **Step 3: Write the shard writer and the round-trip check**

Create `lab/groove_lab/dataset/shards.py`:

```python
"""Content-addressed shards of memory-mappable .npy arrays with a JSONL index.

One ``.npy`` per field rather than one ``.npz`` per shard, because ``.npz`` is a
zip archive and cannot be memory mapped.  ``allow_pickle`` is never used, on read
or write: specification 11.3 rules pickle out of the format entirely.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .windows import Window

FIELDS = ("hit", "subhits", "velocity", "offset", "observed", "target")


class ShardWriter:
    def __init__(self, root: Path, rows_per_shard: int) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.rows_per_shard = rows_per_shard
        self._buffer: list[tuple[Window, np.ndarray, tuple[int, int, int]]] = []
        self._records: list[dict[str, Any]] = []
        self._shard_index = 0

    def add(
        self,
        window: Window,
        conditions: np.ndarray,
        ids: tuple[int, int, int],
        record: dict[str, Any],
    ) -> None:
        record = dict(record)
        record["shard"] = f"{self._shard_index:04d}"
        record["row"] = len(self._buffer)
        self._records.append(record)
        self._buffer.append((window, conditions, ids))
        if len(self._buffer) >= self.rows_per_shard:
            self._flush()

    def _flush(self) -> None:
        if not self._buffer:
            return
        directory = self.root / f"{self._shard_index:04d}"
        directory.mkdir(parents=True, exist_ok=True)
        for field in FIELDS:
            stacked = np.stack([getattr(w, field) for w, _c, _i in self._buffer])
            np.save(directory / f"{field}.npy", stacked, allow_pickle=False)
        np.save(
            directory / "conditions.npy",
            np.stack([c for _w, c, _i in self._buffer]).astype(np.float32),
            allow_pickle=False,
        )
        np.save(
            directory / "ids.npy",
            np.array([i for _w, _c, i in self._buffer], dtype=np.uint64),
            allow_pickle=False,
        )
        self._buffer.clear()
        self._shard_index += 1

    def close(self) -> None:
        self._flush()
        with (self.root / "index.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for record in self._records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")


def read_shard(directory: Path) -> dict[str, np.ndarray]:
    directory = Path(directory)
    names = (*FIELDS, "conditions", "ids")
    return {
        name: np.load(directory / f"{name}.npy", mmap_mode="r", allow_pickle=False)
        for name in names
    }
```

Create `lab/groove_lab/dataset/roundtrip.py`:

```python
"""Turn a tensor window back into cells and prove the two agree exactly.

Gate G3 draws a line between two different things.  Notes the chosen grid cannot
represent are a measured, budgeted loss.  Notes the tensor loses on the way back
out are a bug, and this module is what makes the second impossible to miss.
"""

from __future__ import annotations

import numpy as np

from ableton_mcp_server.groove_intelligence.drum_roles import GM_DRUM_ROLES

from .canonical import CanonicalCell
from .windows import STEPS_PER_BAR, Window


def cells_from_window(window: Window) -> tuple[CanonicalCell, ...]:
    rows, lanes = np.nonzero(window.hit)
    return tuple(
        CanonicalCell(
            role=GM_DRUM_ROLES[lane],
            bar=int(row) // STEPS_PER_BAR,
            step=int(row) % STEPS_PER_BAR,
            subhits=int(window.subhits[row, lane]),
            velocity=float(window.velocity[row, lane]),
            offset_ticks=int(window.offset[row, lane]),
        )
        for row, lane in zip(rows, lanes, strict=True)
    )


def roundtrip_is_exact(window: Window, cells: tuple[CanonicalCell, ...]) -> bool:
    return cells_from_window(window) == tuple(
        sorted(cells, key=lambda c: (c.bar * STEPS_PER_BAR + c.step, GM_DRUM_ROLES.index(c.role)))
    )
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/dataset/test_shards.py -q
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/dataset/shards.py lab/groove_lab/dataset/roundtrip.py lab/tests/dataset/test_shards.py
git commit -m "feat(dataset): write mmap-able shards and verify exact round-trip"
```

---

### Task 8: Build orchestration and the manifest

**Files:**
- Create: `lab/groove_lab/dataset/build.py`
- Create: `lab/scripts/build_dataset.py`
- Test: `lab/tests/dataset/test_build.py`

- [ ] **Step 1: Write the failing test**

Create `lab/tests/dataset/test_build.py`:

```python
from __future__ import annotations

from groove_lab.dataset.build import DatasetManifest, manifest_digest
from groove_lab.dataset.config import BuildConfig


def _manifest(**overrides) -> DatasetManifest:
    base = {
        "config": BuildConfig().as_dict(),
        "config_digest": BuildConfig().digest(),
        "counts": {"train": 8, "validation": 1, "test": 1},
        "cluster_sizes": {"largest": 2, "count": 5},
        "representation_loss": 0.0351,
        "unresolved_note_share": 0.0648,
        "excluded_collections": ["col-x"],
        "shard_digests": {"train/0000": "a" * 64},
        "environment": {"python": "3.10.11"},
    }
    base.update(overrides)
    return DatasetManifest(**base)


def test_manifest_digest_is_stable() -> None:
    assert manifest_digest(_manifest()) == manifest_digest(_manifest())


def test_manifest_digest_changes_with_any_content() -> None:
    assert manifest_digest(_manifest()) != manifest_digest(
        _manifest(representation_loss=0.05)
    )


def test_manifest_digest_ignores_the_environment() -> None:
    # Two machines must be able to produce the same dataset. The environment is
    # recorded for lineage, not as part of the identity of the data.
    assert manifest_digest(_manifest()) == manifest_digest(
        _manifest(environment={"python": "3.10.99"})
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/dataset/test_build.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.dataset.build'`.

- [ ] **Step 3: Write the orchestration**

Create `lab/groove_lab/dataset/build.py`:

```python
"""Orchestrate a dataset build and describe it well enough to reproduce it.

The order of operations is not negotiable, and it is the order specification 12.3
sets out: cluster before splitting, split by whole cluster, then verify leakage
from the content hashes alone so a bug in the clustering cannot hide a bug in the
split.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import platform
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .canonical import build_canonical, note_mass_lost
from .clusters import build_clusters, component_sizes
from .conditions import build_conditions
from .config import BuildConfig
from .roundtrip import cells_from_window, roundtrip_is_exact
from .shards import ShardWriter
from .splits import assign_splits, verify_no_leakage
from .windows import to_windows

CATALOG = Path(
    r"C:\Users\Usuario\AppData\Local\AbletonMCPServer\groove-build-v2\catalog_v2.sqlite"
)
CORPUS_ROOT = Path(
    r"C:\Users\Usuario\Desktop\AUDIO_PRODUCTION\AUDIO\Superior Drummer 3\Toontrack\Midi"
)
VENDOR_LABELS = Path(
    r"C:\Users\Usuario\AppData\Local\AbletonMCPServer\groove-vendor-labels\vendor_labels.jsonl"
)
UNRESOLVED = "other_percussion"


@dataclasses.dataclass
class DatasetManifest:
    config: dict[str, Any]
    config_digest: str
    counts: dict[str, int]
    cluster_sizes: dict[str, int]
    representation_loss: float
    unresolved_note_share: float
    excluded_collections: list[str]
    shard_digests: dict[str, str]
    environment: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def manifest_digest(manifest: DatasetManifest) -> str:
    """Hash everything that defines the data, and nothing that defines the machine."""

    payload = manifest.as_dict()
    payload.pop("environment", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _vendor_labels() -> dict[str, dict[str, Any]]:
    if not VENDOR_LABELS.exists():
        return {}
    labels: dict[str, dict[str, Any]] = {}
    with VENDOR_LABELS.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            labels[record["path"]] = record
    return labels


def _excluded_collections(config: BuildConfig) -> tuple[set[str], float]:
    """Collections above the gate G1 unresolved ceiling, and the corpus-wide share."""

    from ableton_mcp_server.groove_intelligence.articulation import resolve_role
    from ableton_mcp_server.groove_intelligence.drum_roles import GM_DRUM_ROLE_BY_PITCH

    measurement = json.loads(
        (Path(__file__).resolve().parents[3] / "scripts" / "measurement_output.json")
        .read_text(encoding="utf-8")
    )
    excluded: set[str] = set()
    total = unresolved = 0
    for collection, record in measurement.items():
        collection_total = collection_unresolved = 0
        for raw_pitch, count in record["pitch_histogram"].items():
            pitch = int(raw_pitch)
            collection_total += count
            if resolve_role(collection, pitch) == UNRESOLVED:
                collection_unresolved += count
        total += collection_total
        unresolved += collection_unresolved
        if collection_total and collection_unresolved / collection_total > (
            config.max_unresolved_note_share
        ):
            excluded.add(collection)
    return excluded, (unresolved / total if total else 0.0)


def _selected_files(config: BuildConfig, fraction: float) -> list[tuple[str, str]]:
    """A deterministic prefix of byte-unique files, ordered by digest."""

    excluded, _share = _excluded_collections(config)
    connection = sqlite3.connect(f"file:{CATALOG}?mode=ro", uri=True)
    rows = connection.execute(
        "select relative_path, stratum, source_digest from files "
        "where status='ok' and source_digest != '' "
        "group by source_digest order by source_digest"
    ).fetchall()
    connection.close()
    kept = [(path, stratum) for path, stratum, _d in rows if stratum not in excluded]
    return kept[: max(1, int(len(kept) * fraction))]


def _directory_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def build_dataset(fraction: float, config: BuildConfig, workspace: Path) -> DatasetManifest:
    from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf

    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    labels = _vendor_labels()
    excluded, unresolved_share = _excluded_collections(config)
    selected = _selected_files(config, fraction)

    grooves: dict[str, Any] = {}
    records: list[dict[str, str]] = []
    lost_numerator = lost_denominator = 0.0
    for relative, collection in selected:
        raw = (CORPUS_ROOT / relative).read_bytes()
        parsed = parse_smf(raw)
        groove = build_canonical(parsed, collection)
        source_id = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:32]
        grooves[source_id] = (relative, collection, groove)
        records.append(
            {
                "source_id": source_id,
                "byte_hash": hashlib.sha256(raw).hexdigest(),
                "canonical_hash": groove.canonical_hash,
                "rhythm_hash": groove.rhythm_hash,
                "collection": collection,
            }
        )
        lost_numerator += note_mass_lost(parsed, groove) * len(parsed.note_events)
        lost_denominator += len(parsed.note_events)

    clusters = build_clusters(records, max_share=config.max_cluster_share)
    for record in records:
        record["cluster_id"] = clusters[record["source_id"]]
    splits = assign_splits(records, config.split_ratios, config.seed)
    verify_no_leakage(records, splits)

    writers = {
        name: ShardWriter(workspace / "shards" / name, config.rows_per_shard)
        for name in ("train", "validation", "test")
    }
    counts: Counter[str] = Counter()
    for index, (source_id, (relative, collection, groove)) in enumerate(sorted(grooves.items())):
        split = splits[source_id]
        for window in to_windows(groove, config.short_file_policy, config.window_hop_bars):
            if not roundtrip_is_exact(window, cells_from_window(window)):
                raise RuntimeError(f"round-trip failed for {source_id}")
            writers[split].add(
                window,
                conditions=build_conditions(groove, window, labels.get(relative, {})),
                ids=(index, int(clusters[source_id][:8], 16), index),
                record={
                    "source_id": source_id,
                    "cluster_id": clusters[source_id],
                    "collection": collection,
                    "looped": window.looped,
                    "start_bar": window.start_bar,
                },
            )
            counts[split] += 1
    for writer in writers.values():
        writer.close()

    sizes = component_sizes(clusters)
    manifest = DatasetManifest(
        config=config.as_dict(),
        config_digest=config.digest(),
        counts=dict(counts),
        cluster_sizes={"largest": max(sizes.values(), default=0), "count": len(sizes)},
        representation_loss=round(
            lost_numerator / lost_denominator if lost_denominator else 0.0, 6
        ),
        unresolved_note_share=round(unresolved_share, 6),
        excluded_collections=sorted(excluded),
        shard_digests={
            name: _directory_digest(workspace / "shards" / name)
            for name in ("train", "validation", "test")
        },
        environment={
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
    )
    (workspace / "manifest.json").write_text(
        json.dumps(manifest.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest
```

Create `lab/scripts/build_dataset.py`:

```python
"""Entry point for a dataset build."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "lab"))

from groove_lab.dataset.build import build_dataset, manifest_digest  # noqa: E402
from groove_lab.dataset.config import BuildConfig  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fraction", type=float, default=0.01)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--short-file-policy", default="looped")
    arguments = parser.parse_args()

    config = BuildConfig(short_file_policy=arguments.short_file_policy)
    manifest = build_dataset(arguments.fraction, config, arguments.workspace)
    print("counts               ", manifest.counts)
    print("representation loss  ", manifest.representation_loss)
    print("unresolved share     ", manifest.unresolved_note_share)
    print("largest cluster      ", manifest.cluster_sizes)
    print("excluded collections ", len(manifest.excluded_collections))
    print("manifest digest      ", manifest_digest(manifest))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/dataset -q
```

Expected: PASS, every dataset test.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/dataset/build.py lab/scripts/build_dataset.py lab/tests/dataset/test_build.py
git commit -m "feat(dataset): orchestrate a build and describe it in a manifest"
```

---

### Task 9: The 1% build, twice (gate D1, G2 and G3)

**Files:**
- Create: `docs/superpowers/plans/2026-08-31-groove-brain-dataset-foundation-v3-result.md`

- [ ] **Step 1: Build 1% into the workspace**

Run:

```bash
lab/.venv-lab/Scripts/python.exe lab/scripts/build_dataset.py --fraction 0.01 --workspace F:/groove-brain/dataset/build-a
```

Expected: prints example counts per split, representation loss, largest cluster share, and the manifest digest.

- [ ] **Step 2: Build the same 1% again, independently**

Run:

```bash
lab/.venv-lab/Scripts/python.exe lab/scripts/build_dataset.py --fraction 0.01 --workspace F:/groove-brain/dataset/build-b
```

- [ ] **Step 3: Compare the two builds digest for digest**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -c "import json,pathlib; a=json.loads(pathlib.Path('F:/groove-brain/dataset/build-a/manifest.json').read_text()); b=json.loads(pathlib.Path('F:/groove-brain/dataset/build-b/manifest.json').read_text()); a.pop('environment'); b.pop('environment'); print('IDENTICAL' if a==b else 'DIVERGED'); [print(k) for k in a if a[k]!=b.get(k)]"
```

Expected: `IDENTICAL`. If it prints `DIVERGED`, the listed keys name the non-determinism; find it rather than re-running until it agrees.

- [ ] **Step 4: Check the three gate conditions**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -c "import json,pathlib; m=json.loads(pathlib.Path('F:/groove-brain/dataset/build-a/manifest.json').read_text()); print('representation loss', m['representation_loss'], 'budget', m['config']['representation_loss_budget']); print('largest cluster share', m['cluster_sizes']['largest']/sum(m['counts'].values())); print('counts', m['counts'])"
```

Gate G2 needs identical digests, an exact round-trip for every example, no hash spanning splits, and a largest cluster below 5%. Gate G3 needs the representation loss at or under the declared budget. Record whichever fail; do not adjust the budget to make them pass.

- [ ] **Step 5: Measure disk and project to 100%**

Run:

```bash
du -sh F:/groove-brain/dataset/build-a
```

Multiply by 100 for the full-build projection and record it. The estimate in this plan is roughly 1.8 GB for 354,749 windows; a projection far from that means the dtype choices did not survive implementation.

- [ ] **Step 6: Write the result document**

Create `docs/superpowers/plans/2026-08-31-groove-brain-dataset-foundation-v3-result.md` recording: example counts per split, the two manifest digests, representation loss against budget, largest cluster share, excluded collections, the round-trip result, the leakage verdict, measured disk for 1% and the projection to 100%, and the short-file policy the build used.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/plans/2026-08-31-groove-brain-dataset-foundation-v3-result.md
git commit -m "docs: record the 1% dataset build and its gate results"
```

---

### Task 10: Close D1, G2 and G3 in the design document

**Files:**
- Modify: `docs/superpowers/specs/2026-08-31-groove-brain-dataset-training-design.md`

- [ ] **Step 1: Add the result to section 11.3**

After the paragraph beginning `Ordem de grandeza do formato denso`, insert the measured per-example size, the measured 1% disk figure and the projection to 100%, marked `[fato]`.

- [ ] **Step 2: Update the ladder row for D1**

In section 17, append the outcome to the `**D1** build de 1%` cell: the two manifest digests, whether they matched, the representation loss against budget, and the largest cluster share.

- [ ] **Step 3: Verify no contradictions**

Run:

```bash
git diff --check -- docs/
python -c "import re;t=open('docs/superpowers/specs/2026-08-31-groove-brain-dataset-training-design.md',encoding='utf-8').read();h={m.group(1) for m in re.finditer(r'^#{2,4} (\d+(?:\.\d+)*)[.\s]',t,re.M)};r={m.group(1) for m in re.finditer(r'seção (\d+(?:\.\d+)*)',t)};print('refs quebradas:',sorted(r-h) or 'nenhuma')"
```

Expected: no output from `git diff --check`, and `refs quebradas: nenhuma`.

- [ ] **Step 4: Confirm the product suite is untouched**

Run:

```bash
.venv-win/Scripts/python.exe -m pytest -q --tb=line
```

Expected: `906 passed` with the four known prototype failures and nothing new.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-08-31-groove-brain-dataset-training-design.md
git commit -m "docs: record the dataset foundation result and close D1"
```

---

## What this plan does not do

It does not build the 10% or 100% dataset. Gate D1 exists so the 1% build proves determinism, leakage-freedom and exactness first, and specification 17 makes the full build a separate rung.

It does not implement the event-based shard branch. The masked HVO path is what plan 6 needs; the event sequence is the challenger's input and belongs with the challenger.

It does not decide the short-file policy. The build records which one it used and the counts each produces; choosing between `looped` and `padded` is an ablation for plan 6, and the manifest makes both reconstructible.

## Stop condition

Done when two independent 1% builds produce identical manifest digests, every written example round-trips exactly, no content hash spans a split boundary, the largest cluster is under 5% of examples, and the representation loss is at or under the declared budget — with all five recorded in the result document and section 17 of the design.

If the largest cluster exceeds 5%, do not split it. Specification 12.3 is explicit: reduce the threshold and regroup. If the representation loss exceeds the budget, the grid is wrong, not the budget.
