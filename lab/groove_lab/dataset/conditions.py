"""The 16-dimension condition vector, with absence reported rather than guessed.

Every dimension is documented in the plan and in the dataset manifest.  A
condition with no source is zero, and index 10 says whether a vendor genre was
available at all, so the model can learn the difference between "not metal" and
"nobody said".
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from .canonical import CanonicalGroove
from .windows import BARS, Window

DIMENSIONS = 16
GENRE_BUCKETS = ("Pop/Rock/Country", "Metal", "Latin", "Jazz")


def build_conditions(
    groove: CanonicalGroove, window: Window, labels: Mapping[str, object]
) -> np.ndarray:
    vector = np.zeros(DIMENSIONS, dtype=np.float32)

    bpm = labels.get("tempo") or groove.bpm
    if bpm:
        vector[0] = float(np.clip((float(bpm) - 60.0) / 140.0, 0.0, 1.0))
    vector[1] = 1.0 if groove.meter == "4/4" else 0.0

    hits = int(window.hit.sum())
    vector[2] = float(np.clip(hits / (BARS * 32.0), 0.0, 1.0))

    section = str(labels.get("section", "")).lower()
    vector[3] = 1.0 if "groove" in section else 0.0
    vector[4] = 1.0 if "fill" in section else 0.0
    vector[5] = 1.0 if "variation" in section else 0.0

    offsets = window.offset[window.hit == 1]
    if offsets.size:
        vector[6] = float(np.clip(abs(float(offsets.mean())) / 60.0, 0.0, 1.0))
        velocities = window.velocity[window.hit == 1]
        vector[7] = float(np.clip(float(velocities.mean()), 0.0, 1.0))

    lanes_used = int((window.hit.sum(axis=0) > 0).sum())
    vector[8] = float(np.clip(lanes_used / window.hit.shape[1], 0.0, 1.0))
    vector[9] = 1.0 if window.looped else 0.0

    genre = labels.get("genre")
    if genre:
        vector[10] = 1.0
        for index, bucket in enumerate(GENRE_BUCKETS):
            if genre == bucket:
                vector[11 + index] = 1.0
                break
        else:
            vector[15] = 1.0
    return vector
