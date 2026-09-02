"""Score every system on the same windows, under the same task draws.

The cases are built once from a seed and handed to each system unchanged.  A
comparison where the model and the baseline face different maskings is not a
comparison, and building the cases separately per system is the easiest way to
get that wrong without noticing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from ..training.tasks import apply_task, sample_task
from .metrics import hit_f1, velocity_offset_error

PRIMARY_TASKS = frozenset({"temporal_infill", "lane_infill", "fill", "continuation"})


@dataclass
class EvaluationCase:
    truth: dict[str, np.ndarray]
    observed: np.ndarray
    target: np.ndarray
    conditions: np.ndarray
    task: str

    @property
    def counts_for_primary(self) -> bool:
        return self.task in PRIMARY_TASKS


def build_cases(
    examples: Sequence[dict[str, np.ndarray]], seed: int
) -> list[EvaluationCase]:
    rng = np.random.default_rng(seed)
    cases: list[EvaluationCase] = []
    for example in examples:
        task = sample_task(rng)
        observed, target = apply_task(task, example["valid"], rng)
        cases.append(
            EvaluationCase(
                truth=example,
                observed=observed,
                target=target,
                conditions=example["conditions"],
                task=task,
            )
        )
    return cases


def score_system(
    system: Callable[[EvaluationCase], dict[str, np.ndarray]],
    cases: Sequence[EvaluationCase],
) -> dict[str, float]:
    f1_scores: list[float] = []
    velocity_errors: list[float] = []
    offset_errors: list[float] = []
    for case in cases:
        if not case.counts_for_primary:
            continue
        prediction = system(case)
        f1_scores.append(hit_f1(prediction["hit"], case.truth["hit"], case.target))
        velocity_errors.append(
            velocity_offset_error(
                prediction["velocity"],
                case.truth["velocity"],
                case.truth["hit"],
                case.target,
            )
        )
        offset_errors.append(
            velocity_offset_error(
                prediction["offset"],
                case.truth["offset"],
                case.truth["hit"],
                case.target,
            )
        )
    return {
        "hit_f1": float(np.mean(f1_scores)) if f1_scores else 0.0,
        "velocity_mae": float(np.mean(velocity_errors)) if velocity_errors else 0.0,
        "offset_mae": float(np.mean(offset_errors)) if offset_errors else 0.0,
        "cases": float(len(f1_scores)),
    }
