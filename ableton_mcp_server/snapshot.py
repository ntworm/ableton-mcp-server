from __future__ import annotations

from typing import Any


def normalize_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {key: normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    return value


def sort_by_index(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [normalize_value(item) for item in items]
    return sorted(normalized, key=lambda item: int(item.get("index", 0)))


def validate_snapshot(snapshot: Any) -> bool:
    if not isinstance(snapshot, dict):
        return False
    typed_fields: dict[str, type[Any] | tuple[type[Any], ...]] = {
        "schema_version": int,
        "captured_at_unix_ms": (int, type(None)),
        "live_version": str,
        "tempo": (int, float),
        "signature_numerator": int,
        "signature_denominator": int,
        "is_playing": bool,
        "current_song_time": (int, float),
        "tracks": list,
        "control_surfaces": list,
        "browser_categories_count": int,
    }
    return all(
        field in snapshot and isinstance(snapshot[field], expected)
        for field, expected in typed_fields.items()
    )
