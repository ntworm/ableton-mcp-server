from __future__ import annotations

from typing import Any, ClassVar


class BridgeError(Exception):
    """Base error that can cross the JSONL and MCP boundaries."""

    default_code: ClassVar[str] = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        hint: str | None = None,
        *,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.hint = hint
        self.code = code or self.default_code

    def to_envelope(self) -> dict[str, Any]:
        envelope: dict[str, Any] = {
            "status": "error",
            "code": self.code,
            "message": str(self),
        }
        if self.hint:
            envelope["hint"] = self.hint
        return envelope


class UnknownCommandError(BridgeError):
    default_code = "UNKNOWN_COMMAND"


class InvalidParamsError(BridgeError):
    default_code = "INVALID_PARAMS"


class ReadOnlyViolation(BridgeError):
    default_code = "READ_ONLY_VIOLATION"


class BridgeTimeoutError(BridgeError):
    default_code = "TIMEOUT"


class LiveUnavailableError(BridgeError):
    default_code = "LIVE_UNAVAILABLE"


class InternalBridgeError(BridgeError):
    default_code = "INTERNAL_ERROR"


class StaleReferenceError(BridgeError):
    default_code = "STALE_REFERENCE"

    def __init__(self, path_id: str) -> None:
        super().__init__(
            f"Path-id {path_id!r} no longer points at a live object.",
            "Re-list tracks and use a fresh path-id.",
        )


class WrongTypeError(BridgeError):
    default_code = "WRONG_TYPE"


class BadInputError(BridgeError):
    default_code = "BAD_INPUT"


class PlayheadNotMovedError(BridgeError):
    default_code = "PLAYHEAD_NOT_MOVED"

    def __init__(self, requested: float, actual: float, attempts: int) -> None:
        self.requested = requested
        self.actual = actual
        self.attempts = attempts
        super().__init__(
            "Transport setter did not reach the requested value "
            f"(asked={requested}, got={actual} after {attempts} attempts).",
            "Live may be in a transitional state; retry after it settles.",
        )


class CueSnappedToGridError(BridgeError):
    default_code = "CUE_SNAPPED_TO_GRID"


_ERROR_TYPES: dict[str, type[BridgeError]] = {
    cls.default_code: cls
    for cls in (
        UnknownCommandError,
        InvalidParamsError,
        ReadOnlyViolation,
        BridgeTimeoutError,
        LiveUnavailableError,
        InternalBridgeError,
        PlayheadNotMovedError,
        CueSnappedToGridError,
        StaleReferenceError,
        WrongTypeError,
        BadInputError,
    )
}


def error_from_envelope(code: str, message: str, hint: str | None) -> BridgeError:
    """Create the matching typed error without rewriting the remote message."""

    error_type = _ERROR_TYPES.get(code, BridgeError)
    error = error_type.__new__(error_type)
    BridgeError.__init__(error, message, hint, code=code)
    return error
