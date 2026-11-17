"""Provider candidate validation and the deterministic safety net."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from .canonical import canonical_json, reproducibility_key
from .cards import GenerationCardV1, artifact_card_from_artifact
from .deterministic import _parent_ids, deterministic_generate
from .fallback_validate import (
    _DROP_METADATA,  # noqa: F401  (kept importable from this module)
    _PRIVATE_METADATA_KEYS,  # noqa: F401  (kept importable from this module)
    _RIGHTS_RANK,  # noqa: F401  (kept importable from this module)
    ProviderOutputInvalid,
    _candidate_rights,  # noqa: F401  (kept importable from this module)
    _effective_parent_rights,
    _invalid,  # noqa: F401  (kept importable from this module)
    _is_private_metadata_key,  # noqa: F401  (kept importable from this module)
    _rights_value,  # noqa: F401  (kept importable from this module)
    _sanitize_metadata,  # noqa: F401  (kept importable from this module)
    _sanitize_metadata_mapping,  # noqa: F401  (kept importable from this module)
    _sanitize_provider_artifact,
    validate_provider_candidate,
)
from .mcp_models import GenerateRequestV1, GenerationResponseV1
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


def _identity_failure(provider_id: str, message: bytes) -> ProviderFailure:
    """Return the failure of a candidate whose identity does not match the request."""

    return ProviderFailure(
        code=ProviderFailureCode.output_invalid,
        provider_id=provider_id,
        diagnostic_digest=sha256(message).hexdigest()[:16],
    )


def _output_invalid_failure(provider_id: str, diagnostic_digest: str) -> ProviderFailure:
    """Return the failure of a candidate that failed the validation contract."""

    return ProviderFailure(
        code=ProviderFailureCode.output_invalid,
        provider_id=provider_id,
        diagnostic_digest=diagnostic_digest,
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


def _validated_provider_response(
    runtime: GrooveRuntime,
    request: GenerateRequestV1,
    outcome: ProviderArtifactCandidate,
    parent_ids: tuple[str, ...],
    provider_id: str,
) -> GenerationResponseV1:
    """Validate a provider candidate and store it, or fall back deterministically."""

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
        failure = _output_invalid_failure(provider_id, error.diagnostic_digest)
        return _deterministic_fallback(runtime, request, fallback_reason(failure))
    try:
        return _store_provider_result(runtime, request, outcome, artifact, parent_ids)
    except ProviderOutputInvalid as error:
        failure = _output_invalid_failure(provider_id, error.diagnostic_digest)
        return _deterministic_fallback(runtime, request, fallback_reason(failure))


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
        failure = _identity_failure(
            provider_id, b"provider identity parent_artifact_ids mismatch"
        )
        return _deterministic_fallback(runtime, request, fallback_reason(failure))
    if outcome.provider_id != provider_id:
        failure = _identity_failure(provider_id, b"provider identity provider_id mismatch")
        return _deterministic_fallback(runtime, request, fallback_reason(failure))
    return _validated_provider_response(runtime, request, outcome, parent_ids, provider_id)


__all__ = [
    "FallbackV1",
    "ProviderOutputInvalid",
    "ProviderResolution",
    "fallback_reason",
    "generate_with_provider",
    "validate_provider_candidate",
]
