from __future__ import annotations

import numpy as np
import pytest
import torch

from groove_lab import export as export_module
from groove_lab.export import export_to_onnx, run_onnx_session
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


def test_exporter_used_is_recorded(tmp_path) -> None:
    # Self-contained on purpose: EXPORTER_USED is module state, so a test that
    # relied on another test having exported first would pass or fail by ordering.
    torch.manual_seed(0)
    used = export_to_onnx(StepTokenHvo().eval(), tmp_path / "exporter_probe.onnx")
    assert used in {"dynamo", "torchscript"}
    # Read through the module: `from ... import EXPORTER_USED` binds the value at
    # import time and would never see the update.
    assert export_module.EXPORTER_USED == used
