from __future__ import annotations

from typing import Any

import pytest

from AbletonMCPServer_RemoteScript import _command_steps


class FakeParameter:
    def __init__(self, value: float = 0.85, lo: float = 0.0, hi: float = 1.0) -> None:
        self.value = value
        self.min = lo
        self.max = hi

    def str_for_value(self, value: float) -> str:  # noqa: ARG002 — Live API
        return f"{value:.3f}"


class FakeMixer:
    def __init__(self, value: float) -> None:
        self.volume = FakeParameter(value=value)


class FakeTrack:
    def __init__(self, value: float = 0.85) -> None:
        self.name = "Test"
        self.mixer_device = FakeMixer(value)


class FakeSong:
    def __init__(self, value: float = 0.85) -> None:
        self.tracks = [FakeTrack(value)]


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, float]:
    state: dict[str, float] = {"t": 1000.0}
    monkeypatch.setattr(
        "AbletonMCPServer_RemoteScript.time.monotonic",
        lambda: state["t"],
    )
    return state


def _drive_until_done(
    gen: Any,
    clock: dict[str, float],
    *,
    tick: float = 0.005,
    max_seconds: float = 120.0,
) -> dict[str, Any]:
    """Drive a generator to completion advancing a virtual clock."""
    elapsed = 0.0
    while elapsed <= max_seconds:
        try:
            gen.send(None)
        except StopIteration as stop:
            return stop.value
        clock["t"] += tick
        elapsed += tick
    raise AssertionError(
        f"live_fade_steps did not complete within {max_seconds}s of virtual time"
    )


def test_live_fade_duration_zero_is_immediate(clock: dict[str, float]) -> None:
    """``duration=0`` must skip per-step waits and finish in one tick."""
    song = FakeSong()
    gen = _command_steps(
        song,
        None,
        "live_fade",
        {
            "track_index": 0,
            "target_percent": 50.0,
            "duration": 0.0,
            "steps": 10,
        },
        manage_undo=False,
        undo_target=song,
    )
    assert gen is not None
    # First send should already produce the final value (or at least make
    # significant progress) without requiring the clock to advance.
    try:
        gen.send(None)
    except StopIteration as stop:
        result = stop.value
    else:
        # If it yields, drive with very tiny ticks — must finish fast.
        result = _drive_until_done(gen, clock, tick=0.001, max_seconds=0.05)
    assert result["duration"] == 0.0


def test_live_fade_duration_one_second_spans_one_second_of_clock(
    clock: dict[str, float],
) -> None:
    """Steps must span ``duration`` of wall-clock time, not the tick count.

    With ``duration=1.0`` and ``steps=4``, each step should land ~250 ms
    apart on the monotonic clock. The test driver advances the clock by
    10 ms per Live tick; the generator must read ``time.monotonic()`` and
    only yield once the next step's deadline is reached.
    """
    song = FakeSong()
    start_clock = clock["t"]
    gen = _command_steps(
        song,
        None,
        "live_fade",
        {
            "track_index": 0,
            "target_percent": 0.0,
            "duration": 1.0,
            "steps": 4,
        },
        manage_undo=False,
        undo_target=song,
    )
    assert gen is not None

    # Drive with very fine ticks. If the generator respects duration, it
    # will consume ~100 ticks before finishing. If it does not, it will
    # finish in ~5 ticks (one per step + driver overhead).
    tick = 0.01
    max_ticks = 500
    ticks_used = 0
    while ticks_used < max_ticks:
        try:
            gen.send(None)
        except StopIteration:
            break
        clock["t"] += tick
        ticks_used += 1
    else:
        raise AssertionError("live_fade_steps did not finish")

    elapsed = clock["t"] - start_clock
    # Must span close to the full duration. Allow generous tolerance for
    # the discrete step boundaries.
    assert elapsed >= 0.5, (
        f"live_fade_steps ignored duration: finished after only {elapsed:.3f}s "
        f"of clock time but duration=1.0 was requested"
    )
    assert elapsed <= 2.0, (
        f"live_fade_steps overshot duration: took {elapsed:.3f}s for duration=1.0"
    )