"""Assign splits by whole cluster and prove afterwards that nothing leaked.

The verification is deliberately independent of the assignment: it re-derives
leakage from the content hashes alone, so a bug in the clustering cannot hide a
bug in the split, which is the failure mode section 12.3 asks for.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence

SPLIT_NAMES = ("train", "validation", "test")
LEAKAGE_KEYS = ("byte_hash", "canonical_hash", "rhythm_hash")


class LeakageError(RuntimeError):
    """A content hash appears on both sides of a split boundary."""


def _cluster_order(cluster_id: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{cluster_id}".encode()).hexdigest()


def assign_splits(
    records: Sequence[Mapping[str, str]], ratios: tuple[float, float, float], seed: int
) -> dict[str, str]:
    """Return ``source_id`` to split name, moving whole clusters at a time."""

    members: dict[str, list[str]] = defaultdict(list)
    for record in records:
        members[record["cluster_id"]].append(record["source_id"])

    ordered = sorted(members, key=lambda cluster: _cluster_order(cluster, seed))
    total = len(records)
    train_target = ratios[0] * total
    validation_target = ratios[1] * total

    assignment: dict[str, str] = {}
    placed = 0
    for cluster in ordered:
        if placed < train_target:
            name = "train"
        elif placed < train_target + validation_target:
            name = "validation"
        else:
            name = "test"
        for source_id in members[cluster]:
            assignment[source_id] = name
        placed += len(members[cluster])
    return assignment


def verify_no_leakage(
    records: Sequence[Mapping[str, str]], splits: Mapping[str, str]
) -> None:
    """Raise if any content hash spans more than one split."""

    for key in LEAKAGE_KEYS:
        seen: dict[str, set[str]] = defaultdict(set)
        for record in records:
            seen[record[key]].add(splits[record["source_id"]])
        offenders = {value: names for value, names in seen.items() if len(names) > 1}
        if offenders:
            example, names = next(iter(offenders.items()))
            raise LeakageError(
                f"{len(offenders)} values of {key} span multiple splits; "
                f"for example {example} appears in {sorted(names)}"
            )
