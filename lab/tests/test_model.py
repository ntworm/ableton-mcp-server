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
