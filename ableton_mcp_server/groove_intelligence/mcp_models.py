"""Versioned, bounded request and response models for groove retrieval."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from .cards import ArtifactCardV1, CompareCardV1, EvidenceCardV1, GenerationCardV1
from .constants import RANKER_SCHEMA
from .schema import GrooveModel

ArtifactId = Annotated[str, Field(pattern=r"^ga1_[0-9a-f]{64}$", min_length=68, max_length=68)]
SeedBundleId = Annotated[str, Field(pattern=r"^gsb1_[0-9a-f]{64}$", min_length=69, max_length=69)]
QueryText = Annotated[str, Field(min_length=1, max_length=256)]
FacetValue = Annotated[str, Field(min_length=1, max_length=64)]
ProjectionId = Literal["groove.hvo.v2", "groove.features.v2", "groove.grammar.v2"]
ProjectionIds = Annotated[list[ProjectionId], Field(min_length=1, max_length=3)]
ProjectionSelection = Annotated[list[ProjectionId], Field(max_length=3)]
FacetKey = Annotated[str, Field(min_length=1, max_length=32)]
FacetMap = Annotated[
    dict[FacetKey, Annotated[list[FacetValue], Field(min_length=1, max_length=32)]],
    Field(max_length=16),
]
FeatureConstraints = Annotated[list[dict[str, object]], Field(max_length=32)]
BpmRange = Annotated[tuple[float, float], Field(min_length=2, max_length=2)]
Cursor = Annotated[str, Field(min_length=1, max_length=4096)]
QueryHash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", min_length=64, max_length=64)]
TransformMap = Annotated[dict[str, Annotated[float, Field(ge=-1.0, le=1.0)]], Field(max_length=16)]
InlineSearch = Annotated[dict[str, object], Field(min_length=1, max_length=12)]
ArtifactIdList = Annotated[list[ArtifactId], Field(min_length=2, max_length=8)]
ReferenceArtifactIdList = Annotated[list[ArtifactId], Field(max_length=7)]
MetricList = Annotated[
    list[Literal["facets", "features", "hvo", "grammar"]], Field(min_length=1, max_length=4)
]
GenerationSeed = Annotated[int, Field(ge=0, le=9_223_372_036_854_775_807)]
GenerationBars = Annotated[int, Field(ge=1, le=64)]
SearchLimit = Annotated[int, Field(ge=1, le=50)]


class SearchRequestV1(GrooveModel):
    schema_version: Literal["groove.search.request.v1"]
    query: QueryText | None = None
    facets: FacetMap | None = None
    feature_constraints: FeatureConstraints | None = None
    bpm: BpmRange | None = None
    meter: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    seed_bundle_id: SeedBundleId | None = None
    required_projection_ids: ProjectionIds | None = None
    projection_operator: Literal["all", "any"] = "all"
    limit: SearchLimit = 20
    cursor: Cursor | None = None

    @model_validator(mode="after")
    def _criterion_required(self) -> SearchRequestV1:
        if not any(
            (
                self.query,
                self.facets,
                self.feature_constraints,
                self.bpm,
                self.meter,
                self.required_projection_ids,
            )
        ):
            raise ValueError("search request requires at least one criterion")
        if self.bpm is not None and self.bpm[0] > self.bpm[1]:
            raise ValueError("bpm range is reversed")
        return self


GrooveSearchRequest = SearchRequestV1


class GrooveSourceV1(GrooveModel):
    artifact_id: ArtifactId | None = None
    search: InlineSearch | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> GrooveSourceV1:
        if (self.artifact_id is None) == (self.search is None):
            raise ValueError("source requires exactly one artifact_id or search")
        return self


class SearchCriteriaV1(GrooveModel):
    query: str | None = None
    facets: dict[str, list[str]] | None = None
    feature_constraints: list[dict[str, Any]] | None = None
    bpm: tuple[float, float] | None = None
    meter: str | None = None
    required_projection_ids: list[str] | None = None
    projection_operator: Literal["all", "any"] = "all"


class RankingV1(GrooveModel):
    ranker_id: str
    weights: dict[str, float]
    projection_coverage_active: bool = False


class RankedCandidateV1(GrooveModel):
    artifact_id: str
    score: float
    text_score: float = 0.0
    facets_score: float = 0.0
    features_score: float = 0.0
    projection_score: float = 0.0


class SearchCursorV1(GrooveModel):
    schema_version: Literal["groove.search.cursor.v2"] = "groove.search.cursor.v2"
    seed_bundle_id: str = Field(min_length=1, max_length=128)
    logical_index_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    ranker_id: str
    ranker_manifest_digest: str = Field(default="", pattern=r"^(|[0-9a-f]{64})$")
    ranker_schema: str = RANKER_SCHEMA
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    limit: int = Field(ge=1, le=50)
    last_score: float
    last_artifact_id: str = Field(pattern=r"^ga1_[0-9a-f]{64}$")


class SearchResponseV1(GrooveModel):
    schema_version: Literal["groove.search.response.v1"] = "groove.search.response.v1"
    items: list[ArtifactCardV1] = Field(default_factory=list, max_length=50)
    total_hint: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    omitted_count: int = Field(ge=0)
    truncated: bool = False
    next_cursor: str | None = None
    ranking: RankingV1
    provenance: dict[str, Any] = Field(default_factory=dict)


class EvidenceRequestV1(GrooveModel):
    schema_version: Literal["groove.evidence.request.v1"]
    artifact_id: ArtifactId
    query_hash: QueryHash | None = None
    include_projections: ProjectionSelection | None = None


GrooveEvidenceRequest = EvidenceRequestV1


class GenerateRequestV1(GrooveModel):
    schema_version: Literal["groove.generate.request.v1"]
    source: GrooveSourceV1
    transforms: TransformMap
    bars: GenerationBars
    seed: GenerationSeed
    provider: Literal["deterministic", "neural"] = "deterministic"
    reference_artifact_ids: ReferenceArtifactIdList = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_transforms(self) -> GenerateRequestV1:
        if any(value < -1.0 or value > 1.0 for value in self.transforms.values()):
            raise ValueError("transform is outside [-1, 1]")
        unknown = set(self.transforms) - {
            "density",
            "syncopation",
            "swing",
            "microtiming",
            "energy",
            "complexity",
        }
        if unknown:
            raise ValueError("unknown transform axis")
        return self


GrooveGenerateRequest = GenerateRequestV1


class CompareRequestV1(GrooveModel):
    schema_version: Literal["groove.compare.request.v1"]
    artifact_ids: ArtifactIdList
    metrics: MetricList
    normalize: bool = True


GrooveCompareRequest = CompareRequestV1


class ApplyRequestV1(GrooveModel):
    schema_version: Literal["groove.apply.request.v1"]
    artifact_id: ArtifactId
    track_index: Annotated[int, Field(ge=0)]
    clip_index: Annotated[int, Field(ge=0)]
    kit_mapping_profile: Annotated[
        str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    ]
    source_track_index: Annotated[int, Field(ge=0)] | None = None
    source_channel: Annotated[int, Field(ge=0, le=15)] | None = None
    mode: Literal["preview", "commit"] = "preview"
    expected_empty_slot: bool = True

    @model_validator(mode="after")
    def validate_source_selector_pair(self) -> ApplyRequestV1:
        if (self.source_track_index is None) != (self.source_channel is None):
            raise ValueError("source_track_index and source_channel must be provided together")
        return self


GrooveApplyRequest = ApplyRequestV1
GROOVE_REQUEST_MODEL_BY_TOOL: dict[str, type[GrooveModel]] = {
    "groove_search": SearchRequestV1,
    "groove_evidence": EvidenceRequestV1,
    "groove_generate": GenerateRequestV1,
    "groove_compare": CompareRequestV1,
    "groove_apply": ApplyRequestV1,
}


class EvidenceResponseV1(GrooveModel):
    schema_version: Literal["groove.evidence.response.v1"] = "groove.evidence.response.v1"
    artifact: ArtifactCardV1
    card: EvidenceCardV1
    provenance: dict[str, Any] = Field(default_factory=dict)


class GenerationResponseV1(GrooveModel):
    schema_version: Literal["groove.generate.response.v1"] = "groove.generate.response.v1"
    artifact: ArtifactCardV1
    card: GenerationCardV1
    provenance: dict[str, Any] = Field(default_factory=dict)


class CompareResponseV1(GrooveModel):
    schema_version: Literal["groove.compare.response.v1"] = "groove.compare.response.v1"
    items: list[ArtifactCardV1] = Field(default_factory=list, max_length=8)
    card: CompareCardV1
    provenance: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "GrooveSearchRequest",
    "GrooveCompareRequest",
    "GrooveEvidenceRequest",
    "GrooveGenerateRequest",
    "GrooveSourceV1",
    "CompareRequestV1",
    "CompareResponseV1",
    "ApplyRequestV1",
    "GrooveApplyRequest",
    "GROOVE_REQUEST_MODEL_BY_TOOL",
    "EvidenceRequestV1",
    "EvidenceResponseV1",
    "GenerateRequestV1",
    "GenerationResponseV1",
    "RankedCandidateV1",
    "RankingV1",
    "SearchCriteriaV1",
    "SearchCursorV1",
    "SearchRequestV1",
    "SearchResponseV1",
]
