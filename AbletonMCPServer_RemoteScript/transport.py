"""Verified transport writes and the attribute write checks they share."""

from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from ._contracts import CUE_TIME_TOLERANCE, ERROR_LIVE_UNAVAILABLE, PLAYHEAD_MOVE_RETRIES
from .common import Live, PlayheadNotMovedError, RemoteError, _dbg, _safe


def _no_quantization_value() -> Any:
    if Live is None:
        return 0
    return Live.Song.Quantization.q_no_q


def _verified_playhead_steps(
    song: Any,
    target: float,
    *,
    retries: int = PLAYHEAD_MOVE_RETRIES,
) -> Generator[None, None, dict[str, float]]:
    """Advance a verified playhead write across Live UI ticks."""

    previous_quantization = song.clip_trigger_quantization
    actual = float(_safe(lambda: song.current_song_time, -1.0))
    try:
        song.clip_trigger_quantization = _no_quantization_value()
        for attempt in range(retries):
            song.current_song_time = target
            yield
            actual = float(song.current_song_time)
            _dbg(
                "transport attribute=current_song_time asked=%s got=%s tick_attempt=%s"
                % (target, actual, attempt + 1)
            )
            if abs(actual - target) < CUE_TIME_TOLERANCE:
                return {"current_song_time": actual}
        raise PlayheadNotMovedError(target, actual, retries)
    finally:
        song.clip_trigger_quantization = previous_quantization


def _verified_boolean_steps(
    song: Any,
    *,
    attribute: str,
    expected: bool,
    setter: Callable[[], None],
    result_key: str,
    retries: int = PLAYHEAD_MOVE_RETRIES,
) -> Generator[None, None, dict[str, bool]]:
    """Apply and confirm a deferred boolean state change on later UI ticks."""

    actual = bool(_safe(lambda: getattr(song, attribute), not expected))
    for attempt in range(retries):
        setter()
        yield
        actual = bool(getattr(song, attribute))
        _dbg(
            "state attribute=%s asked=%s got=%s tick_attempt=%s"
            % (attribute, expected, actual, attempt + 1)
        )
        if actual is expected:
            return {result_key: actual}
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "State setter for %s did not reach %s after %s UI ticks." % (attribute, expected, retries),
    )


def _verified_numeric_steps(
    song: Any,
    *,
    attribute: str,
    expected: float,
    result_key: str,
    retries: int = PLAYHEAD_MOVE_RETRIES,
) -> Generator[None, None, dict[str, float]]:
    """Compatibility wrapper for verified numeric Song attributes."""

    return (
        yield from _verified_attribute_numeric_steps(
            song,
            attribute=attribute,
            expected=expected,
            result_key=result_key,
            retries=retries,
        )
    )


def _verified_attribute_numeric_steps(
    target: Any,
    *,
    attribute: str,
    expected: float,
    result_key: str,
    retries: int = PLAYHEAD_MOVE_RETRIES,
) -> Generator[None, None, dict[str, float]]:
    """Apply and confirm a numeric attribute change on later UI ticks."""

    actual = float(_safe(lambda: getattr(target, attribute), -1.0))
    for attempt in range(retries):
        setattr(target, attribute, expected)
        yield
        actual = float(getattr(target, attribute))
        _dbg(
            "state attribute=%s asked=%s got=%s tick_attempt=%s"
            % (attribute, expected, actual, attempt + 1)
        )
        if abs(actual - expected) < CUE_TIME_TOLERANCE:
            return {result_key: actual}
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "State setter for %s did not reach %s after %s UI ticks." % (attribute, expected, retries),
    )


def _verified_attribute_boolean_steps(
    target: Any,
    *,
    attribute: str,
    expected: bool,
    result_key: str,
    retries: int = PLAYHEAD_MOVE_RETRIES,
) -> Generator[None, None, dict[str, bool]]:
    """Apply and confirm a boolean attribute change on later UI ticks."""

    actual = bool(_safe(lambda: getattr(target, attribute), not expected))
    for _attempt in range(retries):
        setattr(target, attribute, expected)
        yield
        actual = bool(getattr(target, attribute))
        if actual is expected:
            return {result_key: actual}
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "State setter for %s did not reach %s after %s UI ticks." % (attribute, expected, retries),
    )


def _verified_attribute_string_steps(
    target: Any,
    *,
    attribute: str,
    expected: str,
    result_key: str,
    retries: int = PLAYHEAD_MOVE_RETRIES,
) -> Generator[None, None, dict[str, str]]:
    """Apply and confirm a string attribute change on later UI ticks."""

    actual = str(_safe(lambda: getattr(target, attribute), ""))
    for _attempt in range(retries):
        setattr(target, attribute, expected)
        yield
        actual = str(getattr(target, attribute))
        if actual == expected:
            return {result_key: actual}
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "State setter for %s did not reach %r after %s UI ticks." % (attribute, expected, retries),
    )
