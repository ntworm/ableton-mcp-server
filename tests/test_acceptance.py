from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ableton_mcp_server.acceptance import (
    AcceptanceSafetyError,
    _acceptance_cue_time,
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


def test_acceptance_uses_a_coarse_grid_aligned_free_cue_time() -> None:
    assert _acceptance_cue_time([]) == 256.0
    assert _acceptance_cue_time(
        [{"name": "A", "time": 256.0}, {"name": "B", "time": 512.0}]
    ) == 768.0


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
