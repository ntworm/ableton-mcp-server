"""Cue point creation, renaming, moves and deletion, each confirmed by readback."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from ._contracts import (
    CUE_OPERATION_VERIFY_TICKS,
    CUE_TIME_TOLERANCE,
    ERROR_INVALID_PARAMS,
    ERROR_LIVE_UNAVAILABLE,
    PLAYHEAD_MOVE_RETRIES,
)
from .common import (
    CueSnappedToGridError,
    PlayheadNotMovedError,
    RemoteError,
    _dbg,
    _float_param,
    _required,
    _safe,
    _string_param,
)
from .transport import _no_quantization_value


def _find_cue(song: Any, target_time: float) -> Any:
    for cue in song.cue_points:
        if abs(float(cue.time) - target_time) < CUE_TIME_TOLERANCE:
            return cue
    return None


def _cue_snapshot(song: Any) -> dict[float, str]:
    return {float(cue.time): str(_safe(lambda cue=cue: cue.name, "")) for cue in song.cue_points}


def _snapshot_has_time(snapshot: dict[float, str], target_time: float) -> bool:
    return any(abs(cue_time - target_time) < CUE_TIME_TOLERANCE for cue_time in snapshot)


def _cue_snapshot_delta(
    before: dict[float, str], after: dict[float, str]
) -> tuple[list[float], list[float]]:
    added = [time for time in after if not _snapshot_has_time(before, time)]
    removed = [time for time in before if not _snapshot_has_time(after, time)]
    return added, removed


def _wait_for_cue_state_steps(
    song: Any,
    target_time: float,
    *,
    should_exist: bool,
    ticks: int = CUE_OPERATION_VERIFY_TICKS,
) -> Generator[None, None, Any]:
    """Wait for Live to apply one cue toggle without toggling a second time."""

    cue = _find_cue(song, target_time)
    for attempt in range(ticks):
        yield
        cue = _find_cue(song, target_time)
        _dbg(
            "cue_state time=%s expected=%s observed=%s tick_attempt=%s"
            % (target_time, should_exist, cue is not None, attempt + 1)
        )
        if (cue is not None) is should_exist:
            return cue
    action = "create" if should_exist else "delete"
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "set_or_delete_cue() did not %s the cue near %s after %s UI ticks."
        % (action, target_time, ticks),
    )


def _reverse_snapped_cue_toggle_steps(
    song: Any,
    *,
    requested_time: float,
    before: dict[float, str],
    after: dict[float, str],
) -> Generator[None, None, None]:
    """Reverse the one off-grid toggle before reporting a typed failure."""

    added, removed = _cue_snapshot_delta(before, after)
    if len(added) == 1 and not removed:
        actual_time = added[0]
        yield from _verified_cue_position_steps(song, target=actual_time)
        song.set_or_delete_cue()
        yield from _wait_for_cue_state_steps(song, actual_time, should_exist=False)
        raise CueSnappedToGridError(requested_time, actual_time)
    if len(removed) == 1 and not added:
        actual_time = removed[0]
        original_name = before[actual_time]
        yield from _verified_cue_position_steps(song, target=actual_time)
        song.set_or_delete_cue()
        restored = yield from _wait_for_cue_state_steps(song, actual_time, should_exist=True)
        yield from _verified_cue_name_steps(restored, original_name)
        raise CueSnappedToGridError(requested_time, actual_time)
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "Cue state changed unexpectedly after an off-grid toggle; automatic reversal was not safe.",
        "Inspect Arrangement locators before retrying.",
    )


def _wait_for_created_cue_steps(
    song: Any,
    target_time: float,
    *,
    before: dict[float, str],
    ticks: int = CUE_OPERATION_VERIFY_TICKS,
) -> Generator[None, None, Any]:
    """Observe exact creation or reverse a grid-snapped toggle."""

    for attempt in range(ticks):
        yield
        cue = _find_cue(song, target_time)
        if cue is not None:
            return cue
        after = _cue_snapshot(song)
        added, removed = _cue_snapshot_delta(before, after)
        _dbg(
            "cue_create time=%s observed=False added=%r removed=%r tick_attempt=%s"
            % (target_time, added, removed, attempt + 1)
        )
        if added or removed:
            yield from _reverse_snapped_cue_toggle_steps(
                song,
                requested_time=target_time,
                before=before,
                after=after,
            )
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "set_or_delete_cue() did not create the cue near %s after %s UI ticks."
        % (target_time, ticks),
    )


def _wait_for_deleted_cue_steps(
    song: Any,
    target_time: float,
    *,
    before: dict[float, str],
    ticks: int = CUE_OPERATION_VERIFY_TICKS,
) -> Generator[None, None, None]:
    """Observe exact deletion or reverse a grid-snapped toggle."""

    for attempt in range(ticks):
        yield
        cue = _find_cue(song, target_time)
        after = _cue_snapshot(song)
        added, removed = _cue_snapshot_delta(before, after)
        if cue is None:
            unexpected_removed = [
                time for time in removed if abs(time - target_time) >= CUE_TIME_TOLERANCE
            ]
            if not added and not unexpected_removed:
                return
            raise RemoteError(
                ERROR_LIVE_UNAVAILABLE,
                "Cue deletion changed additional locator state; automatic reversal was not safe.",
                "Inspect Arrangement locators before retrying.",
            )
        _dbg(
            "cue_delete time=%s observed=False added=%r removed=%r tick_attempt=%s"
            % (target_time, added, removed, attempt + 1)
        )
        if added or removed:
            yield from _reverse_snapped_cue_toggle_steps(
                song,
                requested_time=target_time,
                before=before,
                after=after,
            )
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "set_or_delete_cue() did not delete the cue near %s after %s UI ticks."
        % (target_time, ticks),
    )


def _verified_cue_name_steps(
    cue: Any,
    name: str,
    *,
    ticks: int = CUE_OPERATION_VERIFY_TICKS,
) -> Generator[None, None, None]:
    """Confirm a cue rename before reporting creation success."""

    cue.name = name
    actual = str(_safe(lambda: cue.name, ""))
    if actual == name:
        return
    for attempt in range(ticks):
        yield
        actual = str(_safe(lambda: cue.name, ""))
        _dbg("cue_name asked=%r got=%r tick_attempt=%s" % (name, actual, attempt + 1))
        if actual == name:
            return
        cue.name = name
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "Cue near %s was created but its name did not reach %r after %s UI ticks."
        % (float(cue.time), name, ticks),
    )


def _verified_cue_position_steps(
    song: Any,
    *,
    target: float,
    retries: int = PLAYHEAD_MOVE_RETRIES,
) -> Generator[None, None, None]:
    """Move the Arrangement playback position used by cue toggling."""

    actual = float(song.current_song_time)
    if abs(actual - target) < CUE_TIME_TOLERANCE:
        return
    for attempt in range(retries):
        song.current_song_time = target
        yield
        actual = float(song.current_song_time)
        _dbg("cue_position asked=%s got=%s tick_attempt=%s" % (target, actual, attempt + 1))
        if abs(actual - target) < CUE_TIME_TOLERANCE:
            return
    raise PlayheadNotMovedError(target, actual, retries)


def _create_cue_at_cursor_steps(
    song: Any, name: str, target_time: float
) -> Generator[None, None, dict[str, Any]]:
    existing = _find_cue(song, target_time)
    if existing is not None:
        yield from _verified_cue_name_steps(existing, name)
        return {"name": name, "time": float(existing.time), "action": "renamed"}

    before = _cue_snapshot(song)
    yield from _verified_cue_position_steps(
        song,
        target=target_time,
    )
    song.set_or_delete_cue()
    created = yield from _wait_for_created_cue_steps(
        song,
        target_time,
        before=before,
    )
    yield from _verified_cue_name_steps(created, name)
    return {"name": name, "time": float(created.time), "action": "created"}


def _create_cue_point_steps(
    song: Any, params: dict[str, Any]
) -> Generator[None, None, dict[str, Any]]:
    name = _string_param(params, "name")
    target_time = _float_param(params, "time", 0.0, 100000.0)

    previous_time = float(song.current_song_time)
    previous_quantization = song.clip_trigger_quantization
    try:
        song.clip_trigger_quantization = _no_quantization_value()
        return (yield from _create_cue_at_cursor_steps(song, name, target_time))
    finally:
        yield from _verified_cue_position_steps(
            song,
            target=previous_time,
        )
        song.clip_trigger_quantization = previous_quantization


def _delete_cue_point_steps(
    song: Any, params: dict[str, Any]
) -> Generator[None, None, dict[str, Any]]:
    target_time = _float_param(params, "time", 0.0, 100000.0)
    cue = _find_cue(song, target_time)
    if cue is None:
        return {"deleted": False, "reason": "no cue at time"}
    cue_time = float(cue.time)
    before = _cue_snapshot(song)
    previous_time = float(song.current_song_time)
    previous_quantization = song.clip_trigger_quantization
    try:
        song.clip_trigger_quantization = _no_quantization_value()
        yield from _verified_cue_position_steps(
            song,
            target=cue_time,
        )
        song.set_or_delete_cue()
        yield from _wait_for_deleted_cue_steps(song, cue_time, before=before)
        return {"deleted": True, "time": cue_time}
    finally:
        yield from _verified_cue_position_steps(
            song,
            target=previous_time,
        )
        song.clip_trigger_quantization = previous_quantization


def _bulk_create_cue_points_steps(
    song: Any, params: dict[str, Any]
) -> Generator[None, None, dict[str, Any]]:
    items = _required(params, "items")
    if not isinstance(items, list) or not items:
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'items' must be a non-empty list.")
    results = []
    previous_time = float(song.current_song_time)
    previous_quantization = song.clip_trigger_quantization
    try:
        song.clip_trigger_quantization = _no_quantization_value()
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                error = RemoteError(ERROR_INVALID_PARAMS, "Cue item must be an object.")
                results.append({"index": index, **error.to_envelope()})
                continue
            try:
                name = _string_param(item, "name")
                target_time = _float_param(item, "time", 0.0, 100000.0)
                result = yield from _create_cue_at_cursor_steps(song, name, target_time)
                results.append({"index": index, "status": "ok", "result": result})
            except RemoteError as error:
                results.append({"index": index, **error.to_envelope()})
    finally:
        yield from _verified_cue_position_steps(
            song,
            target=previous_time,
        )
        song.clip_trigger_quantization = previous_quantization
    return {"results": results}
