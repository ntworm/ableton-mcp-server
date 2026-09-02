"""The two systems the challenger has to beat, neither of which is trained.

``RetrievalBaseline`` is the incumbent: find the train window that best matches
what the task left observed, and copy its answer.  For infill this is a very
strong opponent, and it is what ships today if no neural model wins.

``MarginalSampler`` is the floor: it reproduces the corpus per-cell hit rates and
knows nothing else.  A model that cannot beat it has learned no structure, only
density.
"""

from __future__ import annotations

import numpy as np

STEPS, LANES = 32, 18


class RetrievalBaseline:
    def __init__(self, corpus: list[dict[str, np.ndarray]]) -> None:
        self.corpus = corpus
        self._hits = np.stack([example["hit"] for example in corpus])

    def complete(
        self, query: dict[str, np.ndarray], observed: np.ndarray
    ) -> dict[str, np.ndarray]:
        """Return the corpus window nearest on the observed cells.

        The observed mask gates the distance, so the hidden half of the query
        cannot influence which neighbour is chosen. Without that the baseline
        would be scoring against an answer it was shown, and the comparison
        would be void.
        """

        if observed.sum() == 0:
            # Nothing to match on: fall back to the first window, deterministically.
            index = 0
        else:
            mask = observed[None, :, :]
            distance = np.abs(self._hits - query["hit"][None, :, :]) * mask
            index = int(distance.sum(axis=(1, 2)).argmin())
        return self.corpus[index]


class MarginalSampler:
    def __init__(self, corpus: list[dict[str, np.ndarray]], seed: int) -> None:
        self.rates = np.stack([example["hit"] for example in corpus]).mean(axis=0)
        self.velocity = float(
            np.stack([example["velocity"] for example in corpus]).mean()
        )
        self.rng = np.random.default_rng(seed)

    def sample(self) -> dict[str, np.ndarray]:
        hit = (self.rng.random((STEPS, LANES)) < self.rates).astype(np.float32)
        return {
            "hit": hit,
            "velocity": (hit * self.velocity).astype(np.float32),
            "offset": np.zeros((STEPS, LANES), dtype=np.float32),
            "subhits": hit.astype(np.int64),
        }
