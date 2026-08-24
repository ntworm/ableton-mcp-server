"""Bounded public cards for the deterministic groove runtime."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, field_validator

from .schema import ArtifactId, GrooveModel, MidiArtifactV1

_PUBLIC_SUMMARY_KEYS = frozenset(
    {
        "bars",
        "meter",
        "roles",
        "generator",
        "taxonomy_version",
        "tempo",
        "bpm",
        "ppq",
        "length_ticks",
        "hits_per_bar",
        "density",
        "dynamics",
        "timing",
        "swing",
        "microtiming",
        "source_kind",
        "redistribution",
        "rights_level",
    }
)
_PUBLIC_LINEAGE_KEYS = frozenset({"parent_artifact_ids", "relations", "ordinals"})
_PUBLIC_PROVENANCE_KEYS = frozenset(
    {"corpus_id", "build_id", "license_id", "license_ids", "provenance_digest"}
)
_PRIVATE_CARD_KEYS = frozenset(
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
_DROP = object()


def _is_private_card_key(value: str) -> bool:
    key = value.casefold().replace("-", "_")
    return key in _PRIVATE_CARD_KEYS or "path" in key or key.startswith("private")


def _sanitize_public_value(
    value: object, *, allowed_keys: frozenset[str], depth: int = 0
) -> object:
    """Keep only small, explicitly public card values at every nesting level."""

    if depth > 4:
        return _DROP
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for index, (raw_key, raw_value) in enumerate(value.items()):
            if index >= 64:
                break
            key = str(raw_key)
            if key not in allowed_keys or _is_private_card_key(key):
                continue
            sanitized = _sanitize_public_value(
                raw_value,
                allowed_keys=allowed_keys,
                depth=depth + 1,
            )
            if sanitized is not _DROP:
                result[key] = sanitized
        return result
    if isinstance(value, (list, tuple)):
        items: list[object] = []
        for item in value[:32]:
            sanitized = _sanitize_public_value(
                item,
                allowed_keys=allowed_keys,
                depth=depth + 1,
            )
            if sanitized is not _DROP:
                items.append(sanitized)
        return items
    if isinstance(value, str):
        if re.search(r"(?i)(?:[a-z]:[\\/]|^[/\\]|\\\\)", value):
            return _DROP
        return value[:128]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value if len(str(value)) <= 32 else _DROP
    if isinstance(value, float):
        return value if math.isfinite(value) else _DROP
    return _DROP


def _sanitize_public_mapping(
    value: Mapping[str, Any] | object, *, allowed_keys: frozenset[str]
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    sanitized = _sanitize_public_value(value, allowed_keys=allowed_keys)
    return sanitized if isinstance(sanitized, dict) else {}


class CapabilityV1(GrooveModel):
    allowed: bool
    reason: str | None = Field(default=None, max_length=256)


class CapabilitiesV1(GrooveModel):
    evidence: CapabilityV1
    generate: CapabilityV1
    apply: CapabilityV1


class ConditionCardV1(GrooveModel):
    schema_version: Literal["groove.card.condition.v1"] = "groove.card.condition.v1"
    summary: dict[str, Any] = Field(default_factory=dict)
    facets: dict[str, list[str]] = Field(default_factory=dict)
    features: dict[str, float | int | str | None] = Field(default_factory=dict)
    projections: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("summary")
    @classmethod
    def _public_summary(cls, value: dict[str, Any]) -> dict[str, Any]:
        sanitized = _sanitize_public_mapping(value, allowed_keys=_PUBLIC_SUMMARY_KEYS)
        if len(sanitized) > 32:
            raise ValueError("summary has too many fields")
        return sanitized


class ArtifactCardV1(GrooveModel):
    schema_version: Literal["groove.card.artifact.v1"] = "groove.card.artifact.v1"
    artifact_id: ArtifactId
    kind: Literal["source", "generated", "mapped"]
    summary: dict[str, Any] = Field(default_factory=dict)
    facets: dict[str, list[str]] = Field(default_factory=dict)
    features: dict[str, float | int | str | None] = Field(default_factory=dict)
    projections: dict[str, str] = Field(default_factory=dict)
    rights_level: Literal["full", "derived_only", "blocked"]
    capabilities: CapabilitiesV1
    provenance: dict[str, Any] = Field(default_factory=dict)
    lineage: dict[str, Any] = Field(default_factory=dict)

    @field_validator("summary")
    @classmethod
    def _bounded_summary(cls, value: dict[str, Any]) -> dict[str, Any]:
        sanitized = _sanitize_public_mapping(value, allowed_keys=_PUBLIC_SUMMARY_KEYS)
        if len(sanitized) > 32:
            raise ValueError("summary has too many fields")
        return sanitized

    @field_validator("facets")
    @classmethod
    def _bounded_facets(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        if len(value) > 16 or any(len(values) > 32 for values in value.values()):
            raise ValueError("facets exceed card bounds")
        return value

    @field_validator("features")
    @classmethod
    def _bounded_features(
        cls, value: dict[str, float | int | str | None]
    ) -> dict[str, float | int | str | None]:
        if len(value) > 64:
            raise ValueError("features exceed card bounds")
        return value

    @field_validator("provenance")
    @classmethod
    def _public_provenance(cls, value: dict[str, Any]) -> dict[str, Any]:
        sanitized = _sanitize_public_mapping(value, allowed_keys=_PUBLIC_PROVENANCE_KEYS)
        if len(sanitized) > 16:
            raise ValueError("provenance has too many fields")
        return sanitized

    @field_validator("lineage")
    @classmethod
    def _public_lineage(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _sanitize_public_mapping(value, allowed_keys=_PUBLIC_LINEAGE_KEYS)


class EvidenceCardV1(GrooveModel):
    schema_version: Literal["groove.card.evidence.v1"] = "groove.card.evidence.v1"
    artifact_id: ArtifactId
    query_hash: str | None = None
    matched_facets: dict[str, list[str]] = Field(default_factory=dict)
    feature_contributions: list[dict[str, Any]] = Field(default_factory=list, max_length=32)
    projection_digests: dict[str, str] = Field(default_factory=dict)
    provenance_digest: str = ""
    limitations: list[str] = Field(default_factory=list, max_length=32)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    references: list[dict[str, Any]] = Field(default_factory=list, max_length=32)
    truncated: bool = False


class GenerationCardV1(GrooveModel):
    schema_version: Literal["groove.card.generation.v1"] = "groove.card.generation.v1"
    artifact_id: ArtifactId
    parent_artifact_ids: tuple[ArtifactId, ...] = Field(default_factory=tuple, max_length=8)
    generator_id: str = "groove-deterministic-v2"
    generator_version: str = "1"
    transforms: dict[str, float] = Field(default_factory=dict)
    seed: int = Field(ge=0)
    provider_requested: str = "deterministic"
    provider_resolved: str = "deterministic"
    fallback: bool | dict[str, str] = False
    summary: dict[str, Any] = Field(default_factory=dict)
    mapping_summary: dict[str, Any] = Field(default_factory=dict)
    deterministic: bool = True
    reproducibility_key: str = ""
    lineage: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("summary")
    @classmethod
    def _public_summary(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _sanitize_public_mapping(value, allowed_keys=_PUBLIC_SUMMARY_KEYS)

    @field_validator("lineage")
    @classmethod
    def _public_lineage(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _sanitize_public_mapping(value, allowed_keys=_PUBLIC_LINEAGE_KEYS)


def artifact_card_from_artifact(artifact: MidiArtifactV1) -> ArtifactCardV1:
    """Validate a bounded public card before a derived artifact is persisted."""

    metadata = artifact.provenance
    rights = str(metadata.get("redistribution", "derived_only"))
    if rights not in {"full", "derived_only", "blocked"}:
        rights = "derived_only"
    raw_facets = metadata.get("facets", {})
    facets: dict[str, list[str]] = {}
    if isinstance(raw_facets, Mapping):
        for raw_axis, values in sorted(
            raw_facets.items(), key=lambda item: str(item[0])
        )[:16]:
            axis = str(raw_axis)
            if isinstance(values, (list, tuple)):
                facets[axis] = sorted({str(value) for value in values})[:32]
    raw_features = metadata.get("features", {})
    features: dict[str, float | int | str | None] = {}
    if isinstance(raw_features, Mapping):
        for name, value in sorted(raw_features.items(), key=lambda item: str(item[0])):
            if len(features) >= 64:
                break
            if isinstance(value, (str, int, float)) or value is None:
                features[str(name)] = value
    raw_summary = metadata.get("summary", {})
    summary = _sanitize_public_mapping(raw_summary, allowed_keys=_PUBLIC_SUMMARY_KEYS)
    capability_values = metadata.get("capabilities", {})
    capabilities = capability_values if isinstance(capability_values, Mapping) else {}
    raw_rights_level = metadata.get(
        "rights_level", {"blocked": 0, "derived_only": 1, "full": 2}[rights]
    )
    try:
        rights_level = max(0, min(2, int(raw_rights_level)))
    except (TypeError, ValueError):
        rights_level = {"blocked": 0, "derived_only": 1, "full": 2}[rights]
    projection_map = {reference.name: reference.version for reference in artifact.projections[:3]}
    public_provenance: dict[str, Any] = {}
    for key in ("corpus_id", "build_id", "license_id", "license_ids", "provenance_digest"):
        if key not in metadata:
            continue
        value = metadata[key]
        if key == "license_ids" and isinstance(value, (list, tuple)):
            value = [str(item) for item in value[:8]]
        public_provenance[key] = value
    return ArtifactCardV1(
        artifact_id=artifact.artifact_id,
        kind=artifact.kind,
        summary=summary,
        facets=facets,
        features=features,
        projections=projection_map,
        rights_level=rights,  # type: ignore[arg-type]
        capabilities=CapabilitiesV1(
            evidence=CapabilityV1(allowed=bool(capabilities.get("evidence", True))),
            generate=CapabilityV1(allowed=bool(capabilities.get("generate", rights_level >= 1))),
            apply=CapabilityV1(
                allowed=bool(capabilities.get("apply", rights_level >= 2)) and rights_level >= 2
            ),
        ),
        provenance=public_provenance,
        lineage=_sanitize_public_mapping(artifact.lineage, allowed_keys=_PUBLIC_LINEAGE_KEYS),
    )


class CompareCardV1(GrooveModel):
    schema_version: Literal["groove.card.compare.v1"] = "groove.card.compare.v1"
    artifact_ids: list[ArtifactId] = Field(min_length=2, max_length=8)
    metric_schema: list[str] = Field(default_factory=list, max_length=4)
    matrix: list[list[float]] = Field(default_factory=list, max_length=8)
    facet_differences: dict[str, Any] = Field(default_factory=dict)
    compatibility: dict[str, Any] = Field(default_factory=dict)
    common_projections: list[str] = Field(default_factory=list, max_length=3)
    lineage: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("lineage")
    @classmethod
    def _public_lineage(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _sanitize_public_mapping(value, allowed_keys=_PUBLIC_LINEAGE_KEYS)


__all__ = [
    "ArtifactCardV1",
    "CapabilityV1",
    "CapabilitiesV1",
    "CompareCardV1",
    "ConditionCardV1",
    "EvidenceCardV1",
    "GenerationCardV1",
    "artifact_card_from_artifact",
]
