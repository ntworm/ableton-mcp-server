from __future__ import annotations

from pathlib import Path

import ableton_mcp_server.groove_intelligence.search as search_module
from ableton_mcp_server.groove_intelligence.mcp_models import SearchRequestV1
from ableton_mcp_server.groove_intelligence.search import rank_candidate, search
from tests.fixtures.groove_runtime import make_pilot_runtime, make_search_request


def test_search_uses_fixed_weights_and_artifact_id_tie_break(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    result = search(
        runtime,
        make_search_request(
            facets={"feel": ["straight"]},
        required_projection_ids=["groove.hvo.v2"],
        ),
    )
    assert [item.artifact_id for item in result.items] == sorted(
        item.artifact_id for item in result.items
    )
    assert result.ranking.ranker_id == "groove-ranker-v2"
    assert result.ranking.weights == {
        "text": 0.2,
        "facets": 0.25,
        "features": 0.4,
        "projection_coverage": 0.15,
    }


def test_missing_required_feature_excludes_candidate_without_zero_score(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    request = SearchRequestV1(
        schema_version="groove.search.request.v1",
        feature_constraints=[{"name": "swing", "op": "gte", "value": 0.2}],
        limit=20,
    )
    assert search(runtime, request).items == []


def test_search_scores_index_rows_without_materializing_every_projection(
    tmp_path: Path, monkeypatch: object
) -> None:
    runtime = make_pilot_runtime(tmp_path)
    calls = 0
    original = runtime.index.load_projection

    def counted(artifact_id: str, projection_id: str) -> object:
        nonlocal calls
        calls += 1
        return original(artifact_id, projection_id)

    monkeypatch.setattr(runtime.index, "load_projection", counted)  # type: ignore[attr-defined]
    search(runtime, make_search_request(facets={"feel": ["straight"]}, limit=1))
    assert calls <= 3


def test_compound_text_queries_share_tokens_with_canonical_facets(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    try:
        card = runtime.card(str(runtime.index.manifest.artifact_ids[0])).model_copy(
            update={
                "facets": {
                    "genre": ["hip_hop", "rnb"],
                    "subgenre": ["boom_bap"],
                }
            }
        )
        for query in ("hip hop", "hip_hop", "boom bap", "boom_bap", "r&b"):
            ranked = rank_candidate(card, make_search_request(query=query))
            assert ranked.text_score > 0, query
    finally:
        runtime.close()


def test_repeated_search_reuses_tokenization_for_immutable_cards(
    tmp_path: Path, monkeypatch: object
) -> None:
    runtime = make_pilot_runtime(tmp_path)
    calls = 0
    original = search_module.search_tokens

    def counted(value: object) -> set[str]:
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(search_module, "search_tokens", counted)
    request = make_search_request(query="hip hop", limit=5)
    try:
        search(runtime, request)
        calls_after_first = calls
        search(runtime, request)
        assert calls == calls_after_first
    finally:
        runtime.close()
