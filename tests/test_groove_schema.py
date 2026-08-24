from __future__ import annotations

import pytest
from pydantic import ValidationError

from ableton_mcp_server import server
from ableton_mcp_server.groove_intelligence.mcp_models import (
    CompareRequestV1,
    EvidenceRequestV1,
    GenerateRequestV1,
    SearchRequestV1,
)
from tests.fixtures.groove_mcp_wire import (
    assert_client_schema_constraints,
    discover_client_wire_schemas,
    generated_server_schema,
    normalize_wire_schema,
)

GROOVE_REQUEST_MODEL_BY_TOOL = {
    "groove_search": SearchRequestV1,
    "groove_evidence": EvidenceRequestV1,
    "groove_generate": GenerateRequestV1,
    "groove_compare": CompareRequestV1,
}


def test_public_projection_ids_are_v2_and_legacy_ids_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SearchRequestV1(
            schema_version="groove.search.request.v1",
            required_projection_ids=["groove.hvo.v1"],  # type: ignore[list-item]
        )
    request = SearchRequestV1(
        schema_version="groove.search.request.v1",
        required_projection_ids=["groove.hvo.v2"],  # type: ignore[list-item]
    )
    assert request.required_projection_ids == ["groove.hvo.v2"]


@pytest.mark.asyncio
async def test_four_fastmcp_schemas_match_actual_client_wire_and_pydantic_models() -> None:
    client_wire = await discover_client_wire_schemas(server.mcp)
    generated = {
        tool.name: generated_server_schema(tool)
        for tool in await server.mcp.list_tools()
        if tool.name in GROOVE_REQUEST_MODEL_BY_TOOL
    }
    for name, model in GROOVE_REQUEST_MODEL_BY_TOOL.items():
        assert normalize_wire_schema(client_wire[name]) == normalize_wire_schema(generated[name])
        assert_client_schema_constraints(client_wire[name], model)
        expected_version = model.model_fields["schema_version"].default
        if expected_version is not None and str(expected_version) != "PydanticUndefined":
            assert normalize_wire_schema(client_wire[name])["properties"]["schema_version"][
                "enum"
            ] == [expected_version]
        assert client_wire[name]["additionalProperties"] is False


def test_public_generate_forwards_reference_artifact_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        server,
        "_groove_generate_from_mapping",
        lambda payload: captured.update(payload) or object(),
    )
    parent = "ga1_" + "a" * 64
    reference = "ga1_" + "b" * 64
    server.groove_generate(
        schema_version="groove.generate.request.v1",
        source={"artifact_id": parent},
        transforms={},
        bars=1,
        seed=7,
        reference_artifact_ids=[reference],
    )
    assert captured["reference_artifact_ids"] == [reference]
    server.groove_generate(
        schema_version="groove.generate.request.v1",
        source={"artifact_id": parent},
        transforms={},
        bars=1,
        seed=7,
    )
    assert captured["reference_artifact_ids"] == []


@pytest.mark.parametrize("name", list(GROOVE_REQUEST_MODEL_BY_TOOL))
def test_invalid_version_or_extra_field_fails_before_runtime_io(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server, "get_groove_runtime", lambda: pytest.fail("runtime must not be resolved")
    )
    adapter = {
        "groove_search": server._groove_search_from_mapping,
        "groove_evidence": server._groove_evidence_from_mapping,
        "groove_generate": server._groove_generate_from_mapping,
        "groove_compare": server._groove_compare_from_mapping,
    }[name]
    with pytest.raises(ValidationError):
        adapter({"schema_version": "wrong.v1", "unexpected": True})
