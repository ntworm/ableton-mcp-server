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
