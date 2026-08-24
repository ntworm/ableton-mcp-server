"""Per-test runtime factories for the deterministic groove test suites."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ableton_mcp_server.groove_intelligence.index import ReadonlyGrooveIndex, open_readonly_index
from ableton_mcp_server.groove_intelligence.runtime import GrooveRuntime
from ableton_mcp_server.groove_intelligence.schema import ArtifactId, MidiArtifactV1
from tests.fixtures.groove_bundle import build_pilot_bundle


class MemoryArtifactStore:
    def __init__(self) -> None:
        self._items: dict[str, MidiArtifactV1] = {}

    def put(self, artifact: MidiArtifactV1) -> ArtifactId:
        self._items[str(artifact.artifact_id)] = artifact
        return artifact.artifact_id

    def get(self, artifact_id: str) -> MidiArtifactV1:
        return self._items[artifact_id]

    def contains(self, artifact_id: str) -> bool:
        return artifact_id in self._items


def build_source_artifact_from_bundle(bundle_dir: Path, artifact_id: str) -> MidiArtifactV1:
    index = open_readonly_index(bundle_dir)
    try:
        return index.load_artifact(artifact_id)
    finally:
        index.close()


def populate_pilot_store(
    index: ReadonlyGrooveIndex,
    store: MemoryArtifactStore,
    bundle_dir: Path,
) -> None:
    del bundle_dir
    for artifact_id in index.manifest.artifact_ids:
        store.put(index.load_artifact(str(artifact_id)))


def make_pilot_runtime(tmp_path: Path) -> GrooveRuntime:
    bundle_dir = build_pilot_bundle(tmp_path)
    index = open_readonly_index(bundle_dir)
    store = MemoryArtifactStore()
    populate_pilot_store(index, store, bundle_dir)
    return GrooveRuntime(index=index, store=store)


def make_pilot_card(runtime: GrooveRuntime) -> Any:
    return runtime.card(str(runtime.index.manifest.artifact_ids[0]))


def make_search_request(**kwargs: Any) -> Any:
    from ableton_mcp_server.groove_intelligence.mcp_models import SearchRequestV1

    values = {
        "schema_version": "groove.search.request.v1",
        "query": None,
        "facets": None,
        "limit": 20,
        "cursor": None,
    }
    values.update(kwargs)
    return SearchRequestV1(**values)


def make_generate_request(runtime: GrooveRuntime, **kwargs: Any) -> Any:
    from ableton_mcp_server.groove_intelligence.mcp_models import GenerateRequestV1

    values = {
        "schema_version": "groove.generate.request.v1",
        "source": {"artifact_id": str(runtime.index.manifest.artifact_ids[0])},
        "transforms": {"density": 0.2},
        "bars": 4,
        "seed": 7,
        "provider": "deterministic",
    }
    values.update(kwargs)
    return GenerateRequestV1(**values)


def make_evidence_request(runtime: GrooveRuntime) -> Any:
    from ableton_mcp_server.groove_intelligence.mcp_models import EvidenceRequestV1

    return EvidenceRequestV1(
        schema_version="groove.evidence.request.v1",
        artifact_id=str(runtime.index.manifest.artifact_ids[0]),
        include_projections=["groove.hvo.v2", "groove.features.v2", "groove.grammar.v2"],
    )


def make_compare_request(runtime: GrooveRuntime) -> Any:
    from ableton_mcp_server.groove_intelligence.mcp_models import CompareRequestV1

    return CompareRequestV1(
        schema_version="groove.compare.request.v1",
        artifact_ids=[str(item) for item in runtime.index.manifest.artifact_ids[:2]],
        metrics=["facets", "features", "hvo", "grammar"],
        normalize=True,
    )


def make_pilot_acceptance_inputs(tmp_path: Path) -> tuple[GrooveRuntime, dict[str, object]]:
    runtime = make_pilot_runtime(tmp_path)
    return runtime, {
        "search": make_search_request(facets={"feel": ["laid_back"]}, limit=1),
        "evidence": make_evidence_request(runtime),
        "generate": make_generate_request(runtime),
        "compare": make_compare_request(runtime),
    }
