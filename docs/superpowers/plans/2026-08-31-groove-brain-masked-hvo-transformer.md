# Groove Brain Masked HVO Transformer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Train the masked HVO transformer on the V3 dataset until it provably memorises a tiny set, then run it at 1% and show it generates structurally valid, non-degenerate grooves — closing rungs M0 and M1 and gate G4.

**Architecture:** The `StepTokenHvo` model the CPU spike selected, extended with a task embedding, trained through a versioned task sampler that decides per example which cells are observed and which are targets. Four masked heads — hit, subhits, velocity, offset — with losses that only see cells the task actually asked for. Generation reuses the iterative confidence decoder already written for the spike.

**Tech Stack:** The lab CPU-only environment. PyTorch 2.12 CPU, the `.npy` mmap shards from plan 4, no GPU.

---

## Scope, narrowed on purpose

Specification section 21 lists plan 6 as closing M0, M1, M2, G4 and G5. This plan
closes **M0, M1 and G4 only**, and the reason is a real dependency rather than a
convenience:

- **G5, the bake-off**, requires the challenger to beat the best baseline. The
  baselines — retrieval, deterministic transforms, GrooVAE, event AR — are plan
  5. Comparing against nothing would not be a bake-off.
- **M2, the 10% run**, wants three seeds per candidate over ten times the data.
  That is where a GPU stops being optional, and the training workspace is plan 1.

Everything M0, M1 and G4 need runs on CPU with the 1% dataset that already
exists, so this plan does not wait for either.

## What plans 3 and 4 already decided

| Decision | Source |
|---|---|
| Tokenisation is **step-token**: 32 tokens, lanes folded into channels | plan 3, spec 19.4 |
| Decoding is budgeted at **32 iterative steps** | plan 3 |
| `intra_op_num_threads=1`; more threads make the CPU budget worse | plan 3 |
| Model is the small tier, ≈4.8M parameters | plan 3 |
| Dataset lives at `F:\groove-brain\dataset\build-a\`, 2,269 train / 226 validation / 252 test windows | plan 4 |
| Stored `target` marks which cells are *legitimate* targets; padding is already excluded | plan 4 |
| `subhits` is stored uncapped; clamping to the head's four classes costs **0.0214%** of hit cells | measured here |

That clamp figure is the number plan 4 promised to report. It is small enough
that a four-class head is not the constraint, and it is recorded rather than
assumed.

## Two tasks deliberately not implemented

The specification lists eight training tasks. This plan implements six and defers
two, each for a reason the specification itself gives:

- **`humanize`** — section 14 promotes it only if the *residual* offset, not the
  systematic swing bias, has useful variety, and requires D0 to decompose the two
  first. That decomposition has not been run. Implementing the task before the
  evidence would be exactly the thing this document keeps refusing to do.
- **`reference`** — needs a reference-encoder path through the model. G4 does not
  evaluate it, and the bake-off in plan 5 is where it would actually be measured.
  Adding architecture that nothing yet tests is scope with no gate behind it.

Both are recorded in the task-mix config as `enabled: false` with these reasons,
so turning them on later is a config change plus an implementation, not an
archaeology exercise.

## File Structure

| Path | Responsibility |
|---|---|
| `lab/groove_lab/training/__init__.py` | Package marker |
| `lab/groove_lab/training/loader.py` | Read mmap shards into batches |
| `lab/groove_lab/training/tasks.py` | The six task maskers and their mix |
| `lab/groove_lab/training/model.py` | `StepTokenHvo` plus a task embedding |
| `lab/groove_lab/training/losses.py` | Masked hit, subhits, velocity, offset losses |
| `lab/groove_lab/training/loop.py` | Train, evaluate, checkpoint, resume |
| `lab/groove_lab/training/generate.py` | Decode and score validity and diversity |
| `lab/scripts/train_masked_hvo.py` | Entry point for M0 and M1 |
| `lab/tests/training/test_*.py` | One test module per unit |

---

### Task 1: Batch loader over the mmap shards

**Files:**
- Create: `lab/groove_lab/training/__init__.py`
- Create: `lab/groove_lab/training/loader.py`
- Test: `lab/tests/training/test_loader.py`

- [ ] **Step 1: Write the failing test**

Create `lab/tests/training/test_loader.py`:

```python
from __future__ import annotations

import numpy as np
import pytest

from groove_lab.training.loader import ShardDataset, clamp_cost

DATASET = "F:/groove-brain/dataset/build-a"


@pytest.fixture(scope="module")
def train() -> ShardDataset:
    return ShardDataset(DATASET, split="train", max_subhits=4)


def test_dataset_reports_its_size(train: ShardDataset) -> None:
    assert len(train) == 2269


def test_an_example_has_every_field_with_the_right_dtype(train: ShardDataset) -> None:
    example = train[0]
    for name in ("hit", "subhits", "velocity", "offset", "valid"):
        assert example[name].shape == (32, 18), name
    assert example["conditions"].shape == (16,)
    assert example["hit"].dtype == np.float32
    assert example["subhits"].dtype == np.int64
    assert example["valid"].dtype == np.float32


def test_subhits_are_clamped_to_the_head_and_the_cost_is_known(train: ShardDataset) -> None:
    for index in range(50):
        assert int(train[index]["subhits"].max()) <= 3
    # Measured over the 1% train split: 0.0214% of hit cells exceed three events.
    assert clamp_cost(DATASET, split="train", max_subhits=4) < 0.001


def test_batches_are_deterministic_for_a_seed(train: ShardDataset) -> None:
    first = train.batch_indices(batch_size=8, seed=3)
    second = train.batch_indices(batch_size=8, seed=3)
    assert first == second
    assert first != train.batch_indices(batch_size=8, seed=4)


def test_collate_stacks_into_arrays(train: ShardDataset) -> None:
    batch = train.collate([0, 1, 2])
    assert batch["hit"].shape == (3, 32, 18)
    assert batch["conditions"].shape == (3, 16)
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/training/test_loader.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.training'`.

- [ ] **Step 3: Write the loader**

Create `lab/groove_lab/training/__init__.py`:

```python
"""Training the masked HVO transformer. Nothing here ships."""
```

Create `lab/groove_lab/training/loader.py`:

```python
"""Read the V3 shards without copying them into memory.

The shards are ``.npy`` arrays written for exactly this: ``mmap_mode='r'`` keeps
the 2.4 GB full build off the heap.  The stored ``target`` array marks which
cells are legitimate targets at all — padding from the short-file policy is
already excluded — so it is loaded as ``valid`` and the task sampler intersects
with it rather than overriding it.
"""

from __future__ import annotations

import json
import random
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

FIELDS = ("hit", "subhits", "velocity", "offset", "target", "conditions")


class ShardDataset:
    def __init__(self, root: str | Path, split: str, max_subhits: int) -> None:
        self.root = Path(root) / "shards" / split
        self.max_subhits = max_subhits
        lines = (self.root / "index.jsonl").read_text(encoding="utf-8").splitlines()
        self.index: list[dict[str, Any]] = [json.loads(line) for line in lines]
        self._shards: dict[str, dict[str, np.ndarray]] = {}

    def __len__(self) -> int:
        return len(self.index)

    def _shard(self, name: str) -> dict[str, np.ndarray]:
        if name not in self._shards:
            directory = self.root / name
            self._shards[name] = {
                field: np.load(directory / f"{field}.npy", mmap_mode="r", allow_pickle=False)
                for field in FIELDS
            }
        return self._shards[name]

    def __getitem__(self, position: int) -> dict[str, np.ndarray]:
        record = self.index[position]
        shard = self._shard(record["shard"])
        row = record["row"]
        return {
            "hit": np.asarray(shard["hit"][row], dtype=np.float32),
            "subhits": np.clip(
                np.asarray(shard["subhits"][row], dtype=np.int64), 0, self.max_subhits - 1
            ),
            "velocity": np.asarray(shard["velocity"][row], dtype=np.float32),
            "offset": np.asarray(shard["offset"][row], dtype=np.float32) / 60.0,
            "valid": np.asarray(shard["target"][row], dtype=np.float32),
            "conditions": np.asarray(shard["conditions"][row], dtype=np.float32),
        }

    def batch_indices(self, batch_size: int, seed: int) -> list[list[int]]:
        order = list(range(len(self)))
        random.Random(seed).shuffle(order)
        return [order[i : i + batch_size] for i in range(0, len(order), batch_size)]

    def collate(self, positions: list[int]) -> dict[str, np.ndarray]:
        examples = [self[position] for position in positions]
        return {key: np.stack([e[key] for e in examples]) for key in examples[0]}


@lru_cache(maxsize=8)
def clamp_cost(root: str, split: str, max_subhits: int) -> float:
    """Share of hit cells whose event count the head's class range cannot hold."""

    dataset = ShardDataset(root, split, max_subhits=256)
    over = total = 0
    for position in range(len(dataset)):
        example = dataset[position]
        counts = example["subhits"][example["hit"] == 1.0]
        total += int(counts.size)
        over += int((counts > max_subhits - 1).sum())
    return over / total if total else 0.0
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/training/test_loader.py -q
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/training/__init__.py lab/groove_lab/training/loader.py lab/tests/training/test_loader.py
git commit -m "feat(training): read the V3 shards without copying them"
```

---

### Task 2: The task sampler

**Files:**
- Create: `lab/groove_lab/training/tasks.py`
- Test: `lab/tests/training/test_tasks.py`

Every task produces one thing: an `observed` mask and a `target` mask, both
intersected with the stored validity mask so padding is never a target.

- [ ] **Step 1: Write the failing test**

Create `lab/tests/training/test_tasks.py`:

```python
from __future__ import annotations

import numpy as np
import pytest

from groove_lab.training.tasks import TASKS, TASK_MIX, apply_task, sample_task


@pytest.fixture
def valid() -> np.ndarray:
    return np.ones((32, 18), dtype=np.float32)


def test_the_six_enabled_tasks_are_the_ones_documented() -> None:
    enabled = {name for name, spec in TASK_MIX.items() if spec["enabled"]}
    assert enabled == {
        "free_generation",
        "variation",
        "temporal_infill",
        "lane_infill",
        "fill",
        "continuation",
    }


def test_the_deferred_tasks_carry_their_reason() -> None:
    for name in ("humanize", "reference"):
        assert TASK_MIX[name]["enabled"] is False
        assert len(TASK_MIX[name]["reason"]) > 40, name


@pytest.mark.parametrize("task", sorted(TASKS))
def test_observed_and_target_never_overlap(task: str, valid: np.ndarray) -> None:
    observed, target = apply_task(task, valid, rng=np.random.default_rng(0))
    assert not np.any((observed > 0) & (target > 0)), task


@pytest.mark.parametrize("task", sorted(TASKS))
def test_nothing_outside_the_validity_mask_is_ever_a_target(task: str) -> None:
    valid = np.ones((32, 18), dtype=np.float32)
    valid[16:, :] = 0.0  # a padded second bar
    observed, target = apply_task(task, valid, rng=np.random.default_rng(1))
    assert target[16:, :].sum() == 0.0, task
    assert observed[16:, :].sum() == 0.0, task


def test_free_generation_targets_everything_valid(valid: np.ndarray) -> None:
    observed, target = apply_task("free_generation", valid, rng=np.random.default_rng(0))
    assert observed.sum() == 0.0
    assert target.sum() == valid.sum()


def test_continuation_observes_the_first_bar_and_targets_the_second(valid) -> None:
    observed, target = apply_task("continuation", valid, rng=np.random.default_rng(0))
    assert observed[:16, :].all()
    assert target[16:, :].all()
    assert target[:16, :].sum() == 0.0


def test_lane_infill_removes_whole_lanes(valid: np.ndarray) -> None:
    observed, target = apply_task("lane_infill", valid, rng=np.random.default_rng(2))
    targeted = target.sum(axis=0)
    assert set(np.unique(targeted)) <= {0.0, 32.0}
    assert 0 < (targeted > 0).sum() < 18


def test_temporal_infill_removes_a_contiguous_range(valid: np.ndarray) -> None:
    _observed, target = apply_task("temporal_infill", valid, rng=np.random.default_rng(3))
    rows = np.nonzero(target.sum(axis=1))[0]
    assert rows.size > 0
    assert rows.tolist() == list(range(rows[0], rows[-1] + 1))


def test_sampling_is_deterministic_for_a_seed() -> None:
    rng = np.random.default_rng(9)
    first = [sample_task(rng) for _ in range(20)]
    rng = np.random.default_rng(9)
    assert [sample_task(rng) for _ in range(20)] == first
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/training/test_tasks.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.training.tasks'`.

- [ ] **Step 3: Write the sampler**

Create `lab/groove_lab/training/tasks.py`:

```python
"""What the model is asked to predict, and what it is allowed to see.

Specification section 14 lists eight tasks.  Six are implemented; ``humanize``
and ``reference`` are declared here with the reason they are off, so enabling
them later is a config change and an implementation rather than a rediscovery.

Every masker returns ``(observed, target)`` intersected with the stored validity
mask, so a cell that does not exist — the padded second bar of a one-bar file —
is never observed and never a target.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

STEPS_PER_BAR = 16

TASK_MIX: dict[str, dict[str, object]] = {
    "free_generation": {"enabled": True, "weight": 0.30, "reason": ""},
    "variation": {"enabled": True, "weight": 0.20, "reason": ""},
    "temporal_infill": {"enabled": True, "weight": 0.15, "reason": ""},
    "lane_infill": {"enabled": True, "weight": 0.15, "reason": ""},
    "fill": {"enabled": True, "weight": 0.10, "reason": ""},
    "continuation": {"enabled": True, "weight": 0.10, "reason": ""},
    "humanize": {
        "enabled": False,
        "weight": 0.0,
        "reason": (
            "Specification 14 promotes humanize only once D0 has separated the "
            "systematic swing bias from the residual jitter, because an aggregate "
            "offset spread cannot tell a swung corpus from an expressive one. That "
            "decomposition has not been run."
        ),
    },
    "reference": {
        "enabled": False,
        "weight": 0.0,
        "reason": (
            "Needs a reference-encoder path through the model. Gate G4 does not "
            "evaluate it and the bake-off in plan 5 is where it would be measured, "
            "so adding the architecture now would be scope with no gate behind it."
        ),
    },
}


def _free_generation(valid: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    return np.zeros_like(valid), valid.copy()


def _variation(valid: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    keep = (rng.random(valid.shape) < rng.uniform(0.3, 0.7)).astype(np.float32)
    observed = keep * valid
    return observed, valid - observed


def _temporal_infill(valid: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    steps = valid.shape[0]
    length = int(rng.integers(4, max(5, steps // 2)))
    start = int(rng.integers(0, steps - length + 1))
    target = np.zeros_like(valid)
    target[start : start + length, :] = 1.0
    target *= valid
    return valid - target, target


def _lane_infill(valid: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    lanes = valid.shape[1]
    count = int(rng.integers(1, max(2, lanes // 3)))
    chosen = rng.choice(lanes, size=count, replace=False)
    target = np.zeros_like(valid)
    target[:, chosen] = 1.0
    target *= valid
    return valid - target, target


def _fill(valid: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    target = np.zeros_like(valid)
    target[STEPS_PER_BAR:, :] = 1.0
    target *= valid
    return valid - target, target


def _continuation(valid: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    return _fill(valid, rng)


TASKS: dict[str, Callable[[np.ndarray, np.random.Generator], tuple[np.ndarray, np.ndarray]]] = {
    "free_generation": _free_generation,
    "variation": _variation,
    "temporal_infill": _temporal_infill,
    "lane_infill": _lane_infill,
    "fill": _fill,
    "continuation": _continuation,
}

TASK_ORDER = tuple(sorted(TASKS))
TASK_INDEX = {name: index for index, name in enumerate(TASK_ORDER)}


def sample_task(rng: np.random.Generator) -> str:
    weights = np.array([float(TASK_MIX[name]["weight"]) for name in TASK_ORDER])
    weights = weights / weights.sum()
    return str(rng.choice(TASK_ORDER, p=weights))


def apply_task(
    task: str, valid: np.ndarray, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    observed, target = TASKS[task](valid.astype(np.float32), rng)
    return observed * valid, target * valid
```

`fill` and `continuation` share a masker on purpose: both condition the second
bar on the first. They stay separate names because the condition vector and the
task embedding distinguish them, and the mix weights them differently.

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/training/test_tasks.py -q
```

Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/training/tasks.py lab/tests/training/test_tasks.py
git commit -m "feat(training): add the six-task sampler with the two deferrals recorded"
```

---

### Task 3: The model with a task embedding

**Files:**
- Create: `lab/groove_lab/training/model.py`
- Test: `lab/tests/training/test_training_model.py`

Specification 12.1 asks for embeddings of lane, position, task and conditions.
The spike's `StepTokenHvo` has position and conditions; this adds the task.

- [ ] **Step 1: Write the failing test**

Create `lab/tests/training/test_training_model.py`:

```python
from __future__ import annotations

import torch

from groove_lab.model import count_parameters
from groove_lab.training.model import MaskedHvo


def _inputs(batch: int = 2) -> dict[str, torch.Tensor]:
    return {
        "hit": torch.zeros(batch, 32, 18),
        "velocity": torch.zeros(batch, 32, 18),
        "offset": torch.zeros(batch, 32, 18),
        "observed_mask": torch.zeros(batch, 32, 18),
        "conditions": torch.zeros(batch, 16),
        "task": torch.zeros(batch, dtype=torch.long),
    }


def test_every_head_has_the_expected_shape() -> None:
    out = MaskedHvo()(**_inputs())
    assert out["hit_logits"].shape == (2, 32, 18)
    assert out["subhits_logits"].shape == (2, 32, 18, 4)
    assert out["velocity"].shape == (2, 32, 18)
    assert out["offset"].shape == (2, 32, 18)


def test_the_task_changes_the_prediction() -> None:
    torch.manual_seed(0)
    model = MaskedHvo().eval()
    inputs = _inputs()
    with torch.no_grad():
        first = model(**inputs)["hit_logits"]
        inputs["task"] = torch.ones(2, dtype=torch.long)
        second = model(**inputs)["hit_logits"]
    assert not torch.allclose(first, second), "the task embedding is not connected"


def test_the_model_stays_in_the_small_tier() -> None:
    assert 3_000_000 < count_parameters(MaskedHvo()) < 12_000_000


def test_offset_and_velocity_are_bounded() -> None:
    torch.manual_seed(1)
    out = MaskedHvo().eval()(**_inputs())
    assert float(out["velocity"].min()) >= 0.0 and float(out["velocity"].max()) <= 1.0
    assert float(out["offset"].min()) >= -1.0 and float(out["offset"].max()) <= 1.0
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/training/test_training_model.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.training.model'`.

- [ ] **Step 3: Write the model**

Create `lab/groove_lab/training/model.py`:

```python
"""The step-token masked HVO, with the task embedding specification 12.1 asks for.

The tokenisation is not a free choice here: the CPU spike measured 32 decoding
steps for the step-token layout against 16 for cell-token, and section 19.4 made
step-token the architecture constraint plan 6 inherits.
"""

from __future__ import annotations

import torch
from torch import nn

from ..model import CONDITIONS, D_MODEL, LANES, MAX_SUBHITS, STEPS, _encoder
from .tasks import TASK_ORDER


class MaskedHvo(nn.Module):
    sequence_length = STEPS

    def __init__(self) -> None:
        super().__init__()
        self.value_projection = nn.Linear(LANES * 4, D_MODEL)
        self.step_embedding = nn.Embedding(STEPS, D_MODEL)
        self.task_embedding = nn.Embedding(len(TASK_ORDER), D_MODEL)
        self.condition_projection = nn.Linear(CONDITIONS, D_MODEL)
        self.encoder = _encoder()
        self.hit_head = nn.Linear(D_MODEL, LANES)
        self.subhits_head = nn.Linear(D_MODEL, LANES * MAX_SUBHITS)
        self.velocity_head = nn.Linear(D_MODEL, LANES)
        self.offset_head = nn.Linear(D_MODEL, LANES)
        self.register_buffer("step_index", torch.arange(STEPS), persistent=False)

    def forward(
        self,
        hit: torch.Tensor,
        velocity: torch.Tensor,
        offset: torch.Tensor,
        observed_mask: torch.Tensor,
        conditions: torch.Tensor,
        task: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        batch = hit.shape[0]
        # Masked cells must carry no information, so the observed mask gates the
        # values rather than merely accompanying them.
        gate = observed_mask
        values = torch.stack(
            (hit * gate, velocity * gate, offset * gate, gate), dim=-1
        )
        embedded = self.value_projection(values.reshape(batch, STEPS, LANES * 4))
        embedded = embedded + self.step_embedding(self.step_index).unsqueeze(0)
        embedded = embedded + self.condition_projection(conditions).unsqueeze(1)
        embedded = embedded + self.task_embedding(task).unsqueeze(1)

        encoded = self.encoder(embedded)
        return {
            "hit_logits": self.hit_head(encoded),
            "subhits_logits": self.subhits_head(encoded).reshape(
                batch, STEPS, LANES, MAX_SUBHITS
            ),
            "velocity": torch.sigmoid(self.velocity_head(encoded)),
            "offset": torch.tanh(self.offset_head(encoded)),
        }
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/training/test_training_model.py -q
```

Expected: PASS, 4 tests.

If `test_the_task_changes_the_prediction` fails, the task embedding is decorative.
That is the exact bug the test exists to catch; fix the wiring, not the test.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/training/model.py lab/tests/training/test_training_model.py
git commit -m "feat(training): add the task embedding to the step-token model"
```

---

### Task 4: Masked losses

**Files:**
- Create: `lab/groove_lab/training/losses.py`
- Test: `lab/tests/training/test_losses.py`

A loss that sees a cell the task did not ask about is a leak of the answer.

- [ ] **Step 1: Write the failing test**

Create `lab/tests/training/test_losses.py`:

```python
from __future__ import annotations

import torch

from groove_lab.training.losses import masked_losses


def _batch(batch: int = 2) -> dict[str, torch.Tensor]:
    return {
        "hit": torch.zeros(batch, 32, 18),
        "subhits": torch.zeros(batch, 32, 18, dtype=torch.long),
        "velocity": torch.zeros(batch, 32, 18),
        "offset": torch.zeros(batch, 32, 18),
    }


def _outputs(batch: int = 2) -> dict[str, torch.Tensor]:
    return {
        "hit_logits": torch.zeros(batch, 32, 18, requires_grad=True),
        "subhits_logits": torch.zeros(batch, 32, 18, 4, requires_grad=True),
        "velocity": torch.zeros(batch, 32, 18, requires_grad=True),
        "offset": torch.zeros(batch, 32, 18, requires_grad=True),
    }


def test_a_cell_outside_the_target_mask_cannot_move_the_loss() -> None:
    target = torch.zeros(2, 32, 18)
    target[0, 0, 0] = 1.0
    truth = _batch()

    baseline = masked_losses(_outputs(), truth, target)["total"]
    truth["hit"][0, 5, 5] = 1.0  # a cell nobody asked about
    changed = masked_losses(_outputs(), truth, target)["total"]
    assert torch.isclose(baseline, changed)


def test_a_cell_inside_the_target_mask_does_move_the_loss() -> None:
    target = torch.zeros(2, 32, 18)
    target[0, 0, 0] = 1.0
    truth = _batch()
    baseline = masked_losses(_outputs(), truth, target)["total"]
    truth["hit"][0, 0, 0] = 1.0
    assert not torch.isclose(baseline, masked_losses(_outputs(), truth, target)["total"])


def test_velocity_and_offset_only_count_where_there_is_a_hit() -> None:
    target = torch.ones(2, 32, 18)
    truth = _batch()
    baseline = masked_losses(_outputs(), truth, target)
    truth["velocity"][0, 3, 3] = 0.9  # no hit at that cell
    after = masked_losses(_outputs(), truth, target)
    assert torch.isclose(baseline["velocity"], after["velocity"])


def test_an_empty_target_mask_gives_a_finite_zero_loss() -> None:
    losses = masked_losses(_outputs(), _batch(), torch.zeros(2, 32, 18))
    for value in losses.values():
        assert torch.isfinite(value)
    assert float(losses["total"]) == 0.0


def test_the_total_is_differentiable() -> None:
    target = torch.ones(2, 32, 18)
    outputs = _outputs()
    masked_losses(outputs, _batch(), target)["total"].backward()
    assert outputs["hit_logits"].grad is not None
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/training/test_losses.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.training.losses'`.

- [ ] **Step 3: Write the losses**

Create `lab/groove_lab/training/losses.py`:

```python
"""Losses that only ever see the cells the task actually asked about.

Two masks compose.  ``target`` says which cells the task is asking the model to
predict; anything outside it is either given to the model as input or does not
exist, and letting it into the loss would be leaking the answer.  Inside the
target, velocity, offset and multiplicity are only meaningful where there is a
hit, which is the second mask.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F

WEIGHTS = {"hit": 1.0, "subhits": 0.2, "velocity": 0.5, "offset": 0.5}


def _mean(values: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    total = mask.sum()
    if float(total) == 0.0:
        return values.sum() * 0.0
    return (values * mask).sum() / total


def masked_losses(
    outputs: dict[str, torch.Tensor],
    truth: dict[str, torch.Tensor],
    target: torch.Tensor,
) -> dict[str, torch.Tensor]:
    hit_loss = _mean(
        F.binary_cross_entropy_with_logits(
            outputs["hit_logits"], truth["hit"], reduction="none"
        ),
        target,
    )

    hit_mask = target * truth["hit"]
    subhits_loss = _mean(
        F.cross_entropy(
            outputs["subhits_logits"].permute(0, 3, 1, 2),
            truth["subhits"],
            reduction="none",
        ),
        hit_mask,
    )
    velocity_loss = _mean(
        F.smooth_l1_loss(outputs["velocity"], truth["velocity"], reduction="none"),
        hit_mask,
    )
    offset_loss = _mean(
        F.smooth_l1_loss(outputs["offset"], truth["offset"], reduction="none"),
        hit_mask,
    )

    losses = {
        "hit": hit_loss,
        "subhits": subhits_loss,
        "velocity": velocity_loss,
        "offset": offset_loss,
    }
    losses["total"] = sum(WEIGHTS[name] * value for name, value in losses.items())
    return losses
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/training/test_losses.py -q
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/training/losses.py lab/tests/training/test_losses.py
git commit -m "feat(training): mask the losses to the cells the task asked for"
```

---

### Task 5: Training loop with checkpoints and resume

**Files:**
- Create: `lab/groove_lab/training/loop.py`
- Test: `lab/tests/training/test_loop.py`

- [ ] **Step 1: Write the failing test**

Create `lab/tests/training/test_loop.py`:

```python
from __future__ import annotations

import numpy as np
import torch

from groove_lab.training.loop import TrainState, run_steps, save_checkpoint, load_checkpoint
from groove_lab.training.model import MaskedHvo


def _fake_batch(batch: int = 4) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(0)
    hit = (rng.random((batch, 32, 18)) > 0.85).astype(np.float32)
    return {
        "hit": hit,
        "subhits": hit.astype(np.int64),
        "velocity": (hit * rng.random((batch, 32, 18))).astype(np.float32),
        "offset": (hit * rng.normal(0, 0.2, (batch, 32, 18))).astype(np.float32),
        "valid": np.ones((batch, 32, 18), dtype=np.float32),
        "conditions": rng.random((batch, 16)).astype(np.float32),
    }


def test_loss_goes_down_on_a_repeated_batch() -> None:
    torch.manual_seed(0)
    state = TrainState(MaskedHvo(), learning_rate=1e-3, seed=0)
    batch = _fake_batch()
    first = run_steps(state, [batch] * 5)
    later = run_steps(state, [batch] * 40)
    assert later < first, f"loss did not fall: {first} -> {later}"


def test_checkpoint_round_trips_the_weights(tmp_path) -> None:
    torch.manual_seed(0)
    state = TrainState(MaskedHvo(), learning_rate=1e-3, seed=0)
    run_steps(state, [_fake_batch()] * 3)
    path = tmp_path / "checkpoint.pt"
    save_checkpoint(state, path)

    restored = TrainState(MaskedHvo(), learning_rate=1e-3, seed=0)
    load_checkpoint(restored, path)
    for before, after in zip(
        state.model.state_dict().values(),
        restored.model.state_dict().values(),
        strict=True,
    ):
        assert torch.equal(before, after)
    assert restored.step == state.step


def test_two_runs_with_the_same_seed_agree() -> None:
    def once() -> float:
        torch.manual_seed(0)
        state = TrainState(MaskedHvo(), learning_rate=1e-3, seed=0)
        return run_steps(state, [_fake_batch()] * 10)

    assert abs(once() - once()) < 1e-6
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/training/test_loop.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.training.loop'`.

- [ ] **Step 3: Write the loop**

Create `lab/groove_lab/training/loop.py`:

```python
"""Train, checkpoint and resume, with every source of randomness declared.

Specification 16.3 asks a run to record its seeds, its sampler state and its
optimizer state.  ``TrainState`` is that record: everything that would change a
result lives in it and goes into the checkpoint.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from .losses import masked_losses
from .tasks import TASK_INDEX, apply_task, sample_task


class TrainState:
    def __init__(self, model: nn.Module, learning_rate: float, seed: int) -> None:
        torch.manual_seed(seed)
        self.model = model
        self.optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
        self.rng = np.random.default_rng(seed)
        self.seed = seed
        self.step = 0


def _prepare(state: TrainState, batch: dict[str, np.ndarray]) -> tuple[dict, dict, torch.Tensor]:
    observed_list, target_list, task_list = [], [], []
    for index in range(batch["hit"].shape[0]):
        task = sample_task(state.rng)
        observed, target = apply_task(task, batch["valid"][index], state.rng)
        observed_list.append(observed)
        target_list.append(target)
        task_list.append(TASK_INDEX[task])

    truth = {
        "hit": torch.from_numpy(batch["hit"]),
        "subhits": torch.from_numpy(batch["subhits"]),
        "velocity": torch.from_numpy(batch["velocity"]),
        "offset": torch.from_numpy(batch["offset"]),
    }
    inputs = {
        "hit": truth["hit"],
        "velocity": truth["velocity"],
        "offset": truth["offset"],
        "observed_mask": torch.from_numpy(np.stack(observed_list)),
        "conditions": torch.from_numpy(batch["conditions"]),
        "task": torch.tensor(task_list, dtype=torch.long),
    }
    return inputs, truth, torch.from_numpy(np.stack(target_list))


def run_steps(state: TrainState, batches: Iterable[dict[str, np.ndarray]]) -> float:
    state.model.train()
    last = 0.0
    for batch in batches:
        inputs, truth, target = _prepare(state, batch)
        outputs = state.model(**inputs)
        loss = masked_losses(outputs, truth, target)["total"]
        state.optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(state.model.parameters(), 1.0)
        state.optimizer.step()
        state.step += 1
        last = float(loss)
    return last


@torch.no_grad()
def evaluate(state: TrainState, batches: Iterable[dict[str, np.ndarray]]) -> float:
    """Evaluate on a fixed task draw, without touching the training randomness.

    Sampling tasks from ``state.rng`` here would do two bad things at once: make
    the reported loss wander between evaluations of the same weights, and shift
    the training stream depending on how often evaluation ran.
    """

    state.model.eval()
    saved = state.rng
    state.rng = np.random.default_rng(state.seed + 10_000)
    try:
        total = 0.0
        count = 0
        for batch in batches:
            inputs, truth, target = _prepare(state, batch)
            total += float(masked_losses(state.model(**inputs), truth, target)["total"])
            count += 1
    finally:
        state.rng = saved
    return total / count if count else 0.0


def save_checkpoint(state: TrainState, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model": state.model.state_dict(),
            "optimizer": state.optimizer.state_dict(),
            "step": state.step,
            "seed": state.seed,
            "rng": state.rng.bit_generator.state,
        },
        path,
    )


def load_checkpoint(state: TrainState, path: Path) -> None:
    payload: dict[str, Any] = torch.load(path, weights_only=False)
    state.model.load_state_dict(payload["model"])
    state.optimizer.load_state_dict(payload["optimizer"])
    state.step = payload["step"]
    state.seed = payload["seed"]
    state.rng.bit_generator.state = payload["rng"]
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/training/test_loop.py -q
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/training/loop.py lab/tests/training/test_loop.py
git commit -m "feat(training): train with checkpoints, resume and declared seeds"
```

---

### Task 6: M0, the deliberate overfit

**Files:**
- Create: `lab/scripts/train_masked_hvo.py`

Specification 17 is blunt about this rung: an inability to overfit is a bug, not
a lack of scale.

- [ ] **Step 1: Write the entry point**

Create `lab/scripts/train_masked_hvo.py` with a `--mode` of `m0` or `m1`,
`--examples`, `--steps`, `--seed` and `--workspace`, loading `ShardDataset`,
looping `run_steps` over `dataset.collate` batches, evaluating on validation
every `--eval-every` steps, checkpointing `best` and `last`, and writing a JSON
run record with the config, seeds, losses and library versions:

```python
"""Train the masked HVO transformer. M0 memorises; M1 learns."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "lab"))

from groove_lab.training.loader import ShardDataset  # noqa: E402
from groove_lab.training.loop import (  # noqa: E402
    TrainState,
    evaluate,
    run_steps,
    save_checkpoint,
)
from groove_lab.training.model import MaskedHvo  # noqa: E402

DATASET = "F:/groove-brain/dataset/build-a"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("m0", "m1"), required=True)
    parser.add_argument("--examples", type=int, default=64)
    parser.add_argument("--steps", type=int, default=2000)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--eval-every", type=int, default=200)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workspace", type=Path, default=Path("F:/groove-brain/runs"))
    arguments = parser.parse_args()

    torch.set_num_threads(1)  # plan 3: more threads make the CPU budget worse
    train = ShardDataset(DATASET, "train", max_subhits=4)
    validation = ShardDataset(DATASET, "validation", max_subhits=4)

    if arguments.mode == "m0":
        positions = list(range(min(arguments.examples, len(train))))
    else:
        positions = list(range(len(train)))

    state = TrainState(MaskedHvo(), arguments.learning_rate, arguments.seed)
    run_dir = arguments.workspace / f"{arguments.mode}-seed{arguments.seed}"
    history: list[dict[str, float]] = []
    best = float("inf")
    started = time.perf_counter()

    while state.step < arguments.steps:
        batches = [
            train.collate(chunk)
            for chunk in _chunks(positions, arguments.batch_size, state.rng)
        ]
        run_steps(state, batches)
        if state.step % arguments.eval_every < len(batches):
            train_loss = evaluate(state, batches[:4])
            validation_loss = evaluate(
                state,
                [
                    validation.collate(chunk)
                    for chunk in validation.batch_indices(arguments.batch_size, 0)[:4]
                ],
            )
            history.append(
                {
                    "step": state.step,
                    "train": train_loss,
                    "validation": validation_loss,
                }
            )
            print(
                f"step {state.step:6d}  train {train_loss:.5f}  "
                f"validation {validation_loss:.5f}",
                flush=True,
            )
            if validation_loss < best:
                best = validation_loss
                save_checkpoint(state, run_dir / "best.pt")

    save_checkpoint(state, run_dir / "last.pt")
    record = {
        "mode": arguments.mode,
        "examples": len(positions),
        "steps": state.step,
        "seed": arguments.seed,
        "batch_size": arguments.batch_size,
        "learning_rate": arguments.learning_rate,
        "final_train_loss": history[-1]["train"] if history else None,
        "best_validation_loss": best,
        "history": history,
        "wall_seconds": round(time.perf_counter() - started, 2),
        "environment": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "platform": platform.platform(),
        },
    }
    (run_dir / "run.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: record[k] for k in
                      ("mode", "examples", "steps", "final_train_loss",
                       "best_validation_loss", "wall_seconds")}, indent=2))


def _chunks(positions: list[int], size: int, rng) -> list[list[int]]:
    order = list(positions)
    rng.shuffle(order)
    return [order[i : i + size] for i in range(0, len(order), size)]


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the overfit**

Run:

```bash
lab/.venv-lab/Scripts/python.exe lab/scripts/train_masked_hvo.py --mode m0 --examples 64 --steps 3000 --batch-size 16 --seed 0
```

Expected: the printed train loss falls steadily. The gate is a final train loss
below **0.05**.

- [ ] **Step 3: If it does not overfit, debug rather than scale**

Check, in this order: that `target` is non-empty for most examples; that
`observed_mask` actually gates the input values, so the answer is not being fed
in; that the loss masks match the task masks. Do not raise the learning rate or
add parameters to force it — an inability to memorise 64 examples is a wiring
bug, and specification 17 says so explicitly.

- [ ] **Step 4: Commit**

```bash
git add lab/scripts/train_masked_hvo.py
git commit -m "feat(training): add the M0 and M1 training entry point"
```

---

### Task 7: Generation, validity and diversity

**Files:**
- Create: `lab/groove_lab/training/generate.py`
- Test: `lab/tests/training/test_generate.py`

Gate G4 wants three things beyond the overfit: valid structure in 100% of cases,
diversity across seeds above a declared floor, and no collapse.

- [ ] **Step 1: Write the failing test**

Create `lab/tests/training/test_generate.py`:

```python
from __future__ import annotations

import numpy as np
import torch

from groove_lab.training.generate import (
    diversity,
    generate,
    is_structurally_valid,
)
from groove_lab.training.model import MaskedHvo


def test_generation_returns_a_full_grid() -> None:
    torch.manual_seed(0)
    grid = generate(MaskedHvo().eval(), conditions=np.zeros(16, dtype=np.float32),
                    seed=0, decoding_steps=8)
    assert grid["hit"].shape == (32, 18)
    assert set(np.unique(grid["hit"])) <= {0.0, 1.0}


def test_a_generated_grid_is_structurally_valid() -> None:
    torch.manual_seed(0)
    grid = generate(MaskedHvo().eval(), np.zeros(16, dtype=np.float32), seed=0,
                    decoding_steps=8)
    assert is_structurally_valid(grid)


def test_an_out_of_range_offset_is_rejected() -> None:
    grid = {
        "hit": np.ones((32, 18), dtype=np.float32),
        "subhits": np.ones((32, 18), dtype=np.int64),
        "velocity": np.zeros((32, 18), dtype=np.float32),
        "offset": np.full((32, 18), 5.0, dtype=np.float32),
    }
    assert not is_structurally_valid(grid)


def test_identical_grids_have_zero_diversity() -> None:
    grid = {"hit": np.ones((32, 18), dtype=np.float32)}
    assert diversity([grid, grid, grid]) == 0.0


def test_different_grids_have_positive_diversity() -> None:
    rng = np.random.default_rng(0)
    grids = [
        {"hit": (rng.random((32, 18)) > 0.5).astype(np.float32)} for _ in range(4)
    ]
    assert diversity(grids) > 0.1
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/training/test_generate.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.training.generate'`.

- [ ] **Step 3: Write the generator and the metrics**

Create `lab/groove_lab/training/generate.py`:

```python
"""Decode a groove and measure whether it is valid and whether it varies.

Decoding reuses the confidence loop the CPU spike measured, so the step count
here is the same quantity section 19.4 budgeted at 32.
"""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

from ..decoding import DecodeState, commit_confident_cells, schedule
from .tasks import TASK_INDEX

STEPS = 32
LANES = 18


@torch.no_grad()
def generate(
    model: nn.Module,
    conditions: np.ndarray,
    seed: int,
    decoding_steps: int,
) -> dict[str, np.ndarray]:
    torch.manual_seed(seed)
    model.eval()
    state = DecodeState.masked(STEPS, LANES)
    task = torch.tensor([TASK_INDEX["free_generation"]], dtype=torch.long)
    condition_tensor = torch.from_numpy(conditions).unsqueeze(0)

    subhits = np.zeros((STEPS, LANES), dtype=np.int64)
    for count in schedule(STEPS * LANES, decoding_steps):
        outputs = model(
            hit=torch.from_numpy(state.hit).unsqueeze(0),
            velocity=torch.from_numpy(state.velocity).unsqueeze(0),
            offset=torch.from_numpy(state.offset).unsqueeze(0),
            observed_mask=torch.from_numpy(state.observed_mask).unsqueeze(0),
            conditions=condition_tensor,
            task=task,
        )
        before = state.observed_mask.copy()
        commit_confident_cells(
            state,
            outputs["hit_logits"][0].numpy(),
            outputs["velocity"][0].numpy(),
            outputs["offset"][0].numpy(),
            count=count,
        )
        just_committed = (state.observed_mask > 0) & (before == 0)
        predicted = outputs["subhits_logits"][0].argmax(dim=-1).numpy()
        subhits[just_committed] = predicted[just_committed]

    return {
        "hit": state.hit,
        "subhits": np.where(state.hit > 0, np.maximum(subhits, 1), 0).astype(np.int64),
        "velocity": state.velocity,
        "offset": state.offset,
    }


def is_structurally_valid(grid: dict[str, np.ndarray]) -> bool:
    """Every rule a candidate must satisfy before anything downstream sees it."""

    hit = grid["hit"]
    if hit.shape != (STEPS, LANES):
        return False
    if not np.isin(hit, (0.0, 1.0)).all():
        return False
    if not np.isfinite(grid["velocity"]).all() or not np.isfinite(grid["offset"]).all():
        return False
    if float(grid["velocity"].min()) < 0.0 or float(grid["velocity"].max()) > 1.0:
        return False
    if float(np.abs(grid["offset"]).max()) > 1.0:
        return False
    # A hit must carry at least one event, and a silent cell must carry none.
    if int(grid["subhits"][hit > 0].min(initial=1)) < 1:
        return False
    return int(grid["subhits"][hit == 0].sum()) == 0


def diversity(grids: list[dict[str, np.ndarray]]) -> float:
    """Mean pairwise Hamming distance between hit grids, in [0, 1]."""

    if len(grids) < 2:
        return 0.0
    distances = []
    for i in range(len(grids)):
        for j in range(i + 1, len(grids)):
            distances.append(float(np.mean(grids[i]["hit"] != grids[j]["hit"])))
    return float(np.mean(distances))
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/training/test_generate.py -q
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/training/generate.py lab/tests/training/test_generate.py
git commit -m "feat(training): decode grooves and score validity and diversity"
```

---

### Task 8: M1 and the gate G4 evidence

**Files:**
- Create: `lab/scripts/gate_g4.py`
- Create: `docs/superpowers/plans/2026-08-31-groove-brain-masked-hvo-transformer-result.md`

- [ ] **Step 1: Run M1 on the 1% train split, three seeds**

Run:

```bash
lab/.venv-lab/Scripts/python.exe lab/scripts/train_masked_hvo.py --mode m1 --steps 4000 --batch-size 32 --seed 0
lab/.venv-lab/Scripts/python.exe lab/scripts/train_masked_hvo.py --mode m1 --steps 4000 --batch-size 32 --seed 1
lab/.venv-lab/Scripts/python.exe lab/scripts/train_masked_hvo.py --mode m1 --steps 4000 --batch-size 32 --seed 2
```

Expected: validation loss falls and then flattens. Record the curves.

- [ ] **Step 2: Write the gate script**

Create `lab/scripts/gate_g4.py`:

```python
"""Measure gate G4 against the thresholds declared before the runs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "lab"))

from groove_lab.training.generate import (  # noqa: E402
    diversity,
    generate,
    is_structurally_valid,
)
from groove_lab.training.loop import TrainState, load_checkpoint  # noqa: E402
from groove_lab.training.model import MaskedHvo  # noqa: E402

RUNS = Path("F:/groove-brain/runs")
OUTPUT = RUNS / "gate_g4.json"
SEEDS = (0, 1, 2)
SAMPLES = 64
DECODING_STEPS = 32

# Declared in the plan before any run. Not to be moved afterwards.
MAX_M0_TRAIN_LOSS = 0.05
MIN_VALIDITY = 1.0
MIN_DIVERSITY = 0.05
CORPUS_HITS_PER_BAR = 16.0
DENSITY_FACTOR = 2.0


def _load(path: Path) -> MaskedHvo:
    state = TrainState(MaskedHvo(), learning_rate=1e-3, seed=0)
    load_checkpoint(state, path)
    return state.model.eval()


def main() -> None:
    torch.set_num_threads(1)

    m0 = json.loads((RUNS / "m0-seed0" / "run.json").read_text(encoding="utf-8"))
    m0_loss = float(m0["final_train_loss"])

    per_seed: dict[int, list[dict[str, np.ndarray]]] = {}
    valid = total = 0
    densities: list[float] = []
    for seed in SEEDS:
        model = _load(RUNS / f"m1-seed{seed}" / "best.pt")
        grids = []
        for sample in range(SAMPLES):
            grid = generate(
                model,
                conditions=np.zeros(16, dtype=np.float32),
                seed=seed * 1000 + sample,
                decoding_steps=DECODING_STEPS,
            )
            grids.append(grid)
            total += 1
            valid += int(is_structurally_valid(grid))
            densities.append(float(grid["hit"].sum()) / 2.0)
        per_seed[seed] = grids

    validity = valid / total if total else 0.0
    # Same sample index, different training seed: pure model-to-model variation.
    across = [
        diversity([per_seed[seed][sample] for seed in SEEDS])
        for sample in range(SAMPLES)
    ]
    across_seeds = float(np.mean(across))
    within = float(np.mean([diversity(per_seed[seed][:16]) for seed in SEEDS]))
    density = float(np.mean(densities))

    results = {
        "m0_final_train_loss": {
            "value": m0_loss,
            "threshold": MAX_M0_TRAIN_LOSS,
            "pass": m0_loss < MAX_M0_TRAIN_LOSS,
        },
        "structural_validity": {
            "value": validity,
            "threshold": MIN_VALIDITY,
            "pass": validity >= MIN_VALIDITY,
        },
        "diversity_across_seeds": {
            "value": across_seeds,
            "threshold": MIN_DIVERSITY,
            "pass": across_seeds >= MIN_DIVERSITY,
        },
        "diversity_within_a_seed": {
            "value": within,
            "threshold": MIN_DIVERSITY,
            "pass": within >= MIN_DIVERSITY,
        },
        "hits_per_bar": {
            "value": density,
            "range": [
                CORPUS_HITS_PER_BAR / DENSITY_FACTOR,
                CORPUS_HITS_PER_BAR * DENSITY_FACTOR,
            ],
            "pass": (
                CORPUS_HITS_PER_BAR / DENSITY_FACTOR
                <= density
                <= CORPUS_HITS_PER_BAR * DENSITY_FACTOR
            ),
        },
        "samples": total,
        "decoding_steps": DECODING_STEPS,
    }
    results["gate_g4_pass"] = all(
        entry["pass"] for entry in results.values() if isinstance(entry, dict)
    )
    OUTPUT.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
```

`diversity_within_a_seed` is measured as well as across seeds on purpose: a model
that produces one groove per seed but always the same one within a seed has
collapsed, and the across-seed number alone would not say so.

- [ ] **Step 3: Run the gate**

Run:

```bash
lab/.venv-lab/Scripts/python.exe lab/scripts/gate_g4.py
```

- [ ] **Step 4: Write the result document**

Create `docs/superpowers/plans/2026-08-31-groove-brain-masked-hvo-transformer-result.md`
recording the M0 overfit curve and final loss, the three M1 curves, the four G4
measurements against their thresholds, wall time per run on CPU, and an explicit
statement that G5 is not attempted because the baselines are plan 5.

- [ ] **Step 5: Update the design document**

In section 17, append the outcome to the `**M0**` and `**M1**` rows. In section
20, append to gate `G4` what was measured against each of its three clauses. Do
not touch `G5`.

- [ ] **Step 6: Verify and commit**

Run:

```bash
git diff --check -- docs/
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests -q
.venv-win/Scripts/python.exe -m pytest -q --tb=line
```

Expected: no whitespace complaints, all lab tests pass, and the product suite
still at `906 passed` with its four known prototype failures.

```bash
git add lab/scripts/gate_g4.py docs/superpowers/plans/2026-08-31-groove-brain-masked-hvo-transformer-result.md docs/superpowers/specs/2026-08-31-groove-brain-dataset-training-design.md
git commit -m "docs: record the M0 and M1 runs and close G4"
```

---

## Thresholds, declared before the runs

| Measure | Threshold | Why this number |
|---|---|---|
| M0 final train loss | **< 0.05** | memorising 64 examples with 4.8M parameters should drive the masked loss near zero; anything above is a wiring bug |
| Structural validity | **100%** | specification 18.1 admits no exceptions, and the checks are mechanical |
| Diversity across seeds | **≥ 0.05** | a collapsed model scores exactly 0.0; 5% of cells differing is the smallest signal distinguishable from collapse |
| Diversity within a seed | **≥ 0.05** | catches the model that varies between seeds but repeats one groove forever inside a seed |
| Generated hit density | **within 2× of 16 hits per bar** | catches both the silent model and the everything-on model, against the measured corpus median |

These are written here, before the runs, so a disappointing number cannot be
turned into a passing one afterwards.

## Stop condition

Done when M0 memorises below its threshold, three M1 seeds train without
collapse, all four G4 measurements are recorded against the thresholds above, and
section 20 of the design carries the result.

If M0 cannot memorise 64 examples, stop and debug the masking. If M1 collapses —
diversity at zero, or density pinned at nothing or everything — that is a real
finding about the task mix and belongs in the result document, not behind a
retuned learning rate.
