from __future__ import annotations

import torch

from groove_lab.training.losses import HIT_POS_WEIGHT, masked_losses


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


def test_a_missed_hit_costs_far_more_than_a_false_hit() -> None:
    # With 18 negatives per positive, plain BCE is minimised by predicting
    # silence, and the first M1 run did exactly that. The positive weight is what
    # stops the trivial solution from being the cheapest one.
    assert 15.0 < HIT_POS_WEIGHT < 20.0

    target = torch.ones(1, 32, 18)
    confident_no = {
        "hit_logits": torch.full((1, 32, 18), -5.0),
        "subhits_logits": torch.zeros(1, 32, 18, 4),
        "velocity": torch.zeros(1, 32, 18),
        "offset": torch.zeros(1, 32, 18),
    }
    truth_silent = {
        "hit": torch.zeros(1, 32, 18),
        "subhits": torch.zeros(1, 32, 18, dtype=torch.long),
        "velocity": torch.zeros(1, 32, 18),
        "offset": torch.zeros(1, 32, 18),
    }
    truth_loud = dict(truth_silent, hit=torch.ones(1, 32, 18))

    missed = float(masked_losses(confident_no, truth_loud, target)["hit"])
    correct = float(masked_losses(confident_no, truth_silent, target)["hit"])
    assert missed > correct * 100
