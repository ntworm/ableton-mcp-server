from __future__ import annotations

from ableton_mcp_server.snapshot import normalize_value, sort_by_index, validate_snapshot


def sample_snapshot() -> dict[str, object]:
    return {
        "schema_version": 1,
        "captured_at_unix_ms": 1719878400000,
        "live_version": "12.4.5",
        "tempo": 120.0,
        "signature_numerator": 4,
        "signature_denominator": 4,
        "is_playing": False,
        "current_song_time": 0.0,
        "tracks": [],
        "control_surfaces": [],
        "browser_categories_count": 7,
    }


def test_normalization_rounds_nested_floats() -> None:
    assert normalize_value({"a": [0.123456789]}) == {"a": [0.123457]}


def test_sort_by_index_does_not_mutate_input() -> None:
    original = [{"index": 2, "value": 0.11111119}, {"index": 0, "value": 1.0}]
    assert sort_by_index(original) == [
        {"index": 0, "value": 1.0},
        {"index": 2, "value": 0.111111},
    ]
    assert original[0]["value"] == 0.11111119


def test_snapshot_validation_requires_types_not_only_keys() -> None:
    snapshot = sample_snapshot()
    assert validate_snapshot(snapshot)
    snapshot["tracks"] = "not-a-list"
    assert not validate_snapshot(snapshot)
    snapshot = sample_snapshot()
    snapshot["tempo"] = "120"
    assert not validate_snapshot(snapshot)
