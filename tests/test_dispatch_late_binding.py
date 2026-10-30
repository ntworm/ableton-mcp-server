"""The dispatcher resolves its step functions at call time.

The dispatcher used to read each step function from its own module globals
while dispatching, so replacing ``dispatch._set_clip_color_steps`` changed
what ran. A module-level table froze the function objects at import time and
silently broke that: the patched function was never called. This test pins
the call-time lookup back in place.
"""

from __future__ import annotations

from typing import Any

from AbletonMCPServer_RemoteScript import dispatch, execute_command
from tests.remote_fakes import FakeApplication, FakeSong


def test_dispatch_uses_the_step_function_currently_bound_on_the_module(
    monkeypatch: Any,
) -> None:
    def patched_steps(song: Any, params: dict[str, Any]) -> Any:
        yield from ()
        return {"patched": True}

    monkeypatch.setattr(dispatch, "_set_clip_color_steps", patched_steps)

    result = execute_command(
        FakeSong(),
        FakeApplication(),
        "set_clip_color",
        {"track_index": 0, "clip_index": 0, "color_index": 3},
    )

    assert result == {"patched": True}
