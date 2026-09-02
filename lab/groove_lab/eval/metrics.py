"""The three metric families specification 18 names.

Prediction answers "did it put the hits where the truth had them", and only on
the cells the task masked.  Musicality answers "does it look like drumming",
which is where the lane distribution lives — plan 6 produced a model that passed
every structural gate while never once playing a closed hi-hat, and no metric in
the programme would have said so.  Originality answers "did it just copy", and
the reference point is the corpus repeating itself at 26.0%.
"""

from __future__ import annotations

import hashlib

import numpy as np

LANES = 18


def hit_f1(predicted: np.ndarray, truth: np.ndarray, mask: np.ndarray) -> float:
    """F1 over masked cells. Empty mask or no positives anywhere scores 0."""

    selected = mask > 0
    if not selected.any():
        return 0.0
    p = (predicted[selected] > 0.5).astype(np.int8)
    t = (truth[selected] > 0.5).astype(np.int8)
    true_positive = float(((p == 1) & (t == 1)).sum())
    if true_positive == 0.0:
        return 0.0
    precision = true_positive / float((p == 1).sum())
    recall = true_positive / float((t == 1).sum())
    return float(2 * precision * recall / (precision + recall))


def velocity_offset_error(
    predicted: np.ndarray, truth: np.ndarray, truth_hit: np.ndarray, mask: np.ndarray
) -> float:
    """Mean absolute error where the truth actually has a hit inside the mask."""

    selected = (mask > 0) & (truth_hit > 0.5)
    if not selected.any():
        return 0.0
    return float(np.abs(predicted[selected] - truth[selected]).mean())


def lane_distribution(grids: list[np.ndarray]) -> np.ndarray:
    """Mean hits per lane per window."""

    if not grids:
        return np.zeros(LANES, dtype=np.float64)
    return np.stack(grids).sum(axis=1).mean(axis=0)


def lane_distribution_distance(
    grids: list[np.ndarray], reference: list[np.ndarray]
) -> float:
    """L1 distance between normalised lane profiles, in [0, 2].

    Normalised so a system is not rewarded merely for matching total density: the
    question is whether the hits land in plausible lanes.
    """

    left = lane_distribution(grids)
    right = lane_distribution(reference)
    left = left / left.sum() if left.sum() else left
    right = right / right.sum() if right.sum() else right
    return float(np.abs(left - right).sum())


def _rhythm_hash(grid: np.ndarray) -> str:
    cells = np.argwhere(grid > 0.5)
    payload = ";".join(f"{int(row)}:{int(lane)}" for row, lane in cells)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def exact_repeat_rate(grids: list[np.ndarray], corpus: list[np.ndarray]) -> float:
    """Share of grids whose onset pattern already exists in the corpus.

    The corpus repeats itself at 26.0%, measured in specification 4.2, so a
    system copying at that rate is indistinguishable from the data by this
    metric. Anything above it is copying more than the source does.
    """

    if not grids:
        return 0.0
    known = {_rhythm_hash(grid) for grid in corpus}
    hits = sum(1 for grid in grids if _rhythm_hash(grid) in known)
    return hits / len(grids)
