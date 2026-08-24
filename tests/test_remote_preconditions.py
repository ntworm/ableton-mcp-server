from __future__ import annotations

from AbletonMCPServer_RemoteScript import execute_command
from tests.remote_fakes import FakeApplication, FakeSong


def test_invalid_precondition_is_admitted_before_undo() -> None:
    app = FakeApplication()
    result = execute_command(
        FakeSong(),
        app,
        "run_batch",
        {
            "commands": [{"type": "set_tempo", "params": {"tempo": 120}}],
            "preconditions": [{"type": "bad", "version": "v1", "params": {}}],
        },
    )
    assert result["code"] == "PRECONDITION_INVALID"
    assert app.begin_count == 0


def test_occupied_slot_fails_before_undo() -> None:
    song = FakeSong()
    app = FakeApplication()
    result = execute_command(
        song,
        app,
        "run_batch",
        {
            "commands": [{"type": "set_tempo", "params": {"tempo": 120}}],
            "preconditions": [
                {
                    "type": "slot_empty",
                    "version": "v1",
                    "params": {"track_index": 0, "clip_index": 0},
                }
            ],
        },
    )
    assert result["code"] == "PRECONDITION_FAILED"
    assert app.begin_count == 0
