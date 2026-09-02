from __future__ import annotations

import numpy as np

from groove_lab.eval.metrics import (
    exact_repeat_rate,
    hit_f1,
    lane_distribution,
    lane_distribution_distance,
    velocity_offset_error,
)

STEPS, LANES = 32, 18


def _grid(cells: list[tuple[int, int]]) -> np.ndarray:
    grid = np.zeros((STEPS, LANES), dtype=np.float32)
    for row, lane in cells:
        grid[row, lane] = 1.0
    return grid


def test_a_perfect_prediction_scores_one() -> None:
    truth = _grid([(0, 0), (8, 1)])
    mask = np.ones((STEPS, LANES), dtype=np.float32)
    assert hit_f1(truth, truth, mask) == 1.0


def test_silence_against_a_real_groove_scores_zero() -> None:
    truth = _grid([(0, 0), (8, 1)])
    mask = np.ones((STEPS, LANES), dtype=np.float32)
    assert hit_f1(np.zeros_like(truth), truth, mask) == 0.0


def test_only_masked_cells_count() -> None:
    truth = _grid([(0, 0)])
    predicted = _grid([(0, 0), (5, 5)])
    mask = np.zeros((STEPS, LANES), dtype=np.float32)
    mask[0, 0] = 1.0
    # The wrong cell at (5, 5) is outside the mask, so it must not be punished.
    assert hit_f1(predicted, truth, mask) == 1.0


def test_velocity_and_offset_error_only_counts_true_hits() -> None:
    truth_hit = _grid([(0, 0)])
    truth_velocity = np.zeros((STEPS, LANES), dtype=np.float32)
    truth_velocity[0, 0] = 0.5
    predicted_velocity = np.full((STEPS, LANES), 0.9, dtype=np.float32)
    predicted_velocity[0, 0] = 0.5
    mask = np.ones((STEPS, LANES), dtype=np.float32)
    error = velocity_offset_error(predicted_velocity, truth_velocity, truth_hit, mask)
    assert error == 0.0


def test_lane_distribution_sums_to_the_hit_count() -> None:
    grids = [_grid([(0, 0), (8, 0), (4, 2)])]
    assert lane_distribution(grids).sum() == 3.0


def test_distance_to_itself_is_zero_and_to_a_different_shape_is_not() -> None:
    same = [_grid([(0, 0), (8, 0)])]
    other = [_grid([(0, 5), (8, 5)])]
    assert lane_distribution_distance(same, same) == 0.0
    assert lane_distribution_distance(same, other) > 0.5


def test_exact_repeat_rate_finds_a_copy() -> None:
    corpus = [_grid([(0, 0), (8, 1)]), _grid([(4, 2)])]
    assert exact_repeat_rate([_grid([(0, 0), (8, 1)])], corpus) == 1.0
    assert exact_repeat_rate([_grid([(1, 1)])], corpus) == 0.0
