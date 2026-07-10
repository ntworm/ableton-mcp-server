from __future__ import annotations

from AbletonMCPServer_RemoteScript import execute_command
from tests.remote_fakes import FakeApplication, FakeSong


def test_standalone_mutation_is_one_undo_step() -> None:
    app = FakeApplication()
    song = FakeSong()
    assert execute_command(song, app, "set_tempo", {"tempo": 128.0}) == {"tempo": 128.0}
    assert (app.begin_count, app.end_count) == (1, 1)


def test_batch_uses_one_outer_undo_and_aborts_with_successful_prefix_persisting() -> None:
    app = FakeApplication()
    song = FakeSong()
    result = execute_command(
        song,
        app,
        "run_batch",
        {
            "commands": [
                {"type": "set_tempo", "params": {"tempo": 128.0}},
                {
                    "type": "create_clip",
                    "params": {"track_index": 0, "clip_index": 0, "length_beats": 4.0},
                },
                {"type": "set_loop", "params": {"enabled": True}},
            ]
        },
    )
    assert song.tempo == 128.0
    assert song.loop is False
    assert result["completed"] == 1
    assert result["aborted_at"] == 1
    assert result["rolled_back"] is False
    assert (app.begin_count, app.end_count) == (1, 1)


def test_batch_closes_undo_step_when_unexpected_handler_error_occurs() -> None:
    app = FakeApplication()
    song = FakeSong()
    result = execute_command(
        song,
        app,
        "run_batch",
        {"commands": [{"type": "set_tempo", "params": {}}]},
    )
    assert result["aborted_at"] == 0
    assert result["results"][0]["code"] == "INVALID_PARAMS"
    assert (app.begin_count, app.end_count) == (1, 1)
