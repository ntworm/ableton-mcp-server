"""Validation of a provider candidate before it enters the content store."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any

from . import GrooveBlobRejected, GrooveMidiError
from .canonical import canonical_json
from .constants import (
    FEATURES_SCHEMA_VERSION,
    GRAMMAR_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION_V3,
)
from .midi_lossless import ParsedSmfV1, decompress_bounded, parse_smf
from .projections import derive_features, derive_grammar, derive_hvo, derive_hvo_v3
from .provider import (
    ProviderArtifactCandidate,
    ProviderIdentityInvalid,
    ProviderLimitsV1,
)
from .runtime import GrooveRuntime
from .schema import MidiArtifactV1


class ProviderOutputInvalid(ValueError):
    """An untrusted provider candidate failed validation."""

    def __init__(self, message: str, *, diagnostic_digest: str | None = None) -> None:
        super().__init__(message)
        self.diagnostic_digest = diagnostic_digest or sha256(
            message.encode("utf-8")
        ).hexdigest()[:16]


_RIGHTS_RANK = {"blocked": 0, "derived_only": 1, "full": 2}
_PRIVATE_METADATA_KEYS = frozenset(
    {
        "blob",
        "notes",
        "payload",
        "raw_payload",
        "path",
        "private_path",
        "source_path",
        "sql",
        "sqlite",
    }
)
_DROP_METADATA = object()


def _invalid(message: str, *, digest: str | None = None) -> ProviderOutputInvalid:
    return ProviderOutputInvalid(message, diagnostic_digest=digest)


def _is_private_metadata_key(value: str) -> bool:
    key = value.casefold().replace("-", "_")
    return (
        key in _PRIVATE_METADATA_KEYS
        or "path" in key
        or key.startswith("private")
        or key in {"secret", "token", "password"}
    )


def _sanitize_mapping(value: Mapping[Any, Any], *, depth: int) -> dict[str, object]:
    """Clone the entries of a provider mapping without its private values."""

    result: dict[str, object] = {}
    for index, (raw_key, raw_value) in enumerate(value.items()):
        if index >= 64:
            break
        key = str(raw_key)
        if _is_private_metadata_key(key):
            continue
        sanitized = _sanitize_metadata(raw_value, depth=depth + 1)
        if sanitized is not _DROP_METADATA:
            result[key] = sanitized
    return result


def _sanitize_sequence(value: Sequence[Any], *, depth: int) -> list[object]:
    """Clone the items of a provider sequence without its private values."""

    result_list: list[object] = []
    for item in value[:32]:
        sanitized = _sanitize_metadata(item, depth=depth + 1)
        if sanitized is not _DROP_METADATA:
            result_list.append(sanitized)
    return result_list


def _sanitize_scalar(value: object) -> object:
    """Return a bounded scalar provider value or the drop marker."""

    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value if len(str(value)) <= 32 else _DROP_METADATA
    if isinstance(value, float):
        return value if math.isfinite(value) else _DROP_METADATA
    return _DROP_METADATA


def _sanitize_metadata(value: object, *, depth: int = 0) -> object:
    """Clone bounded provider metadata while dropping private values recursively."""

    if depth > 8:
        return _DROP_METADATA
    if isinstance(value, Mapping):
        return _sanitize_mapping(value, depth=depth)
    if isinstance(value, (list, tuple)):
        return _sanitize_sequence(value, depth=depth)
    if isinstance(value, str):
        if re.search(r"(?i)(?:[a-z]:[\\/]|^[/\\]|\\\\)", value):
            return _DROP_METADATA
        return value[:256]
    return _sanitize_scalar(value)


def _sanitize_metadata_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize_metadata(value)
    return sanitized if isinstance(sanitized, dict) else {}


def _sanitize_provider_artifact(artifact: MidiArtifactV1) -> MidiArtifactV1:
    provenance = _sanitize_metadata_mapping(artifact.provenance)
    lineage = _sanitize_metadata_mapping(artifact.lineage)
    try:
        provenance_digest = provenance.get("provenance_digest")
        digest_body = {
            key: value
            for key, value in provenance.items()
            if key != "provenance_digest"
        }
        expected_digest = sha256(canonical_json(digest_body)).hexdigest()
    except (TypeError, ValueError) as error:
        raise _invalid("provider provenance is not canonical") from error
    source_attestation = (
        artifact.kind == "source"
        and all(
            key in provenance
            for key in ("corpus_id", "build_id", "source_digest", "license_id")
        )
    )
    if provenance_digest != expected_digest and not source_attestation:
        raise _invalid("provider provenance digest mismatch")
    if not source_attestation:
        provenance["provenance_digest"] = expected_digest
    return artifact.model_copy(
        update={"provenance": provenance, "lineage": lineage}
    )


def _rights_value(
    metadata: Mapping[str, Any], *, field: str, default_level: int | None = None
) -> tuple[str, int]:
    redistribution = metadata.get("redistribution")
    if not isinstance(redistribution, str) or redistribution not in _RIGHTS_RANK:
        raise _invalid(f"{field} redistribution is invalid")
    raw_level = metadata.get("rights_level", default_level)
    if isinstance(raw_level, bool) or not isinstance(raw_level, int) or not 0 <= raw_level <= 2:
        raise _invalid(f"{field} rights level is invalid")
    return redistribution, raw_level


def _candidate_rights(candidate: ProviderArtifactCandidate) -> tuple[str, int]:
    candidate_rights = candidate.rights
    redistribution = candidate_rights.get("redistribution")
    if not isinstance(redistribution, str) or redistribution not in _RIGHTS_RANK:
        raise _invalid("provider candidate redistribution is invalid")
    raw_blocked_lineage = candidate_rights.get("blocked_lineage", 0)
    if (
        isinstance(raw_blocked_lineage, bool)
        or not isinstance(raw_blocked_lineage, int)
        or raw_blocked_lineage != 0
    ):
        raise _invalid("provider rights are invalid")
    return redistribution, _RIGHTS_RANK[redistribution]


def _effective_parent_rights(
    runtime: GrooveRuntime, parent_ids: tuple[str, ...]
) -> tuple[str, int]:
    parent_rights: list[tuple[str, int]] = []
    for parent_id in parent_ids:
        try:
            parent = runtime.store.get(parent_id)
        except (KeyError, TypeError, ValueError) as error:
            raise _invalid("provider parent is unavailable") from error
        parent_rights.append(
            _rights_value(
                parent.provenance,
                field="provider parent",
                default_level=None,
            )
        )
    if not parent_rights:
        raise _invalid("provider requires at least one parent")
    effective_redistribution = min(
        (item[0] for item in parent_rights), key=lambda item: _RIGHTS_RANK[item]
    )
    effective_level = min(item[1] for item in parent_rights)
    return effective_redistribution, effective_level


def _parsed_payload(
    artifact: MidiArtifactV1,
    limits: ProviderLimitsV1,
) -> tuple[bytes, ParsedSmfV1]:
    """Validate the payload bounds of a candidate and parse its MIDI bytes."""

    blob = artifact.payload.blob
    if len(blob) != artifact.payload.compressed_size:
        raise _invalid("compressed payload size mismatch")
    if len(blob) > limits.max_response_bytes:
        raise _invalid("provider payload exceeds response limit")
    if artifact.payload.raw_size > limits.max_response_bytes:
        raise _invalid("provider raw payload exceeds response limit")
    try:
        raw = decompress_bounded(
            blob,
            codec=artifact.payload.codec,
            raw_size=artifact.payload.raw_size,
            max_compressed=limits.max_response_bytes,
            max_raw=limits.max_response_bytes,
        )
        parsed = parse_smf(raw)
    except (GrooveBlobRejected, GrooveMidiError, ValueError, TypeError) as error:
        raise _invalid("provider payload is not valid MIDI") from error
    return raw, parsed


def _validate_parsed_midi(
    artifact: MidiArtifactV1,
    parsed: ParsedSmfV1,
    actual_digest: str,
    limits: ProviderLimitsV1,
) -> None:
    """Validate the derived MIDI facts of a candidate against its payload."""

    if artifact.events_digest != parsed.source_events_digest:
        raise _invalid("provider events digest mismatch")
    if artifact.format != parsed.format:
        raise _invalid("provider MIDI format mismatch")
    expected_timing = {
        "length_ticks": parsed.length_ticks,
        "meters": parsed.meters,
        "tempos": parsed.tempos,
    }
    if canonical_json(artifact.timing) != canonical_json(expected_timing):
        raise _invalid("provider MIDI timing mismatch")
    if tuple(track.model_dump(mode="json") for track in artifact.tracks) != tuple(
        track.model_dump(mode="json") for track in parsed.tracks
    ):
        raise _invalid("provider MIDI track metadata mismatch")
    source_digest = artifact.provenance.get("source_digest")
    if str(source_digest) != actual_digest:
        raise _invalid("provider source digest mismatch")
    event_count = max(len(parsed.events), sum(track.event_count for track in artifact.tracks))
    if event_count > limits.max_events:
        raise _invalid("provider candidate exceeds event limit")
    if len(artifact.provenance) > 32 or len(artifact.lineage) > 32:
        raise _invalid("provider provenance is unbounded")


def _validate_rights(
    candidate: ProviderArtifactCandidate,
    artifact: MidiArtifactV1,
    effective_redistribution: str | None,
    effective_rights_level: int | None,
) -> None:
    """Validate the rights of a candidate against its provenance and its parents."""

    candidate_redistribution, _ = _candidate_rights(candidate)
    artifact_redistribution, artifact_rights_level = _rights_value(
        artifact.provenance,
        field="provider artifact",
        default_level=None,
    )
    if candidate_redistribution != artifact_redistribution:
        raise _invalid("provider rights diverge from provenance")
    if effective_redistribution is None:
        effective_redistribution = artifact_redistribution
    if effective_redistribution not in _RIGHTS_RANK:
        raise _invalid("provider effective rights are invalid")
    if candidate_redistribution != effective_redistribution:
        raise _invalid("provider candidate elevates or diverges from parent rights")
    if effective_rights_level is not None:
        if not 0 <= effective_rights_level <= 2:
            raise _invalid("provider effective rights level is invalid")
        if artifact_rights_level != effective_rights_level:
            raise _invalid("provider rights level diverges from parent rights")
    if candidate_redistribution == "blocked":
        raise _invalid("provider candidate has blocked rights")


def _validate_lineage(
    candidate: ProviderArtifactCandidate,
    artifact: MidiArtifactV1,
) -> None:
    """Validate that the lineage of a candidate matches its identity."""

    if candidate.identity.parent_artifact_ids and artifact.lineage:
        parents = artifact.lineage.get("parent_artifact_ids", ())
        if (
            parents
            and tuple(str(item) for item in parents)
            != candidate.identity.parent_artifact_ids
        ):
            raise _invalid("provider lineage does not match identity")


def _validate_projections(artifact: MidiArtifactV1, parsed: ParsedSmfV1) -> None:
    """Validate the projections of a candidate against the parsed payload."""

    hvo_projection = derive_hvo(parsed)
    # A generated groove belongs to no vendor library, so its v3 projection
    # resolves through General MIDI.  It still has to be present: every artifact
    # in the index carries the same projection set, and a missing one reads as a
    # corrupt row rather than as an absent collection.
    hvo_v3_projection = derive_hvo_v3(parsed, "")
    features_projection = derive_features(parsed, hvo_projection)
    grammar_projection = derive_grammar(parsed, hvo_projection)
    expected_projections = {
        "hvo": (HVO_SCHEMA_VERSION, hvo_projection),
        "hvo_v3": (HVO_SCHEMA_VERSION_V3, hvo_v3_projection),
        "features": (FEATURES_SCHEMA_VERSION, features_projection),
        "grammar": (GRAMMAR_SCHEMA_VERSION, grammar_projection),
    }
    references = {reference.name: reference for reference in artifact.projections}
    if len(references) != len(expected_projections) or set(references) != set(expected_projections):
        raise _invalid("provider projections are incomplete")
    for name, (version, projection) in expected_projections.items():
        reference = references[name]
        expected_digest = sha256(
            canonical_json(projection.model_dump(mode="json"))
        ).hexdigest()
        if (
            reference.status != "available"
            or reference.version != version
            or reference.digest != expected_digest
        ):
            raise _invalid("provider projection digest mismatch")


def validate_provider_candidate(
    candidate: ProviderArtifactCandidate,
    limits: ProviderLimitsV1,
    *,
    effective_redistribution: str | None = None,
    effective_rights_level: int | None = None,
) -> MidiArtifactV1:
    """Validate every provider-controlled field before content-store insertion."""

    try:
        candidate.identity.require_production_complete()
    except ProviderIdentityInvalid as error:
        raise _invalid("provider candidate identity is incomplete") from error
    artifact = _sanitize_provider_artifact(candidate.artifact)
    raw, parsed = _parsed_payload(artifact, limits)
    actual_digest = sha256(raw).hexdigest()
    if candidate.payload_digest != actual_digest or artifact.payload.sha256 != actual_digest:
        raise _invalid("provider payload digest mismatch")
    _validate_parsed_midi(artifact, parsed, actual_digest, limits)
    _validate_rights(candidate, artifact, effective_redistribution, effective_rights_level)
    _validate_lineage(candidate, artifact)
    _validate_projections(artifact, parsed)
    return artifact
