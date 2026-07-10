from __future__ import annotations

import pytest

from AbletonMCPServer_RemoteScript import (
    PlayheadNotMovedError,
    _set_transport_value,
    execute_command,
)
from tests.remote_fakes import FakeApplication, FakeSong


def test_transport_helper_reads_the_real_attribute_and_retries() -> None:
    song = FakeSong(stuck_writes=2)
    sleeps: list[float] = []
    actual = _set_transport_value(
        song,
        "current_song_time",
        8.0,
        retries=3,
        sleep_fn=sleeps.append,
    )
    assert actual == 8.0
    assert song.transport_write_attempts == 3
    assert sleeps == [0.01, 0.01]
    assert song.clip_trigger_quantization == "quarter"


def test_transport_helper_raises_after_verified_failure_and_restores_quantization() -> None:
    song = FakeSong(stuck_writes=99)
    with pytest.raises(PlayheadNotMovedError) as exc_info:
        _set_transport_value(song, "current_song_time", 8.0, sleep_fn=lambda _: None)
    assert exc_info.value.code == "PLAYHEAD_NOT_MOVED"
    assert song.transport_write_attempts == 3
    assert song.clip_trigger_quantization == "quarter"


def test_all_transport_mutations_return_observed_values() -> None:
    song = FakeSong()
    app = FakeApplication()
    assert execute_command(song, app, "set_current_song_time", {"time": 12.0}) == {
        "current_song_time": 12.0
    }
    assert execute_command(song, app, "set_loop_start", {"start_beat": 4.0}) == {"loop_start": 4.0}
    assert execute_command(song, app, "set_loop_length", {"length_beats": 8.0}) == {
        "loop_length": 8.0
    }
