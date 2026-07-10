from __future__ import annotations

from typing import Any


def diff_snapshots(
    snapshot_a: dict[str, Any], snapshot_b: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []

    def walk(before: Any, after: Any, path: str) -> None:
        if type(before) is not type(after):
            changed.append({"path": path, "before": before, "after": after})
            return
        if isinstance(before, dict):
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
                walk(before[key], after[key], next_path)
            return
        if isinstance(before, list):
            for index in range(max(len(before), len(after))):
                next_path = f"{path}.{index}" if path else str(index)
                if index >= len(before):
                    added.append({"path": next_path, "value": after[index]})
                elif index >= len(after):
                    removed.append({"path": next_path, "value": before[index]})
                else:
                    walk(before[index], after[index], next_path)
            return
        if before != after:
            changed.append({"path": path, "before": before, "after": after})

    walk(snapshot_a, snapshot_b, "")
    return {"added": added, "removed": removed, "changed": changed}
