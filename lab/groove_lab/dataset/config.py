"""Every knob of a dataset build, frozen, with a digest for the manifest.

A build that cannot be described by one hashable object cannot be reproduced,
and gate G2 asks for two independent builds with identical digests.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json

SHORT_FILE_POLICIES = ("looped", "padded")


@dataclasses.dataclass(frozen=True)
class BuildConfig:
    # Grid, from specification section 11.2.
    bars: int = 2
    grid_division: int = 16
    steps: int = 32
    lanes: int = 18
    condition_dimensions: int = 16

    # Windowing, from section 11.4. 33.6% of files are shorter than two bars, so
    # the policy is explicit and recorded rather than implied.
    short_file_policy: str = "looped"
    window_hop_bars: int = 2

    # Clustering and splits, from section 12.
    split_ratios: tuple[float, float, float] = (0.8, 0.1, 0.1)
    max_cluster_share: float = 0.05

    # Representation, from section 11.2. The measured loss of a sixteenth grid is
    # 3.51% of note mass; the budget is set just above it so a regression fails.
    representation_loss_budget: float = 0.04

    # Gate G1: a collection above this unresolved note mass stays out of training.
    max_unresolved_note_share: float = 0.10

    rows_per_shard: int = 4096
    seed: int = 20260831

    def __post_init__(self) -> None:
        if self.short_file_policy not in SHORT_FILE_POLICIES:
            raise ValueError(
                f"short_file_policy must be one of {SHORT_FILE_POLICIES}, "
                f"got {self.short_file_policy!r}"
            )
        if abs(sum(self.split_ratios) - 1.0) > 1e-9:
            raise ValueError(f"split_ratios must sum to 1.0, got {self.split_ratios}")

    def as_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)

    def digest(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
