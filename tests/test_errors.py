from __future__ import annotations

import pytest

from ableton_mcp_server.errors import (
    BridgeError,
    CueSnappedToGridError,
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


def test_error_factory_maps_cue_grid_snap() -> None:
    error = error_from_envelope(
        "CUE_SNAPPED_TO_GRID",
        "Live snapped requested 24.0 to 32.0.",
        "Disable Arrangement Snap-to-Grid.",
    )
    assert isinstance(error, CueSnappedToGridError)
    assert error.code == "CUE_SNAPPED_TO_GRID"


def test_error_factory_keeps_unknown_code_machine_readable() -> None:
    error = error_from_envelope("FUTURE_CODE", "future failure", None)
    assert type(error) is BridgeError
    assert error.code == "FUTURE_CODE"


@pytest.mark.parametrize(
    ("code", "class_name"),
    [
        ("CAPABILITY_UNAVAILABLE", "CapabilityUnavailableError"),
        ("AMBIGUOUS_MATCH", "AmbiguousMatchError"),
        ("VERIFICATION_FAILED", "VerificationFailedError"),
        ("ACCEPTANCE_GUARD_FAILED", "AcceptanceGuardFailedError"),
    ],
)
def test_new_public_error_codes_are_typed(code: str, class_name: str) -> None:
    error = error_from_envelope(code, "message", "hint")
    assert type(error).__name__ == class_name
    assert error.code == code
