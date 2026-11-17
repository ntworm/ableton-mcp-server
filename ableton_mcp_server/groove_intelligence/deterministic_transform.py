"""Deterministic note transforms and projections of the offline groove generator."""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from . import GrooveMidiError
from .canonical import canonical_json, sha256_hex
from .constants import (
    FEATURES_SCHEMA_VERSION,
    GRAMMAR_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION_V3,
)
from .drum_roles import GM_DRUM_ROLE_BY_PITCH, GM_DRUM_ROLES
from .midi_lossless import ParsedSmfV1, serialize_note_smf
from .projections import (
    CANONICAL_PPQ,
    derive_features,
    derive_grammar,
    derive_hvo,
    derive_hvo_v3,
)
from .runtime import GrooveRuntime
from .schema import MidiArtifactV1, NoteEventV1, ProjectionRefV1


@dataclass(frozen=True)
class _MusicalNote:
    track_index: int
    channel: int
    pitch: int
    velocity: int
    start_ticks: int
    duration_ticks: int
    source_order: int


_PITCH_BY_DRUM_ROLE: dict[str, int] = {
    role: min(
        pitch for pitch, mapped_role in GM_DRUM_ROLE_BY_PITCH.items() if mapped_role == role
    )
    for role in GM_DRUM_ROLES
}
_DRUM_ROLE_ALIASES = {
    "closed_hat": "hat_closed",
    "open_hat": "hat_open",
    "other": "other_percussion",
}


def _pitch_for_drum_role(role: object) -> int:
    canonical_role = _DRUM_ROLE_ALIASES.get(str(role), str(role))
    return _PITCH_BY_DRUM_ROLE.get(
        canonical_role, _PITCH_BY_DRUM_ROLE["other_percussion"]
    )


def _bar_ticks(ppq: int, meter: tuple[int, int]) -> int:
    numerator, denominator_power = meter
    value = Fraction(ppq * numerator * 4, 2**denominator_power)
    return max(1, int(value))


def _initial_notes(
    parsed: tuple[ParsedSmfV1, ...],
    *,
    bars: int,
    ppq: int,
    meter: tuple[int, int],
) -> list[_MusicalNote]:
    bar_ticks = _bar_ticks(ppq, meter)
    length_ticks = bar_ticks * bars
    notes: list[_MusicalNote] = []
    order = 0
    for parent_index, source in enumerate(parsed):
        source_notes = source.note_events
        if not source_notes:
            source_notes = [
                NoteEventV1(
                    event_id=0,
                    track_index=1,
                    channel=9,
                    pitch=36,
                    velocity=80,
                    start_ticks=0,
                    duration_ticks=max(1, ppq // 4),
                )
            ]
        for bar in range(bars):
            for source_note in source_notes:
                start = bar * bar_ticks + (source_note.start_ticks % bar_ticks)
                if start >= length_ticks:
                    continue
                duration = max(1, min(source_note.duration_ticks, length_ticks - start))
                notes.append(
                    _MusicalNote(
                        track_index=parent_index + 1,
                        channel=source_note.channel,
                        pitch=source_note.pitch,
                        velocity=source_note.velocity,
                        start_ticks=start,
                        duration_ticks=duration,
                        source_order=order,
                    )
                )
                order += 1
    return notes


# Above this, a note reads as an accent rather than a ghost or a filler hit.
# The polyrhythm axis moves accents only, so the straight grid stays audible
# underneath the shifted one.
_ACCENT_VELOCITY = 80


def _replace(note: _MusicalNote, **updates: int) -> _MusicalNote:
    values = {
        "track_index": note.track_index,
        "channel": note.channel,
        "pitch": note.pitch,
        "velocity": note.velocity,
        "start_ticks": note.start_ticks,
        "duration_ticks": note.duration_ticks,
        "source_order": note.source_order,
    }
    values.update(updates)
    return _MusicalNote(**values)


def _clamp_note(note: _MusicalNote, *, length_ticks: int) -> _MusicalNote:
    start = max(0, min(max(0, length_ticks - 1), note.start_ticks))
    duration = max(1, min(note.duration_ticks, max(1, length_ticks - start)))
    return _replace(
        note,
        pitch=max(0, min(127, note.pitch)),
        velocity=max(1, min(127, note.velocity)),
        channel=max(0, min(15, note.channel)),
        start_ticks=start,
        duration_ticks=duration,
    )


def _transform_notes(
    notes: list[_MusicalNote],
    transforms: Mapping[str, float],
    *,
    seed: int,
    ppq: int,
    meter: tuple[int, int],
    length_ticks: int,
) -> list[_MusicalNote]:
    result = list(notes)
    seed_variation = seed % 5 - 2
    if seed_variation:
        result = [_replace(note, velocity=note.velocity + seed_variation) for note in result]
    result = _apply_density(result, transforms, ppq=ppq, seed=seed)
    result = _apply_energy(result, transforms)
    result = _apply_microtiming(result, transforms, ppq=ppq)
    result = _apply_swing(result, transforms, ppq=ppq)
    result = _apply_syncopation(result, transforms, ppq=ppq, bar_ticks=_bar_ticks(ppq, meter))
    result = _apply_polyrhythm(result, transforms, ppq=ppq, seed=seed)
    result = _apply_complexity(result, transforms, ppq=ppq)
    return [
        _clamp_note(note, length_ticks=length_ticks)
        for note in sorted(
            result,
            key=lambda item: (item.track_index, item.start_ticks, item.pitch, item.source_order),
        )
    ]


def _apply_density(
    notes: list[_MusicalNote],
    transforms: Mapping[str, float],
    *,
    ppq: int,
    seed: int,
) -> list[_MusicalNote]:
    """Add, thin or shorten the notes of a density transform."""
    density = float(transforms.get("density", 0.0))
    result = notes
    if density > 0.0 and result:
        extra = max(1, int(round(len(result) * 0.5 * density)))
        for index in range(extra):
            source = result[index % len(result)]
            offset = max(1, round(ppq / 8)) * (index + 1)
            result.append(
                _replace(
                    source,
                    velocity=max(1, source.velocity - 1),
                    start_ticks=source.start_ticks + offset,
                    source_order=len(result),
                )
            )
    elif density < 0.0 and len(result) > 1:
        rng = random.Random(seed)
        keep = max(1, int(round(len(result) * (1.0 + density * 0.5))))
        result = sorted(result, key=lambda note: (rng.random(), note.source_order))[:keep]
    # A density transform remains observable for a one-hit source by shortening
    # its note; positive density already changes the event count.
    if density < 0.0:
        shortened = []
        for note in result:
            duration = max(1, round(note.duration_ticks * (1 + density * 0.25)))
            density_velocity = note.velocity - 1 if note.velocity > 1 else note.velocity + 2
            shortened.append(
                _replace(
                    note,
                    duration_ticks=duration,
                    velocity=(
                        density_velocity
                        if duration == note.duration_ticks
                        else note.velocity
                    ),
                )
            )
        result = shortened
    return result


def _apply_energy(
    notes: list[_MusicalNote],
    transforms: Mapping[str, float],
) -> list[_MusicalNote]:
    """Shift every velocity of an energy transform."""
    energy = float(transforms.get("energy", 0.0))
    if not energy:
        return notes
    delta = max(1, round(abs(energy) * 16))
    energized = []
    for note in notes:
        direction = 1 if energy > 0 else -1
        velocity = note.velocity + direction * delta
        if velocity == note.velocity or velocity < 1 or velocity > 127:
            velocity = note.velocity - direction * delta
        energized.append(_replace(note, velocity=velocity))
    return energized


def _apply_microtiming(
    notes: list[_MusicalNote],
    transforms: Mapping[str, float],
    *,
    ppq: int,
) -> list[_MusicalNote]:
    """Shift the note starts of a microtiming transform."""
    microtiming = float(transforms.get("microtiming", 0.0))
    if not microtiming:
        return notes
    amount = max(1, round(abs(microtiming) * ppq / 32))
    direction = 1 if microtiming > 0 else -1
    return [
        _replace(
            note,
            start_ticks=note.start_ticks
            + (amount * direction if note.start_ticks != 0 or direction > 0 else 0),
        )
        for note in notes
    ]


def _apply_swing(
    notes: list[_MusicalNote],
    transforms: Mapping[str, float],
    *,
    ppq: int,
) -> list[_MusicalNote]:
    """Shift the off-beat note starts of a swing transform."""
    swing = float(transforms.get("swing", 0.0))
    if not swing:
        return notes
    amount = max(1, round(abs(swing) * ppq / 16))
    eighth = max(1, ppq // 2)
    direction = 1 if swing > 0 else -1
    return [
        _replace(
            note,
            start_ticks=note.start_ticks
            + (
                amount * direction
                if (note.start_ticks // eighth) % 2 or (note.start_ticks == 0 and direction > 0)
                else 0
            ),
        )
        for note in notes
    ]


def _apply_syncopation(
    notes: list[_MusicalNote],
    transforms: Mapping[str, float],
    *,
    ppq: int,
    bar_ticks: int,
) -> list[_MusicalNote]:
    """Shift the notes that start on a bar of a syncopation transform."""
    syncopation = float(transforms.get("syncopation", 0.0))
    if not syncopation:
        return notes
    amount = max(1, round(abs(syncopation) * ppq / 8))
    direction = 1 if syncopation > 0 else -1
    return [
        _replace(
            note,
            start_ticks=note.start_ticks
            + (amount * direction if note.start_ticks % bar_ticks == 0 else 0),
        )
        for note in notes
    ]


def _apply_polyrhythm(
    notes: list[_MusicalNote],
    transforms: Mapping[str, float],
    *,
    ppq: int,
    seed: int,
) -> list[_MusicalNote]:
    """Move the accented notes onto the triplet grid of a polyrhythm transform."""
    polyrhythm = float(transforms.get("polyrhythm", 0.0))
    if not polyrhythm:
        return notes
    # A 3-over-4 feel: the accented notes move onto the triplet grid while
    # the rest hold the straight one, which is what makes the two grids
    # audible at once. ``round(ppq / 3)`` is the triplet; the intensity
    # decides how many accents move, not how far.
    poly_shift = max(1, round(ppq / 3)) * (1 if polyrhythm > 0 else -1)
    # A dedicated stream. Drawing from the shared rng would make enabling
    # this axis silently change what a negative density transform selects.
    poly_rng = random.Random(seed ^ 0x504F4C59)
    return [
        _replace(
            note,
            start_ticks=max(0, note.start_ticks + poly_shift)
            if note.velocity > _ACCENT_VELOCITY and poly_rng.random() < abs(polyrhythm)
            else note.start_ticks,
        )
        for note in notes
    ]


def _apply_complexity(
    notes: list[_MusicalNote],
    transforms: Mapping[str, float],
    *,
    ppq: int,
) -> list[_MusicalNote]:
    """Shift the pitch and the duration of a complexity transform."""
    complexity = float(transforms.get("complexity", 0.0))
    if not complexity:
        return notes
    shift = 1 if complexity > 0 else -1
    duration_delta = max(1, round(abs(complexity) * ppq / 16))
    return [
        _replace(
            note,
            pitch=(note.pitch + shift if 0 < note.pitch + shift < 127 else note.pitch - shift),
            duration_ticks=note.duration_ticks
            + (duration_delta if complexity > 0 else -duration_delta),
        )
        for note in notes
    ]


def _projection_values(
    parsed: ParsedSmfV1,
) -> tuple[
    tuple[ProjectionRefV1, ...],
    dict[str, Any],
    dict[str, object],
    dict[str, float | int | str | None],
]:
    hvo = derive_hvo(parsed)
    # No vendor library stands behind a generated groove, so v3 resolves through
    # General MIDI here.  It is emitted anyway so a generated artifact carries the
    # same projection set as a corpus one.
    hvo_v3 = derive_hvo_v3(parsed, "")
    features = derive_features(parsed, hvo)
    grammar = derive_grammar(parsed, hvo)
    values = {
        HVO_SCHEMA_VERSION: hvo.model_dump(mode="json"),
        HVO_SCHEMA_VERSION_V3: hvo_v3.model_dump(mode="json"),
        FEATURES_SCHEMA_VERSION: features.model_dump(mode="json"),
        GRAMMAR_SCHEMA_VERSION: grammar.model_dump(mode="json"),
    }
    refs = tuple(
        ProjectionRefV1(
            name=name,
            version=version,
            digest=sha256_hex(canonical_json(values[version])),
        )
        for name, version in (
            ("hvo", HVO_SCHEMA_VERSION),
            ("hvo_v3", HVO_SCHEMA_VERSION_V3),
            ("features", FEATURES_SCHEMA_VERSION),
            ("grammar", GRAMMAR_SCHEMA_VERSION),
        )
    )
    summary: dict[str, object] = {
        "bars": features.values["bars"].value,
        "meter": features.values["meter"].value,
        "roles": sorted({cell.role for cell in hvo.cells}),
        "generator": "groove-deterministic-v2",
    }
    feature_values = {name: value.value for name, value in features.values.items()}
    return refs, values, summary, feature_values


def _projected_parent(runtime: GrooveRuntime, parent: MidiArtifactV1, parent_id: str) -> bytes:
    """Materialize a rights-safe parent whose raw payload is intentionally withheld."""

    try:
        hvo = runtime.index.load_projection(parent_id, HVO_SCHEMA_VERSION).model_dump(mode="json")
        features = runtime.index.load_projection(
            parent_id, FEATURES_SCHEMA_VERSION
        ).model_dump(mode="json")
    except (AttributeError, KeyError, ValueError) as error:
        raise GrooveMidiError(
            "parent MIDI payload is empty and projections are unavailable"
        ) from error
    values = features.get("values", {})
    ppq_value = values.get("ppq", {}).get("value", parent.format.ppq)
    ppq = int(ppq_value) if isinstance(ppq_value, (int, float)) else parent.format.ppq
    meter_text = values.get("meter", {}).get("value", "4/4")
    try:
        numerator_text, denominator_text = str(meter_text).split("/", 1)
        numerator, denominator = int(numerator_text), int(denominator_text)
        denominator_power = denominator.bit_length() - 1
    except (ValueError, TypeError):
        numerator, denominator_power = 4, 2
    bar_ticks = _bar_ticks(ppq, (numerator, denominator_power))
    native_grid_ticks = round(int(hvo.get("grid_ticks", 120)) * ppq / CANONICAL_PPQ)
    notes: list[NoteEventV1] = []
    for index, cell in enumerate(hvo.get("cells", [])):
        if not isinstance(cell, Mapping):
            continue
        velocity = max(1, min(127, round(float(cell.get("velocity", 0.5)) * 127)))
        notes.append(
            NoteEventV1(
                event_id=index,
                track_index=1,
                channel=9,
                pitch=_pitch_for_drum_role(cell.get("role", "other_percussion")),
                velocity=velocity,
                start_ticks=max(
                    0,
                    int(cell.get("bar", 0)) * bar_ticks
                    + int(cell.get("step", 0)) * native_grid_ticks
                    + round(int(cell.get("offset_ticks", 0)) * ppq / CANONICAL_PPQ),
                ),
                duration_ticks=max(1, ppq // 8),
            )
        )
    bars_value = values.get("bars", {}).get("value", 1)
    bars = max(1, int(bars_value)) if isinstance(bars_value, (int, float)) else 1
    return serialize_note_smf(
        notes,
        ppq=ppq,
        length_ticks=bar_ticks * bars,
        meter=(numerator, denominator_power),
        track_names={1: "Projected parent"},
    )
