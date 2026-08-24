"""Pydantic value objects shared by the phase-one compiler and index."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, NewType

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .constants import (
    FEATURES_SCHEMA_VERSION,
    GRAMMAR_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION,
    INDEX_SCHEMA_VERSION,
    NORMALIZER_ID,
    PARSER_ID,
    RANKER_ID,
    SEED_SCHEMA_VERSION,
)

ArtifactId = NewType("ArtifactId", str)
Redistribution = Literal["full", "derived_only", "blocked"]
ArtifactKind = Literal["source", "generated", "mapped"]


class GrooveModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


class BuildInput(GrooveModel):
    path: Path
    source_kind: str
    license_id: str
    redistribution: Redistribution


class MidiEventV1(GrooveModel):
    track_index: int = Field(ge=0)
    event_index: int = Field(ge=0)
    event_id: int = Field(ge=0)
    delta_ticks: int = Field(ge=0)
    absolute_ticks: int = Field(ge=0)
    event_type: str
    channel: int | None = Field(default=None, ge=0, le=15)
    status: int | None = Field(default=None, ge=0, le=255)
    payload_hex: str = ""
    meta_type: int | None = Field(default=None, ge=0, le=255)


class NoteEventV1(GrooveModel):
    event_id: int = Field(ge=0)
    close_event_id: int | None = Field(default=None, ge=0)
    close_order: int | None = Field(default=None, ge=0)
    track_index: int = Field(ge=0)
    channel: int = Field(ge=0, le=15)
    pitch: int = Field(ge=0, le=127)
    velocity: int = Field(ge=1, le=127)
    start_ticks: int = Field(ge=0)
    duration_ticks: int = Field(ge=0)

    @property
    def absolute_ticks(self) -> int:
        return self.start_ticks


class SmfFormatV1(GrooveModel):
    smf_type: int = Field(ge=0, le=2)
    ppq: int = Field(gt=0)
    track_count: int = Field(ge=0, le=256)


class TrackInfoV1(GrooveModel):
    track_index: int = Field(ge=0)
    name: str = ""
    events_digest: str = ""
    event_count: int = Field(default=0, ge=0)


class CompressedBlobV1(GrooveModel):
    codec: str
    raw_size: int = Field(ge=0)
    compressed_size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    blob: bytes


class ProjectionRefV1(GrooveModel):
    name: str
    version: str
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["available", "unavailable"] = "available"


class MidiArtifactV1(GrooveModel):
    schema_version: str = "groove.midi-artifact.v1"
    artifact_id: ArtifactId = Field(pattern=r"^ga1_[0-9a-f]{64}$")
    kind: ArtifactKind = "source"
    format: SmfFormatV1
    timing: dict[str, Any] = Field(default_factory=dict)
    tracks: tuple[TrackInfoV1, ...] = ()
    payload: CompressedBlobV1
    events_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance: dict[str, Any] = Field(default_factory=dict)
    lineage: dict[str, Any] = Field(default_factory=dict)
    projections: tuple[ProjectionRefV1, ...] = ()


class BuildManifestInputV1(GrooveModel):
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_id: ArtifactId = Field(pattern=r"^ga1_[0-9a-f]{64}$")
    source_kind: str
    license_id: str
    redistribution: Redistribution
    provenance_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class BuildManifestV1(GrooveModel):
    schema_version: str = "groove.build-manifest.v1"
    corpus_id: str
    build_id: str
    parser_id: str = PARSER_ID
    normalizer_id: str = NORMALIZER_ID
    projection_versions: dict[str, str] = Field(
        default_factory=lambda: {
            "hvo": HVO_SCHEMA_VERSION,
            "features": FEATURES_SCHEMA_VERSION,
            "grammar": GRAMMAR_SCHEMA_VERSION,
        }
    )
    limits: dict[str, int] = Field(default_factory=dict)
    inputs: tuple[BuildManifestInputV1, ...] = ()
    manifest_digest: str = Field(default="" , pattern=r"^(|[0-9a-f]{64})$")


class GrooveSeedBundleManifestV1(GrooveModel):
    seed_schema: str = SEED_SCHEMA_VERSION
    seed_bundle_id: str
    corpus_id: str
    build_id: str
    schema_version: str = INDEX_SCHEMA_VERSION
    parser_id: str = PARSER_ID
    normalizer_id: str = NORMALIZER_ID
    projection_versions: dict[str, str] = Field(default_factory=dict)
    limits: dict[str, int] = Field(default_factory=dict)
    inputs: tuple[BuildManifestInputV1, ...] = ()
    artifact_ids: tuple[ArtifactId, ...] = ()
    ranker_id: str = RANKER_ID
    ranker_manifest_digest: str = ""
    logical_index_digest: str = ""
    bundle_manifest_digest: str = ""
    manifest_digest: str = ""
    file_checksums: dict[str, str] = Field(default_factory=dict)

    @field_validator("artifact_ids")
    @classmethod
    def validate_artifact_ids(cls, value: tuple[ArtifactId, ...]) -> tuple[ArtifactId, ...]:
        for artifact_id in value:
            if not str(artifact_id).startswith("ga1_"):
                raise ValueError("artifact_id must use ga1_ prefix")
        return value


class CompiledGrooveArtifactV1(GrooveModel):
    artifact: MidiArtifactV1
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_kind: str
    license_id: str
    redistribution: Redistribution
    rights_level: int = Field(ge=0, le=2)
    capabilities: dict[str, bool] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    facets: tuple[dict[str, Any], ...] = ()
    features: tuple[dict[str, Any], ...] = ()
    projections: tuple[dict[str, Any], ...] = ()
    lineage_rows: tuple[dict[str, Any], ...] = ()
    provenance_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @property
    def artifact_id(self) -> ArtifactId:
        return self.artifact.artifact_id


class HvoCellV1(GrooveModel):
    role: str
    bar: int = Field(ge=0)
    step: int = Field(ge=0)
    hit: int = Field(ge=0, le=1)
    velocity: float = Field(ge=0.0, le=1.0)
    offset_ticks: int
    event_ids: list[int] = Field(default_factory=list)


class HvoProjectionV1(GrooveModel):
    schema_version: str = HVO_SCHEMA_VERSION
    grid_ticks: int = Field(gt=0)
    roles: tuple[str, ...]
    cells: list[HvoCellV1]
    source_events_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class FeatureValueV1(GrooveModel):
    value: float | int | str | None = None
    unit: str = ""
    algorithm_version: str = "groove-features-v2"
    status: Literal["available", "unavailable"] = "available"


class FeaturesProjectionV1(GrooveModel):
    schema_version: str = FEATURES_SCHEMA_VERSION
    values: dict[str, FeatureValueV1]
    source_events_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class GrammarProjectionV1(GrooveModel):
    schema_version: str = GRAMMAR_SCHEMA_VERSION
    tokens: list[dict[str, Any]] = Field(default_factory=list)
    transitions: list[dict[str, Any]] = Field(default_factory=list)
    source_events_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
