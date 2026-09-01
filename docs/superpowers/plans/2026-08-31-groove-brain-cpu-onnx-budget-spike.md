# Groove Brain CPU/ONNX Budget Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure how many iterative decoding steps a masked HVO model can afford inside the provider's hard limit of `cpu_seconds <= 2.0`, using an untrained model, so the architecture is chosen before anything is trained.

**Architecture:** A CPU-only lab virtual environment, isolated from the product environment, holds PyTorch, ONNX and ONNX Runtime. Two tokenisations of the same 32-step by 18-lane grid are built — one token per cell (576 tokens) and one token per step with lanes as channels (32 tokens) — exported to ONNX and measured under the seven `ProviderLimitsV1` ceilings. The deliverable is a number: the maximum decoding steps each tokenisation supports, and therefore which one the training plan may use.

**Tech Stack:** Python 3.10 on Windows x64, PyTorch CPU wheel, `torch.onnx` with the Dynamo exporter, `onnxruntime` CPU execution provider, `psutil` for peak working set, `time.process_time` for CPU seconds.

---

## Why this runs before any training

`ProviderLimitsV1` (`ableton_mcp_server/groove_intelligence/provider.py:49-59`) declares seven ceilings with `le=` in the schema, so they cannot be raised by configuration:

| Limit | Value |
|---|---|
| `generation_seconds` | `<= 5.0` |
| `cpu_seconds` | `<= 2.0` |
| `startup_seconds` | `<= 2.0` |
| `shutdown_seconds` | `<= 1.0` |
| `memory_mib` | `<= 512` |
| `max_response_bytes` | `<= 262144` |
| `max_events` | `<= 2048` |

`cpu_seconds` is CPU time summed across threads, not wall time. Iterative decoding multiplies the forward cost by the number of steps. If the chosen architecture cannot decode within 2.0 CPU-seconds, discovering that after the bake-off would invalidate two training plans.

**Expected outcome, stated in advance so the measurement can contradict it:** the cell-as-token layout is 576 tokens and costs roughly 7.5 GFLOP per forward pass, which on this machine is likely to allow only a small number of decoding steps. The step-as-token layout is 32 tokens and should cost far less. If that expectation holds, the training plan uses step-as-token. If it does not, the measurement wins.

## File Structure

Everything lives under a new `lab/` tree, separate from the product package, plus one gitignore entry.

| Path | Responsibility |
|---|---|
| `lab/README.md` | How to create the lab environment and run the spike |
| `lab/requirements.txt` | Pinned CPU-only lab dependencies |
| `lab/groove_lab/__init__.py` | Package marker |
| `lab/groove_lab/model.py` | The two masked HVO variants and their parameter counts |
| `lab/groove_lab/decoding.py` | The iterative confidence decoding loop, framework-agnostic |
| `lab/groove_lab/export.py` | Torch to ONNX export and the parity check |
| `lab/groove_lab/budget.py` | Measurement harness for the seven limits |
| `lab/scripts/run_spike.py` | Entry point that sweeps decoding steps and writes the report |
| `lab/tests/test_model.py` | Shape and parameter-count tests |
| `lab/tests/test_decoding.py` | Decoding loop tests |
| `lab/tests/test_budget.py` | Harness tests |
| `docs/superpowers/plans/2026-08-31-groove-brain-cpu-onnx-budget-spike-result.md` | The measured answer |
| `.gitignore` | Excludes `lab/.venv-lab/` and `lab/artifacts/` |

The product package `ableton_mcp_server/` is not touched. The product environment `.venv-win` is not touched.

---

### Task 1: Lab environment, isolated from the product

**Files:**
- Create: `lab/requirements.txt`
- Create: `lab/README.md`
- Modify: `.gitignore`

- [ ] **Step 1: Write the requirements file**

Create `lab/requirements.txt`:

```text
# CPU-only lab dependencies. Never installed into the product environment.
# Install with:
#   pip install -r lab/requirements.txt --index-url https://download.pytorch.org/whl/cpu \
#       --extra-index-url https://pypi.org/simple
torch==2.12.0
onnx==1.18.0
onnxruntime==1.24.0
numpy==2.2.6
psutil==7.0.0
pytest==8.4.1
```

- [ ] **Step 2: Add the ignore entries**

Append to `.gitignore`:

```text
lab/.venv-lab/
lab/artifacts/
```

- [ ] **Step 3: Create the lab environment**

Run:

```bash
py -3.10 -m venv lab/.venv-lab
```

Expected: the directory `lab/.venv-lab/Scripts/python.exe` exists.

- [ ] **Step 4: Install the dependencies**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pip install -r lab/requirements.txt --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple
```

Expected: installation completes. If a pinned version is unavailable, install the nearest available version and record the exact resolved versions in Step 6 rather than silently drifting.

- [ ] **Step 5: Verify the environment is CPU-only and the product environment is untouched**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -c "import torch, onnxruntime; print(torch.__version__, torch.cuda.is_available(), onnxruntime.__version__, onnxruntime.get_available_providers())"
```

Expected: prints a torch version, `False` for CUDA, an onnxruntime version, and a provider list containing `CPUExecutionProvider`. The `False` matters: a CUDA build would make the measurement optimistic relative to the user's machine.

Run:

```bash
.venv-win/Scripts/python.exe -c "import importlib.util as u; print(u.find_spec('torch'))"
```

Expected: `None`. The product environment must not have acquired PyTorch.

- [ ] **Step 6: Write the lab README**

Create `lab/README.md`:

```markdown
# Groove Brain lab

Experiment code for the Groove Brain training program. Nothing here ships. The
product package `ableton_mcp_server/` never imports from `groove_lab`, and the
product environment `.venv-win` never installs these dependencies.

## Environment

```bash
py -3.10 -m venv lab/.venv-lab
lab/.venv-lab/Scripts/python.exe -m pip install -r lab/requirements.txt \
  --index-url https://download.pytorch.org/whl/cpu \
  --extra-index-url https://pypi.org/simple
```

CPU-only on purpose. The budget spike measures the user's inference path, which
is CPU, so a CUDA build would make the numbers optimistic.

## Running the budget spike

```bash
lab/.venv-lab/Scripts/python.exe lab/scripts/run_spike.py
```

Writes `lab/artifacts/budget.json` and the report at
`docs/superpowers/plans/2026-08-31-groove-brain-cpu-onnx-budget-spike-result.md`.

## Resolved versions

Recorded by `run_spike.py` into `lab/artifacts/budget.json` under `environment`.
```

- [ ] **Step 7: Commit**

```bash
git add lab/requirements.txt lab/README.md .gitignore
git commit -m "chore(lab): add an isolated CPU-only lab environment"
```

---

### Task 2: The two model variants

**Files:**
- Create: `lab/groove_lab/__init__.py`
- Create: `lab/groove_lab/model.py`
- Test: `lab/tests/test_model.py`

The grid is 32 steps by 18 lanes, matching `groove.hvo.v3`. Both variants take the same inputs and produce the same four heads. They differ only in what a token is.

- [ ] **Step 1: Write the failing test**

Create `lab/tests/test_model.py`:

```python
from __future__ import annotations

import torch

from groove_lab.model import CellTokenHvo, StepTokenHvo, count_parameters

STEPS = 32
LANES = 18
CONDITIONS = 16
BATCH = 2


def _inputs(batch: int = BATCH) -> dict[str, torch.Tensor]:
    return {
        "hit": torch.zeros(batch, STEPS, LANES),
        "velocity": torch.zeros(batch, STEPS, LANES),
        "offset": torch.zeros(batch, STEPS, LANES),
        "observed_mask": torch.zeros(batch, STEPS, LANES),
        "conditions": torch.zeros(batch, CONDITIONS),
    }


def test_cell_token_shapes() -> None:
    model = CellTokenHvo()
    out = model(**_inputs())
    assert out["hit_logits"].shape == (BATCH, STEPS, LANES)
    assert out["subhits_logits"].shape == (BATCH, STEPS, LANES, 4)
    assert out["velocity"].shape == (BATCH, STEPS, LANES)
    assert out["offset"].shape == (BATCH, STEPS, LANES)


def test_step_token_shapes() -> None:
    model = StepTokenHvo()
    out = model(**_inputs())
    assert out["hit_logits"].shape == (BATCH, STEPS, LANES)
    assert out["subhits_logits"].shape == (BATCH, STEPS, LANES, 4)
    assert out["velocity"].shape == (BATCH, STEPS, LANES)
    assert out["offset"].shape == (BATCH, STEPS, LANES)


def test_sequence_lengths_differ_as_designed() -> None:
    assert CellTokenHvo().sequence_length == STEPS * LANES == 576
    assert StepTokenHvo().sequence_length == STEPS == 32


def test_parameter_counts_are_in_the_small_band() -> None:
    # The spec's small tier is 6 layers, d_model 256, 8 heads, FFN 1024, which is
    # about 4.7M parameters in the encoder blocks alone.
    for model in (CellTokenHvo(), StepTokenHvo()):
        total = count_parameters(model)
        assert 3_000_000 < total < 12_000_000, total


def test_models_are_deterministic_for_a_fixed_seed() -> None:
    torch.manual_seed(0)
    first = CellTokenHvo()
    torch.manual_seed(0)
    second = CellTokenHvo()
    inputs = _inputs()
    with torch.no_grad():
        a = first(**inputs)["hit_logits"]
        b = second(**inputs)["hit_logits"]
    assert torch.equal(a, b)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/test_model.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab'`.

- [ ] **Step 3: Write the package marker and the models**

Create `lab/groove_lab/__init__.py`:

```python
"""Experiment code for the Groove Brain training program. Nothing here ships."""
```

Create `lab/groove_lab/model.py`:

```python
"""Two tokenisations of the same masked HVO grid, at the spec's small tier.

The grid is 32 steps by 18 lanes, matching ``groove.hvo.v3``.  Both variants read
the same five inputs and produce the same four heads.  They differ only in what a
transformer token is, which is the single decision that drives inference cost:

* :class:`CellTokenHvo` gives every ``(step, lane)`` cell its own token, so the
  sequence is 576 long and self-attention is quadratic in that;
* :class:`StepTokenHvo` gives every step one token with the lanes folded into the
  channel dimension, so the sequence is 32 long.

Both carry a ``subhits`` head, because section 11.2 of the design makes the
multiplicity channel mandatory: no dense one-hit-per-cell grid represents the
corpus without loss.
"""

from __future__ import annotations

import torch
from torch import nn

STEPS = 32
LANES = 18
CONDITIONS = 16
MAX_SUBHITS = 4

D_MODEL = 256
LAYERS = 6
HEADS = 8
FFN = 1024


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())


def _encoder() -> nn.TransformerEncoder:
    layer = nn.TransformerEncoderLayer(
        d_model=D_MODEL,
        nhead=HEADS,
        dim_feedforward=FFN,
        dropout=0.0,
        batch_first=True,
        norm_first=True,
    )
    return nn.TransformerEncoder(layer, num_layers=LAYERS, enable_nested_tensor=False)


class CellTokenHvo(nn.Module):
    """One token per (step, lane) cell. Sequence length 576."""

    sequence_length = STEPS * LANES

    def __init__(self) -> None:
        super().__init__()
        self.value_projection = nn.Linear(4, D_MODEL)
        self.step_embedding = nn.Embedding(STEPS, D_MODEL)
        self.lane_embedding = nn.Embedding(LANES, D_MODEL)
        self.condition_projection = nn.Linear(CONDITIONS, D_MODEL)
        self.encoder = _encoder()
        self.hit_head = nn.Linear(D_MODEL, 1)
        self.subhits_head = nn.Linear(D_MODEL, MAX_SUBHITS)
        self.velocity_head = nn.Linear(D_MODEL, 1)
        self.offset_head = nn.Linear(D_MODEL, 1)

        steps = torch.arange(STEPS).unsqueeze(1).expand(STEPS, LANES).reshape(-1)
        lanes = torch.arange(LANES).unsqueeze(0).expand(STEPS, LANES).reshape(-1)
        self.register_buffer("step_index", steps, persistent=False)
        self.register_buffer("lane_index", lanes, persistent=False)

    def forward(
        self,
        hit: torch.Tensor,
        velocity: torch.Tensor,
        offset: torch.Tensor,
        observed_mask: torch.Tensor,
        conditions: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        batch = hit.shape[0]
        values = torch.stack((hit, velocity, offset, observed_mask), dim=-1)
        tokens = values.reshape(batch, STEPS * LANES, 4)
        embedded = self.value_projection(tokens)
        embedded = embedded + self.step_embedding(self.step_index).unsqueeze(0)
        embedded = embedded + self.lane_embedding(self.lane_index).unsqueeze(0)
        embedded = embedded + self.condition_projection(conditions).unsqueeze(1)

        encoded = self.encoder(embedded)
        grid = encoded.reshape(batch, STEPS, LANES, D_MODEL)
        return {
            "hit_logits": self.hit_head(grid).squeeze(-1),
            "subhits_logits": self.subhits_head(grid),
            "velocity": torch.sigmoid(self.velocity_head(grid).squeeze(-1)),
            "offset": torch.tanh(self.offset_head(grid).squeeze(-1)),
        }


class StepTokenHvo(nn.Module):
    """One token per step, lanes folded into channels. Sequence length 32."""

    sequence_length = STEPS

    def __init__(self) -> None:
        super().__init__()
        self.value_projection = nn.Linear(LANES * 4, D_MODEL)
        self.step_embedding = nn.Embedding(STEPS, D_MODEL)
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
    ) -> dict[str, torch.Tensor]:
        batch = hit.shape[0]
        values = torch.stack((hit, velocity, offset, observed_mask), dim=-1)
        tokens = values.reshape(batch, STEPS, LANES * 4)
        embedded = self.value_projection(tokens)
        embedded = embedded + self.step_embedding(self.step_index).unsqueeze(0)
        embedded = embedded + self.condition_projection(conditions).unsqueeze(1)

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

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/test_model.py -q
```

Expected: PASS, 5 tests.

If `test_parameter_counts_are_in_the_small_band` fails, print the two counts and record them; do not widen the band to make the test pass. A count outside 3M to 12M means the configuration constants drifted from the spec's small tier and the constants are what should change.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/__init__.py lab/groove_lab/model.py lab/tests/test_model.py
git commit -m "feat(lab): add cell-token and step-token masked HVO variants"
```

---

### Task 3: The iterative decoding loop

**Files:**
- Create: `lab/groove_lab/decoding.py`
- Test: `lab/tests/test_decoding.py`

Confidence decoding: start with everything masked, run a forward pass, commit the most confident cells, feed them back as observed, repeat. The number of passes is the quantity this whole spike exists to bound.

- [ ] **Step 1: Write the failing test**

Create `lab/tests/test_decoding.py`:

```python
from __future__ import annotations

import numpy as np

from groove_lab.decoding import DecodeState, commit_confident_cells, schedule

STEPS = 32
LANES = 18


def test_schedule_commits_everything_and_never_stalls() -> None:
    for total_steps in (1, 2, 4, 8, 16):
        counts = schedule(STEPS * LANES, total_steps)
        assert len(counts) == total_steps
        assert sum(counts) == STEPS * LANES
        assert all(count >= 1 for count in counts)


def test_state_starts_fully_masked() -> None:
    state = DecodeState.masked(STEPS, LANES)
    assert state.observed_mask.sum() == 0
    assert state.hit.shape == (STEPS, LANES)


def test_locked_lanes_are_observed_from_the_start_and_never_overwritten() -> None:
    state = DecodeState.masked(STEPS, LANES)
    state.lock_lane(4, hits=np.ones(STEPS, dtype=np.float32))
    assert state.observed_mask[:, 4].all()

    logits = np.full((STEPS, LANES), 10.0, dtype=np.float32)
    velocity = np.full((STEPS, LANES), 0.5, dtype=np.float32)
    offset = np.zeros((STEPS, LANES), dtype=np.float32)
    commit_confident_cells(state, logits, velocity, offset, count=STEPS * LANES)

    assert state.hit[:, 4].tolist() == [1.0] * STEPS


def test_commit_marks_exactly_the_requested_number_of_cells() -> None:
    state = DecodeState.masked(STEPS, LANES)
    rng = np.random.default_rng(0)
    logits = rng.normal(size=(STEPS, LANES)).astype(np.float32)
    velocity = np.zeros((STEPS, LANES), dtype=np.float32)
    offset = np.zeros((STEPS, LANES), dtype=np.float32)

    before = int(state.observed_mask.sum())
    commit_confident_cells(state, logits, velocity, offset, count=10)
    after = int(state.observed_mask.sum())
    assert after - before == 10


def test_full_decode_observes_every_cell() -> None:
    state = DecodeState.masked(STEPS, LANES)
    rng = np.random.default_rng(1)
    for count in schedule(STEPS * LANES, 8):
        logits = rng.normal(size=(STEPS, LANES)).astype(np.float32)
        zeros = np.zeros((STEPS, LANES), dtype=np.float32)
        commit_confident_cells(state, logits, zeros, zeros, count=count)
    assert state.observed_mask.all()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/test_decoding.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.decoding'`.

- [ ] **Step 3: Write the decoding module**

Create `lab/groove_lab/decoding.py`:

```python
"""Iterative confidence decoding over the masked HVO grid.

The loop lives outside the exported graph, which is the shape the provider will
have: the helper runs the session once per decoding step.  That is why the spike
measures cost per forward pass and multiplies, and why section 19.1 of the design
requires the golden suite to compare the whole step sequence rather than one
pass.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def schedule(total_cells: int, total_steps: int) -> list[int]:
    """Split ``total_cells`` commits over ``total_steps`` passes, front-loaded.

    Every pass commits at least one cell, and the counts sum to exactly
    ``total_cells`` so the grid is always fully decoded.
    """

    if total_steps < 1:
        raise ValueError("total_steps must be at least 1")
    if total_cells < total_steps:
        raise ValueError("cannot spread fewer cells than steps")

    base = total_cells // total_steps
    remainder = total_cells % total_steps
    return [base + (1 if index < remainder else 0) for index in range(total_steps)]


@dataclass
class DecodeState:
    hit: np.ndarray
    velocity: np.ndarray
    offset: np.ndarray
    observed_mask: np.ndarray
    locked_mask: np.ndarray

    @classmethod
    def masked(cls, steps: int, lanes: int) -> DecodeState:
        zeros = lambda: np.zeros((steps, lanes), dtype=np.float32)  # noqa: E731
        return cls(zeros(), zeros(), zeros(), zeros(), zeros())

    def lock_lane(self, lane: int, hits: np.ndarray) -> None:
        """Pin a lane the user chose to keep. It is observed input, never a target."""

        self.hit[:, lane] = hits
        self.observed_mask[:, lane] = 1.0
        self.locked_mask[:, lane] = 1.0


def commit_confident_cells(
    state: DecodeState,
    hit_logits: np.ndarray,
    velocity: np.ndarray,
    offset: np.ndarray,
    count: int,
) -> int:
    """Commit the ``count`` most confident unobserved cells. Returns how many moved."""

    candidates = state.observed_mask == 0.0
    available = int(candidates.sum())
    if available == 0 or count <= 0:
        return 0
    take = min(count, available)

    confidence = np.abs(hit_logits)
    confidence = np.where(candidates, confidence, -np.inf)
    flat = confidence.reshape(-1)
    chosen = np.argpartition(-flat, take - 1)[:take]
    rows, columns = np.unravel_index(chosen, confidence.shape)

    state.hit[rows, columns] = (hit_logits[rows, columns] > 0.0).astype(np.float32)
    state.velocity[rows, columns] = velocity[rows, columns]
    state.offset[rows, columns] = offset[rows, columns]
    state.observed_mask[rows, columns] = 1.0
    return take
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/test_decoding.py -q
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/decoding.py lab/tests/test_decoding.py
git commit -m "feat(lab): add iterative confidence decoding over the HVO grid"
```

---

### Task 4: ONNX export and parity

**Files:**
- Create: `lab/groove_lab/export.py`
- Test: `lab/tests/test_export.py`

- [ ] **Step 1: Write the failing test**

Create `lab/tests/test_export.py`:

```python
from __future__ import annotations

import numpy as np
import pytest
import torch

from groove_lab.export import EXPORTER_USED, export_to_onnx, run_onnx_session
from groove_lab.model import CONDITIONS, LANES, STEPS, CellTokenHvo, StepTokenHvo


def _numpy_inputs(batch: int = 1) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(7)
    shape = (batch, STEPS, LANES)
    return {
        "hit": rng.integers(0, 2, shape).astype(np.float32),
        "velocity": rng.random(shape).astype(np.float32),
        "offset": (rng.random(shape) * 2 - 1).astype(np.float32),
        "observed_mask": rng.integers(0, 2, shape).astype(np.float32),
        "conditions": rng.random((batch, CONDITIONS)).astype(np.float32),
    }


@pytest.mark.parametrize("factory", [CellTokenHvo, StepTokenHvo])
def test_onnx_matches_torch_within_tolerance(tmp_path, factory) -> None:
    torch.manual_seed(0)
    model = factory().eval()
    path = tmp_path / f"{factory.__name__}.onnx"
    export_to_onnx(model, path)
    assert path.exists()

    inputs = _numpy_inputs()
    with torch.no_grad():
        expected = model(**{k: torch.from_numpy(v) for k, v in inputs.items()})
    actual = run_onnx_session(path, inputs)

    for name in ("hit_logits", "subhits_logits", "velocity", "offset"):
        np.testing.assert_allclose(
            actual[name], expected[name].numpy(), rtol=1e-4, atol=1e-5,
            err_msg=f"{factory.__name__} output {name} drifted between torch and ONNX",
        )


def test_exporter_used_is_recorded() -> None:
    assert EXPORTER_USED in {"dynamo", "torchscript"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/test_export.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.export'`.

- [ ] **Step 3: Write the export module**

Create `lab/groove_lab/export.py`:

```python
"""Export a masked HVO variant to ONNX and run it under ONNX Runtime.

TorchScript has been deprecated since PyTorch 2.10, so the Dynamo exporter is the
supported route.  The module records which exporter actually succeeded in
``EXPORTER_USED``, because that fact belongs in the spike's report rather than in
somebody's memory.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from torch import nn

from .model import CONDITIONS, LANES, STEPS

INPUT_NAMES = ["hit", "velocity", "offset", "observed_mask", "conditions"]
OUTPUT_NAMES = ["hit_logits", "subhits_logits", "velocity", "offset"]

EXPORTER_USED = "unknown"


def _example_inputs(batch: int = 1) -> tuple[torch.Tensor, ...]:
    shape = (batch, STEPS, LANES)
    return (
        torch.zeros(shape),
        torch.zeros(shape),
        torch.zeros(shape),
        torch.zeros(shape),
        torch.zeros((batch, CONDITIONS)),
    )


def export_to_onnx(model: nn.Module, path: Path) -> str:
    """Write ``model`` to ``path`` and return the exporter that produced it."""

    global EXPORTER_USED
    model.eval()
    args = _example_inputs()
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        torch.onnx.export(
            model,
            args,
            str(path),
            input_names=INPUT_NAMES,
            output_names=OUTPUT_NAMES,
            dynamo=True,
        )
        EXPORTER_USED = "dynamo"
    except Exception:  # noqa: BLE001 - the fallback is the point of this branch
        torch.onnx.export(
            model,
            args,
            str(path),
            input_names=INPUT_NAMES,
            output_names=OUTPUT_NAMES,
            opset_version=17,
        )
        EXPORTER_USED = "torchscript"
    return EXPORTER_USED


def make_session(path: Path, threads: int) -> ort.InferenceSession:
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(
        str(path), sess_options=options, providers=["CPUExecutionProvider"]
    )


def run_onnx_session(
    path: Path, inputs: dict[str, np.ndarray], threads: int = 1
) -> dict[str, np.ndarray]:
    session = make_session(path, threads)
    names = [output.name for output in session.get_outputs()]
    values = session.run(None, inputs)
    return dict(zip(names, values, strict=True))
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/test_export.py -q
```

Expected: PASS, 3 tests.

If the Dynamo exporter fails and the fallback also fails, stop and report the exact error rather than loosening the tolerance. An export that cannot be produced is itself the spike's answer for that variant.

If the outputs are named differently by the exporter, read the real names from `session.get_outputs()` — the test already does this through `run_onnx_session` — and fix `OUTPUT_NAMES` to match rather than renaming in the assertion.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/export.py lab/tests/test_export.py
git commit -m "feat(lab): export the HVO variants to ONNX with a parity check"
```

---

### Task 5: The budget harness

**Files:**
- Create: `lab/groove_lab/budget.py`
- Test: `lab/tests/test_budget.py`

`cpu_seconds` is CPU time summed across threads. `time.process_time()` returns exactly that for the current process on Windows, and inference runs in-process, so no external tooling is needed. Peak memory needs the native allocations ONNX Runtime makes outside Python, so it comes from `psutil`.

- [ ] **Step 1: Write the failing test**

Create `lab/tests/test_budget.py`:

```python
from __future__ import annotations

import time

from groove_lab.budget import LIMITS, Measurement, measure, verdict


def test_limits_match_the_provider_contract() -> None:
    assert LIMITS["generation_seconds"] == 5.0
    assert LIMITS["cpu_seconds"] == 2.0
    assert LIMITS["startup_seconds"] == 2.0
    assert LIMITS["shutdown_seconds"] == 1.0
    assert LIMITS["memory_mib"] == 512
    assert LIMITS["max_response_bytes"] == 262144
    assert LIMITS["max_events"] == 2048


def test_measure_records_wall_and_cpu_time() -> None:
    def burn() -> None:
        deadline = time.process_time() + 0.05
        while time.process_time() < deadline:
            pass

    result = measure(burn)
    assert isinstance(result, Measurement)
    assert result.wall_seconds >= 0.04
    assert result.cpu_seconds >= 0.04
    assert result.peak_memory_mib > 0


def test_verdict_fails_on_the_binding_limit() -> None:
    passing = {"cpu_seconds": 1.0, "generation_seconds": 1.0, "memory_mib": 100}
    failing = {"cpu_seconds": 2.5, "generation_seconds": 1.0, "memory_mib": 100}
    assert verdict(passing) == []
    assert verdict(failing) == ["cpu_seconds"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/test_budget.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'groove_lab.budget'`.

- [ ] **Step 3: Write the budget module**

Create `lab/groove_lab/budget.py`:

```python
"""Measure a callable against the provider's seven hard limits.

The values mirror ``ProviderLimitsV1`` in
``ableton_mcp_server/groove_intelligence/provider.py``.  They are declared with
``le=`` in that schema, so they are ceilings that configuration cannot raise, and
this module treats them the same way.

``cpu_seconds`` is CPU time summed across threads, which is what
``time.process_time`` reports for the current process.  With eight intra-op
threads, half a second of wall time is four CPU-seconds and already over budget.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import psutil

LIMITS: dict[str, float] = {
    "generation_seconds": 5.0,
    "cpu_seconds": 2.0,
    "startup_seconds": 2.0,
    "shutdown_seconds": 1.0,
    "memory_mib": 512,
    "max_response_bytes": 262144,
    "max_events": 2048,
}


@dataclass
class Measurement:
    wall_seconds: float
    cpu_seconds: float
    peak_memory_mib: float


def measure(action: Callable[[], object]) -> Measurement:
    process = psutil.Process()
    before_memory = process.memory_info().rss
    wall_start = time.perf_counter()
    cpu_start = time.process_time()

    action()

    cpu_seconds = time.process_time() - cpu_start
    wall_seconds = time.perf_counter() - wall_start
    after_memory = process.memory_info().rss
    return Measurement(
        wall_seconds=wall_seconds,
        cpu_seconds=cpu_seconds,
        peak_memory_mib=max(before_memory, after_memory) / (1024 * 1024),
    )


def verdict(values: dict[str, float]) -> list[str]:
    """Return the names of the limits ``values`` breaks, in declaration order."""

    return [name for name, ceiling in LIMITS.items() if name in values and values[name] > ceiling]
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests/test_budget.py -q
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add lab/groove_lab/budget.py lab/tests/test_budget.py
git commit -m "feat(lab): measure a callable against the provider budget"
```

---

### Task 6: The sweep

**Files:**
- Create: `lab/scripts/run_spike.py`

This is the task that produces the answer. It sweeps both tokenisations, thread counts of 1, 4 and 8, and decoding step counts of 1, 2, 4, 8, 16 and 32, and finds the largest step count that stays inside every limit.

- [ ] **Step 1: Write the runner**

Create `lab/scripts/run_spike.py`:

```python
"""Sweep decoding steps and threads to find what fits in cpu_seconds <= 2.0.

Writes ``lab/artifacts/budget.json`` and the result document under
``docs/superpowers/plans/``.  Nothing here is trained: the weights are random,
because the question is arithmetic cost, not quality.
"""

from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "lab"))

from groove_lab.budget import LIMITS, measure, verdict  # noqa: E402
from groove_lab.decoding import DecodeState, commit_confident_cells, schedule  # noqa: E402
from groove_lab.export import export_to_onnx, make_session  # noqa: E402
from groove_lab.model import (  # noqa: E402
    CONDITIONS,
    LANES,
    STEPS,
    CellTokenHvo,
    StepTokenHvo,
    count_parameters,
)

ARTIFACTS = REPO_ROOT / "lab" / "artifacts"
RESULT_DOC = (
    REPO_ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-08-31-groove-brain-cpu-onnx-budget-spike-result.md"
)

THREAD_COUNTS = (1, 4, 8)
STEP_COUNTS = (1, 2, 4, 8, 16, 32)
VARIANTS = {"cell_token": CellTokenHvo, "step_token": StepTokenHvo}


def _decode_once(session: ort.InferenceSession, total_steps: int) -> int:
    """Run one full decode and return the number of committed cells."""

    state = DecodeState.masked(STEPS, LANES)
    conditions = np.zeros((1, CONDITIONS), dtype=np.float32)
    committed = 0
    for count in schedule(STEPS * LANES, total_steps):
        outputs = session.run(
            None,
            {
                "hit": state.hit[None, ...],
                "velocity": state.velocity[None, ...],
                "offset": state.offset[None, ...],
                "observed_mask": state.observed_mask[None, ...],
                "conditions": conditions,
            },
        )
        names = [output.name for output in session.get_outputs()]
        result = dict(zip(names, outputs, strict=True))
        committed += commit_confident_cells(
            state,
            result["hit_logits"][0],
            result["velocity"][0],
            result["offset"][0],
            count=count,
        )
    return committed


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(0)

    report: dict[str, object] = {
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "processor": platform.processor(),
            "torch": torch.__version__,
            "onnxruntime": ort.__version__,
            "cuda_available": torch.cuda.is_available(),
            "providers": ort.get_available_providers(),
        },
        "limits": LIMITS,
        "variants": {},
    }

    for name, factory in VARIANTS.items():
        model = factory().eval()
        path = ARTIFACTS / f"{name}.onnx"
        exporter = export_to_onnx(model, path)
        entry: dict[str, object] = {
            "sequence_length": model.sequence_length,
            "parameters": count_parameters(model),
            "onnx_bytes": path.stat().st_size,
            "exporter": exporter,
            "runs": [],
            "max_decoding_steps": {},
        }

        for threads in THREAD_COUNTS:
            start_wall = time.perf_counter()
            start_cpu = time.process_time()
            session = make_session(path, threads)
            session.run(None, {
                "hit": np.zeros((1, STEPS, LANES), dtype=np.float32),
                "velocity": np.zeros((1, STEPS, LANES), dtype=np.float32),
                "offset": np.zeros((1, STEPS, LANES), dtype=np.float32),
                "observed_mask": np.zeros((1, STEPS, LANES), dtype=np.float32),
                "conditions": np.zeros((1, CONDITIONS), dtype=np.float32),
            })
            startup_seconds = time.perf_counter() - start_wall
            startup_cpu = time.process_time() - start_cpu

            best = 0
            for total_steps in STEP_COUNTS:
                _decode_once(session, total_steps)  # warm the caches
                result = measure(lambda: _decode_once(session, total_steps))
                values = {
                    "generation_seconds": result.wall_seconds,
                    "cpu_seconds": result.cpu_seconds,
                    "startup_seconds": startup_seconds,
                    "memory_mib": result.peak_memory_mib,
                }
                broken = verdict(values)
                entry["runs"].append({
                    "threads": threads,
                    "decoding_steps": total_steps,
                    "wall_seconds": round(result.wall_seconds, 4),
                    "cpu_seconds": round(result.cpu_seconds, 4),
                    "startup_seconds": round(startup_seconds, 4),
                    "startup_cpu_seconds": round(startup_cpu, 4),
                    "peak_memory_mib": round(result.peak_memory_mib, 1),
                    "limits_broken": broken,
                })
                if not broken:
                    best = total_steps
            entry["max_decoding_steps"][str(threads)] = best

        report["variants"][name] = entry

    (ARTIFACTS / "budget.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_result_document(report)
    print(json.dumps({
        name: entry["max_decoding_steps"] for name, entry in report["variants"].items()
    }, indent=2))


def _write_result_document(report: dict) -> None:
    environment = report["environment"]
    lines = [
        "# CPU/ONNX budget spike - result",
        "",
        "Measured with untrained weights. The question is arithmetic cost, not quality.",
        "",
        "## Environment",
        "",
        f"- Python {environment['python']} on {environment['platform']}",
        f"- PyTorch {environment['torch']}, CUDA available: {environment['cuda_available']}",
        f"- ONNX Runtime {environment['onnxruntime']}, providers: "
        f"{', '.join(environment['providers'])}",
        "",
        "## Maximum decoding steps inside every limit",
        "",
        "| Variant | Sequence | Parameters | ONNX bytes | 1 thread | 4 threads | 8 threads |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, entry in report["variants"].items():
        best = entry["max_decoding_steps"]
        lines.append(
            f"| `{name}` | {entry['sequence_length']} | {entry['parameters']} | "
            f"{entry['onnx_bytes']} | {best['1']} | {best['4']} | {best['8']} |"
        )
    lines += [
        "",
        "A value of 0 means even a single decoding pass breaks a limit.",
        "",
        "## Every run",
        "",
        "| Variant | Threads | Steps | Wall s | CPU s | Peak MiB | Limits broken |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, entry in report["variants"].items():
        for run in entry["runs"]:
            broken = ", ".join(run["limits_broken"]) or "none"
            lines.append(
                f"| `{name}` | {run['threads']} | {run['decoding_steps']} | "
                f"{run['wall_seconds']} | {run['cpu_seconds']} | "
                f"{run['peak_memory_mib']} | {broken} |"
            )
    lines += ["", "Raw data: `lab/artifacts/budget.json`."]
    RESULT_DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the sweep**

Run:

```bash
lab/.venv-lab/Scripts/python.exe lab/scripts/run_spike.py
```

Expected: prints a JSON object mapping each variant to its maximum decoding steps per thread count, and writes both `lab/artifacts/budget.json` and the result document.

- [ ] **Step 3: Sanity-check the numbers before believing them**

Run:

```bash
lab/.venv-lab/Scripts/python.exe -c "import json,pathlib; d=json.loads(pathlib.Path('lab/artifacts/budget.json').read_text()); [print(n, r['threads'], r['decoding_steps'], r['wall_seconds'], r['cpu_seconds']) for n,e in d['variants'].items() for r in e['runs'][:6]]"
```

Check three things, and if any fails the measurement is wrong rather than surprising:

1. `cpu_seconds` grows roughly linearly with `decoding_steps` at a fixed thread count. If it does not, the warm-up run is not warming what you think.
2. At 8 threads, `cpu_seconds` is meaningfully larger than at 1 thread for the same work, while `wall_seconds` is smaller. That is the whole point of the limit being CPU time.
3. `cell_token` costs substantially more than `step_token` at equal steps. 576 tokens against 32 with quadratic attention should be visible; if the two are close, the tokenisation is not doing what `model.py` says.

- [ ] **Step 4: Commit**

```bash
git add lab/scripts/run_spike.py docs/superpowers/plans/2026-08-31-groove-brain-cpu-onnx-budget-spike-result.md
git commit -m "feat(lab): sweep decoding steps against the CPU budget"
```

---

### Task 7: Package footprint

**Files:**
- Modify: `lab/scripts/run_spike.py`

O2 asks for a ceiling on the `.ablx`. The spike can supply the runtime and model half of that number.

- [ ] **Step 1: Add footprint measurement**

Add this function to `lab/scripts/run_spike.py`, above `main`:

```python
def _runtime_footprint() -> dict[str, int]:
    """Bytes ONNX Runtime and the model would add on top of the Gate 0 package."""

    runtime_root = Path(ort.__file__).resolve().parent
    native = sum(
        path.stat().st_size
        for path in runtime_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".dll", ".pyd", ".so"}
    )
    return {
        "onnxruntime_native_bytes": native,
        "gate0_ablx_bytes": 154852,
    }
```

- [ ] **Step 2: Record it in the report**

In `main`, insert one line immediately before `for name, factory in VARIANTS.items():`, at the same indentation as that `for`:

```python
    report["footprint"] = _runtime_footprint()
```

- [ ] **Step 3: Surface it in the result document**

In `_write_result_document`, replace the final `lines += ["", "Raw data: `lab/artifacts/budget.json`."]` with:

```python
    footprint = report["footprint"]
    native_mib = footprint["onnxruntime_native_bytes"] / (1024 * 1024)
    lines += [
        "",
        "## Package footprint",
        "",
        f"- ONNX Runtime native libraries: {native_mib:.1f} MiB",
        f"- Gate 0 `.ablx` baseline: {footprint['gate0_ablx_bytes']} bytes",
        "- Model weights per variant are the `ONNX bytes` column above.",
        "",
        "This is the runtime and model half of the `.ablx` ceiling that decision O2",
        "has to set. It does not include the helper, the UI or the catalog.",
        "",
        "Raw data: `lab/artifacts/budget.json`.",
    ]
```

- [ ] **Step 4: Re-run and verify**

Run:

```bash
lab/.venv-lab/Scripts/python.exe lab/scripts/run_spike.py
```

Expected: the result document now ends with a `## Package footprint` section showing a non-zero MiB figure.

- [ ] **Step 5: Commit**

`lab/artifacts/` is gitignored because the ONNX files inside it are large, but `budget.json` is small and is the evidence behind the report, so it is force-added.

```bash
git add lab/scripts/run_spike.py docs/superpowers/plans/2026-08-31-groove-brain-cpu-onnx-budget-spike-result.md
git add -f lab/artifacts/budget.json
git commit -m "feat(lab): record the ONNX runtime and model package footprint"
```

---

### Task 8: Close gate P0 in the design document

**Files:**
- Modify: `docs/superpowers/specs/2026-08-31-groove-brain-dataset-training-design.md`

- [ ] **Step 1: Read the measured answer**

Run:

```bash
cat docs/superpowers/plans/2026-08-31-groove-brain-cpu-onnx-budget-spike-result.md
```

- [ ] **Step 2: Add the result to section 19.4**

In the design document, find the paragraph beginning `` `cpu_seconds <= 2,0` é o limite que decide a viabilidade ``. Immediately after that paragraph, insert a block in this shape, filling every bracket from the result document. Do not paraphrase the numbers.

```markdown
`[fato]` Resultado do spike do plano 3, medido em 2026-XX-XX com pesos aleatórios:

| Tokenização | Sequência | Parâmetros | ONNX | Passos máximos em 1/4/8 threads |
|---|---|---|---|---|
| célula por token | 576 | [N] | [N] bytes | [a] / [b] / [c] |
| passo por token | 32 | [N] | [N] bytes | [a] / [b] / [c] |

`[decisão]` A tokenização escolhida para o plano 6 é **[a vencedora]**, porque
[a razão medida]. O decoding do produto fica limitado a **[N] passos**, e esse
número entra no plano 6 como restrição de arquitetura, não como meta.
```

- [ ] **Step 3: Update the ladder entry for P0**

In section 17, the `**P0** spike de CPU e ONNX` row currently describes the work. Append the outcome to its cell, in this shape:

```markdown
Resultado: [N] passos de decoding em [tokenização], com [X] CPU-segundos por passe.
```

- [ ] **Step 4: Verify no contradictions were introduced**

Run:

```bash
git diff --check -- docs/
python -c "import re;t=open('docs/superpowers/specs/2026-08-31-groove-brain-dataset-training-design.md',encoding='utf-8').read();h={m.group(1) for m in re.finditer(r'^#{2,4} (\d+(?:\.\d+)*)[.\s]',t,re.M)};r={m.group(1) for m in re.finditer(r'seção (\d+(?:\.\d+)*)',t)};print('refs quebradas:',sorted(r-h) or 'nenhuma')"
```

Expected: `git diff --check` produces no output, and the reference check prints `refs quebradas: nenhuma`.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-08-31-groove-brain-dataset-training-design.md
git commit -m "docs: record the CPU/ONNX budget spike result and close P0"
```

---

## What this spike does not do

It does not train anything, does not touch the corpus, does not build a dataset, and does not measure quality. Random weights cost the same arithmetic as trained weights, which is the only thing being asked.

It also does not settle whether the winning tokenisation is musically adequate. A 32-token layout gives the model one vector per step and forces lane structure through the channel dimension; whether that is expressive enough is a question for the bake-off in plan 6, not for this measurement.

## Stop condition

The spike is done when `docs/superpowers/plans/2026-08-31-groove-brain-cpu-onnx-budget-spike-result.md` states a maximum decoding step count per variant per thread count, and section 19.4 of the design document carries that number.

If both variants come back at 0 steps, that is a valid and important result: it means the small tier does not fit the provider contract on CPU at all, and plan 6 must either shrink the model below the spec's small tier or the `cpu_seconds` ceiling must be formally renegotiated before any training begins. Do not quietly raise the limit to make the number look better.
