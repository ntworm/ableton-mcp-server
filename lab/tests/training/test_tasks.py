from __future__ import annotations

import numpy as np
import pytest

from groove_lab.training.tasks import TASK_MIX, TASKS, apply_task, sample_task


@pytest.fixture
def valid() -> np.ndarray:
    return np.ones((32, 18), dtype=np.float32)


def test_the_six_enabled_tasks_are_the_ones_documented() -> None:
    enabled = {name for name, spec in TASK_MIX.items() if spec["enabled"]}
    assert enabled == {
        "free_generation",
        "variation",
        "temporal_infill",
        "lane_infill",
        "fill",
        "continuation",
    }


def test_the_deferred_tasks_carry_their_reason() -> None:
    for name in ("humanize", "reference"):
        assert TASK_MIX[name]["enabled"] is False
        assert len(str(TASK_MIX[name]["reason"])) > 40, name


@pytest.mark.parametrize("task", sorted(TASKS))
def test_observed_and_target_never_overlap(task: str, valid: np.ndarray) -> None:
    observed, target = apply_task(task, valid, rng=np.random.default_rng(0))
    assert not np.any((observed > 0) & (target > 0)), task


@pytest.mark.parametrize("task", sorted(TASKS))
def test_nothing_outside_the_validity_mask_is_ever_a_target(task: str) -> None:
    valid = np.ones((32, 18), dtype=np.float32)
    valid[16:, :] = 0.0  # a padded second bar
    observed, target = apply_task(task, valid, rng=np.random.default_rng(1))
    assert target[16:, :].sum() == 0.0, task
    assert observed[16:, :].sum() == 0.0, task


def test_free_generation_targets_everything_valid(valid: np.ndarray) -> None:
    observed, target = apply_task("free_generation", valid, rng=np.random.default_rng(0))
    assert observed.sum() == 0.0
    assert target.sum() == valid.sum()


def test_continuation_observes_the_first_bar_and_targets_the_second(valid) -> None:
    observed, target = apply_task("continuation", valid, rng=np.random.default_rng(0))
    assert observed[:16, :].all()
    assert target[16:, :].all()
    assert target[:16, :].sum() == 0.0


def test_lane_infill_removes_whole_lanes(valid: np.ndarray) -> None:
    _observed, target = apply_task("lane_infill", valid, rng=np.random.default_rng(2))
    targeted = target.sum(axis=0)
    assert set(np.unique(targeted)) <= {0.0, 32.0}
    assert 0 < (targeted > 0).sum() < 18


def test_temporal_infill_removes_a_contiguous_range(valid: np.ndarray) -> None:
    _observed, target = apply_task("temporal_infill", valid, rng=np.random.default_rng(3))
    rows = np.nonzero(target.sum(axis=1))[0]
    assert rows.size > 0
    assert rows.tolist() == list(range(rows[0], rows[-1] + 1))


def test_sampling_is_deterministic_for_a_seed() -> None:
    rng = np.random.default_rng(9)
    first = [sample_task(rng) for _ in range(20)]
    rng = np.random.default_rng(9)
    assert [sample_task(rng) for _ in range(20)] == first
