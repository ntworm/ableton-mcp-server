"""Errors, parameter parsing and debug logging shared by the Remote Script modules."""

from __future__ import annotations

import logging
import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ._contracts import (
    ERROR_BAD_INPUT,
    ERROR_CUE_SNAPPED_TO_GRID,
    ERROR_INVALID_PARAMS,
    ERROR_PLAYHEAD_NOT_MOVED,
)

try:  # These modules only exist inside Ableton Live.
    import Live  # type: ignore[import-not-found]
    from ableton.v2.control_surface import ControlSurface  # type: ignore[import-not-found]
except ImportError:  # Local tests exercise the pure handlers without Live.
    Live = None  # type: ignore[assignment]

    class ControlSurface:  # type: ignore[no-redef]
        def __init__(self, c_instance: Any) -> None:
            self._c_instance = c_instance
            self.song = c_instance.song

        def update_display(self) -> None:
            return None

        def disconnect(self) -> None:
            return None

        def show_message(self, _message: str) -> None:
            return None


logger = logging.getLogger("AbletonMCPServer")
_VERBOSE = os.environ.get("ABLETON_MCP_SERVER_VERBOSE") == "1"


def _dbg(message: str) -> None:
    if _VERBOSE:
        logger.info("[MCP-Server] %s", message)


class RemoteError(Exception):
    """Structured error produced by a Remote Script handler."""

    def __init__(
        self,
        code: str,
        message: str,
        hint: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint
        # Machine-readable payload for errors that carry more than prose.
        # ``CAPABILITY_UNAVAILABLE`` uses it for the API evidence behind the
        # refusal and for the request the caller made.
        self.details = details

    def to_envelope(self) -> dict[str, Any]:
        envelope: dict[str, Any] = {
            "status": "error",
            "code": self.code,
            "message": str(self),
        }
        if self.hint:
            envelope["hint"] = self.hint
        if self.details:
            envelope["details"] = self.details
        return envelope


class PlayheadNotMovedError(RemoteError):
    def __init__(self, requested: float, actual: float, attempts: int) -> None:
        self.requested = requested
        self.actual = actual
        self.attempts = attempts
        super().__init__(
            ERROR_PLAYHEAD_NOT_MOVED,
            "Transport setter did not reach the requested value "
            "(asked=%s, got=%s after %s attempts)." % (requested, actual, attempts),
            "Live may be in a transitional state; retry after it settles.",
        )


class CueSnappedToGridError(RemoteError):
    def __init__(self, requested: float, actual: float) -> None:
        self.requested = requested
        self.actual = actual
        super().__init__(
            ERROR_CUE_SNAPPED_TO_GRID,
            "Live snapped the cue operation from requested %s to %s. "
            "The unintended grid operation was reversed." % (requested, actual),
            "Disable Arrangement Snap-to-Grid (Ctrl/Cmd+4) or use a grid-aligned time.",
        )


@dataclass(frozen=True)
class _FallbackMidiNoteSpecification:
    """Test-only stand-in for ``Live.Clip.MidiNoteSpecification``."""

    pitch: int
    start_time: float
    duration: float
    velocity: int
    mute: bool
    probability: float | None = None
    release_velocity: float | None = None
    velocity_deviation: float | None = None


def _midi_note_specification(**values: Any) -> Any:
    if Live is None:
        return _FallbackMidiNoteSpecification(**values)
    return Live.Clip.MidiNoteSpecification(**values)


def _safe(getter: Callable[[], Any], default: Any) -> Any:
    try:
        return getter()
    except (AttributeError, RuntimeError, TypeError):
        return default


def _optional_int(value: Any) -> int | None:
    """Coerce a LOM integer property to ``int``, or ``None`` when absent.

    ``bool`` is excluded on purpose: it is an ``int`` subclass in Python, and
    a host that answered ``True`` for ``color_index`` would otherwise be
    reported as colour ``1``.
    """

    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    """Coerce a LOM numeric property to ``float``, or ``None`` when absent.

    Beat times arrive as floats but a host that has no value answers ``None``,
    and ``bool`` is refused for the same reason as in ``_optional_int``.
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _required(params: dict[str, Any], name: str) -> Any:
    if name not in params:
        raise RemoteError(ERROR_INVALID_PARAMS, "Missing required parameter %r." % name)
    return params[name]


def _integer_param(params: dict[str, Any], name: str, minimum: int = 0) -> int:
    value = _required(params, name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Parameter %r must be an integer >= %s." % (name, minimum),
        )
    return value


def _float_param(
    params: dict[str, Any],
    name: str,
    minimum: float = 0.0,
    maximum: float | None = None,
    strictly_positive: bool = False,
) -> float:
    raw = _required(params, name)
    if isinstance(raw, bool):
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter %r must be numeric." % name)
    try:
        value = float(raw)
    except (TypeError, ValueError) as error:
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter %r must be numeric." % name) from error
    if not math.isfinite(value):
        raise RemoteError(ERROR_BAD_INPUT, "Parameter %r must be finite." % name)
    if strictly_positive and value <= minimum:
        raise RemoteError(ERROR_BAD_INPUT, "Parameter %r must be > %s." % (name, minimum))
    if not strictly_positive and value < minimum:
        raise RemoteError(ERROR_BAD_INPUT, "Parameter %r must be >= %s." % (name, minimum))
    if maximum is not None and value > maximum:
        raise RemoteError(ERROR_BAD_INPUT, "Parameter %r must be <= %s." % (name, maximum))
    return value


def _string_param(params: dict[str, Any], name: str) -> str:
    value = _required(params, name)
    if not isinstance(value, str) or not value.strip():
        raise RemoteError(ERROR_BAD_INPUT, "Parameter %r must be a non-empty string." % name)
    return value.strip()


def _bounded_int_param(params: dict[str, Any], name: str, minimum: int, maximum: int) -> int:
    value = _required(params, name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter %r must be an integer." % name)
    if value < minimum or value > maximum:
        raise RemoteError(
            ERROR_BAD_INPUT,
            "Parameter %r must be in %s..%s." % (name, minimum, maximum),
        )
    return value
