# Groove Brain Baselines and Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the evaluation harness the programme has been missing, put the masked HVO transformer up against the incumbent retrieval baseline on the same data and the same tasks, and answer gate G5 with a number instead of a hope.

**Architecture:** A metrics module covering the three families specification 18 names — prediction, musicality, originality — then two baselines that need no training: nearest-neighbour retrieval over the train split, and a marginal sampler that reproduces the corpus statistics and nothing else. One runner scores every system on the same validation windows under the same task draws. A pre-registered listening protocol and a MIDI exporter make the human half possible without running it.

**Tech Stack:** The lab CPU-only environment, the V3 shards from plan 4, the checkpoints from plan 6, and the product's `serialize_note_smf` for the listening test.

---

## Why this plan exists in this shape

Plan 6 closed gate G4 and then produced this, from the model that passed it:

| Lane | Generated per window | Corpus per window |
|---|---|---|
| `hat_pedal` | 14.94 | 2.38 |
| `hat_closed` | **0.00** | 4.99 |
| `kick` | 4.31 | 8.26 |

A model can clear every G4 clause and still not be a groove, because G4 asks
whether the output is mute, frozen or structurally invalid. Per-lane
plausibility is a musicality metric; specification 18.3 already lists
"distribution by lane and position" and this plan is where it becomes a number
that gates something.

## Scope, and what moves to its own plan

Specification section 21 lists plan 5 as covering the retrieval and deterministic
benchmark, GrooVAE, event AR, the metrics and the human protocol. This plan does
the first, second, fourth and fifth. **GrooVAE and the event-based
autoregressive decoder each become their own plan**, for a reason the gate text
itself supports:

- G5 asks whether the challenger beats **the best baseline**. The incumbent — the
  thing that ships today if nothing wins — is retrieval plus deterministic
  transforms. That is the baseline G5 is about.
- GrooVAE and event AR are *other challengers*. They matter for choosing an
  architecture at M2 and G6, not for deciding whether a neural model is worth
  having at all. Each is an implementation the size of plan 6, and folding two of
  them in here would delay the one measurement that decides whether the
  programme continues.

## Declared before any run

Moving these afterwards invalidates the gate.

**Primary metric for G5: hit F1 on masked target cells, over the infill family**
— `temporal_infill`, `lane_infill`, `fill`, `continuation` — measured on the
validation split. Those tasks have a ground truth; free generation does not, so
it cannot carry a primary metric and is judged on musicality, originality and the
listening test instead.

| Gate condition | Threshold |
|---|---|
| G5 primary | masked HVO hit F1 beats the best baseline on all three seeds, by more than the baseline's own seed-to-seed spread |
| Musicality side-condition | lane-distribution distance to the corpus no worse than the best baseline's |
| Originality side-condition | exact rhythm-hash match rate against train **below** the corpus internal repeat rate of 26.0% |

The originality condition is where retrieval is expected to lose by
construction: it returns real corpus windows, so its copy rate is 100% by
definition. That asymmetry is the point, and it is stated now rather than
discovered as a convenient result later.

## File Structure

| Path | Responsibility |
|---|---|
| `lab/groove_lab/eval/__init__.py` | Package marker |
| `lab/groove_lab/eval/metrics.py` | Prediction, musicality and originality metrics |
| `lab/groove_lab/eval/baselines.py` | Retrieval and marginal-sampler baselines |
| `lab/groove_lab/eval/runner.py` | Score every system on the same windows and tasks |
| `lab/groove_lab/eval/export.py` | Grid to MIDI, for listening |
| `lab/scripts/evaluate_systems.py` | Entry point producing the comparison table |
| `lab/scripts/make_listening_set.py` | Anonymised, randomised listening pairs |
| `docs/superpowers/specs/2026-08-31-groove-brain-listening-protocol.md` | The pre-registered human protocol |
| `lab/tests/eval/test_*.py` | One test module per unit |

---

### Task 1: Metrics

**Files:**
- Create: `lab/groove_lab/eval/__init__.py`
- Create: `lab/groove_lab/eval/metrics.py`
- Test: `lab/tests/eval/test_metrics.py`

- [ ] **Step 1: Write the failing test**

Create `lab/tests/eval/test_metrics.py`:

```python
from __future__ import annotations

import numpy as np

from groove_lab.eval.metrics import (
    exact_repeat_rate,
    hit_f1,
    lane_distribution,
    lane_distribution_distance,
    velocity_offset_error,
)

STEPS, LANES = 32, 18


def _grid(cells: list[tuple[int, int]]) -> np.ndarray:
    grid = np.zeros((STEPS, LANES), dtype=np.float32)
    for row, lane in cells:
        grid[row, lane] = 1.0
    return grid


def test_a_perfect_prediction_scores_one() -> None:
    truth = _grid([(0, 0), (8, 1)])
    mask = np.ones((STEPS, LANES), dtype=np.float32)
    assert hit_f1(truth, truth, mask) == 1.0


def test_silence_against_a_real_groove_scores_zero() -> None:
    truth = _grid([(0, 0), (8, 1)])
    mask = np.ones((STEPS, LANES), dtype=np.float32)
    assert hit_f1(np.zeros_like(truth), truth, mask) == 0.0


def test_only_masked_cells_count() -> None:
    truth = _grid([(0, 0)])
    predicted = _grid([(0, 0), (5, 5)])
    mask = np.zeros((STEPS, LANES), dtype=np.float32)
    mask[0, 0] = 1.0
    # The wrong cell at (5, 5) is outside the mask, so it must not be punished.
    assert hit_f1(predicted, truth, mask) == 1.0


def test_velocity_and_offset_error_only_counts_true_hits() -> None:
    truth_hit = _grid([(0, 0)])
    truth_velocity = np.zeros((STEPS, LANES), dtype=np.float32)
    truth_velocity[0, 0] = 0.5
    predicted_velocity = np.full((STEPS, LANES), 0.9, dtype=np.float32)
    predicted_velocity[0, 0] = 0.5
    mask = np.ones((STEPS, LANES), dtype=np.float32)
    error = velocity_offset_error(
        predicted_velocity, truth_velocity, truth_hit, mask
    )
    assert error == 0.0


def test_lane_distribution_sums_to_the_hit_count() -> None:
    grids = [_grid([(0, 0), (8, 0), (4, 2)])]
    assert lane_distribution(grids).sum() == 3.0


def test_distance_to_itself_is_zero_and_to_a_different_shape_is_not() -> None:
    same = [_grid([(0, 0), (8, 0)])]
    other = [_grid([(0, 5), (8, 5)])]
    assert lane_distribution_distance(same, same) == 0.0
    assert lane_distribution_distance(same, other) > 0.5


def test_exact_repeat_rate_finds_a_copy() -> None:
    corpus = [_grid([(0, 0), (8, 1)]), _grid([(4, 2)])]
    assert exact_repeat_rate([_grid([(0, 0), (8, 1)])], corpus) == 1.0
    assert exact_repeat_rate([_grid([(1, 1)])], corpus) == 0.0
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/eval/test_metrics.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.eval'`.

- [ ] **Step 3: Write the metrics**

Create `lab/groove_lab/eval/__init__.py`:

```python
"""Evaluation: metrics, baselines, and the comparison runner."""
```

Create `lab/groove_lab/eval/metrics.py`:

```python
"""The three metric families specification 18 names.

Prediction answers "did it put the hits where the truth had them", and only on
the cells the task masked.  Musicality answers "does it look like drumming",
which is where the lane distribution lives — plan 6 produced a model that passed
every structural gate while never once playing a closed hi-hat, and no metric in
the programme would have said so.  Originality answers "did it just copy", and
the reference point is the corpus repeating itself at 26.0%.
"""

from __future__ import annotations

import hashlib

import numpy as np

LANES = 18


def hit_f1(predicted: np.ndarray, truth: np.ndarray, mask: np.ndarray) -> float:
    """F1 over masked cells. Empty mask or no positives anywhere scores 0."""

    selected = mask > 0
    if not selected.any():
        return 0.0
    p = (predicted[selected] > 0.5).astype(np.int8)
    t = (truth[selected] > 0.5).astype(np.int8)
    true_positive = float(((p == 1) & (t == 1)).sum())
    if true_positive == 0.0:
        return 0.0
    precision = true_positive / float((p == 1).sum())
    recall = true_positive / float((t == 1).sum())
    return float(2 * precision * recall / (precision + recall))


def velocity_offset_error(
    predicted: np.ndarray, truth: np.ndarray, truth_hit: np.ndarray, mask: np.ndarray
) -> float:
    """Mean absolute error where the truth actually has a hit inside the mask."""

    selected = (mask > 0) & (truth_hit > 0.5)
    if not selected.any():
        return 0.0
    return float(np.abs(predicted[selected] - truth[selected]).mean())


def lane_distribution(grids: list[np.ndarray]) -> np.ndarray:
    """Mean hits per lane per window."""

    if not grids:
        return np.zeros(LANES, dtype=np.float64)
    return np.stack(grids).sum(axis=1).mean(axis=0)


def lane_distribution_distance(
    grids: list[np.ndarray], reference: list[np.ndarray]
) -> float:
    """L1 distance between normalised lane profiles, in [0, 2].

    Normalised so a system is not rewarded merely for matching total density: the
    question is whether the hits land in plausible lanes.
    """

    left = lane_distribution(grids)
    right = lane_distribution(reference)
    left = left / left.sum() if left.sum() else left
    right = right / right.sum() if right.sum() else right
    return float(np.abs(left - right).sum())


def _rhythm_hash(grid: np.ndarray) -> str:
    cells = np.argwhere(grid > 0.5)
    payload = ";".join(f"{int(row)}:{int(lane)}" for row, lane in cells)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def exact_repeat_rate(grids: list[np.ndarray], corpus: list[np.ndarray]) -> float:
    """Share of grids whose onset pattern already exists in the corpus.

    The corpus repeats itself at 26.0%, measured in specification 4.2, so a
    system copying at that rate is indistinguishable from the data by this
    metric. Anything above it is copying more than the source does.
    """

    if not grids:
        return 0.0
    known = {_rhythm_hash(grid) for grid in corpus}
    hits = sum(1 for grid in grids if _rhythm_hash(grid) in known)
    return hits / len(grids)
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/eval/test_metrics.py -q
```

Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/eval/__init__.py lab/groove_lab/eval/metrics.py lab/tests/eval/test_metrics.py
git commit -m "feat(eval): add prediction, musicality and originality metrics"
```

---

### Task 2: The two baselines

**Files:**
- Create: `lab/groove_lab/eval/baselines.py`
- Test: `lab/tests/eval/test_baselines.py`

Retrieval is the incumbent and the strong opponent. The marginal sampler is the
floor: it reproduces the corpus per-lane, per-step hit rates and nothing else, so
any system that cannot beat it has learned nothing about structure.

- [ ] **Step 1: Write the failing test**

Create `lab/tests/eval/test_baselines.py`:

```python
from __future__ import annotations

import numpy as np

from groove_lab.eval.baselines import MarginalSampler, RetrievalBaseline

STEPS, LANES = 32, 18


def _example(seed: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    hit = (rng.random((STEPS, LANES)) > 0.94).astype(np.float32)
    return {
        "hit": hit,
        "velocity": (hit * 0.7).astype(np.float32),
        "offset": np.zeros((STEPS, LANES), dtype=np.float32),
        "conditions": rng.random(16).astype(np.float32),
    }


def test_retrieval_returns_a_real_corpus_window() -> None:
    corpus = [_example(index) for index in range(20)]
    baseline = RetrievalBaseline(corpus)
    query = corpus[7]
    observed = np.ones((STEPS, LANES), dtype=np.float32)
    observed[16:, :] = 0.0
    result = baseline.complete(query, observed)
    # Perfect observed match: the nearest neighbour must be the query itself.
    assert np.array_equal(result["hit"], corpus[7]["hit"])


def test_retrieval_cannot_see_the_answer() -> None:
    # The whole comparison is void if the baseline matches on cells the task
    # masked. Two queries identical on the observed half and opposite on the
    # hidden half must retrieve the same neighbour.
    corpus = [_example(index) for index in range(20)]
    baseline = RetrievalBaseline(corpus)
    observed = np.ones((STEPS, LANES), dtype=np.float32)
    observed[16:, :] = 0.0

    query = {key: value.copy() for key, value in corpus[3].items()}
    tampered = {key: value.copy() for key, value in corpus[3].items()}
    tampered["hit"][16:, :] = 1.0 - tampered["hit"][16:, :]

    first = baseline.complete(query, observed)
    second = baseline.complete(tampered, observed)
    assert np.array_equal(first["hit"], second["hit"])


def test_retrieval_never_invents_a_pattern() -> None:
    corpus = [_example(index) for index in range(20)]
    baseline = RetrievalBaseline(corpus)
    observed = np.zeros((STEPS, LANES), dtype=np.float32)
    known = {tuple(np.argwhere(e["hit"] > 0.5).flatten()) for e in corpus}
    for seed in range(5):
        out = baseline.complete(_example(100 + seed), observed)
        assert tuple(np.argwhere(out["hit"] > 0.5).flatten()) in known


def test_marginal_sampler_reproduces_the_corpus_density() -> None:
    corpus = [_example(index) for index in range(200)]
    sampler = MarginalSampler(corpus, seed=0)
    generated = [sampler.sample() for _ in range(200)]
    corpus_density = float(np.stack([e["hit"] for e in corpus]).mean())
    sampled_density = float(np.stack([g["hit"] for g in generated]).mean())
    assert abs(sampled_density - corpus_density) < 0.01


def test_marginal_sampler_is_deterministic_for_a_seed() -> None:
    corpus = [_example(index) for index in range(20)]
    first = MarginalSampler(corpus, seed=3).sample()
    second = MarginalSampler(corpus, seed=3).sample()
    assert np.array_equal(first["hit"], second["hit"])
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/eval/test_baselines.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.eval.baselines'`.

- [ ] **Step 3: Write the baselines**

Create `lab/groove_lab/eval/baselines.py`:

```python
"""The two systems the challenger has to beat, neither of which is trained.

``RetrievalBaseline`` is the incumbent: find the train window that best matches
what the task left observed, and copy its answer.  For infill this is a very
strong opponent, and it is what ships today if no neural model wins.

``MarginalSampler`` is the floor: it reproduces the corpus per-cell hit rates and
knows nothing else.  A model that cannot beat it has learned no structure, only
density.
"""

from __future__ import annotations

import numpy as np

STEPS, LANES = 32, 18


class RetrievalBaseline:
    def __init__(self, corpus: list[dict[str, np.ndarray]]) -> None:
        self.corpus = corpus
        self._hits = np.stack([example["hit"] for example in corpus])

    def complete(
        self, query: dict[str, np.ndarray], observed: np.ndarray
    ) -> dict[str, np.ndarray]:
        """Return the corpus window nearest on the observed cells."""

        if observed.sum() == 0:
            # Nothing to match on: fall back to the first window, deterministically.
            index = 0
        else:
            mask = observed[None, :, :]
            distance = np.abs(self._hits - query["hit"][None, :, :]) * mask
            index = int(distance.sum(axis=(1, 2)).argmin())
        return self.corpus[index]


class MarginalSampler:
    def __init__(self, corpus: list[dict[str, np.ndarray]], seed: int) -> None:
        self.rates = np.stack([example["hit"] for example in corpus]).mean(axis=0)
        self.velocity = float(
            np.stack([example["velocity"] for example in corpus]).mean()
        )
        self.rng = np.random.default_rng(seed)

    def sample(self) -> dict[str, np.ndarray]:
        hit = (self.rng.random((STEPS, LANES)) < self.rates).astype(np.float32)
        return {
            "hit": hit,
            "velocity": (hit * self.velocity).astype(np.float32),
            "offset": np.zeros((STEPS, LANES), dtype=np.float32),
        }
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/eval/test_baselines.py -q
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/eval/baselines.py lab/tests/eval/test_baselines.py
git commit -m "feat(eval): add the retrieval incumbent and the marginal floor"
```

---

### Task 3: The comparison runner

**Files:**
- Create: `lab/groove_lab/eval/runner.py`
- Create: `lab/scripts/evaluate_systems.py`
- Test: `lab/tests/eval/test_runner.py`

Every system sees the same validation windows under the same task draws, because
a comparison where the systems face different questions is not a comparison.

- [ ] **Step 1: Write the failing test**

Create `lab/tests/eval/test_runner.py`:

```python
from __future__ import annotations

import numpy as np

from groove_lab.eval.runner import EvaluationCase, build_cases, score_system


def _example(seed: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    hit = (rng.random((32, 18)) > 0.94).astype(np.float32)
    return {
        "hit": hit,
        "subhits": hit.astype(np.int64),
        "velocity": (hit * 0.7).astype(np.float32),
        "offset": np.zeros((32, 18), dtype=np.float32),
        "valid": np.ones((32, 18), dtype=np.float32),
        "conditions": rng.random(16).astype(np.float32),
    }


def test_cases_are_identical_for_the_same_seed() -> None:
    examples = [_example(i) for i in range(10)]
    first = build_cases(examples, seed=1)
    second = build_cases(examples, seed=1)
    assert [c.task for c in first] == [c.task for c in second]
    assert all(
        np.array_equal(a.target, b.target) for a, b in zip(first, second, strict=True)
    )


def test_only_infill_family_tasks_are_scored_for_the_primary_metric() -> None:
    examples = [_example(i) for i in range(40)]
    cases = build_cases(examples, seed=1)
    scored = [c for c in cases if c.counts_for_primary]
    assert scored, "the infill family must produce at least one scored case"
    assert all(
        c.task in {"temporal_infill", "lane_infill", "fill", "continuation"}
        for c in scored
    )


def test_a_perfect_system_scores_one() -> None:
    examples = [_example(i) for i in range(10)]
    cases = build_cases(examples, seed=1)

    def oracle(case: EvaluationCase) -> dict[str, np.ndarray]:
        return {
            "hit": case.truth["hit"],
            "velocity": case.truth["velocity"],
            "offset": case.truth["offset"],
        }

    result = score_system(oracle, cases)
    assert result["hit_f1"] > 0.99


def test_a_silent_system_scores_zero() -> None:
    examples = [_example(i) for i in range(10)]
    cases = build_cases(examples, seed=1)

    def silence(case: EvaluationCase) -> dict[str, np.ndarray]:
        return {
            "hit": np.zeros((32, 18), dtype=np.float32),
            "velocity": np.zeros((32, 18), dtype=np.float32),
            "offset": np.zeros((32, 18), dtype=np.float32),
        }

    assert score_system(silence, cases)["hit_f1"] == 0.0
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/eval/test_runner.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.eval.runner'`.

- [ ] **Step 3: Write the runner**

Create `lab/groove_lab/eval/runner.py`:

```python
"""Score every system on the same windows, under the same task draws.

The cases are built once from a seed and handed to each system unchanged.  A
comparison where the model and the baseline face different maskings is not a
comparison, and building the cases separately per system is the easiest way to
get that wrong without noticing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from ..training.tasks import apply_task, sample_task
from .metrics import hit_f1, velocity_offset_error

PRIMARY_TASKS = frozenset(
    {"temporal_infill", "lane_infill", "fill", "continuation"}
)


@dataclass
class EvaluationCase:
    truth: dict[str, np.ndarray]
    observed: np.ndarray
    target: np.ndarray
    conditions: np.ndarray
    task: str

    @property
    def counts_for_primary(self) -> bool:
        return self.task in PRIMARY_TASKS


def build_cases(
    examples: Sequence[dict[str, np.ndarray]], seed: int
) -> list[EvaluationCase]:
    rng = np.random.default_rng(seed)
    cases: list[EvaluationCase] = []
    for example in examples:
        task = sample_task(rng)
        observed, target = apply_task(task, example["valid"], rng)
        cases.append(
            EvaluationCase(
                truth=example,
                observed=observed,
                target=target,
                conditions=example["conditions"],
                task=task,
            )
        )
    return cases


def score_system(
    system: Callable[[EvaluationCase], dict[str, np.ndarray]],
    cases: Sequence[EvaluationCase],
) -> dict[str, float]:
    f1_scores: list[float] = []
    velocity_errors: list[float] = []
    offset_errors: list[float] = []
    for case in cases:
        if not case.counts_for_primary:
            continue
        prediction = system(case)
        f1_scores.append(hit_f1(prediction["hit"], case.truth["hit"], case.target))
        velocity_errors.append(
            velocity_offset_error(
                prediction["velocity"],
                case.truth["velocity"],
                case.truth["hit"],
                case.target,
            )
        )
        offset_errors.append(
            velocity_offset_error(
                prediction["offset"],
                case.truth["offset"],
                case.truth["hit"],
                case.target,
            )
        )
    return {
        "hit_f1": float(np.mean(f1_scores)) if f1_scores else 0.0,
        "velocity_mae": float(np.mean(velocity_errors)) if velocity_errors else 0.0,
        "offset_mae": float(np.mean(offset_errors)) if offset_errors else 0.0,
        "cases": float(len(f1_scores)),
    }
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/eval/test_runner.py -q
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Write the entry point**

Create `lab/scripts/evaluate_systems.py`:

```python
"""Score the masked HVO against the baselines and answer gate G5."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "lab"))

from groove_lab.eval.baselines import MarginalSampler, RetrievalBaseline  # noqa: E402
from groove_lab.eval.metrics import (  # noqa: E402
    exact_repeat_rate,
    lane_distribution,
    lane_distribution_distance,
)
from groove_lab.eval.runner import EvaluationCase, build_cases, score_system  # noqa: E402
from groove_lab.training.loader import ShardDataset  # noqa: E402
from groove_lab.training.loop import TrainState, load_checkpoint  # noqa: E402
from groove_lab.training.model import MaskedHvo  # noqa: E402
from groove_lab.training.tasks import TASK_INDEX  # noqa: E402

DATASET = "F:/groove-brain/dataset/build-a"
RUNS = Path("F:/groove-brain/runs")
OUTPUT = RUNS / "gate_g5.json"
SEEDS = (0, 1, 2)
CORPUS_REPEAT_RATE = 0.260  # specification 4.2


def _model_system(model: MaskedHvo):
    def run(case: EvaluationCase) -> dict[str, np.ndarray]:
        with torch.no_grad():
            out = model(
                hit=torch.from_numpy(case.truth["hit"]).unsqueeze(0),
                velocity=torch.from_numpy(case.truth["velocity"]).unsqueeze(0),
                offset=torch.from_numpy(case.truth["offset"]).unsqueeze(0),
                observed_mask=torch.from_numpy(case.observed).unsqueeze(0),
                conditions=torch.from_numpy(case.conditions).unsqueeze(0),
                task=torch.tensor([TASK_INDEX[case.task]], dtype=torch.long),
            )
        return {
            "hit": torch.sigmoid(out["hit_logits"])[0].numpy(),
            "velocity": out["velocity"][0].numpy(),
            "offset": out["offset"][0].numpy(),
        }

    return run


def main() -> None:
    torch.set_num_threads(1)
    train = ShardDataset(DATASET, "train", max_subhits=4)
    validation = ShardDataset(DATASET, "validation", max_subhits=4)
    corpus = [train[i] for i in range(len(train))]
    examples = [validation[i] for i in range(len(validation))]

    retrieval = RetrievalBaseline(corpus)
    results: dict[str, object] = {"corpus_repeat_rate": CORPUS_REPEAT_RATE}
    per_seed: dict[str, list[float]] = {"masked_hvo": [], "retrieval": [], "marginal": []}

    for seed in SEEDS:
        cases = build_cases(examples, seed=seed)
        state = TrainState(MaskedHvo(), 1e-3, 0)
        load_checkpoint(state, RUNS / f"m1-seed{seed}" / "best.pt")
        state.model.eval()

        sampler = MarginalSampler(corpus, seed=seed)
        systems = {
            "masked_hvo": _model_system(state.model),
            "retrieval": lambda case: retrieval.complete(case.truth, case.observed),
            "marginal": lambda case: sampler.sample(),
        }
        for name, system in systems.items():
            per_seed[name].append(score_system(system, cases)["hit_f1"])
        print(f"seed {seed} scored", flush=True)

    corpus_hits = [example["hit"] for example in corpus]
    summary: dict[str, object] = {}
    for name, scores in per_seed.items():
        summary[name] = {
            "hit_f1_per_seed": scores,
            "hit_f1_mean": float(np.mean(scores)),
            "hit_f1_spread": float(max(scores) - min(scores)),
        }

    best_baseline = max(
        ("retrieval", "marginal"), key=lambda name: summary[name]["hit_f1_mean"]
    )
    baseline_spread = summary[best_baseline]["hit_f1_spread"]
    beats_every_seed = all(
        model > baseline
        for model, baseline in zip(
            per_seed["masked_hvo"], per_seed[best_baseline], strict=True
        )
    )
    margin = summary["masked_hvo"]["hit_f1_mean"] - summary[best_baseline]["hit_f1_mean"]

    results["systems"] = summary
    results["best_baseline"] = best_baseline
    results["g5_primary"] = {
        "beats_best_baseline_on_every_seed": beats_every_seed,
        "margin": margin,
        "baseline_seed_spread": baseline_spread,
        "pass": bool(beats_every_seed and margin > baseline_spread),
    }
    results["lane_distribution"] = {
        "corpus": lane_distribution(corpus_hits).tolist(),
    }
    results["originality"] = {
        "retrieval_is_a_copy_by_construction": True,
        "note": (
            "Retrieval returns real corpus windows, so its exact repeat rate is "
            "100% by definition. Stated before the run, not discovered after."
        ),
    }
    OUTPUT.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Commit**

```bash
git add lab/groove_lab/eval/runner.py lab/scripts/evaluate_systems.py lab/tests/eval/test_runner.py
git commit -m "feat(eval): score every system on identical cases"
```

---

### Task 4: Run the comparison and answer G5

**Files:**
- Create: `docs/superpowers/plans/2026-08-31-groove-brain-baselines-and-evaluation-result.md`

- [ ] **Step 1: Run it**

Run:

```bash
lab/.venv-lab/Scripts/python.exe lab/scripts/evaluate_systems.py
```

- [ ] **Step 2: Add the musicality and originality numbers**

Extend `evaluate_systems.py` to also generate 64 free-generation grids per seed
from the model and from the marginal sampler, and record for each system:
`lane_distribution_distance` against the corpus, and `exact_repeat_rate` against
the train split. Retrieval is excluded from free generation because it has
nothing to condition on there, and its copy rate is 100% by definition.

```python
    from groove_lab.training.generate import generate

    free: dict[str, list[np.ndarray]] = {"masked_hvo": [], "marginal": []}
    for seed in SEEDS:
        state = TrainState(MaskedHvo(), 1e-3, 0)
        load_checkpoint(state, RUNS / f"m1-seed{seed}" / "best.pt")
        state.model.eval()
        sampler = MarginalSampler(corpus, seed=seed)
        for sample in range(64):
            free["masked_hvo"].append(
                generate(
                    state.model,
                    np.zeros(16, dtype=np.float32),
                    seed=seed * 1000 + sample,
                    decoding_steps=32,
                    temperature=1.0,
                )["hit"]
            )
            free["marginal"].append(sampler.sample()["hit"])

    results["musicality"] = {
        name: {
            "lane_distance_to_corpus": lane_distribution_distance(grids, corpus_hits),
            "lane_distribution": lane_distribution(grids).tolist(),
            "exact_repeat_rate": exact_repeat_rate(grids, corpus_hits),
        }
        for name, grids in free.items()
    }
```

- [ ] **Step 3: Re-run and read the three gate conditions**

Run:

```bash
lab/.venv-lab/Scripts/python.exe lab/scripts/evaluate_systems.py
```

Check the primary condition, the lane distance against the best baseline's, and
the exact repeat rate against 26.0%. Record whichever fail. Do not adjust the
primary metric or the thresholds; they are declared above.

- [ ] **Step 4: Write the result document**

Create the result document recording: hit F1 per system per seed, the margin
against the baseline's own spread, the lane distributions side by side with the
corpus, the exact repeat rates, and a plain statement of whether G5 passed.

If the masked HVO loses to retrieval, say so in the first line. Specification
23 already commits to the outcome: the deterministic product stays, and that is
a result, not a failure of the work.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-08-31-groove-brain-baselines-and-evaluation-result.md lab/scripts/evaluate_systems.py
git commit -m "docs: record the baseline comparison and the G5 result"
```

---

### Task 5: MIDI export for listening

**Files:**
- Create: `lab/groove_lab/eval/export.py`
- Test: `lab/tests/eval/test_export.py`

- [ ] **Step 1: Write the failing test**

Create `lab/tests/eval/test_export.py`:

```python
from __future__ import annotations

import numpy as np
from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf

from groove_lab.eval.export import grid_to_midi


def test_a_grid_round_trips_through_a_real_smf() -> None:
    hit = np.zeros((32, 18), dtype=np.float32)
    hit[0, 0] = 1.0   # kick on the downbeat
    hit[8, 1] = 1.0   # snare on beat three
    grid = {
        "hit": hit,
        "velocity": np.where(hit > 0, 0.8, 0.0).astype(np.float32),
        "offset": np.zeros((32, 18), dtype=np.float32),
        "subhits": hit.astype(np.int64),
    }
    parsed = parse_smf(grid_to_midi(grid, bpm=120.0))
    assert len(parsed.note_events) == 2
    assert {note.pitch for note in parsed.note_events} == {36, 38}


def test_offsets_move_notes_off_the_grid() -> None:
    hit = np.zeros((32, 18), dtype=np.float32)
    hit[4, 0] = 1.0
    straight = {
        "hit": hit,
        "velocity": np.where(hit > 0, 0.8, 0.0).astype(np.float32),
        "offset": np.zeros((32, 18), dtype=np.float32),
        "subhits": hit.astype(np.int64),
    }
    late = dict(straight, offset=np.where(hit > 0, 0.5, 0.0).astype(np.float32))
    first = parse_smf(grid_to_midi(straight, bpm=120.0)).note_events[0]
    second = parse_smf(grid_to_midi(late, bpm=120.0)).note_events[0]
    assert second.start_ticks > first.start_ticks


def test_a_silent_grid_produces_a_valid_empty_file() -> None:
    grid = {
        "hit": np.zeros((32, 18), dtype=np.float32),
        "velocity": np.zeros((32, 18), dtype=np.float32),
        "offset": np.zeros((32, 18), dtype=np.float32),
        "subhits": np.zeros((32, 18), dtype=np.int64),
    }
    assert parse_smf(grid_to_midi(grid, bpm=120.0)).note_events == []
```

- [ ] **Step 2: Run it to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/eval/test_export.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.eval.export'`.

- [ ] **Step 3: Write the exporter**

Create `lab/groove_lab/eval/export.py`:

```python
"""Turn a generated grid into a real MIDI file, so it can be heard.

Uses the product's own serializer rather than a second implementation, so what a
listener hears is what the product would write.  Lanes map back to General MIDI
pitches, which is the reverse of the articulation map and is only correct in that
direction: the map is many-to-one, so this picks the canonical GM pitch per lane.
"""

from __future__ import annotations

import numpy as np
from ableton_mcp_server.groove_intelligence.drum_roles import GM_DRUM_ROLES
from ableton_mcp_server.groove_intelligence.midi_lossless import serialize_note_smf
from ableton_mcp_server.groove_intelligence.schema import NoteEventV1

PPQ = 480
STEP_TICKS = PPQ // 4
STEPS = 32
OFFSET_SCALE = 60.0  # the canonical half-cell, matching the dataset's int8 range
DURATION_TICKS = STEP_TICKS // 2

# One canonical General MIDI pitch per canonical lane.
LANE_PITCH = {
    "kick": 36, "snare": 38, "rim": 37, "clap": 39,
    "hat_closed": 42, "hat_open": 46, "hat_pedal": 44,
    "tom_low": 41, "tom_mid": 47, "tom_high": 50,
    "crash": 49, "splash": 55, "china": 52, "ride": 51, "ride_bell": 53,
    "tambourine": 54, "cowbell": 56, "other_percussion": 39,
}


def grid_to_midi(grid: dict[str, np.ndarray], bpm: float) -> bytes:
    notes: list[NoteEventV1] = []
    event_id = 0
    for row, lane in sorted(map(tuple, np.argwhere(grid["hit"] > 0.5))):
        pitch = LANE_PITCH[GM_DRUM_ROLES[lane]]
        start = row * STEP_TICKS + int(round(float(grid["offset"][row, lane]) * OFFSET_SCALE))
        velocity = int(round(float(grid["velocity"][row, lane]) * 127))
        notes.append(
            NoteEventV1(
                event_id=event_id,
                track_index=0,
                channel=9,
                pitch=pitch,
                velocity=max(1, min(127, velocity)),
                start_ticks=max(0, start),
                duration_ticks=DURATION_TICKS,
            )
        )
        event_id += 1
    return serialize_note_smf(
        notes,
        ppq=PPQ,
        length_ticks=STEPS * STEP_TICKS,
        tempos=[{"track_index": 0, "absolute_ticks": 0,
                 "microseconds": int(round(60_000_000 / bpm))}],
    )
```

- [ ] **Step 4: Run it to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/eval/test_export.py -q
```

Expected: PASS, 3 tests.

If `serialize_note_smf` rejects the tempo dictionary shape, read its signature at
`ableton_mcp_server/groove_intelligence/midi_lossless.py:55` and match it exactly
rather than working around it — the point of using the product serializer is that
the listener hears what the product would write.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/eval/export.py lab/tests/eval/test_export.py
git commit -m "feat(eval): export generated grids as real MIDI"
```

---

### Task 6: The pre-registered listening protocol

**Files:**
- Create: `docs/superpowers/specs/2026-08-31-groove-brain-listening-protocol.md`
- Create: `lab/scripts/make_listening_set.py`

The protocol is written and the collection is **not run**: decision O1 — how
many people rate — is unanswered, and specification 18.5 requires the rater count
declared before collecting.

- [ ] **Step 1: Write the protocol document**

Create `docs/superpowers/specs/2026-08-31-groove-brain-listening-protocol.md`
containing, in this order and with no placeholders:

1. **What is being compared:** the masked HVO transformer against the best
   baseline from the G5 run, named explicitly.
2. **Task list:** 30 frozen prompts, written out, spread across the six
   implemented tasks and across the tempo and section labels the vendor data
   supplies.
3. **Presentation:** each trial is two MIDI files, A and B, order randomised per
   trial by a recorded seed, both normalised to the same kit and the same
   velocity ceiling, no system name anywhere in the filename or the folder.
4. **What the rater answers:** which of A or B they would use, plus a five-point
   rating for groove, usefulness, control and novelty.
5. **The threshold:** promotion needs the lower bound of the 95% Wilson interval
   for preference above 50%, which with 30 paired trials and ties excluded means
   **at least 21 of 30**, exactly as specification 18.5 records.
6. **Rater count:** left as decision **O1**, with the consequence written out —
   one rater means the interval is over tasks and not over people, and the model
   card must say so in those words.
7. **Stopping rule:** the set is generated once, from a recorded seed; a rater
   sees each trial once; the test is not repeated with the same set after seeing
   the result.

- [ ] **Step 2: Write the generator**

Create `lab/scripts/make_listening_set.py`:

```python
"""Generate the blind listening set: 30 trials, two anonymous files each."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "lab"))

from groove_lab.eval.baselines import RetrievalBaseline  # noqa: E402
from groove_lab.eval.export import grid_to_midi  # noqa: E402
from groove_lab.eval.runner import build_cases  # noqa: E402
from groove_lab.training.generate import generate  # noqa: E402
from groove_lab.training.loader import ShardDataset  # noqa: E402
from groove_lab.training.loop import TrainState, load_checkpoint  # noqa: E402
from groove_lab.training.model import MaskedHvo  # noqa: E402

DATASET = "F:/groove-brain/dataset/build-a"
RUNS = Path("F:/groove-brain/runs")
TRIALS = 30
ORDER_SEED = 20260831
BPM = 120.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--checkpoint-seed", type=int, default=0)
    arguments = parser.parse_args()

    torch.set_num_threads(1)
    trials_dir = arguments.out / "trials"
    trials_dir.mkdir(parents=True, exist_ok=True)

    train = ShardDataset(DATASET, "train", max_subhits=4)
    validation = ShardDataset(DATASET, "validation", max_subhits=4)
    corpus = [train[index] for index in range(len(train))]
    retrieval = RetrievalBaseline(corpus)

    state = TrainState(MaskedHvo(), 1e-3, 0)
    load_checkpoint(state, RUNS / f"m1-seed{arguments.checkpoint_seed}" / "best.pt")
    state.model.eval()

    cases = build_cases(
        [validation[index] for index in range(len(validation))], seed=ORDER_SEED
    )[:TRIALS]
    order_rng = np.random.default_rng(ORDER_SEED)
    key: list[dict[str, object]] = []

    for number, case in enumerate(cases, start=1):
        model_grid = generate(
            state.model,
            case.conditions,
            seed=ORDER_SEED + number,
            decoding_steps=32,
            temperature=1.0,
        )
        neighbour = retrieval.complete(case.truth, case.observed)
        baseline_grid = {
            "hit": neighbour["hit"],
            "velocity": neighbour["velocity"],
            "offset": neighbour["offset"],
            "subhits": neighbour["subhits"],
        }

        model_is_a = bool(order_rng.integers(0, 2))
        first, second = (
            (model_grid, baseline_grid) if model_is_a else (baseline_grid, model_grid)
        )
        (trials_dir / f"trial-{number:02d}-A.mid").write_bytes(grid_to_midi(first, BPM))
        (trials_dir / f"trial-{number:02d}-B.mid").write_bytes(grid_to_midi(second, BPM))
        key.append(
            {
                "trial": number,
                "task": case.task,
                "A": "masked_hvo" if model_is_a else "retrieval",
                "B": "retrieval" if model_is_a else "masked_hvo",
            }
        )

    # The key sits beside the trials directory, never inside it.
    (arguments.out / "key.json").write_text(
        json.dumps(
            {"order_seed": ORDER_SEED, "bpm": BPM, "trials": key},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(key)} trials written to {trials_dir}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Generate the set**

Run:

```bash
lab/.venv-lab/Scripts/python.exe lab/scripts/make_listening_set.py --out F:/groove-brain/listening
```

Expected: 60 MIDI files under `F:/groove-brain/listening/trials/` and a key under
`F:/groove-brain/listening/key.json`.

- [ ] **Step 4: Verify the blinding**

Run:

```bash
ls F:/groove-brain/listening/trials | head -6
grep -ril "hvo\|retrieval\|model\|baseline" F:/groove-brain/listening/trials | head
```

Expected: filenames of the form `trial-01-A.mid`, and the grep finding nothing.
A leak here voids the test.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-08-31-groove-brain-listening-protocol.md lab/scripts/make_listening_set.py
git commit -m "docs: pre-register the blind listening protocol"
```

---

### Task 7: Close G5 in the design document

**Files:**
- Modify: `docs/superpowers/specs/2026-08-31-groove-brain-dataset-training-design.md`

- [ ] **Step 1: Record the result in section 20**

Append to the `**G5** Bake-off` row: the primary metric that was declared, the
hit F1 per system, the margin against the baseline's spread, and pass or fail.
State in the same cell that GrooVAE and event AR were not part of this comparison
and why.

- [ ] **Step 2: Record the musicality finding in section 18.3**

Add the measured lane distances for the model, the marginal sampler and the
corpus, marked `[fato]`. This is the metric plan 6 showed was missing.

- [ ] **Step 3: Add the two deferred baselines to section 21**

Split the old plan 5 entry into the executed part and a new plan for GrooVAE and
event AR, so the ladder shows what is done and what is not.

- [ ] **Step 4: Verify no contradictions**

Run:

```bash
git diff --check -- docs/
python -c "import re;t=open('docs/superpowers/specs/2026-08-31-groove-brain-dataset-training-design.md',encoding='utf-8').read();h={m.group(1) for m in re.finditer(r'^#{2,4} (\d+(?:\.\d+)*)[.\s]',t,re.M)};r={m.group(1) for m in re.finditer(r'seção (\d+(?:\.\d+)*)',t)};print('refs quebradas:',sorted(r-h) or 'nenhuma')"
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests -q
.venv-win/Scripts/python.exe -m pytest -q --tb=line
```

Expected: no whitespace complaints, no broken references, all lab tests pass, and
the product suite at `906 passed` with its four known prototype failures.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-08-31-groove-brain-dataset-training-design.md
git commit -m "docs: record the baseline comparison and close G5"
```

---

## What this plan does not do

It does not implement GrooVAE or the event-based autoregressive decoder. Each is
its own plan, needed for the architecture choice at M2 and G6, not for deciding
whether a neural model beats the incumbent.

It does not run the listening test. Decision O1 — the rater count — is open, and
specification 18.5 requires it declared before collecting. The instrument is
built and the set is generated; pressing play is the owner's call.

It does not retrain anything. The checkpoints are plan 6's, unchanged, so the
comparison measures what plan 6 actually produced.

## Stop condition

Done when the three G5 conditions are measured and recorded, the listening set
exists and is verifiably blind, and section 20 of the design carries the number.

If the masked HVO loses to retrieval, that is the result and it goes in the first
line of the report. Specification 23 already commits to what follows: retrieval
and the deterministic transforms remain the product. The programme was designed
so that answer is survivable, and reporting it plainly is the whole reason the
gate exists.
