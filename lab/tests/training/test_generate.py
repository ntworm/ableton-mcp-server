from __future__ import annotations

import numpy as np
import torch

from groove_lab.training.generate import diversity, generate, is_structurally_valid
from groove_lab.training.model import MaskedHvo


def test_generation_returns_a_full_grid() -> None:
    torch.manual_seed(0)
    grid = generate(
        MaskedHvo().eval(),
        conditions=np.zeros(16, dtype=np.float32),
        seed=0,
        decoding_steps=8,
    )
    assert grid["hit"].shape == (32, 18)
    assert set(np.unique(grid["hit"])) <= {0.0, 1.0}


def test_a_generated_grid_is_structurally_valid() -> None:
    torch.manual_seed(0)
    grid = generate(
        MaskedHvo().eval(), np.zeros(16, dtype=np.float32), seed=0, decoding_steps=8
    )
    assert is_structurally_valid(grid)


def test_an_out_of_range_offset_is_rejected() -> None:
    grid = {
        "hit": np.ones((32, 18), dtype=np.float32),
        "subhits": np.ones((32, 18), dtype=np.int64),
        "velocity": np.zeros((32, 18), dtype=np.float32),
        "offset": np.full((32, 18), 5.0, dtype=np.float32),
    }
    assert not is_structurally_valid(grid)


def test_identical_grids_have_zero_diversity() -> None:
    grid = {"hit": np.ones((32, 18), dtype=np.float32)}
    assert diversity([grid, grid, grid]) == 0.0


def test_different_grids_have_positive_diversity() -> None:
    rng = np.random.default_rng(0)
    grids = [{"hit": (rng.random((32, 18)) > 0.5).astype(np.float32)} for _ in range(4)]
    assert diversity(grids) > 0.1
