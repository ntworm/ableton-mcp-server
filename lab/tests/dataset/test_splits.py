from __future__ import annotations

import pytest

from groove_lab.dataset.splits import LeakageError, assign_splits, verify_no_leakage


def _records(count: int, cluster_size: int) -> list[dict]:
    return [
        {
            "source_id": str(index),
            "cluster_id": f"c{index // cluster_size}",
            "byte_hash": f"b{index}",
            "canonical_hash": f"c{index}",
            "rhythm_hash": f"r{index}",
        }
        for index in range(count)
    ]


def test_whole_clusters_never_straddle_a_split() -> None:
    records = _records(300, cluster_size=3)
    splits = assign_splits(records, ratios=(0.8, 0.1, 0.1), seed=1)
    by_cluster: dict[str, set[str]] = {}
    for record in records:
        by_cluster.setdefault(record["cluster_id"], set()).add(splits[record["source_id"]])
    assert all(len(values) == 1 for values in by_cluster.values())


def test_ratios_are_approximately_honoured() -> None:
    records = _records(1000, cluster_size=2)
    splits = assign_splits(records, ratios=(0.8, 0.1, 0.1), seed=1)
    counts = {
        name: sum(1 for value in splits.values() if value == name)
        for name in ("train", "validation", "test")
    }
    assert 0.75 <= counts["train"] / 1000 <= 0.85
    assert 0.05 <= counts["validation"] / 1000 <= 0.15
    assert 0.05 <= counts["test"] / 1000 <= 0.15


def test_assignment_is_deterministic_for_a_seed() -> None:
    records = _records(200, cluster_size=2)
    assert assign_splits(records, (0.8, 0.1, 0.1), seed=7) == assign_splits(
        records, (0.8, 0.1, 0.1), seed=7
    )


def test_leakage_verifier_catches_a_shared_hash() -> None:
    records = _records(10, cluster_size=1)
    splits = {record["source_id"]: "train" for record in records}
    splits["9"] = "test"
    records[9]["rhythm_hash"] = records[0]["rhythm_hash"]
    with pytest.raises(LeakageError) as error:
        verify_no_leakage(records, splits)
    assert "rhythm_hash" in str(error.value)


def test_leakage_verifier_passes_a_clean_split() -> None:
    records = _records(10, cluster_size=1)
    splits = {record["source_id"]: "train" for record in records}
    splits["9"] = "test"
    verify_no_leakage(records, splits)
