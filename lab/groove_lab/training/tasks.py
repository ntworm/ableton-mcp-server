"""What the model is asked to predict, and what it is allowed to see.

Specification section 14 lists eight tasks.  Six are implemented; ``humanize``
and ``reference`` are declared here with the reason they are off, so enabling
them later is a config change and an implementation rather than a rediscovery.

Every masker returns ``(observed, target)`` intersected with the stored validity
mask, so a cell that does not exist — the padded second bar of a one-bar file —
is never observed and never a target.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

STEPS_PER_BAR = 16

TASK_MIX: dict[str, dict[str, object]] = {
    "free_generation": {"enabled": True, "weight": 0.30, "reason": ""},
    "variation": {"enabled": True, "weight": 0.20, "reason": ""},
    "temporal_infill": {"enabled": True, "weight": 0.15, "reason": ""},
    "lane_infill": {"enabled": True, "weight": 0.15, "reason": ""},
    "fill": {"enabled": True, "weight": 0.10, "reason": ""},
    "continuation": {"enabled": True, "weight": 0.10, "reason": ""},
    "humanize": {
        "enabled": False,
        "weight": 0.0,
        "reason": (
            "Specification 14 promotes humanize only once D0 has separated the "
            "systematic swing bias from the residual jitter, because an aggregate "
            "offset spread cannot tell a swung corpus from an expressive one. That "
            "decomposition has not been run."
        ),
    },
    "reference": {
        "enabled": False,
        "weight": 0.0,
        "reason": (
            "Needs a reference-encoder path through the model. Gate G4 does not "
            "evaluate it and the bake-off in plan 5 is where it would be measured, "
            "so adding the architecture now would be scope with no gate behind it."
        ),
    },
}


def _free_generation(
    valid: np.ndarray, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    return np.zeros_like(valid), valid.copy()


def _variation(
    valid: np.ndarray, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    keep = (rng.random(valid.shape) < rng.uniform(0.3, 0.7)).astype(np.float32)
    observed = keep * valid
    return observed, valid - observed


def _temporal_infill(
    valid: np.ndarray, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    steps = valid.shape[0]
    length = int(rng.integers(4, max(5, steps // 2)))
    start = int(rng.integers(0, steps - length + 1))
    target = np.zeros_like(valid)
    target[start : start + length, :] = 1.0
    target *= valid
    return valid - target, target


def _lane_infill(
    valid: np.ndarray, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    lanes = valid.shape[1]
    count = int(rng.integers(1, max(2, lanes // 3)))
    chosen = rng.choice(lanes, size=count, replace=False)
    target = np.zeros_like(valid)
    target[:, chosen] = 1.0
    target *= valid
    return valid - target, target


def _fill(valid: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    target = np.zeros_like(valid)
    target[STEPS_PER_BAR:, :] = 1.0
    target *= valid
    return valid - target, target


def _continuation(
    valid: np.ndarray, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    return _fill(valid, rng)


TASKS: dict[
    str, Callable[[np.ndarray, np.random.Generator], tuple[np.ndarray, np.ndarray]]
] = {
    "free_generation": _free_generation,
    "variation": _variation,
    "temporal_infill": _temporal_infill,
    "lane_infill": _lane_infill,
    "fill": _fill,
    "continuation": _continuation,
}

TASK_ORDER = tuple(sorted(TASKS))
TASK_INDEX = {name: index for index, name in enumerate(TASK_ORDER)}


def sample_task(rng: np.random.Generator) -> str:
    weights = np.array([float(TASK_MIX[name]["weight"]) for name in TASK_ORDER])
    weights = weights / weights.sum()
    return str(rng.choice(TASK_ORDER, p=weights))


def apply_task(
    task: str, valid: np.ndarray, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    observed, target = TASKS[task](valid.astype(np.float32), rng)
    return observed * valid, target * valid
