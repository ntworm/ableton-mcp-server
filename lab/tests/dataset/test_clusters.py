from __future__ import annotations

import pytest

from groove_lab.dataset.clusters import (
    GiantComponentError,
    build_clusters,
    component_sizes,
)


def _record(source: str, byte: str, canonical: str, rhythm: str, collection: str) -> dict:
    return {
        "source_id": source,
        "byte_hash": byte,
        "canonical_hash": canonical,
        "rhythm_hash": rhythm,
        "collection": collection,
    }


def test_identical_bytes_land_in_one_cluster() -> None:
    records = [
        _record("a", "H", "C", "R", "col1"),
        _record("b", "H", "C", "R", "col1"),
        _record("c", "OTHER", "C2", "R2", "col2"),
    ]
    clusters = build_clusters(records, max_share=1.0)
    assert clusters["a"] == clusters["b"]
    assert clusters["a"] != clusters["c"]


def test_same_rhythm_across_collections_still_shares_a_cluster() -> None:
    # Measured: 346 onset patterns repeat across different collections. Grouping
    # by hierarchy alone would put these on opposite sides of the split.
    records = [
        _record("a", "H1", "C1", "SAME", "col1"),
        _record("b", "H2", "C2", "SAME", "col2"),
    ]
    clusters = build_clusters(records, max_share=1.0)
    assert clusters["a"] == clusters["b"]


def test_unrelated_files_stay_apart() -> None:
    records = [
        _record("a", "H1", "C1", "R1", "col1"),
        _record("b", "H2", "C2", "R2", "col2"),
    ]
    clusters = build_clusters(records, max_share=1.0)
    assert clusters["a"] != clusters["b"]


def test_a_giant_component_is_rejected_not_tolerated() -> None:
    records = [_record(str(i), "H", "C", "R", "col") for i in range(100)]
    with pytest.raises(GiantComponentError) as error:
        build_clusters(records, max_share=0.05)
    assert "100" in str(error.value)


def test_component_sizes_are_reported_for_the_manifest() -> None:
    records = [
        _record("a", "H", "C", "R", "col1"),
        _record("b", "H", "C", "R", "col1"),
        _record("c", "H2", "C2", "R2", "col2"),
    ]
    clusters = build_clusters(records, max_share=1.0)
    sizes = component_sizes(clusters)
    assert sorted(sizes.values(), reverse=True) == [2, 1]
