from __future__ import annotations

import numpy as np
import torch

from groove_lab.training.loop import (
    TrainState,
    load_checkpoint,
    run_steps,
    save_checkpoint,
)
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
