"""Bounded evidence aggregation and deterministic card comparison."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from . import GrooveIndexInvalid
from .canonical import canonical_json, sha256_hex
from .cards import ArtifactCardV1, CompareCardV1, EvidenceCardV1
from .constants import FEATURES_SCHEMA_VERSION, GRAMMAR_SCHEMA_VERSION, HVO_SCHEMA_VERSION
from .mcp_models import (
    CompareRequestV1,
    CompareResponseV1,
    EvidenceRequestV1,
    EvidenceResponseV1,
    ProjectionId,
)
from .runtime import GrooveRuntime
from .schema import (
    ArtifactId,
    FeaturesProjectionV1,
    GrammarProjectionV1,
    HvoProjectionV1,
    MidiArtifactV1,
)
from .similarity import feature_distance, grammar_distance, hvo_distance


def evidence(runtime: GrooveRuntime, request: EvidenceRequestV1) -> EvidenceResponseV1:
    artifact = runtime.store.get(str(request.artifact_id))
    artifact_card = runtime.card(str(request.artifact_id))
    references: list[dict[str, object]] = []
    roles = artifact_card.summary.get("roles", [])
    if isinstance(roles, list):
        for role in sorted(str(item) for item in roles)[:32]:
            references.append({"role": role, "count": 1, "digest": artifact.events_digest})
    default_projection_ids: list[ProjectionId] = [
        cast(ProjectionId, HVO_SCHEMA_VERSION),
        cast(ProjectionId, FEATURES_SCHEMA_VERSION),
        cast(ProjectionId, GRAMMAR_SCHEMA_VERSION),
    ]
    requested_projections = set(request.include_projections or default_projection_ids)
    projection_digests = {
        reference.name: reference.digest
        for reference in artifact.projections
        if reference.name in requested_projections or reference.version in requested_projections
    }
    card = EvidenceCardV1(
        artifact_id=artifact.artifact_id,
        query_hash=request.query_hash,
        matched_facets=artifact_card.facets,
        feature_contributions=[
            {"name": name, "requested": False, "observed": value, "weight": 0.0, "distance": 0.0}
            for name, value in sorted(artifact_card.features.items())[:32]
        ],
        projection_digests=projection_digests,
        provenance_digest=str(artifact_card.provenance.get("provenance_digest", "")),
        references=references,
    )
    result = EvidenceResponseV1(
        artifact=artifact_card,
        card=card,
        provenance={"seed_bundle_id": runtime.index.manifest.seed_bundle_id},
    )
    if len(canonical_json(result.model_dump(mode="json"))) > 32 * 1024:
        result.card.feature_contributions = result.card.feature_contributions[:8]
        result.card.references = result.card.references[:8]
        result.card.truncated = True
    return result


def _projection(
    runtime: GrooveRuntime,
    artifact_id: str,
    projection_id: str | None,
) -> object | None:
    artifact = runtime.store.get(artifact_id)
    if projection_id is None:
        if artifact.kind == "generated":
            raise GrooveIndexInvalid("generated artifact projection reference is missing")
        return None
    if projection_id not in {
        HVO_SCHEMA_VERSION,
        FEATURES_SCHEMA_VERSION,
        GRAMMAR_SCHEMA_VERSION,
    }:
        raise GrooveIndexInvalid("projection schema version is unsupported")
    if artifact.kind == "generated":
        return _generated_projection(artifact, projection_id)
    return cast(object, runtime.index.load_projection(artifact_id, projection_id))


def _generated_projection(artifact: MidiArtifactV1, projection_id: str) -> object:
    raw_projection = _generated_projection_value(artifact, projection_id)
    try:
        if projection_id == HVO_SCHEMA_VERSION:
            return HvoProjectionV1.model_validate(raw_projection)
        if projection_id == FEATURES_SCHEMA_VERSION:
            return FeaturesProjectionV1.model_validate(raw_projection)
        return GrammarProjectionV1.model_validate(raw_projection)
    except ValueError as error:
        raise GrooveIndexInvalid("generated projection is invalid") from error


def _generated_projection_value(artifact: MidiArtifactV1, projection_id: str) -> Mapping[str, Any]:
    """The stored value of a generated projection, checked against its reference."""
    raw_values = artifact.provenance.get("_projection_values")
    if not isinstance(raw_values, Mapping):
        raise GrooveIndexInvalid("generated projection values are missing")
    raw_projection = raw_values.get(projection_id)
    if not isinstance(raw_projection, Mapping):
        raise GrooveIndexInvalid("generated projection value is missing")
    reference = next(
        (item for item in artifact.projections if item.version == projection_id),
        None,
    )
    if reference is None or reference.status != "available":
        raise GrooveIndexInvalid("generated projection reference is missing")
    if raw_projection.get("schema_version") != projection_id:
        raise GrooveIndexInvalid("generated projection schema version mismatch")
    if sha256_hex(canonical_json(raw_projection)) != reference.digest:
        raise GrooveIndexInvalid("generated projection digest mismatch")
    return raw_projection


def _projection_compatibility(
    cards: Sequence[ArtifactCardV1], projection_name: str
) -> str:
    present = [projection_name in card.projections for card in cards]
    if all(present):
        return "compatible"
    if any(present):
        return "incompatible"
    return "unavailable"


def _feature_compatibility(cards: Sequence[ArtifactCardV1], feature_name: str) -> str:
    values = [card.features.get(feature_name) for card in cards]
    if any(value is None for value in values):
        return "unavailable"
    first = values[0]
    return "compatible" if all(value == first for value in values[1:]) else "incompatible"


def _limitations(compatibility: dict[str, str]) -> list[str]:
    limitations: list[str] = []
    for name in ("features", "grammar", "hvo"):
        status = compatibility[name]
        if status == "unavailable":
            limitations.append(f"{name} projection unavailable")
        elif status == "incompatible":
            limitations.append(f"{name} projection sets are incompatible")
    meter_status = compatibility["meter"]
    if meter_status != "compatible":
        limitations.append(f"meter compatibility is {meter_status}")
    return limitations[:32]


def compare(runtime: GrooveRuntime, request: CompareRequestV1) -> CompareResponseV1:
    artifact_ids = [str(artifact_id) for artifact_id in request.artifact_ids]
    cards = [runtime.card(artifact_id) for artifact_id in artifact_ids]
    projections: dict[tuple[int, str], object | None] = {}

    def get_projection(index: int, name: str) -> object | None:
        key = (index, name)
        if key not in projections:
            card = cards[index]
            projection_id = card.projections.get(name)
            projections[key] = _projection(
                runtime,
                artifact_ids[index],
                projection_id,
            )
        return projections[key]

    matrices: list[list[float]] = []
    for left_index, left in enumerate(cards):
        row: list[float] = []
        for right_index, right in enumerate(cards):
            if left_index == right_index or left.artifact_id == right.artifact_id:
                row.append(0.0)
                continue
            row.append(
                _pair_distance(request.metrics, cards, get_projection, left_index, right_index)
            )
        matrices.append(row)
    common = sorted(
        set(cards[0].projections).intersection(*(set(card.projections) for card in cards[1:]))
    )
    compatibility = _compare_compatibility(cards)
    compare_card = CompareCardV1(
        artifact_ids=[ArtifactId(str(item)) for item in request.artifact_ids],
        metric_schema=list(request.metrics),
        matrix=matrices,
        compatibility=compatibility,
        common_projections=common[:3],
        lineage={"artifact_ids": artifact_ids},
        limitations=_limitations(compatibility),
    )
    return CompareResponseV1(
        items=cards,
        card=compare_card,
        provenance={"seed_bundle_id": runtime.index.manifest.seed_bundle_id},
    )


def _pair_distance(
    metrics: Sequence[str],
    cards: Sequence[ArtifactCardV1],
    get_projection: Callable[[int, str], object | None],
    left_index: int,
    right_index: int,
) -> float:
    """Mean of the requested metric distances between two cards."""
    left, right = cards[left_index], cards[right_index]
    distances: list[float] = []
    if "facets" in metrics:
        distances.append(_facet_distance(left, right))
    measures: tuple[tuple[str, Callable[[object | None, object | None], float]], ...] = (
        ("features", feature_distance),
        ("hvo", hvo_distance),
        ("grammar", grammar_distance),
    )
    for name, distance in measures:
        if name in metrics:
            left_value = get_projection(left_index, name)
            right_value = get_projection(right_index, name)
            distances.append(
                1.0
                if left_value is None or right_value is None
                else distance(left_value, right_value)
            )
    return round(sum(distances) / len(distances), 9) if distances else 0.0


def _facet_distance(left: ArtifactCardV1, right: ArtifactCardV1) -> float:
    """Share of facet axes whose value sets differ between two cards."""
    axes = sorted(set(left.facets) | set(right.facets))
    return (
        0.0
        if not axes
        else sum(
            0.0
            if set(left.facets.get(axis, [])) == set(right.facets.get(axis, []))
            else 1.0
            for axis in axes
        )
        / len(axes)
    )


def _compare_compatibility(cards: Sequence[ArtifactCardV1]) -> dict[str, str]:
    """Compatibility of the compared cards for PPQ, meter and each projection."""
    compatibility = {
        "ppq": (
            "unavailable"
            if any(card.features.get("ppq") is None for card in cards)
            else "compatible"
        ),
        "meter": _feature_compatibility(cards, "meter"),
    }
    for projection_name in ("features", "grammar", "hvo"):
        compatibility[projection_name] = _projection_compatibility(cards, projection_name)
    return compatibility


__all__ = ["compare", "evidence"]
