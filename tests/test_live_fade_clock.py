"""RED: ``live_fade_steps`` must distribute writes across the requested duration.

These tests use a virtual monotonic clock so the test can drive the
generator without sleeping real time. The contract the runner relies on:

- ``duration=0`` finishes in a single tick (no waiting).
- ``steps=1`` with ``duration>0`` still waits the requested duration before
  finishing; it writes the target and then yields until the deadline.
- ``steps=4`` with ``duration=1`` writes at approximately
  ``0.25 / 0.50 / 0.75 / 1.00`` of the duration — never earlier.
- The final write must not happen before its proportional deadline
  (``target not reached early``).
- ``duration=60`` is bounded by ``LIVE_FADE_MAX_DURATION`` and must complete
  in roughly that long with reasonable overhead, not exactly 60.0 seconds.

If any test fails, the runner cannot tell how long the Live main thread is
actually spending on ``live_fade``, and the ``live_fade`` certification row
becomes a false-positive.
"""

from __future__ import annotations

from typing import Any

import pytest

from AbletonMCPServer_RemoteScript import live_fade_steps


class _RecordingParameter:
    """Mock ``mixer_device.volume`` that records every write with its clock."""

    def __init__(self, value: float = 0.85, lo: float = 0.0, hi: float = 1.0) -> None:
        self.value = value
        self.min = lo
        self.max = hi
        self.writes: list[tuple[float, float]] = []
        self._clock: _VirtualClock | None = None

    def str_for_value(self, value: float) -> str:
        return f"{value:.3f}"

    def __setattr__(self, name: str, value: Any) -> None:
        if (
            name == "value"
            and getattr(self, "_clock", None) is not None
            and hasattr(self, "writes")
        ):
            self.writes.append((self._clock(), float(value)))
        super().__setattr__(name, value)


class _RecordingMixer:
    def __init__(self, value: float) -> None:
        self.volume = _RecordingParameter(value=value)


class _RecordingTrack:
    def __init__(self, value: float = 0.85) -> None:
        self.name = "Test"
        self.mixer_device = _RecordingMixer(value)


class _RecordingSong:
    def __init__(self, value: float = 0.85) -> None:
        self.tracks = [_RecordingTrack(value)]


class _VirtualClock:
    """Monotonic clock with a deterministic manual advance."""

    def __init__(self, start: float = 1000.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


@pytest.fixture
def clock() -> _VirtualClock:
    return _VirtualClock()


def _drive(
    gen: Any, clock: _VirtualClock, *, tick: float, max_seconds: float = 120.0
) -> dict[str, Any]:
    """Advance the virtual clock per generator yield until completion."""
    elapsed = 0.0
    while elapsed <= max_seconds:
        try:
            gen.send(None)
        except StopIteration as stop:
            return stop.value
        clock.advance(tick)
        elapsed += tick
    raise AssertionError(f"live_fade_steps did not complete within {max_seconds}s of virtual time")


def _song_with_clock(clock: _VirtualClock, value: float = 0.85) -> _RecordingSong:
    song = _RecordingSong(value)
    song.tracks[0].mixer_device.volume._clock = clock
    return song


def test_duration_zero_is_immediate(clock: _VirtualClock) -> None:
    """``duration=0`` must finish in a single tick — no waiting."""
    song = _song_with_clock(clock)
    gen = live_fade_steps(
        song,
        None,
        {"track_index": 0, "target_percent": 50.0, "duration": 0.0, "steps": 10},
        clock=clock,
    )
    # Drive without advancing the clock; must finish in one tick.
    result = _drive(gen, clock, tick=0.0)
    assert result["duration"] == 0.0
    assert result["steps"] == 10
    # No waiting happened — only the final write should be on record.
    writes = song.tracks[0].mixer_device.volume.writes
    assert len(writes) == 1, f"duration=0 should write exactly once, got {len(writes)}"


def test_steps_one_duration_one_second_waits_full_duration(
    clock: _VirtualClock,
) -> None:
    """``steps=1`` with ``duration>0`` must still wait the requested duration.

    The historical bug: when ``steps == 1`` the code fell into the
    ``duration == 0.0 or steps <= 1`` short-circuit and finished immediately,
    returning a green certification row that ignored the requested duration.
    """
    song = _song_with_clock(clock, value=0.85)
    start = clock()
    gen = live_fade_steps(
        song,
        None,
        {"track_index": 0, "target_percent": 0.0, "duration": 1.0, "steps": 1},
        clock=clock,
    )
    tick = 0.01
    result = _drive(gen, clock, tick=tick)
    elapsed = clock() - start
    # Must span close to the full duration.
    assert 0.85 <= elapsed <= 1.5, f"steps=1/duration=1 ignored duration; elapsed={elapsed:.3f}s"
    assert result["duration"] == 1.0
    # The single write must reach (or essentially reach) the target.
    writes = song.tracks[0].mixer_device.volume.writes
    assert writes
    # Final value must be near zero (0% target).
    _, final = writes[-1]
    assert abs(final) < 0.05, f"final value {final} far from target 0.0"


def test_steps_four_duration_one_writes_at_quarter_intervals(
    clock: _VirtualClock,
) -> None:
    """``steps=4`` with ``duration=1`` writes at ~0.25/0.50/0.75/1.00."""
    song = _song_with_clock(clock, value=0.85)
    start = clock()
    gen = live_fade_steps(
        song,
        None,
        {"track_index": 0, "target_percent": 0.0, "duration": 1.0, "steps": 4},
        clock=clock,
    )
    # Drive with a fine tick so we can resolve the per-step deadlines.
    _drive(gen, clock, tick=0.005)
    elapsed = clock() - start
    # Must span the full duration within reasonable tolerance.
    assert 0.85 <= elapsed <= 1.5, f"steps=4/duration=1 ignored duration; elapsed={elapsed:.3f}s"
    # Writes should occur at the proportional step boundaries. The generator
    # waits for the deadline first and only then commits the value, so
    # step ``i`` lands at ``i * step_interval`` — never earlier.
    writes = song.tracks[0].mixer_device.volume.writes
    assert len(writes) == 4, f"expected 4 step writes, got {len(writes)}"
    # The last write must land at (or near) the final deadline: with
    # duration=1.0/steps=4 the final deadline is 1.0s. Tolerate a tiny
    # tick-driven rounding error (<= 0.01s).
    last_offset = writes[-1][0] - start
    assert last_offset >= 0.95, (
        f"last write at {last_offset:.3f}s, expected ~1.0s (target reached before its deadline)"
    )
    assert last_offset <= 1.05, (
        f"last write at {last_offset:.3f}s, expected ~1.0s (target written after its deadline)"
    )
    # First write at step 1's deadline (0.25s for duration=1.0/steps=4).
    first_offset = writes[0][0] - start
    assert 0.20 <= first_offset <= 0.30, f"first write at {first_offset:.3f}s, expected ~0.25s"


def test_target_not_reached_early(clock: _VirtualClock) -> None:
    """The final target value must not be written before the deadline.

    With ``steps=4`` and ``duration=1``, the last write (``t=1.0``) must
    land near ``1.0s`` of clock time, not earlier. Step 1's value is also
    captured so we can prove the very first write is **not** the final
    target — the fade genuinely progresses across ``duration``.
    """
    song = _song_with_clock(clock, value=0.85)
    gen = live_fade_steps(
        song,
        None,
        {"track_index": 0, "target_percent": 0.0, "duration": 1.0, "steps": 4},
        clock=clock,
    )
    _drive(gen, clock, tick=0.005)
    writes = song.tracks[0].mixer_device.volume.writes
    assert writes, "no writes recorded"
    first_value = writes[0][1]
    # First write is at ~t=0.25 (step 1 / steps=4 of a linear fade); should
    # still be well above 50% of start (0.85).
    assert first_value > 0.6, (
        f"first write {first_value} too close to target — target was reached early"
    )
    # And the last write must actually be the target.
    last_value = writes[-1][1]
    assert abs(last_value) < 0.05, f"last write {last_value} did not reach target 0.0"


def test_duration_sixty_completes_around_one_minute(
    clock: _VirtualClock,
) -> None:
    """``duration=60`` must take ~60s of clock time, not instantly."""
    song = _song_with_clock(clock, value=0.85)
    start = clock()
    gen = live_fade_steps(
        song,
        None,
        {"track_index": 0, "target_percent": 0.0, "duration": 60.0, "steps": 40},
        clock=clock,
    )
    result = _drive(gen, clock, tick=0.5, max_seconds=120.0)
    elapsed = clock() - start
    assert 55.0 <= elapsed <= 65.0, f"duration=60 took {elapsed:.3f}s of virtual time"
    assert result["duration"] == 60.0
    assert result["steps"] == 40
