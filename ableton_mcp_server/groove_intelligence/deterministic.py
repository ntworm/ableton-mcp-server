"""Seeded, offline deterministic musical artifact generation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import GrooveMidiError
from .canonical import artifact_id_from_identity, canonical_json, reproducibility_key, sha256_hex
from .cards import GenerationCardV1, artifact_card_from_artifact
from .deterministic_transform import (
    _ACCENT_VELOCITY,
    _DRUM_ROLE_ALIASES,
    _PITCH_BY_DRUM_ROLE,
    _bar_ticks,
    _clamp_note,
    _initial_notes,
    _MusicalNote,
    _pitch_for_drum_role,
    _projected_parent,
    _projection_values,
    _replace,
    _transform_notes,
)
from .mcp_models import GenerateRequestV1, GenerationResponseV1
from .midi_lossless import (
    ParsedSmfV1,
    compress_bounded,
    decompress_bounded,
    parse_smf,
    serialize_note_smf,
)
from .runtime import GrooveRuntime
from .schema import (
    ArtifactId,
    CompressedBlobV1,
    MidiArtifactV1,
    NoteEventV1,
    ProjectionRefV1,
)

_GENERATION_EVENT_LIMIT = 2_048


class GrooveLimitExceeded(ValueError):
    """A generated artifact exceeds a bounded generation limit."""


class GrooveRightsRejected(PermissionError):
    """The parent rights lattice does not permit the requested operation."""


class GrooveParentIncompatible(ValueError):
    """Multiple parents cannot be recombined without changing their contract."""


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


def _generation_parents(
    runtime: GrooveRuntime, request: GenerateRequestV1
) -> tuple[tuple[str, ...], tuple[MidiArtifactV1, ...]]:
    """Resolve the parent artifacts of a generation request."""
    parent_ids = _parent_ids(runtime, request)
    parents = tuple(runtime.store.get(parent_id) for parent_id in parent_ids)
    if sum(track.event_count for parent in parents for track in parent.tracks) > 2_048:
        raise GrooveLimitExceeded("generation is limited to 2048 events")
    return parent_ids, parents


def _parsed_parents(
    runtime: GrooveRuntime,
    parents: tuple[MidiArtifactV1, ...],
    parent_ids: tuple[str, ...],
) -> tuple[ParsedSmfV1, ...]:
    """Parse the parents of a request and reject an incompatible contract."""
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
    return parsed


def _generated_smf(
    parsed: tuple[ParsedSmfV1, ...],
    parents: tuple[MidiArtifactV1, ...],
    request: GenerateRequestV1,
    ppq: int,
    meter: tuple[int, int],
    length_ticks: int,
) -> bytes:
    """Serialize the transformed notes into a canonical SMF payload."""
    notes: list[_MusicalNote] = _transform_notes(
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
    return serialize_note_smf(
        generated_notes,
        ppq=ppq,
        length_ticks=length_ticks,
        meter=meter,
        tempos=parsed[0].tempos,
        track_names={index + 1: f"Generated parent {index + 1}" for index in range(len(parents))},
    )


def _collected_license_ids(parents: tuple[MidiArtifactV1, ...]) -> list[str]:
    """Collect the distinct license ids of the parents."""
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
    return license_ids


def _generated_provenance(
    parents: tuple[MidiArtifactV1, ...],
    payload: CompressedBlobV1,
    redistribution: str,
    rights_level: int,
    summary: dict[str, Any],
    feature_values: dict[str, float | int | str | None],
    projection_values: dict[str, Any],
) -> dict[str, Any]:
    """Build the provenance record of a generated artifact."""
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
    license_ids = _collected_license_ids(parents)
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
    provenance["provenance_digest"] = sha256_hex(canonical_json(provenance))
    return provenance


def _generated_identity(
    parent_ids: tuple[str, ...],
    request: GenerateRequestV1,
    payload: CompressedBlobV1,
    generated_parsed: ParsedSmfV1,
    projection_refs: tuple[ProjectionRefV1, ...],
    provenance_digest: str,
) -> dict[str, Any]:
    """Build the identity record that names a generated artifact."""
    return {
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
        "provenance_digest": provenance_digest,
    }


def _generated_artifact(
    generated_parsed: ParsedSmfV1,
    payload: CompressedBlobV1,
    parents: tuple[MidiArtifactV1, ...],
    parent_ids: tuple[str, ...],
    request: GenerateRequestV1,
    redistribution: str,
    rights_level: int,
) -> MidiArtifactV1:
    """Build the stored artifact of a generation run."""
    projection_refs, projection_values, summary, feature_values = _projection_values(
        generated_parsed
    )
    provenance = _generated_provenance(
        parents,
        payload,
        redistribution,
        rights_level,
        summary,
        feature_values,
        projection_values,
    )
    identity = _generated_identity(
        parent_ids,
        request,
        payload,
        generated_parsed,
        projection_refs,
        provenance["provenance_digest"],
    )
    artifact_id = artifact_id_from_identity(identity)
    relation = "recombination" if len(parent_ids) > 1 else "deterministic_transform"
    lineage = {
        "parent_artifact_ids": list(parent_ids),
        "relations": [relation] * len(parent_ids),
        "ordinals": list(range(len(parent_ids))),
    }
    return MidiArtifactV1(
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


def _generation_response(
    runtime: GrooveRuntime,
    request: GenerateRequestV1,
    parent_ids: tuple[str, ...],
    generated: MidiArtifactV1,
    fallback: Any | None,
) -> GenerationResponseV1:
    """Build the card and the response of a generation run."""
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
        summary=generated.provenance["summary"],
        deterministic=True,
        reproducibility_key=reproducibility,
        lineage=generated.lineage,
    )
    artifact_card = artifact_card_from_artifact(generated)
    return GenerationResponseV1(
        card=card,
        artifact=artifact_card,
        provenance={
            "reproducibility_key": reproducibility,
            "seed_bundle_id": runtime.index.manifest.seed_bundle_id,
        },
    )


def deterministic_generate(
    runtime: GrooveRuntime,
    request: GenerateRequestV1,
    fallback: Any | None = None,
) -> GenerationResponseV1:
    if request.bars > 64:
        raise GrooveLimitExceeded("generation is limited to 64 bars")
    parent_ids, parents = _generation_parents(runtime, request)
    redistribution, rights_level = _rights_meet(parents)
    parsed = _parsed_parents(runtime, parents, parent_ids)
    ppq = parsed[0].format.ppq
    meter = _meter(parsed[0])
    _preflight_event_count(parsed, bars=request.bars, transforms=request.transforms)
    length_ticks = _bar_ticks(ppq, meter) * request.bars
    raw = _generated_smf(parsed, parents, request, ppq, meter, length_ticks)
    generated_parsed = parse_smf(raw)
    if (
        len(generated_parsed.events) > _GENERATION_EVENT_LIMIT
        or len(generated_parsed.note_events) > _GENERATION_EVENT_LIMIT
    ):
        raise GrooveLimitExceeded("generation is limited to 2048 events")
    payload = compress_bounded(raw, "zlib-raw-midi-v1")
    generated = _generated_artifact(
        generated_parsed,
        payload,
        parents,
        parent_ids,
        request,
        redistribution,
        rights_level,
    )
    result = _generation_response(
        runtime,
        request,
        parent_ids,
        generated,
        fallback,
    )
    if len(canonical_json(result.model_dump(mode="json"))) > 16 * 1024:
        raise GrooveLimitExceeded("generation response exceeds 16 KiB")
    runtime.store.put(generated)
    return result


__all__ = [
    "GrooveLimitExceeded",
    "GrooveMidiError",
    "GrooveParentIncompatible",
    "GrooveRightsRejected",
    "_ACCENT_VELOCITY",
    "_DRUM_ROLE_ALIASES",
    "_PITCH_BY_DRUM_ROLE",
    "_bar_ticks",
    "_clamp_note",
    "_initial_notes",
    "_MusicalNote",
    "_pitch_for_drum_role",
    "_projected_parent",
    "_projection_values",
    "_replace",
    "_transform_notes",
    "deterministic_generate",
]
