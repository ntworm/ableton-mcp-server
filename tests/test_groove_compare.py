from __future__ import annotations

from pathlib import Path

import pytest

from ableton_mcp_server.groove_intelligence import GrooveIndexInvalid
from ableton_mcp_server.groove_intelligence.build import (
    authorize_input,
    build_seed_bundle,
    compile_one,
)
from ableton_mcp_server.groove_intelligence.canonical import canonical_json
from ableton_mcp_server.groove_intelligence.constants import (
    FEATURES_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION,
)
from ableton_mcp_server.groove_intelligence.deterministic import deterministic_generate
from ableton_mcp_server.groove_intelligence.evidence import compare, evidence
from ableton_mcp_server.groove_intelligence.index import open_readonly_index, write_index
from ableton_mcp_server.groove_intelligence.mcp_models import CompareRequestV1
from ableton_mcp_server.groove_intelligence.runtime import GrooveRuntime
from ableton_mcp_server.groove_intelligence.schema import BuildInput
from ableton_mcp_server.groove_intelligence.similarity import feature_distance
from tests.fixtures.groove_runtime import (
    make_compare_request,
    make_evidence_request,
    make_generate_request,
    make_pilot_runtime,
)
from tests.fixtures.groove_smf import MINIMAL_TYPE1_SMF


def _build_compare_runtime(tmp_path: Path, *, right_start: int = 120) -> GrooveRuntime:
    source_root = tmp_path / "corpus"
    source_root.mkdir(parents=True)
    left_path = source_root / "same-name-left.mid"
    right_path = source_root / "same-name-right.mid"
    left_path.write_bytes(MINIMAL_TYPE1_SMF)
    right_path.write_bytes(
        MINIMAL_TYPE1_SMF.replace(
            b"\x00\x99\x24\x64", bytes([right_start]) + b"\x99\x24\x64"
        )
    )
    inputs = [
        BuildInput(
            path=left_path,
            source_kind="author",
            license_id="private-full",
            redistribution="full",
        ),
        BuildInput(
            path=right_path,
            source_kind="author",
            license_id="private-full",
            redistribution="full",
        ),
    ]
    manifest = build_seed_bundle(
        input_root=source_root,
        inputs=inputs,
        output_dir=tmp_path / "bundle",
        build_config={"compare": "v2"},
    )
    compiled = []
    for declared in inputs:
        authorized, token = authorize_input(
            source_root,
            declared.path,
            source_kind=declared.source_kind,
            license_id=declared.license_id,
            redistribution=declared.redistribution,
        )
        compiled.append(
            compile_one(authorized, build_id=manifest.build_id, authorized_source=token)
        )
    bundle = tmp_path / "bundle"
    write_index(bundle, compiled, manifest)
    index = open_readonly_index(bundle)
    from tests.fixtures.groove_runtime import MemoryArtifactStore

    store = MemoryArtifactStore()
    for artifact_id in index.manifest.artifact_ids:
        store.put(index.load_artifact(str(artifact_id)))
    return GrooveRuntime(index=index, store=store)


def _request(runtime: GrooveRuntime, metrics: list[str]) -> CompareRequestV1:
    return CompareRequestV1(
        schema_version="groove.compare.request.v1",
        artifact_ids=[str(item) for item in runtime.index.manifest.artifact_ids],
        metrics=metrics,  # type: ignore[arg-type]
        normalize=True,
    )


def test_evidence_and_compare_are_cards_only_and_bound_details(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    evidence_result = evidence(runtime, make_evidence_request(runtime))
    compare_result = compare(runtime, make_compare_request(runtime))
    serialized = canonical_json(evidence_result.model_dump())
    assert b"events" not in serialized
    assert len(evidence_result.card.references) <= 32
    assert len(canonical_json(compare_result.model_dump())) <= 128 * 1024


def test_compare_uses_hvo_and_grammar_content_not_projection_names(tmp_path: Path) -> None:
    runtime = _build_compare_runtime(tmp_path)
    result = compare(runtime, _request(runtime, ["hvo", "grammar"]))

    assert result.card.common_projections == ["features", "grammar", "hvo"]
    assert result.card.matrix[0][0] == 0.0
    assert result.card.matrix[1][1] == 0.0
    assert result.card.matrix[0][1] == result.card.matrix[1][0]
    assert result.card.matrix[0][1] > 0.0
    assert all(0.0 <= value <= 1.0 for row in result.card.matrix for value in row)


def test_compare_is_zero_for_identity_and_keeps_metrics_bounded(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    artifact_id = str(runtime.index.manifest.artifact_ids[0])
    request = CompareRequestV1(
        schema_version="groove.compare.request.v1",
        artifact_ids=[artifact_id, artifact_id],
        metrics=["facets", "features", "hvo", "grammar"],
        normalize=True,
    )

    result = compare(runtime, request)

    assert result.card.matrix == [[0.0, 0.0], [0.0, 0.0]]


def test_feature_distance_uses_musical_unit_scale_instead_of_raw_delta() -> None:
    left = {"values": {"hits": {"value": 2, "unit": "hits/bar"}}}
    right = {"values": {"hits": {"value": 4, "unit": "hits/bar"}}}

    assert feature_distance(left, right) == 0.5


def test_feature_distance_ignores_technical_ppq_resolution() -> None:
    left = {
        "values": {
            "ppq": {"value": 480, "unit": "ticks_per_quarter"},
            "hits": {"value": 2, "unit": "hits/bar"},
        }
    }
    right = {
        "values": {
            "ppq": {"value": 9600, "unit": "ticks_per_quarter"},
            "hits": {"value": 2, "unit": "hits/bar"},
        }
    }

    assert feature_distance(left, right) == 0.0


def test_compare_reports_missing_projections_and_meter_incompatibility(
    tmp_path: Path,
) -> None:
    runtime = make_pilot_runtime(tmp_path)
    artifact_ids = [str(item) for item in runtime.index.manifest.artifact_ids[:2]]
    cards = {artifact_id: runtime.card(artifact_id) for artifact_id in artifact_ids}
    cards[artifact_ids[0]] = cards[artifact_ids[0]].model_copy(
        update={
            "projections": {
                name: version
                for name, version in cards[artifact_ids[0]].projections.items()
                if name != "hvo"
            }
        }
    )
    cards[artifact_ids[1]] = cards[artifact_ids[1]].model_copy(
        update={
            "projections": {
                name: version
                for name, version in cards[artifact_ids[1]].projections.items()
                if name != "hvo"
            },
            "features": {**cards[artifact_ids[1]].features, "meter": "3/4"},
        }
    )

    class CardOnlyRuntime:
        index = runtime.index
        store = runtime.store

        def card(self, artifact_id: str) -> object:
            return cards[artifact_id]

    result = compare(
        CardOnlyRuntime(),
        CompareRequestV1(
            schema_version="groove.compare.request.v1",
            artifact_ids=artifact_ids,
            metrics=["hvo"],
            normalize=True,
        ),
    )

    assert result.card.matrix[0][1] == result.card.matrix[1][0] == 1.0
    assert result.card.compatibility["hvo"] == "unavailable"
    assert result.card.compatibility["meter"] == "incompatible"
    assert result.card.limitations == [
        "hvo projection unavailable",
        "meter compatibility is incompatible",
    ]


def test_compare_resolves_real_generated_projections_from_store(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    source_id = str(runtime.index.manifest.artifact_ids[0])
    generated = deterministic_generate(
        runtime,
        make_generate_request(runtime, source={"artifact_id": source_id}, bars=1),
    )
    generated_id = str(generated.artifact.artifact_id)
    request = CompareRequestV1(
        schema_version="groove.compare.request.v1",
        artifact_ids=[source_id, generated_id],
        metrics=["features", "hvo", "grammar"],
        normalize=True,
    )

    result = compare(runtime, request)

    assert result.card.matrix[0][0] == result.card.matrix[1][1] == 0.0
    assert result.card.matrix[0][1] == result.card.matrix[1][0]
    assert 0.0 <= result.card.matrix[0][1] <= 1.0
    generated_artifact = runtime.store.get(generated_id)
    projection_values = generated_artifact.provenance["_projection_values"]
    assert projection_values[HVO_SCHEMA_VERSION]["schema_version"] == HVO_SCHEMA_VERSION


@pytest.mark.parametrize("tamper", ["digest", "v1", "missing"])
def test_compare_rejects_tampered_or_missing_generated_projection(
    tmp_path: Path, tamper: str
) -> None:
    runtime = make_pilot_runtime(tmp_path)
    source_id = str(runtime.index.manifest.artifact_ids[0])
    generated = deterministic_generate(
        runtime,
        make_generate_request(runtime, source={"artifact_id": source_id}, bars=1),
    )
    generated_id = str(generated.artifact.artifact_id)
    generated_artifact = runtime.store.get(generated_id)
    projection_values = dict(generated_artifact.provenance["_projection_values"])
    if tamper == "missing":
        projection_values.pop(FEATURES_SCHEMA_VERSION)
    else:
        hvo = dict(projection_values[HVO_SCHEMA_VERSION])
        hvo["schema_version"] = "groove.hvo.v1" if tamper == "v1" else HVO_SCHEMA_VERSION
        if tamper == "digest":
            hvo["cells"] = []
        projection_values[HVO_SCHEMA_VERSION] = hvo
    provenance = {
        **generated_artifact.provenance,
        "_projection_values": projection_values,
    }
    runtime.store.put(generated_artifact.model_copy(update={"provenance": provenance}))

    with pytest.raises(GrooveIndexInvalid):
        compare(
            runtime,
            CompareRequestV1(
                schema_version="groove.compare.request.v1",
                artifact_ids=[source_id, generated_id],
                metrics=["features", "hvo", "grammar"],
                normalize=True,
            ),
        )
