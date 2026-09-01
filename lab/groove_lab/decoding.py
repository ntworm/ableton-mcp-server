"""Iterative confidence decoding over the masked HVO grid.

The loop lives outside the exported graph, which is the shape the provider will
have: the helper runs the session once per decoding step.  That is why the spike
measures cost per forward pass and multiplies, and why section 19.1 of the design
requires the golden suite to compare the whole step sequence rather than one
pass.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def schedule(total_cells: int, total_steps: int) -> list[int]:
    """Split ``total_cells`` commits over ``total_steps`` passes, front-loaded.

    Every pass commits at least one cell, and the counts sum to exactly
    ``total_cells`` so the grid is always fully decoded.
    """

    if total_steps < 1:
        raise ValueError("total_steps must be at least 1")
    if total_cells < total_steps:
        raise ValueError("cannot spread fewer cells than steps")

    base = total_cells // total_steps
    remainder = total_cells % total_steps
    return [base + (1 if index < remainder else 0) for index in range(total_steps)]


@dataclass
class DecodeState:
    hit: np.ndarray
    velocity: np.ndarray
    offset: np.ndarray
    observed_mask: np.ndarray
    locked_mask: np.ndarray

    @classmethod
    def masked(cls, steps: int, lanes: int) -> DecodeState:
        def zeros() -> np.ndarray:
            return np.zeros((steps, lanes), dtype=np.float32)

        return cls(zeros(), zeros(), zeros(), zeros(), zeros())

    def lock_lane(self, lane: int, hits: np.ndarray) -> None:
        """Pin a lane the user chose to keep. It is observed input, never a target."""

        self.hit[:, lane] = hits
        self.observed_mask[:, lane] = 1.0
        self.locked_mask[:, lane] = 1.0


def commit_confident_cells(
    state: DecodeState,
    hit_logits: np.ndarray,
    velocity: np.ndarray,
    offset: np.ndarray,
    count: int,
) -> int:
    """Commit the ``count`` most confident unobserved cells. Returns how many moved."""

    candidates = state.observed_mask == 0.0
    available = int(candidates.sum())
    if available == 0 or count <= 0:
        return 0
    take = min(count, available)

    confidence = np.abs(hit_logits)
    confidence = np.where(candidates, confidence, -np.inf)
    flat = confidence.reshape(-1)
    chosen = np.argpartition(-flat, take - 1)[:take]
    rows, columns = np.unravel_index(chosen, confidence.shape)

    state.hit[rows, columns] = (hit_logits[rows, columns] > 0.0).astype(np.float32)
    state.velocity[rows, columns] = velocity[rows, columns]
    state.offset[rows, columns] = offset[rows, columns]
    state.observed_mask[rows, columns] = 1.0
    return take
