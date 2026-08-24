from __future__ import annotations

import sys

from ableton_mcp_server.groove_intelligence.resource_limits import (
    PosixProcessGroupEnforcer,
    UnavailableEnforcer,
    WindowsJobObjectEnforcer,
    select_resource_enforcer,
)


def test_resource_enforcer_selection_is_platform_explicit() -> None:
    assert isinstance(select_resource_enforcer("win32"), WindowsJobObjectEnforcer)
    if sys.platform != "win32":
        assert isinstance(select_resource_enforcer("linux"), PosixProcessGroupEnforcer)


def test_unavailable_enforcer_is_explicit_not_a_noop() -> None:
    enforcer = UnavailableEnforcer()
    assert enforcer.available is False
