from __future__ import annotations

from typing import Any


def diff_snapshots(
    snapshot_a: dict[str, Any], snapshot_b: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []

    def walk(before: Any, after: Any, path: str) -> None:
        """Walk two values and record their differences in the three lists."""
        _walk_values(before, after, path, added, removed, changed)

    walk(snapshot_a, snapshot_b, "")
    return {"added": added, "removed": removed, "changed": changed}


def _walk_values(
    before: Any,
    after: Any,
    path: str,
    added: list[dict[str, Any]],
    removed: list[dict[str, Any]],
    changed: list[dict[str, Any]],
) -> None:
    """Record the differences of two values found at one path."""
    if type(before) is not type(after):
        changed.append({"path": path, "before": before, "after": after})
        return
    if isinstance(before, dict):
        _walk_mapping(before, after, path, added, removed, changed)
        return
    if isinstance(before, list):
        _walk_sequence(before, after, path, added, removed, changed)
        return
    if before != after:
        changed.append({"path": path, "before": before, "after": after})


def _walk_mapping(
    before: dict[Any, Any],
    after: dict[Any, Any],
    path: str,
    added: list[dict[str, Any]],
    removed: list[dict[str, Any]],
    changed: list[dict[str, Any]],
) -> None:
    """Record the key level differences of two mappings."""
    before_keys = set(before)
    after_keys = set(after)
    for key in sorted(after_keys - before_keys):
        next_path = f"{path}.{key}" if path else key
        added.append({"path": next_path, "value": after[key]})
    for key in sorted(before_keys - after_keys):
        next_path = f"{path}.{key}" if path else key
        removed.append({"path": next_path, "value": before[key]})
    for key in sorted(before_keys & after_keys):
        next_path = f"{path}.{key}" if path else key
        _walk_values(before[key], after[key], next_path, added, removed, changed)


def _walk_sequence(
    before: list[Any],
    after: list[Any],
    path: str,
    added: list[dict[str, Any]],
    removed: list[dict[str, Any]],
    changed: list[dict[str, Any]],
) -> None:
    """Record the index level differences of two sequences."""
    for index in range(max(len(before), len(after))):
        next_path = f"{path}.{index}" if path else str(index)
        if index >= len(before):
            added.append({"path": next_path, "value": after[index]})
        elif index >= len(after):
            removed.append({"path": next_path, "value": before[index]})
        else:
            _walk_values(before[index], after[index], next_path, added, removed, changed)
