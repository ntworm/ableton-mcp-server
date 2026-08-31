"""Deterministic HVO, feature, and grammar projections over lossless events."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from fractions import Fraction
from statistics import mean, pstdev

from .canonical import canonical_json
from .drum_roles import GM_DRUM_ROLE_BY_PITCH, GM_DRUM_ROLES
from .articulation import resolve_role
from .midi_lossless import ParsedSmfV1
from .schema import (
    FeaturesProjectionV1,
    FeatureValueV1,
    GrammarProjectionV1,
    HvoCellV1,
    HvoProjectionV1,
    NoteEventV1,
)

CANONICAL_PPQ = 480
GRID_TICKS = CANONICAL_PPQ // 4
ROLE_BY_PITCH = GM_DRUM_ROLE_BY_PITCH
ROLES = GM_DRUM_ROLES


def _role(pitch: int) -> str:
    return ROLE_BY_PITCH.get(pitch, "other_percussion")


def _round_fraction(value: Fraction) -> int:
    """Round an exact musical tick value to the nearest canonical tick."""

    return int(round(float(value)))


def _round_grid_index(value: Fraction) -> int:
    """Round a non-negative source-grid position, preserving half-up ties."""

    whole, remainder = divmod(value.numerator, value.denominator)
    if remainder * 2 >= value.denominator:
        whole += 1
    return whole


def _meter(parsed: ParsedSmfV1) -> tuple[int, int]:
    if parsed.meters:
        meter = min(
            parsed.meters,
            key=lambda item: (item["absolute_ticks"], item["track_index"]),
        )
        return meter["numerator"], meter["denominator_power"]
    return 4, 2


def _bar_ticks(parsed: ParsedSmfV1) -> Fraction:
    numerator, denominator_power = _meter(parsed)
    return max(
        Fraction(1, 1),
        Fraction(int(parsed.format.ppq) * numerator * 4, 2**denominator_power),
    )


def _canonical_ticks(parsed: ParsedSmfV1, ticks: int) -> int:
    return _round_fraction(Fraction(ticks * CANONICAL_PPQ, int(parsed.format.ppq)))


def _grid_position(parsed: ParsedSmfV1, absolute_ticks: int) -> tuple[int, int, int]:
    bar_ticks = _bar_ticks(parsed)
    source_grid_ticks = Fraction(int(parsed.format.ppq), 4)
    bar = int(Fraction(absolute_ticks, 1) // bar_ticks)
    within_bar = Fraction(absolute_ticks, 1) - bar * bar_ticks
    step = _round_grid_index(within_bar / source_grid_ticks)
    steps_per_bar = max(1, int(bar_ticks / source_grid_ticks))
    if step >= steps_per_bar:
        bar += 1
        step = 0
    nearest = bar * bar_ticks + step * source_grid_ticks
    return bar, step, _round_fraction(
        (Fraction(absolute_ticks, 1) - nearest) * CANONICAL_PPQ / int(parsed.format.ppq)
    )


def derive_hvo(parsed: ParsedSmfV1) -> HvoProjectionV1:
    grouped: dict[tuple[str, int, int], list[tuple[NoteEventV1, int]]] = defaultdict(list)
    for note in parsed.note_events:
        bar, step, offset = _grid_position(parsed, note.start_ticks)
        grouped[(_role(note.pitch), bar, step)].append((note, offset))
    cells: list[HvoCellV1] = []
    for (role, bar, step), values in sorted(grouped.items(), key=lambda item: item[0]):
        cells.append(
            HvoCellV1(
                role=role,
                bar=bar,
                step=step,
                hit=1,
                velocity=round(mean(note.velocity / 127 for note, _offset in values), 9),
                offset_ticks=round(mean(offset for _note, offset in values)),
                event_ids=[note.event_id for note, _offset in values],
            )
        )
    return HvoProjectionV1(
        grid_ticks=GRID_TICKS,
        roles=ROLES,
        cells=cells,
        source_events_digest=parsed.source_events_digest,
    )


def _available(value: float | int | str, unit: str = "") -> FeatureValueV1:
    return FeatureValueV1(value=value, unit=unit, status="available")


def _unavailable(unit: str = "") -> FeatureValueV1:
    return FeatureValueV1(value=None, unit=unit, status="unavailable")


def derive_features(parsed: ParsedSmfV1, hvo: HvoProjectionV1) -> FeaturesProjectionV1:
    bar_ticks = _bar_ticks(parsed)
    bars = max(1, math.ceil(float(Fraction(max(parsed.length_ticks, 1), 1) / bar_ticks)))
    numerator, denominator_power = _meter(parsed)
    meter = f"{numerator}/{2**denominator_power}"
    beats_per_bar = bar_ticks / int(parsed.format.ppq)
    beats = bars * beats_per_bar
    beat_value: float | int = (
        int(beats) if beats.denominator == 1 else float(beats)
    )
    velocities = [note.velocity / 127 for note in parsed.note_events]
    offsets = [cell.offset_ticks for cell in hvo.cells]
    role_counts = Counter(cell.role for cell in hvo.cells)
    values: dict[str, FeatureValueV1] = {
        "bars": _available(bars, "bars"),
        "beats": _available(beat_value, "beats"),
        "meter": _available(meter, "meter"),
        "ppq": _available(parsed.format.ppq, "ticks_per_quarter"),
        "hits_per_bar": _available(len(parsed.note_events) / bars, "hits/bar"),
        "roles_present": _available(len(role_counts), "roles"),
        "velocity_mean": _available(round(mean(velocities), 9), "normalized_velocity")
        if velocities
        else _unavailable("normalized_velocity"),
        "velocity_std": _available(round(pstdev(velocities), 9), "normalized_velocity")
        if len(velocities) > 1
        else _unavailable("normalized_velocity"),
        "offset_mean": _available(round(mean(offsets), 9), "ticks")
        if offsets
        else _unavailable("ticks"),
        "offset_std": _available(round(pstdev(offsets), 9), "ticks")
        if len(offsets) > 1
        else _unavailable("ticks"),
        "tempo_min": _unavailable("bpm"),
        "tempo_max": _unavailable("bpm"),
    }
    if parsed.tempos:
        bpms = [
            60_000_000 / tempo["microseconds"]
            for tempo in parsed.tempos
            if tempo["microseconds"] > 0
        ]
        if bpms:
            values["tempo_min"] = _available(round(min(bpms), 9), "bpm")
            values["tempo_max"] = _available(round(max(bpms), 9), "bpm")
    return FeaturesProjectionV1(values=values, source_events_digest=parsed.source_events_digest)


def derive_grammar(parsed: ParsedSmfV1, hvo: HvoProjectionV1) -> GrammarProjectionV1:
    by_id = {note.event_id: note for note in parsed.note_events}
    tokens: list[dict[str, int | str]] = []
    for cell in hvo.cells:
        for event_id in cell.event_ids:
            note = by_id[event_id]
            tokens.append(
                {
                    "role": cell.role,
                    "grid_step": cell.step,
                    "velocity_bin": min(7, int(note.velocity * 8 / 128)),
                    "offset_bin": max(-8, min(8, int(round(cell.offset_ticks / 15)))),
                    "duration_bin": min(15, _canonical_ticks(parsed, note.duration_ticks) // 30),
                    "event_id": event_id,
                }
            )
    tokens.sort(
        key=lambda token: (
            int(token["grid_step"]),
            str(token["role"]),
            int(token["event_id"]),
        )
    )
    counts: Counter[tuple[str, str]] = Counter()
    for first, second in zip(tokens, tokens[1:], strict=False):
        keys = ("role", "grid_step", "velocity_bin", "offset_bin", "duration_bin")
        left = canonical_json({key: first[key] for key in keys}).decode()
        right = canonical_json({key: second[key] for key in keys}).decode()
        counts[(left, right)] += 1
    transitions = [
        {
            "from": left,
            "to": right,
            "count": count,
            "probability": round(
                (count + 1) / (sum(counts.values()) + len(counts)),
                9,
            ),
        }
        for (left, right), count in sorted(counts.items())
    ]
    return GrammarProjectionV1(
        tokens=tokens,
        transitions=transitions,
        source_events_digest=parsed.source_events_digest,
    )

def derive_hvo_v3(parsed: ParsedSmfV1, stratum: str) -> HvoProjectionV1:
    grouped: dict[tuple[str, int, int], list[tuple[NoteEventV1, int]]] = defaultdict(list)
    for note in parsed.note_events:
        bar, step, offset = _grid_position(parsed, note.start_ticks)
        grouped[(resolve_role(stratum, note.pitch), bar, step)].append((note, offset))
    cells: list[HvoCellV1] = []
    for (role, bar, step), values in sorted(grouped.items(), key=lambda item: item[0]):
        cells.append(
            HvoCellV1(
                role=role,
                bar=bar,
                step=step,
                hit=1,
                velocity=round(mean(note.velocity / 127 for note, _offset in values), 9),
                offset_ticks=round(mean(offset for _note, offset in values)),
                event_ids=[note.event_id for note, _offset in values],
            )
        )
    return HvoProjectionV1(
        grid_ticks=GRID_TICKS,
        roles=ROLES,
        cells=cells,
        source_events_digest=parsed.source_events_digest,
    )
