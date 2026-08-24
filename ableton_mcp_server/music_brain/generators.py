"""Deterministic note generators."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

_BEATS_PER_BAR = 4.0

# General MIDI drum map, the subset this kit uses.
_KICK = 36
_SNARE = 38
_CLOSED_HAT = 42
_PEDAL_HAT = 44
_OPEN_HAT = 46

# Beats carrying the backbeat inside a bar, zero-indexed: "2 and 4".
_BACKBEAT = (1.0, 3.0)

# Hat grid step in beats, indexed by the electro level.
_HAT_STEPS = (1.0, 0.5, 0.25)


@dataclass(frozen=True, slots=True)
class Traits:
    """Four orthogonal axes, each owning exactly one verb.

    ``electro`` builds the grid, ``space`` subtracts from it, ``weirdness``
    deviates what survived and ``groove`` displaces it in time. No axis does
    two jobs, which is what keeps a combination such as
    ``Traits(groove=0.8, space=0.6)`` predictable instead of arbitrary.
    """

    groove: float = 0.0
    electro: float = 0.0
    weirdness: float = 0.0
    space: float = 0.0

    def electro_level(self) -> int:
        """Return the discrete grid level 0..2 that ``electro`` selects."""
        return min(int(self.electro * 3), len(_HAT_STEPS) - 1)


@dataclass(frozen=True, slots=True)
class Generation:
    """Generated notes plus the traits that actually changed them."""

    notes: list[dict[str, Any]]
    traits_applied: list[str] = field(default_factory=list)


def generate_drum_groove(
    *, bars: int, seed: int, traits: Traits | None = None
) -> Generation:
    """Return a drum groove that depends only on ``bars``, ``seed`` and traits."""
    traits = traits or Traits()
    rng = random.Random(seed)
    notes = _build_drums(bars=bars, rng=rng, traits=traits)
    return _run_pipeline(
        notes, rng=rng, traits=traits, bars=bars, ghost_pitch=_SNARE, root_midi=None
    )


def generate_bass(
    *, bars: int, seed: int, root_midi: int, traits: Traits | None = None
) -> Generation:
    """Return a root-only bass line.

    Every note is ``root_midi`` in some octave, so the line cannot imply a
    harmony the caller did not ask for.
    """
    traits = traits or Traits()
    rng = random.Random(seed)
    notes = _build_bass(bars=bars, rng=rng, root_midi=root_midi, traits=traits)
    return _run_pipeline(
        notes, rng=rng, traits=traits, bars=bars, ghost_pitch=None, root_midi=root_midi
    )


def _run_pipeline(
    notes: list[dict[str, Any]],
    *,
    rng: random.Random,
    traits: Traits,
    bars: int,
    ghost_pitch: int | None,
    root_midi: int | None,
) -> Generation:
    """Run the fixed trait pipeline and report which axes really moved.

    The order is part of the contract, not an implementation detail: build the
    grid, subtract from it, deviate what survived, then displace it in time.
    Any other order produces different notes for the same request.

    An axis is reported only when its stage changed the notes. A value too
    small to cross ``electro``'s grid threshold, or a ``space`` draw that
    happened to keep everything, does not get to claim credit.
    """
    applied: list[str] = []

    if traits.electro_level() > 0:
        applied.append("electro")

    _Stage = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
    stages: tuple[tuple[str, _Stage], ...] = (
        ("space", lambda current: _apply_space(current, rng=rng, space=traits.space)),
        (
            "weirdness",
            lambda current: _apply_weirdness(
                current,
                rng=rng,
                weirdness=traits.weirdness,
                bars=bars,
                ghost_pitch=ghost_pitch,
                root_midi=root_midi,
            ),
        ),
        (
            "groove",
            lambda current: _apply_groove(current, groove=traits.groove, bars=bars),
        ),
    )

    for name, stage in stages:
        moved = stage(notes)
        if moved != notes:
            applied.append(name)
        notes = moved

    return Generation(notes=notes, traits_applied=applied)


def _apply_space(
    notes: list[dict[str, Any]], *, rng: random.Random, space: float
) -> list[dict[str, Any]]:
    """Subtract notes and lengthen the survivors.

    ``space`` never invents anything. At full strength roughly 40% of the
    events survive and each lasts three times as long, which is what makes room
    for sustained material instead of just thinning the pattern out.
    """
    if space <= 0:
        return notes

    survival = 1.0 - space * 0.6
    stretch = 1.0 + space * 2.0
    kept = [
        {**note, "duration": float(note["duration"]) * stretch}
        for note in notes
        if rng.random() < survival
    ]
    # A pattern that survives as silence is not a musical result; keep the
    # densest bar's downbeat rather than hand back nothing.
    return kept or [dict(notes[0])]


def _apply_weirdness(
    notes: list[dict[str, Any]],
    *,
    rng: random.Random,
    weirdness: float,
    bars: int,
    ghost_pitch: int | None,
    root_midi: int | None,
) -> list[dict[str, Any]]:
    """Deviate what survived, inside hard limits.

    Three deviations, all bounded: ghost notes at a velocity that reads as
    texture rather than as a hit, timing jitter under a thirty-second note, and
    octave leaps that never leave the requested pitch class. Nothing here can
    push a note out of the requested bars or out of the MIDI range, which is
    what separates this from noise.
    """
    if weirdness <= 0:
        return notes

    limit = bars * _BEATS_PER_BAR
    jitter = weirdness * 0.05
    deviated: list[dict[str, Any]] = []

    for note in notes:
        start = float(note["start_time"]) + rng.uniform(-jitter, jitter)
        pitch = int(note["pitch"])
        if root_midi is not None and rng.random() < weirdness * 0.25:
            pitch = _fold_into_midi_range(pitch + rng.choice((-12, 12)))
        deviated.append(
            {**note, "start_time": _clamp(start, 0.0, limit), "pitch": pitch}
        )

    if ghost_pitch is not None:
        for bar in range(bars):
            for beat in range(4):
                if rng.random() >= weirdness * 0.3:
                    continue
                start = bar * _BEATS_PER_BAR + beat + 0.5
                deviated.append(
                    _note(ghost_pitch, _clamp(start, 0.0, limit), 0.1, rng.randrange(30, 46))
                )

    return deviated


def _apply_groove(
    notes: list[dict[str, Any]], *, groove: float, bars: int
) -> list[dict[str, Any]]:
    """Displace and accent, without touching the note set.

    Off-beat events are pushed late by up to a third of a beat, which lands on
    triplet swing at full strength, and whatever sits on the backbeat is
    accented. Nothing is added and nothing is removed, so ``groove`` composes
    cleanly with the three axes that do change the note set.

    Swing needs something off the grid to move: at ``electro`` zero the kit sits
    on quarter notes and only the accent is audible.
    """
    if groove <= 0:
        return notes

    limit = bars * _BEATS_PER_BAR
    swing = groove * 0.167
    accent = groove * 20.0
    swung: list[dict[str, Any]] = []

    for note in notes:
        start = float(note["start_time"])
        velocity = float(note["velocity"])
        if start % 1.0:
            start = _clamp(start + swing, 0.0, limit)
        if start % _BEATS_PER_BAR in _BACKBEAT:
            velocity += accent
        swung.append(
            {
                **note,
                "start_time": start,
                "velocity": int(_clamp(velocity, 1.0, 128.0)),
            }
        )

    return swung


def _clamp(value: float, low: float, high: float) -> float:
    """Keep ``value`` inside the half-open range the caller asked for."""
    return max(low, min(value, high - 1e-9))


def _build_drums(*, bars: int, rng: random.Random, traits: Traits) -> list[dict[str, Any]]:
    """Lay the kit over the grid ``electro`` selects."""
    level = traits.electro_level()
    hat_step = _HAT_STEPS[level]
    notes: list[dict[str, Any]] = []

    for bar in range(bars):
        bar_start = bar * _BEATS_PER_BAR

        for beat in range(4):
            notes.append(_note(_KICK, bar_start + beat, 0.25, 100))

        for backbeat in _BACKBEAT:
            notes.append(_note(_SNARE, bar_start + backbeat, 0.25, 105))

        step_count = int(_BEATS_PER_BAR / hat_step)
        for step in range(step_count):
            offset = step * hat_step
            notes.append(
                _note(
                    _hat_pitch(level=level, step=step, offset=offset),
                    bar_start + offset,
                    0.25,
                    rng.randrange(70, 95),
                )
            )

    return notes


def _hat_pitch(*, level: int, step: int, offset: float) -> int:
    """Pick the hat articulation for one grid step.

    Level 0 keeps the hat closed. Level 1 opens it on the off-beat. Level 2
    rotates closed, open and pedal so the machine grid stops sounding flat.
    """
    if level == 0:
        return _CLOSED_HAT
    if level == 1:
        return _OPEN_HAT if offset % 1.0 else _CLOSED_HAT
    return (_CLOSED_HAT, _OPEN_HAT, _CLOSED_HAT, _PEDAL_HAT)[step % 4]


def _build_bass(
    *, bars: int, rng: random.Random, root_midi: int, traits: Traits
) -> list[dict[str, Any]]:
    """Pulse the root at the rate ``electro`` selects."""
    level = traits.electro_level()
    notes: list[dict[str, Any]] = []

    for bar in range(bars):
        bar_start = bar * _BEATS_PER_BAR
        if level == 0:
            notes.append(_note(root_midi, bar_start, 1.0, 110))
            answer = bar_start + rng.choice((2.0, 2.5, 3.0))
            notes.append(_note(root_midi, answer, 0.5, rng.randrange(85, 105)))
            continue

        step = _HAT_STEPS[level]
        for index in range(int(_BEATS_PER_BAR / step)):
            notes.append(
                _note(root_midi, bar_start + index * step, step * 0.9, rng.randrange(85, 112))
            )

    return notes


def _note(pitch: int, start_time: float, duration: float, velocity: int) -> dict[str, Any]:
    return {
        "pitch": pitch,
        "start_time": float(start_time),
        "duration": duration,
        "velocity": velocity,
    }


def _fold_into_midi_range(pitch: int) -> int:
    """Move ``pitch`` by whole octaves until it fits in 0..127."""
    while pitch > 127:
        pitch -= 12
    while pitch < 0:
        pitch += 12
    return pitch
