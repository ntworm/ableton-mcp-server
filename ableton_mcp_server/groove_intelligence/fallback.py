"""Provider candidate validation and the deterministic safety net."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from . import GrooveBlobRejected, GrooveMidiError
from .canonical import canonical_json, reproducibility_key
from .cards import GenerationCardV1, artifact_card_from_artifact
from .constants import (
    FEATURES_SCHEMA_VERSION,
    GRAMMAR_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION_V3,
)
from .deterministic import _parent_ids, deterministic_generate
from .mcp_models import GenerateRequestV1, GenerationResponseV1
from .midi_lossless import decompress_bounded, parse_smf
from .projections import derive_features, derive_grammar, derive_hvo, derive_hvo_v3
from .provider import (
    GrooveProvider,
    ProviderArtifactCandidate,
    ProviderFailure,
    ProviderFailureCode,
    ProviderIdentityInvalid,
    ProviderLimitsV1,
    build_condition_card,
)
from .runtime import GrooveRuntime
from .schema import ArtifactId, MidiArtifactV1


class ProviderOutputInvalid(ValueError):
    """An untrusted provider candidate failed validation."""

    def __init__(self, message: str, *, diagnostic_digest: str | None = None) -> None:
        super().__init__(message)
        self.diagnostic_digest = diagnostic_digest or sha256(
            message.encode("utf-8")
        ).hexdigest()[:16]


class FallbackV1(dict[str, str]):
    """Bounded card-compatible fallback details.

    ``GenerationCardV1`` predates the provider contract and intentionally uses
    ``bool | dict[str, str]`` for this field.  A small dict subclass keeps that
    wire contract stable while providing a typed constructor for provider code.
    """

    def __init__(
        self,
        *,
        reason: str,
        provider_id: str = "",
        diagnostic_digest: str = "",
        deterministic_provider: str = "groove-deterministic-v2",
    ) -> None:
        values = {
            "reason": reason,
            "deterministic_provider": deterministic_provider,
        }
        if provider_id:
            values["provider_id"] = provider_id
        if diagnostic_digest:
            values["diagnostic_digest"] = diagnostic_digest
        super().__init__(values)

    @property
    def reason(self) -> str:
        return self["reason"]


class ProviderResolution:
    """Small internal representation of the selected provider outcome."""

    def __init__(
        self,
        *,
        provider_requested: str,
        provider_resolved: str,
        fallback: FallbackV1 | bool,
        deterministic: bool,
    ) -> None:
        self.provider_requested = provider_requested
        self.provider_resolved = provider_resolved
        self.fallback = fallback
        self.deterministic = deterministic


def fallback_reason(failure: ProviderFailure) -> FallbackV1:
    """Project a provider failure into bounded, non-sensitive card metadata."""

    return FallbackV1(
        reason=failure.code.value,
        provider_id=failure.provider_id,
        diagnostic_digest=failure.diagnostic_digest,
    )


def _invalid(message: str, *, digest: str | None = None) -> ProviderOutputInvalid:
    return ProviderOutputInvalid(message, diagnostic_digest=digest)


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


def _is_private_metadata_key(value: str) -> bool:
    key = value.casefold().replace("-", "_")
    return (
        key in _PRIVATE_METADATA_KEYS
        or "path" in key
        or key.startswith("private")
        or key in {"secret", "token", "password"}
    )


def _sanitize_metadata(value: object, *, depth: int = 0) -> object:
    """Clone bounded provider metadata while dropping private values recursively."""

    if depth > 8:
        return _DROP_METADATA
    if isinstance(value, Mapping):
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
    if isinstance(value, (list, tuple)):
        result_list: list[object] = []
        for item in value[:32]:
            sanitized = _sanitize_metadata(item, depth=depth + 1)
            if sanitized is not _DROP_METADATA:
                result_list.append(sanitized)
        return result_list
    if isinstance(value, str):
        if re.search(r"(?i)(?:[a-z]:[\\/]|^[/\\]|\\\\)", value):
            return _DROP_METADATA
        return value[:256]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value if len(str(value)) <= 32 else _DROP_METADATA
    if isinstance(value, float):
        return value if math.isfinite(value) else _DROP_METADATA
    return _DROP_METADATA


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
    actual_digest = sha256(raw).hexdigest()
    if candidate.payload_digest != actual_digest or artifact.payload.sha256 != actual_digest:
        raise _invalid("provider payload digest mismatch")
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
    if candidate.identity.parent_artifact_ids and artifact.lineage:
        parents = artifact.lineage.get("parent_artifact_ids", ())
        if (
            parents
            and tuple(str(item) for item in parents)
            != candidate.identity.parent_artifact_ids
        ):
            raise _invalid("provider lineage does not match identity")
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
    return artifact


def _parent_id(runtime: GrooveRuntime, request: GenerateRequestV1) -> str:
    from .deterministic import _source_id

    return _source_id(runtime, request)


def _identity_for(runtime: GrooveRuntime, provider: GrooveProvider, provider_id: str) -> Any:
    resolver = getattr(provider, "identity_for", None)
    if callable(resolver):
        return resolver(provider_id)
    identity = getattr(provider, "identity", None)
    if identity is not None:
        return identity
    identity = getattr(runtime, "provider_identity", None)
    if identity is not None:
        return identity
    return None


def _provider_failure(value: object) -> ProviderFailure:
    if isinstance(value, ProviderFailure):
        return value
    return ProviderFailure(
        code=ProviderFailureCode.output_invalid,
        provider_id="unknown",
        diagnostic_digest=sha256(b"provider returned unsupported output").hexdigest()[:16],
    )


def _deterministic_fallback(
    runtime: GrooveRuntime,
    request: GenerateRequestV1,
    fallback: FallbackV1,
) -> GenerationResponseV1:
    result = deterministic_generate(runtime, request, fallback=fallback)
    # Keep the established wire shape (dict) while exposing the typed reason
    # to in-process callers and tests.
    result.card.fallback = fallback
    return result


def _store_provider_result(
    runtime: GrooveRuntime,
    request: GenerateRequestV1,
    candidate: ProviderArtifactCandidate,
    artifact: MidiArtifactV1,
    parent_ids: tuple[str, ...],
) -> GenerationResponseV1:
    artifact = _sanitize_provider_artifact(artifact)
    identity = candidate.identity
    reproducibility = reproducibility_key(
        schema_versions={"artifact": artifact.schema_version, "generator": "groove-provider-v1"},
        seed_bundle_id=runtime.index.manifest.seed_bundle_id,
        algorithm_versions={"provider": identity.provider_version},
        canonical_request=request.model_dump(mode="json", exclude_none=True),
        parent_artifact_ids=parent_ids,
        provider_identity=identity.model_dump(mode="json"),
    )
    summary_value = artifact.provenance.get("summary", {})
    summary = dict(summary_value) if isinstance(summary_value, Mapping) else {}
    lineage = dict(artifact.lineage)
    if not lineage.get("parent_artifact_ids"):
        lineage = {
            "parent_artifact_ids": list(parent_ids),
            "relations": ["provider_recombination" if len(parent_ids) > 1 else "provider"]
            * len(parent_ids),
            "ordinals": list(range(len(parent_ids))),
        }
    card = GenerationCardV1(
        artifact_id=artifact.artifact_id,
        parent_artifact_ids=tuple(ArtifactId(parent_id) for parent_id in parent_ids),
        generator_id=f"groove-provider-{candidate.provider_id}",
        generator_version=identity.provider_version,
        transforms=dict(request.transforms),
        seed=request.seed,
        provider_requested=request.provider,
        provider_resolved=candidate.provider_id,
        fallback=False,
        summary=summary,
        deterministic=False,
        reproducibility_key=reproducibility,
        lineage=lineage,
    )
    try:
        artifact_card = artifact_card_from_artifact(artifact)
    except (TypeError, ValueError) as error:
        raise ProviderOutputInvalid("provider artifact card is invalid") from error
    result = GenerationResponseV1(
        card=card,
        artifact=artifact_card,
        provenance={
            "reproducibility_key": reproducibility,
            "seed_bundle_id": runtime.index.manifest.seed_bundle_id,
        },
    )
    if len(canonical_json(result.model_dump(mode="json"))) > 16 * 1024:
        raise ProviderOutputInvalid("provider response exceeds public card limit")
    runtime.store.put(artifact)
    return result


def generate_with_provider(
    runtime: GrooveRuntime, request: GenerateRequestV1
) -> GenerationResponseV1:
    """Resolve neural generation while keeping deterministic generation complete."""

    if request.provider == "deterministic":
        return deterministic_generate(runtime, request)
    provider = runtime.provider
    if provider is None:
        return _deterministic_fallback(
            runtime, request, FallbackV1(reason=ProviderFailureCode.offline_policy.value)
        )
    provider_id = str(getattr(provider, "provider_id", "neural"))
    identity = _identity_for(runtime, provider, provider_id)
    if identity is not None:
        identity.require_production_complete()
    parent_ids = _parent_ids(runtime, request)
    parent_id = parent_ids[0]
    condition = build_condition_card(
        runtime.card(parent_id),
        parent_artifact_ids=parent_ids,
        seed=request.seed,
        limits=ProviderLimitsV1(),
    )
    outcome = provider.generate(
        condition,
        parent_ids,
        request.seed,
        ProviderLimitsV1(),
    )
    if isinstance(outcome, ProviderFailure):
        return _deterministic_fallback(runtime, request, fallback_reason(outcome))
    if not isinstance(outcome, ProviderArtifactCandidate):
        return _deterministic_fallback(
            runtime, request, fallback_reason(_provider_failure(outcome))
        )
    if tuple(outcome.identity.parent_artifact_ids) != parent_ids:
        failure = ProviderFailure(
            code=ProviderFailureCode.output_invalid,
            provider_id=provider_id,
            diagnostic_digest=sha256(
                b"provider identity parent_artifact_ids mismatch"
            ).hexdigest()[:16],
        )
        return _deterministic_fallback(runtime, request, fallback_reason(failure))
    if outcome.provider_id != provider_id:
        failure = ProviderFailure(
            code=ProviderFailureCode.output_invalid,
            provider_id=provider_id,
            diagnostic_digest=sha256(
                b"provider identity provider_id mismatch"
            ).hexdigest()[:16],
        )
        return _deterministic_fallback(runtime, request, fallback_reason(failure))
    try:
        effective_redistribution, effective_rights_level = _effective_parent_rights(
            runtime, parent_ids
        )
        artifact = validate_provider_candidate(
            outcome,
            ProviderLimitsV1(),
            effective_redistribution=effective_redistribution,
            effective_rights_level=effective_rights_level,
        )
    except ProviderIdentityInvalid:
        raise
    except ProviderOutputInvalid as error:
        failure = ProviderFailure(
            code=ProviderFailureCode.output_invalid,
            provider_id=provider_id,
            diagnostic_digest=error.diagnostic_digest,
        )
        return _deterministic_fallback(runtime, request, fallback_reason(failure))
    try:
        return _store_provider_result(runtime, request, outcome, artifact, parent_ids)
    except ProviderOutputInvalid as error:
        failure = ProviderFailure(
            code=ProviderFailureCode.output_invalid,
            provider_id=provider_id,
            diagnostic_digest=error.diagnostic_digest,
        )
        return _deterministic_fallback(runtime, request, fallback_reason(failure))


__all__ = [
    "FallbackV1",
    "ProviderOutputInvalid",
    "ProviderResolution",
    "fallback_reason",
    "generate_with_provider",
    "validate_provider_candidate",
]
