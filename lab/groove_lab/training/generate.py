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


DEFAULT_TEMPERATURE = 1.0


@torch.no_grad()
def generate(
    model: nn.Module,
    conditions: np.ndarray,
    seed: int,
    decoding_steps: int,
    temperature: float = DEFAULT_TEMPERATURE,
) -> dict[str, np.ndarray]:
    """Decode one groove. ``temperature`` is what makes the seed mean anything.

    Specification 12.1 asks for confidence decoding *with temperature*.  Without
    it the loop is a pure argmax over deterministic logits, every seed returns
    the identical grid, and any diversity metric reads exactly zero no matter how
    good the model is.

    Adding logistic noise scaled by the temperature to a logit and then
    thresholding at zero is exactly a Bernoulli draw from
    ``sigmoid(logit / temperature)``, so the same perturbed value can order the
    confidence ranking and decide the hit.
    """

    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
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
        logits = outputs["hit_logits"][0].numpy()
        if temperature > 0.0:
            logits = logits + rng.logistic(size=logits.shape) * temperature
        before = state.observed_mask.copy()
        commit_confident_cells(
            state,
            logits,
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
