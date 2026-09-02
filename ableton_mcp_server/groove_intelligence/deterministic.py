"""Seeded, offline deterministic musical artifact generation."""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from . import GrooveMidiError
from .canonical import artifact_id_from_identity, canonical_json, reproducibility_key, sha256_hex
from .cards import GenerationCardV1, artifact_card_from_artifact
from .constants import (
    FEATURES_SCHEMA_VERSION,
    GRAMMAR_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION_V3,
)
from .drum_roles import GM_DRUM_ROLE_BY_PITCH, GM_DRUM_ROLES
from .mcp_models import GenerateRequestV1, GenerationResponseV1
from .midi_lossless import (
    ParsedSmfV1,
    compress_bounded,
    decompress_bounded,
    parse_smf,
    serialize_note_smf,
)
from .projections import (
    CANONICAL_PPQ,
    derive_features,
    derive_grammar,
    derive_hvo,
    derive_hvo_v3,
)
from .runtime import GrooveRuntime
from .schema import ArtifactId, MidiArtifactV1, NoteEventV1, ProjectionRefV1

_GENERATION_EVENT_LIMIT = 2_048


class GrooveLimitExceeded(ValueError):
    """A generated artifact exceeds a bounded generation limit."""


class GrooveRightsRejected(PermissionError):
    """The parent rights lattice does not permit the requested operation."""


class GrooveParentIncompatible(ValueError):
    """Multiple parents cannot be recombined without changing their contract."""


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


def _source_id(runtime: GrooveRuntime, request: GenerateRequestV1) -> str:
    if request.source.artifact_id is not None:
        return str(request.source.artifact_id)
    assert request.source.search is not None
    from .mcp_models import SearchRequestV1
    from .search import search

    inline_payload = dict(request.source.search)
    inline_payload.setdefault("schema_version", "groove.search.request.v1")
    inline_payload["limit"] = 1
    inline_payload["cursor"] = None
    result = search(runtime, SearchRequestV1.model_validate(inline_payload))
    if not result.items:
        raise ValueError("inline search did not select an artifact")
    return str(result.items[0].artifact_id)


def _parent_ids(runtime: GrooveRuntime, request: GenerateRequestV1) -> tuple[str, ...]:
    source_id = _source_id(runtime, request)
    references = tuple(str(item) for item in request.reference_artifact_ids)
    parent_ids = (source_id, *references)
    if len(set(parent_ids)) != len(parent_ids):
        raise GrooveParentIncompatible("duplicate parent artifact_id")
    if len(parent_ids) > 8:
        raise GrooveLimitExceeded("generation accepts at most eight parents")
    return parent_ids


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


def _raw_parent(runtime: GrooveRuntime, parent: MidiArtifactV1, parent_id: str) -> ParsedSmfV1:
    if parent.payload.blob:
        raw = decompress_bounded(
            parent.payload.blob,
            codec=parent.payload.codec,
            raw_size=parent.payload.raw_size,
        )
    else:
        raw = _projected_parent(runtime, parent, parent_id)
    parsed = parse_smf(raw)
    # Index rows intentionally do not duplicate track_count, but PPQ is part
    # of the parent contract. Detect an edited/inconsistent derived record.
    if int(parent.format.ppq) != parsed.format.ppq:
        raise GrooveParentIncompatible("incompatible PPQ metadata")
    return parsed


def _meter(parsed: ParsedSmfV1) -> tuple[int, int]:
    if not parsed.meters:
        return 4, 2
    meter = min(parsed.meters, key=lambda item: (item["absolute_ticks"], item["track_index"]))
    return int(meter["numerator"]), int(meter["denominator_power"])


def _rights(parent: MidiArtifactV1) -> tuple[str, int]:
    redistribution = str(parent.provenance.get("redistribution", "derived_only"))
    defaults = {"blocked": 0, "derived_only": 1, "full": 2}
    if redistribution not in defaults:
        raise GrooveRightsRejected("incompatible rights metadata")
    level = int(parent.provenance.get("rights_level", defaults.get(redistribution, 0)))
    if redistribution == "blocked" or level < 1:
        raise GrooveRightsRejected("artifact rights do not allow generation")
    return redistribution, min(level, defaults[redistribution])


def _rights_meet(parents: tuple[MidiArtifactV1, ...]) -> tuple[str, int]:
    ranks = {"blocked": 0, "derived_only": 1, "full": 2}
    values = [_rights(parent) for parent in parents]
    level = min(item[1] for item in values)
    redistribution = min((item[0] for item in values), key=lambda item: ranks.get(item, 0))
    return redistribution, level


def _event_limit(parents: tuple[MidiArtifactV1, ...], parsed: tuple[ParsedSmfV1, ...]) -> None:
    declared = sum(track.event_count for parent in parents for track in parent.tracks)
    actual = sum(len(item.events) for item in parsed)
    if max(declared, actual) > _GENERATION_EVENT_LIMIT:
        raise GrooveLimitExceeded("generation is limited to 2048 events")


def _preflight_event_count(
    parsed: tuple[ParsedSmfV1, ...],
    *,
    bars: int,
    transforms: Mapping[str, float],
) -> None:
    """Reject an oversized expansion before allocating repeated note lists."""

    notes_per_bar = sum(max(1, len(source.note_events)) for source in parsed)
    note_count = notes_per_bar * bars
    density = float(transforms.get("density", 0.0))
    if density > 0.0:
        note_count += max(1, int(round(note_count * 0.5 * density)))

    # The serializer emits two events per note, one track-name and one EOT
    # event per parent track, and at least one tempo, one meter, and one EOT
    # event on the metadata track.  Keep this bound conservative and exact for
    # the current canonical serializer so rejection happens before allocation.
    metadata_events = max(1, len(parsed[0].tempos)) + 2 + 2 * len(parsed)
    estimated_events = note_count * 2 + metadata_events
    if estimated_events > _GENERATION_EVENT_LIMIT:
        raise GrooveLimitExceeded("generation is limited to 2048 events")


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
    rng = random.Random(seed)
    result = list(notes)
    seed_variation = seed % 5 - 2
    if seed_variation:
        result = [_replace(note, velocity=note.velocity + seed_variation) for note in result]
    density = float(transforms.get("density", 0.0))
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

    energy = float(transforms.get("energy", 0.0))
    if energy:
        delta = max(1, round(abs(energy) * 16))
        energized = []
        for note in result:
            direction = 1 if energy > 0 else -1
            velocity = note.velocity + direction * delta
            if velocity == note.velocity or velocity < 1 or velocity > 127:
                velocity = note.velocity - direction * delta
            energized.append(_replace(note, velocity=velocity))
        result = energized

    bar_ticks = _bar_ticks(ppq, meter)
    microtiming = float(transforms.get("microtiming", 0.0))
    if microtiming:
        amount = max(1, round(abs(microtiming) * ppq / 32))
        direction = 1 if microtiming > 0 else -1
        result = [
            _replace(
                note,
                start_ticks=note.start_ticks
                + (amount * direction if note.start_ticks != 0 or direction > 0 else 0),
            )
            for note in result
        ]

    swing = float(transforms.get("swing", 0.0))
    if swing:
        amount = max(1, round(abs(swing) * ppq / 16))
        eighth = max(1, ppq // 2)
        direction = 1 if swing > 0 else -1
        result = [
            _replace(
                note,
                start_ticks=note.start_ticks
                + (
                    amount * direction
                    if (note.start_ticks // eighth) % 2 or (note.start_ticks == 0 and direction > 0)
                    else 0
                ),
            )
            for note in result
        ]

    syncopation = float(transforms.get("syncopation", 0.0))
    if syncopation:
        amount = max(1, round(abs(syncopation) * ppq / 8))
        direction = 1 if syncopation > 0 else -1
        result = [
            _replace(
                note,
                start_ticks=note.start_ticks
                + (amount * direction if note.start_ticks % bar_ticks == 0 else 0),
            )
            for note in result
        ]

    polyrhythm = float(transforms.get("polyrhythm", 0.0))
    if polyrhythm:
        # A 3-over-4 feel: the accented notes move onto the triplet grid while
        # the rest hold the straight one, which is what makes the two grids
        # audible at once. ``round(ppq / 3)`` is the triplet; the intensity
        # decides how many accents move, not how far.
        poly_shift = max(1, round(ppq / 3)) * (1 if polyrhythm > 0 else -1)
        # A dedicated stream. Drawing from the shared rng would make enabling
        # this axis silently change what a negative density transform selects.
        poly_rng = random.Random(seed ^ 0x504F4C59)
        result = [
            _replace(
                note,
                start_ticks=max(0, note.start_ticks + poly_shift)
                if note.velocity > _ACCENT_VELOCITY and poly_rng.random() < abs(polyrhythm)
                else note.start_ticks,
            )
            for note in result
        ]

    complexity = float(transforms.get("complexity", 0.0))
    if complexity:
        shift = 1 if complexity > 0 else -1
        duration_delta = max(1, round(abs(complexity) * ppq / 16))
        result = [
            _replace(
                note,
                pitch=(note.pitch + shift if 0 < note.pitch + shift < 127 else note.pitch - shift),
                duration_ticks=note.duration_ticks
                + (duration_delta if complexity > 0 else -duration_delta),
            )
            for note in result
        ]

    return [
        _clamp_note(note, length_ticks=length_ticks)
        for note in sorted(
            result,
            key=lambda item: (item.track_index, item.start_ticks, item.pitch, item.source_order),
        )
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


def deterministic_generate(
    runtime: GrooveRuntime,
    request: GenerateRequestV1,
    fallback: Any | None = None,
) -> GenerationResponseV1:
    if request.bars > 64:
        raise GrooveLimitExceeded("generation is limited to 64 bars")
    parent_ids = _parent_ids(runtime, request)
    parents = tuple(runtime.store.get(parent_id) for parent_id in parent_ids)
    if sum(track.event_count for parent in parents for track in parent.tracks) > 2_048:
        raise GrooveLimitExceeded("generation is limited to 2048 events")
    redistribution, rights_level = _rights_meet(parents)
    parsed = tuple(
        _raw_parent(runtime, parent, parent_id)
        for parent, parent_id in zip(parents, parent_ids, strict=True)
    )
    _event_limit(parents, parsed)
    ppq = parsed[0].format.ppq
    meter = _meter(parsed[0])
    for other in parsed[1:]:
        if other.format.ppq != ppq:
            raise GrooveParentIncompatible("incompatible PPQ between parents")
        if _meter(other) != meter:
            raise GrooveParentIncompatible("incompatible meter between parents")
    _preflight_event_count(parsed, bars=request.bars, transforms=request.transforms)
    length_ticks = _bar_ticks(ppq, meter) * request.bars
    notes = _transform_notes(
        _initial_notes(parsed, bars=request.bars, ppq=ppq, meter=meter),
        request.transforms,
        seed=request.seed,
        ppq=ppq,
        meter=meter,
        length_ticks=length_ticks,
    )
    generated_notes = tuple(
        NoteEventV1(
            event_id=index,
            track_index=note.track_index,
            channel=note.channel,
            pitch=note.pitch,
            velocity=note.velocity,
            start_ticks=note.start_ticks,
            duration_ticks=note.duration_ticks,
        )
        for index, note in enumerate(notes)
    )
    raw = serialize_note_smf(
        generated_notes,
        ppq=ppq,
        length_ticks=length_ticks,
        meter=meter,
        tempos=parsed[0].tempos,
        track_names={index + 1: f"Generated parent {index + 1}" for index in range(len(parents))},
    )
    generated_parsed = parse_smf(raw)
    if (
        len(generated_parsed.events) > _GENERATION_EVENT_LIMIT
        or len(generated_parsed.note_events) > _GENERATION_EVENT_LIMIT
    ):
        raise GrooveLimitExceeded("generation is limited to 2048 events")
    payload = compress_bounded(raw, "zlib-raw-midi-v1")
    projection_refs, projection_values, summary, feature_values = _projection_values(
        generated_parsed
    )
    first_metadata = parents[0].provenance
    facets: dict[str, list[str]] = {}
    for parent in parents:
        raw_facets = parent.provenance.get("facets", {})
        if isinstance(raw_facets, Mapping):
            for axis, values in raw_facets.items():
                if isinstance(values, (list, tuple)):
                    facets.setdefault(str(axis), []).extend(str(value) for value in values)
    facets = {
        axis: sorted(set(values))[:32]
        for axis, values in sorted(facets.items())[:16]
    }
    license_ids: list[str] = []
    for parent in parents:
        raw_license_ids = parent.provenance.get("license_ids")
        parent_license_ids = (
            [str(value) for value in raw_license_ids]
            if isinstance(raw_license_ids, (list, tuple))
            else [str(parent.provenance.get("license_id", "derived"))]
        )
        for license_id in parent_license_ids:
            if license_id not in license_ids:
                license_ids.append(license_id)
            if len(license_ids) >= 8:
                break
        if len(license_ids) >= 8:
            break
    provenance = {
        "source_digest": payload.sha256,
        "source_kind": "generated",
        "license_id": first_metadata.get("license_id", "derived"),
        "license_ids": license_ids[:8],
        "redistribution": redistribution,
        "rights_level": rights_level,
        "capabilities": {
            "search": True,
            "evidence": True,
            "generate": True,
            "apply": rights_level >= 2,
        },
        "summary": summary,
        "facets": facets,
        "features": feature_values,
        "_projection_values": projection_values,
    }
    provenance["provenance_digest"] = sha256_hex(
        canonical_json(provenance)
    )
    identity = {
        "schema_version": "groove.midi-artifact.v1",
        "kind": "generated",
        "parent_artifact_ids": list(parent_ids),
        "transforms": dict(sorted(request.transforms.items())),
        "bars": request.bars,
        "seed": request.seed,
        "provider": "deterministic",
        "payload_sha256": payload.sha256,
        "events_digest": generated_parsed.source_events_digest,
        "projection_digests": {ref.name: ref.digest for ref in projection_refs},
        "provenance_digest": provenance["provenance_digest"],
    }
    artifact_id = artifact_id_from_identity(identity)
    reproducibility = reproducibility_key(
        schema_versions={
            "artifact": "groove.midi-artifact.v1",
            "generator": "groove-deterministic-v2",
        },
        seed_bundle_id=runtime.index.manifest.seed_bundle_id,
        algorithm_versions={"generator": "groove-deterministic-v2"},
        canonical_request=request.model_dump(mode="json", exclude_none=True),
        parent_artifact_ids=parent_ids,
        provider_identity={"provider": "deterministic", "version": "2"},
    )
    relation = "recombination" if len(parent_ids) > 1 else "deterministic_transform"
    lineage = {
        "parent_artifact_ids": list(parent_ids),
        "relations": [relation] * len(parent_ids),
        "ordinals": list(range(len(parent_ids))),
    }
    generated = MidiArtifactV1(
        artifact_id=artifact_id,
        kind="generated",
        format=generated_parsed.format,
        timing={
            "length_ticks": generated_parsed.length_ticks,
            "meters": generated_parsed.meters,
            "tempos": generated_parsed.tempos,
        },
        tracks=tuple(generated_parsed.tracks),
        payload=payload,
        events_digest=generated_parsed.source_events_digest,
        provenance=provenance,
        lineage=lineage,
        projections=projection_refs,
    )
    fallback_value: bool | dict[str, str] = False
    if fallback is not None:
        fallback_value = (
            {str(key): str(value) for key, value in fallback.items()}
            if isinstance(fallback, Mapping)
            else {"reason": str(fallback)}
        )
    elif request.provider == "neural":
        fallback_value = {
            "reason": "offline_policy",
            "deterministic_provider": "groove-deterministic-v2",
        }
    card = GenerationCardV1(
        artifact_id=generated.artifact_id,
        parent_artifact_ids=tuple(ArtifactId(parent_id) for parent_id in parent_ids),
        generator_id="groove-deterministic-v2",
        generator_version="2",
        transforms=dict(request.transforms),
        seed=request.seed,
        provider_requested=request.provider,
        provider_resolved="deterministic",
        fallback=fallback_value,
        summary=summary,
        deterministic=True,
        reproducibility_key=reproducibility,
        lineage=lineage,
    )
    artifact_card = artifact_card_from_artifact(generated)
    result = GenerationResponseV1(
        card=card,
        artifact=artifact_card,
        provenance={
            "reproducibility_key": reproducibility,
            "seed_bundle_id": runtime.index.manifest.seed_bundle_id,
        },
    )
    if len(canonical_json(result.model_dump(mode="json"))) > 16 * 1024:
        raise GrooveLimitExceeded("generation response exceeds 16 KiB")
    runtime.store.put(generated)
    return result


__all__ = [
    "GrooveLimitExceeded",
    "GrooveParentIncompatible",
    "GrooveRightsRejected",
    "deterministic_generate",
]
