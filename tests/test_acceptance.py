from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from ableton_mcp_server.acceptance import (
    AcceptanceSafetyError,
    _acceptance_cue_time,
    run_live_acceptance,
)
from ableton_mcp_server.client import Client
from scripts.mock_remote_script import default_snapshot, run_mock_server


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
        run_live_acceptance(
            client,
            confirm_project_name="DISPOSABLE",
            track_index=0,
            clip_index=1,
        )
    assert client.calls == ["get_project_metadata"]


def test_acceptance_exercises_reads_mutations_and_partial_batch_over_real_jsonl() -> None:
    snapshot = deepcopy(default_snapshot())
    snapshot["tracks"][0]["clip_slots"].append(
        {
            "id": "track:0/clipslot:1",
            "clip_id": None,
            "index": 1,
            "has_clip": False,
            "clip_name": "",
            "length_beats": 0.0,
            "is_playing": False,
            "notes": [],
        }
    )
    server = run_mock_server(port=0, snapshot=snapshot)
    client = Client(port=server.port, reconnect=False)
    try:
        result = run_live_acceptance(
            client,
            confirm_project_name="Mock Set",
            track_index=0,
            clip_index=1,
            fire_clip=True,
        )
        assert result["status"] == "ok"
        assert result["notes_added"] == 4
        assert result["cue_round_trip"] is True
        assert result["batch"]["completed"] == 2
        assert result["batch"]["aborted_at"] == 2
        assert result["batch"]["rolled_back"] is False
        assert client.call("get_session_info", {})["tempo"] == 120.0
        assert client.call("get_loop_settings", {}) == {
            "loop": False,
            "loop_start": 0.0,
            "loop_length": 4.0,
        }
    finally:
        client.close()
        server.stop()
