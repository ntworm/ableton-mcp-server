from __future__ import annotations

from contracts import ALLOWED_MUTATIONS, READ_ONLY_COMMANDS, is_allowed_mutation, is_read_only

from .errors import ReadOnlyViolation

__all__ = [
    "ALLOWED_MUTATIONS",
    "READ_ONLY_COMMANDS",
    "assert_not_blocked",
    "is_allowed_mutation",
    "is_read_only",
]


def assert_not_blocked(command_name: str) -> None:
    normalized = command_name.strip().lower()
    if normalized in READ_ONLY_COMMANDS:
        raise ReadOnlyViolation(
            f"Command {command_name!r} is blocked: creative mutation is not available."
        )
