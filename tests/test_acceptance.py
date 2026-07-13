from __future__ import annotations

import asyncio
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
        # The mock_server only implements the legacy subset; limit the
        # runner to the mutation profile so it does not fail every read
        # probe that the fake cannot satisfy.
        result = asyncio.run(
            run_live_acceptance(
                client,
                confirm_project_name="Mock Set",
                track_index=0,
                clip_index=1,
                fire_clip=True,
                profiles=("mutations",),
            )
        )
        assert result["certification"]["tool_count"] == 65
        statuses = {row["tool"]: row["status"] for row in result["certification"]["tools"]}
        # The mutation profile records every catalogued tool. The mock
        # server does not implement ``clear_clip_notes`` (it is a newer
        # command), so the runner is expected to report that row as
        # ``failed`` and the downstream mutations fall back to a similar
        # failure path; the legacy probes remain ``live_passed``.
        for tool in ("set_tempo", "set_loop", "create_clip",
                     "create_cue_point", "delete_cue_point"):
            assert statuses[tool] == "live_passed", (
                f"{tool} unexpectedly {statuses[tool]!r}"
            )
        # ``clear_clip_notes`` is not in the mock so its row is the
        # single expected failure surface.
        assert statuses["clear_clip_notes"] == "failed"
        assert client.call("get_session_info", {})["tempo"] == 120.0
        assert client.call("get_loop_settings", {}) == {
            "loop": False,
            "loop_start": 0.0,
            "loop_length": 4.0,
        }
    finally:
        client.close()
        server.stop()
