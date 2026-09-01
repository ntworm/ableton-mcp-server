from __future__ import annotations

import numpy as np
import pytest

from groove_lab.training.loader import ShardDataset, clamp_cost

DATASET = "F:/groove-brain/dataset/build-a"


@pytest.fixture(scope="module")
def train() -> ShardDataset:
    return ShardDataset(DATASET, split="train", max_subhits=4)


def test_dataset_reports_its_size(train: ShardDataset) -> None:
    assert len(train) == 2269


def test_an_example_has_every_field_with_the_right_dtype(train: ShardDataset) -> None:
    example = train[0]
    for name in ("hit", "subhits", "velocity", "offset", "valid"):
        assert example[name].shape == (32, 18), name
    assert example["conditions"].shape == (16,)
    assert example["hit"].dtype == np.float32
    assert example["subhits"].dtype == np.int64
    assert example["valid"].dtype == np.float32


def test_subhits_are_clamped_to_the_head_and_the_cost_is_known(
    train: ShardDataset,
) -> None:
    for index in range(50):
        assert int(train[index]["subhits"].max()) <= 3
    # Measured over the 1% train split: 0.0214% of hit cells exceed three events.
    assert clamp_cost(DATASET, split="train", max_subhits=4) < 0.001


def test_batches_are_deterministic_for_a_seed(train: ShardDataset) -> None:
    first = train.batch_indices(batch_size=8, seed=3)
    second = train.batch_indices(batch_size=8, seed=3)
    assert first == second
    assert first != train.batch_indices(batch_size=8, seed=4)


def test_collate_stacks_into_arrays(train: ShardDataset) -> None:
    batch = train.collate([0, 1, 2])
    assert batch["hit"].shape == (3, 32, 18)
    assert batch["conditions"].shape == (3, 16)
