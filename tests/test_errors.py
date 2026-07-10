from __future__ import annotations

from ableton_mcp_server.errors import (
    BridgeError,
    PlayheadNotMovedError,
    StaleReferenceError,
    error_from_envelope,
)


def test_typed_error_serializes_optional_hint() -> None:
    error = StaleReferenceError("track:9")
    assert error.to_envelope() == {
        "status": "error",
        "code": "STALE_REFERENCE",
        "message": "Path-id 'track:9' no longer points at a live object.",
        "hint": "Re-list tracks and use a fresh path-id.",
    }


def test_transport_error_records_observed_value() -> None:
    error = PlayheadNotMovedError(8.0, 4.0, 3)
    assert error.code == "PLAYHEAD_NOT_MOVED"
    assert "asked=8.0" in str(error)
    assert "got=4.0" in str(error)
    assert error.attempts == 3


def test_error_factory_maps_known_code_and_retains_remote_hint() -> None:
    error = error_from_envelope(
        "STALE_REFERENCE",
        "track:4 disappeared",
        "Refresh the snapshot.",
    )
    assert isinstance(error, StaleReferenceError)
    assert str(error) == "track:4 disappeared"
    assert error.hint == "Refresh the snapshot."


def test_error_factory_keeps_unknown_code_machine_readable() -> None:
    error = error_from_envelope("FUTURE_CODE", "future failure", None)
    assert type(error) is BridgeError
    assert error.code == "FUTURE_CODE"
