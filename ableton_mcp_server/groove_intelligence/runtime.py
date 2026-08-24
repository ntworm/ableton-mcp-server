"""Runtime-owned stores, cards, and exact MCP response budgeting."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, cast, runtime_checkable

from fastmcp.tools import ToolResult
from mcp.types import TextContent

from . import GrooveIndexInvalid
from .canonical import canonical_json
from .cards import (
    ArtifactCardV1,
    CapabilitiesV1,
    CapabilityV1,
    CompareCardV1,
    ConditionCardV1,
    EvidenceCardV1,
    GenerationCardV1,
)
from .constants import FEATURES_SCHEMA_VERSION, GRAMMAR_SCHEMA_VERSION, HVO_SCHEMA_VERSION
from .provider import GrooveProvider
from .schema import ArtifactId, MidiArtifactV1

_PROJECTION_VERSIONS = {
    "hvo": HVO_SCHEMA_VERSION,
    "features": FEATURES_SCHEMA_VERSION,
    "grammar": GRAMMAR_SCHEMA_VERSION,
}


class GrooveResponseBudgetExceeded(ValueError):
    """A complete tool result exceeds its byte budget."""


@runtime_checkable
class ArtifactStore(Protocol):
    def put(self, artifact: MidiArtifactV1) -> str: ...

    def get(self, artifact_id: str) -> MidiArtifactV1: ...

    def contains(self, artifact_id: str) -> bool: ...


class ResponseBudget:
    def __init__(self, max_bytes: int = 524_288) -> None:
        if max_bytes < 0:
            raise ValueError("max_bytes must be non-negative")
        self.max_bytes = max_bytes

    def measure_tool_result(self, result: ToolResult) -> int:
        return len(serialize_tool_result(result))

    def assert_tool_result(self, result: ToolResult) -> None:
        if self.measure_tool_result(result) > self.max_bytes:
            raise GrooveResponseBudgetExceeded("response budget exceeded")


def _wire_block(block: object) -> object:
    if hasattr(block, "model_dump"):
        return cast(
            object, block.model_dump(mode="json", by_alias=True, exclude_none=False)
        )
    return block


def serialize_tool_result(result: ToolResult) -> bytes:
    """Serialize the exact fields FastMCP exposes on a ToolResult once."""

    wire = {
        "structured_content": result.structured_content,
        "content": [_wire_block(block) for block in result.content],
        "is_error": result.is_error,
        "meta": result.meta,
    }
    return canonical_json(wire)


def assert_tool_result_budget(result: ToolResult, budget: ResponseBudget) -> None:
    budget.assert_tool_result(result)


def build_budgeted_json(value: object, budget: ResponseBudget) -> str:
    """Build canonical JSON and fail if its single text body exceeds a budget."""

    text = canonical_json(value).decode("utf-8")
    result = ToolResult(
        structured_content=value if isinstance(value, dict) else {"value": value},
        content=[TextContent(type="text", text=text)],
    )
    assert_tool_result_budget(result, budget)
    return text


class GrooveRuntime:
    def __init__(
        self,
        *,
        index: Any,
        store: ArtifactStore,
        client: Any | None = None,
        provider: GrooveProvider | None = None,
    ) -> None:
        self.index = index
        self.store = store
        self.client = client
        self.provider = provider

    def card(self, artifact_id: str) -> ArtifactCardV1:
        artifact = self.store.get(artifact_id)
        metadata = artifact.provenance
        projection_map: dict[str, str] = {}
        projection_values = metadata.get("_projection_values", {})
        if not isinstance(projection_values, Mapping):
            projection_values = {}
        for reference in artifact.projections[:3]:
            expected_version = _PROJECTION_VERSIONS.get(reference.name)
            if expected_version is None or reference.version != expected_version:
                raise GrooveIndexInvalid("artifact contains an unsupported projection reference")
            projection_id = reference.version
            projection_map[reference.name] = projection_id
            # Materialize bounded validated projections through the adapter.
            if projection_id not in projection_values:
                self.index.load_projection(artifact_id, projection_id)
        rights = str(metadata.get("redistribution", "derived_only"))
        if rights not in {"full", "derived_only", "blocked"}:
            rights = "derived_only"
        capability_values = metadata.get("capabilities", {})
        if not isinstance(capability_values, Mapping):
            capability_values = {}
        rights_level = int(
            metadata.get("rights_level", {"blocked": 0, "derived_only": 1, "full": 2}[rights])
        )
        apply_allowed = (
            bool(capability_values.get("apply", rights_level >= 2)) and rights_level >= 2
        )
        card = ArtifactCardV1(
            artifact_id=artifact.artifact_id,
            kind=artifact.kind,
            summary=dict(metadata.get("summary", {}))
            if isinstance(metadata.get("summary", {}), Mapping)
            else {},
            facets={
                str(axis): [str(item) for item in values]
                for axis, values in (
                    metadata.get("facets", {})
                    if isinstance(metadata.get("facets", {}), Mapping)
                    else {}
                ).items()
                if isinstance(values, (list, tuple))
            },
            features={
                str(name): value
                for name, value in (
                    metadata.get("features", {})
                    if isinstance(metadata.get("features", {}), Mapping)
                    else {}
                ).items()
                if isinstance(value, (str, int, float)) or value is None
            },
            projections=projection_map,
            rights_level=rights,  # type: ignore[arg-type]
            capabilities=CapabilitiesV1(
                evidence=CapabilityV1(allowed=bool(capability_values.get("evidence", True))),
                generate=CapabilityV1(
                    allowed=bool(capability_values.get("generate", rights_level >= 1))
                ),
                apply=CapabilityV1(allowed=apply_allowed),
            ),
            provenance={
                key: metadata[key]
                for key in ("corpus_id", "build_id", "license_id", "provenance_digest")
                if key in metadata
            },
            lineage=dict(artifact.lineage),
        )
        serialized = canonical_json(card.model_dump(exclude_none=True))
        if len(serialized) > 6 * 1024:
            raise GrooveResponseBudgetExceeded("artifact card exceeds 6 KiB")
        return card

    def card_from_search_row(self, row: Mapping[str, object]) -> ArtifactCardV1:
        """Project an indexed search row without loading projection BLOBs."""

        raw_facets = row.get("facets", ())
        facets: dict[str, list[str]] = {}
        if isinstance(raw_facets, (list, tuple)):
            for item in raw_facets:
                if isinstance(item, Mapping):
                    axis = str(item.get("axis", ""))
                    value = str(item.get("value", ""))
                    if axis and value:
                        facets.setdefault(axis, []).append(value)
        raw_features = row.get("features", ())
        features: dict[str, float | int | str | None] = {}
        if isinstance(raw_features, (list, tuple)):
            for item in raw_features:
                if isinstance(item, Mapping):
                    name = str(item.get("name", ""))
                    if name and item.get("status") == "available":
                        feature_value = item.get("value")
                        if isinstance(feature_value, (str, int, float)) or feature_value is None:
                            features[name] = feature_value
        raw_projections = row.get("projections", ())
        projections: dict[str, str] = {}
        if isinstance(raw_projections, (list, tuple)):
            for item in raw_projections:
                if isinstance(item, Mapping):
                    name = str(item.get("name", ""))
                    version = str(item.get("version", ""))
                    if name and version:
                        if _PROJECTION_VERSIONS.get(name) != version:
                            raise GrooveIndexInvalid(
                                "search row contains an unsupported projection reference"
                            )
                        projections[name] = version
        rights = str(row.get("redistribution", "derived_only"))
        if rights not in {"full", "derived_only", "blocked"}:
            rights = "derived_only"
        capabilities_raw = row.get("capabilities", {})
        capabilities: Mapping[str, object] = (
            capabilities_raw if isinstance(capabilities_raw, Mapping) else {}
        )
        raw_rights_level = row.get("rights_level", 0)
        rights_level = int(raw_rights_level) if isinstance(raw_rights_level, int) else 0
        raw_summary = row.get("summary", {})
        summary = (
            {str(key): value for key, value in raw_summary.items()}
            if isinstance(raw_summary, Mapping)
            else {}
        )
        return ArtifactCardV1(
            artifact_id=ArtifactId(str(row["artifact_id"])),
            kind=str(row.get("kind", "source")),  # type: ignore[arg-type]
            summary=summary,
            facets=facets,
            features=features,
            projections=projections,
            rights_level=rights,  # type: ignore[arg-type]
            capabilities=CapabilitiesV1(
                evidence=CapabilityV1(allowed=bool(capabilities.get("evidence", True))),
                generate=CapabilityV1(
                    allowed=bool(capabilities.get("generate", rights_level >= 1))
                ),
                apply=CapabilityV1(
                    allowed=bool(capabilities.get("apply", rights_level >= 2))
                ),
            ),
            provenance={
                key: row[key]
                for key in ("corpus_id", "build_id", "license_id", "provenance_digest")
                if key in row
            },
            lineage={},
        )

    def close(self) -> None:
        close = getattr(self.index, "close", None)
        if callable(close):
            close()


__all__ = [
    "ArtifactStore",
    "GrooveProvider",
    "GrooveResponseBudgetExceeded",
    "GrooveRuntime",
    "ResponseBudget",
    "assert_tool_result_budget",
    "build_budgeted_json",
    "serialize_tool_result",
    "ArtifactCardV1",
    "CompareCardV1",
    "ConditionCardV1",
    "EvidenceCardV1",
    "GenerationCardV1",
]
