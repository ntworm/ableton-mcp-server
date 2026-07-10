from __future__ import annotations

import pytest

from ableton_mcp_server.errors import ReadOnlyViolation
from ableton_mcp_server.write_guard import assert_not_blocked


def test_explicit_debug_mutations_are_allowed_case_insensitively() -> None:
    assert_not_blocked("SET_TEMPO")
    assert_not_blocked("create_clip")
    assert_not_blocked("fire_clip")
    assert_not_blocked("add_notes_to_clip")


def test_blocked_creative_command_raises_typed_error() -> None:
    with pytest.raises(ReadOnlyViolation) as exc_info:
        assert_not_blocked("delete_track")
    assert exc_info.value.code == "READ_ONLY_VIOLATION"


def test_unknown_name_is_left_for_dispatcher_not_prefix_blocked() -> None:
    assert_not_blocked("set_future_debug_property")
