from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ableton_mcp_server.acceptance import (
    AcceptanceSafetyError,
    _acceptance_safe_cue_times,
    run_live_acceptance,
)


class MetadataOnlyClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def call(
        self,
        command: str,
        _params: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> Any:
        self.calls.append(command)
        assert timeout is None
        return {"song_name": "Valuable Project", "file_path": "valuable.als"}


def test_acceptance_picks_two_grid_aligned_free_cue_times() -> None:
    """The helper returns two distinct, grid-aligned times inside song_length.

    The previous implementation returned ``256`` (and ``cue_time + 64``),
    which exceeded the 232-beat ``TESTE_CODEX`` canonical song_length and
    broke the cue probes on the real Set.
    """
    t1, t2 = _acceptance_safe_cue_times(song_length=232.0, locators=[], grid=8.0)
    assert t1 != t2
    assert 0.0 <= t1 <= 232.0
    assert 0.0 <= t2 <= 232.0
    assert t1 % 8.0 == 0.0
    assert t2 % 8.0 == 0.0
    # Bypasses any prior locator at exactly ``256.0``.
    t3, t4 = _acceptance_safe_cue_times(
        song_length=512.0,
        locators=[{"name": "A", "time": 256.0}, {"name": "B", "time": 512.0}],
        grid=64.0,
    )
    assert t3 not in (256.0, 512.0)
    assert t4 not in (256.0, 512.0)


def test_acceptance_refuses_to_mutate_when_project_confirmation_does_not_match() -> None:
    client = MetadataOnlyClient()
    with pytest.raises(AcceptanceSafetyError, match="does not match"):
        asyncio.run(
            run_live_acceptance(
                client,
                confirm_project_name="DISPOSABLE",
                track_index=0,
                clip_index=1,
            )
        )
    # The composed-profile probes run first and the metadata probe is the
    # only one that targets the TCP bridge before the safety check fires.
    assert "get_project_metadata" in client.calls
