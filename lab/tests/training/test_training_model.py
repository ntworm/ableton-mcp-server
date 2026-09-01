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
    with torch.no_grad():
        out = MaskedHvo().eval()(**_inputs())
    assert float(out["velocity"].min()) >= 0.0 and float(out["velocity"].max()) <= 1.0
    assert float(out["offset"].min()) >= -1.0 and float(out["offset"].max()) <= 1.0


def test_a_masked_cell_leaks_nothing() -> None:
    # The whole training signal depends on this: with observed_mask at zero the
    # model must give the same answer whatever the hidden truth was.
    torch.manual_seed(2)
    model = MaskedHvo().eval()
    quiet = _inputs()
    loud = _inputs()
    loud["hit"] = torch.ones(2, 32, 18)
    loud["velocity"] = torch.ones(2, 32, 18)
    with torch.no_grad():
        assert torch.allclose(
            model(**quiet)["hit_logits"], model(**loud)["hit_logits"]
        )
