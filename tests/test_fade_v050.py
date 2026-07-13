"""v0.5.0 live_fade generator and request model tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ableton_mcp_server import models
from AbletonMCPServer_RemoteScript import RemoteError, execute_command
from tests.remote_fakes import FakeApplication, FakeParameter, FakeSong, FakeTrack


def _make_fake_song_with_track(*, volume: float, min: float, max: float) -> FakeSong:
    """Construct a ``FakeSong`` whose only track has the given volume/min/max.

    The shared ``FakeSong`` constructor does not accept a ``tracks=`` kwarg, so
    we replace the default ``tracks`` list with a single track whose
    ``mixer_device.volume`` mirrors the live_fade fixtures described in the plan.
    """

    track = FakeTrack("Fade Target")
    track.mixer_device.volume = FakeParameter("Volume", volume, minimum=min, maximum=max)
    song = FakeSong()
    song.tracks = [track]
    song.scenes[0].clip_slots = [track.clip_slots[0]]
    return song


def test_live_fade_smoothstep_interpolates_within_min_max() -> None:
    song = _make_fake_song_with_track(volume=0.0, min=0.0, max=0.85)
    result = execute_command(
        song,
        FakeApplication(),
        "live_fade",
        {
            "track_index": 0,
            "target_percent": 100,
            "duration": 0,
            "steps": 4,
            "curve": "smoothstep",
        },
    )

    assert result["curve"] == "smoothstep"
    assert result["steps"] == 4
    assert 0.7 <= result["final_value"] <= 0.85


def test_live_fade_rejects_target_percent_above_unity_without_flag() -> None:
    song = _make_fake_song_with_track(volume=0.0, min=0.0, max=1.0)

    with pytest.raises(RemoteError) as error:
        execute_command(
            song,
            FakeApplication(),
            "live_fade",
            {
                "track_index": 0,
                "target_percent": 120,
                "duration": 0,
            },
        )

    assert error.value.code == "INVALID_PARAMS"
    assert "unity" in str(error.value).lower()


def test_live_fade_rejects_duration_above_max() -> None:
    song = _make_fake_song_with_track(volume=0.0, min=0.0, max=1.0)

    with pytest.raises(RemoteError) as error:
        execute_command(
            song,
            FakeApplication(),
            "live_fade",
            {
                "track_index": 0,
                "target_percent": 50,
                "duration": 90,
            },
        )

    assert error.value.code == "INVALID_PARAMS"


def test_live_fade_rejects_invalid_curve() -> None:
    song = _make_fake_song_with_track(volume=0.0, min=0.0, max=1.0)

    with pytest.raises(RemoteError) as error:
        execute_command(
            song,
            FakeApplication(),
            "live_fade",
            {
                "track_index": 0,
                "target_percent": 50,
                "duration": 0,
                "curve": "gibberish",
            },
        )

    assert error.value.code == "INVALID_PARAMS"


def test_live_fade_model_rejects_both_target_percent_and_value() -> None:
    with pytest.raises(ValidationError):
        models.LiveFadeRequest(
            track_index=0,
            target_percent=50,
            target_value=0.5,
            duration=0,
        )
