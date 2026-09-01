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


def _prepare(
    state: TrainState, batch: dict[str, np.ndarray]
) -> tuple[dict[str, torch.Tensor], dict[str, torch.Tensor], torch.Tensor]:
    observed_list = []
    target_list = []
    task_list = []
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
        last = float(loss.detach())
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
