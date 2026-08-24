"""Bounded, content-based musical similarity over stored projections."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite
from typing import Any, cast

CANONICAL_GRID_TICKS = 120
_TECHNICAL_FEATURE_NAMES = {"ppq", "ticks_per_quarter"}


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="python")
        if isinstance(dumped, Mapping):
            return cast(Mapping[str, object], dumped)
    return {}


def _sequence(value: object) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _number(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    number = float(value)
    return number if isfinite(number) else default


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, value))


def _relative_distance(left: float, right: float) -> float:
    denominator = max(abs(left), abs(right), 1.0e-12)
    return _bounded(abs(left - right) / denominator)


def _canonical_offset(offset_ticks: float, grid_ticks: float) -> float:
    """Return offset in sixteenth-note units, independent of source PPQ."""

    grid = grid_ticks if grid_ticks > 0 else float(CANONICAL_GRID_TICKS)
    return offset_ticks / grid


def _hvo_cells(
    projection: object,
) -> tuple[dict[tuple[str, int, int], tuple[float, float, float]], float]:
    value = _mapping(projection)
    grid_ticks = _number(value.get("grid_ticks"), CANONICAL_GRID_TICKS)
    cells: dict[tuple[str, int, int], tuple[float, float, float]] = {}
    for raw_cell in _sequence(value.get("cells")):
        cell = _mapping(raw_cell)
        role = str(cell.get("role", ""))
        if not role:
            continue
        bar = int(max(0.0, _number(cell.get("bar"))))
        step = int(max(0.0, _number(cell.get("step"))))
        hit = 1.0 if _number(cell.get("hit")) > 0.0 else 0.0
        velocity = _bounded(_number(cell.get("velocity")))
        offset = _canonical_offset(_number(cell.get("offset_ticks")), grid_ticks)
        cells[(role, bar, step)] = (hit, velocity, offset)
    return cells, grid_ticks


def hvo_distance(left: object | None, right: object | None) -> float:
    """Compare HVO occupancy, normalized velocity, and canonical offsets."""

    if left is None or right is None:
        return 0.0 if left is None and right is None else 1.0
    left_cells, _left_grid = _hvo_cells(left)
    right_cells, _right_grid = _hvo_cells(right)
    keys = sorted(set(left_cells) | set(right_cells))
    if not keys:
        return 0.0
    occupancy = 0.0
    velocity = 0.0
    offset = 0.0
    comparable = 0
    for key in keys:
        left_value = left_cells.get(key, (0.0, 0.0, 0.0))
        right_value = right_cells.get(key, (0.0, 0.0, 0.0))
        occupancy += abs(left_value[0] - right_value[0])
        if left_value[0] > 0.0 and right_value[0] > 0.0:
            velocity += abs(left_value[1] - right_value[1])
            offset += _bounded(abs(left_value[2] - right_value[2]))
            comparable += 1
    occupancy_distance = occupancy / len(keys)
    if comparable == 0:
        return round(_bounded(occupancy_distance), 9)
    velocity_distance = velocity / comparable
    offset_distance = offset / comparable
    return round(
        _bounded(
            0.5 * occupancy_distance
            + 0.25 * velocity_distance
            + 0.25 * offset_distance
        ),
        9,
    )


def _token_key(value: object) -> tuple[str, int, int, int, int] | None:
    token = _mapping(value)
    role = str(token.get("role", ""))
    if not role:
        return None
    return (
        role,
        int(_number(token.get("grid_step"))),
        int(_number(token.get("velocity_bin"))),
        int(_number(token.get("offset_bin"))),
        int(_number(token.get("duration_bin"))),
    )


def _distribution_distance(
    left: Mapping[tuple[Any, ...], float], right: Mapping[tuple[Any, ...], float]
) -> float:
    if not left and not right:
        return 0.0
    total_left = float(sum(left.values()))
    total_right = float(sum(right.values()))
    if total_left <= 0.0 or total_right <= 0.0:
        return 1.0
    keys = sorted(set(left) | set(right), key=repr)
    return round(
        _bounded(
            0.5
            * sum(
                abs(left.get(key, 0) / total_left - right.get(key, 0) / total_right)
                for key in keys
            )
        ),
        9,
    )


def _grammar_distributions(
    projection: object,
) -> tuple[dict[tuple[Any, ...], float], dict[tuple[Any, ...], float]]:
    value = _mapping(projection)
    tokens: dict[tuple[Any, ...], float] = {}
    for raw_token in _sequence(value.get("tokens")):
        key = _token_key(raw_token)
        if key is not None:
            tokens[key] = tokens.get(key, 0.0) + 1.0

    transitions: dict[tuple[Any, ...], float] = {}
    for raw_transition in _sequence(value.get("transitions")):
        transition = _mapping(raw_transition)
        source = transition.get("from")
        target = transition.get("to")
        if source is None or target is None:
            continue
        count = _number(transition.get("count"), 0.0)
        if count <= 0.0:
            count = _number(transition.get("probability"), 0.0)
        if count > 0.0:
            transition_key = (str(source), str(target))
            transitions[transition_key] = transitions.get(transition_key, 0.0) + count
    return tokens, transitions


def grammar_distance(left: object | None, right: object | None) -> float:
    """Compare normalized token and transition distributions."""

    if left is None or right is None:
        return 0.0 if left is None and right is None else 1.0
    left_tokens, left_transitions = _grammar_distributions(left)
    right_tokens, right_transitions = _grammar_distributions(right)
    return round(
        _bounded(
            0.5 * _distribution_distance(left_tokens, right_tokens)
            + 0.5 * _distribution_distance(left_transitions, right_transitions)
        ),
        9,
    )


def _feature_values(projection: object | None) -> dict[str, tuple[object, str]]:
    if projection is None:
        return {}
    raw_values = _mapping(_mapping(projection).get("values"))
    result: dict[str, tuple[object, str]] = {}
    for name, raw_value in raw_values.items():
        value = _mapping(raw_value)
        if str(value.get("status", "available")) != "available":
            result[str(name)] = (None, str(value.get("unit", "")))
        else:
            result[str(name)] = (value.get("value"), str(value.get("unit", "")))
    return result


def feature_distance(left: object | None, right: object | None) -> float:
    """Compare features using unit-aware musical scales, not raw subtraction."""

    left_values = _feature_values(left)
    right_values = _feature_values(right)
    names = sorted(set(left_values) | set(right_values))
    if not names:
        return 0.0
    distances: list[float] = []
    for name in names:
        left_value, left_unit = left_values.get(name, (None, ""))
        right_value, right_unit = right_values.get(name, (None, ""))
        if (
            name.casefold() in _TECHNICAL_FEATURE_NAMES
            or left_unit == "ticks_per_quarter"
            or right_unit == "ticks_per_quarter"
        ):
            continue
        if left_value is None or right_value is None:
            distances.append(0.0 if left_value is None and right_value is None else 1.0)
        elif (
            isinstance(left_value, (int, float))
            and not isinstance(left_value, bool)
            and isinstance(right_value, (int, float))
            and not isinstance(right_value, bool)
        ):
            unit = min((item for item in (left_unit, right_unit) if item), default="")
            if unit in {"normalized_velocity", "normalized_offset"}:
                distances.append(_bounded(abs(float(left_value) - float(right_value))))
            else:
                distances.append(_relative_distance(float(left_value), float(right_value)))
        else:
            distances.append(0.0 if left_value == right_value else 1.0)
    return round(_bounded(sum(distances) / len(distances)), 9) if distances else 0.0


__all__ = ["feature_distance", "grammar_distance", "hvo_distance"]
