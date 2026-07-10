from __future__ import annotations

from ableton_mcp_server.diff import diff_snapshots


def test_recursive_diff_is_deterministic() -> None:
    before = {"tempo": 120.0, "tracks": [{"name": "Bass"}], "old": True}
    after = {"tempo": 128.0, "tracks": [{"name": "Bass"}, {"name": "Drums"}], "new": 1}
    assert diff_snapshots(before, after) == {
        "added": [
            {"path": "new", "value": 1},
            {"path": "tracks.1", "value": {"name": "Drums"}},
        ],
        "removed": [{"path": "old", "value": True}],
        "changed": [{"path": "tempo", "before": 120.0, "after": 128.0}],
    }


def test_type_change_is_one_changed_entry() -> None:
    assert diff_snapshots({"value": 1}, {"value": "1"})["changed"] == [
        {"path": "value", "before": 1, "after": "1"}
    ]
