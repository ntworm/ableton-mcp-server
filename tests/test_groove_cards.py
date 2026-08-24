from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp.tools import ToolResult
from mcp.types import TextContent

from ableton_mcp_server.groove_intelligence.canonical import canonical_json
from ableton_mcp_server.groove_intelligence.runtime import (
    GrooveResponseBudgetExceeded,
    ResponseBudget,
    assert_tool_result_budget,
    serialize_tool_result,
)
from tests.fixtures.groove_runtime import make_pilot_runtime


def test_artifact_card_is_bounded_and_contains_capabilities_without_payload(
    tmp_path: Path,
) -> None:
    runtime = make_pilot_runtime(tmp_path)
    card = next(
        runtime.card(str(artifact_id))
        for artifact_id in runtime.index.manifest.artifact_ids
        if runtime.card(str(artifact_id)).capabilities.apply.allowed
    )
    serialized = canonical_json(card.model_dump(exclude_none=True))
    assert len(serialized) <= 6 * 1024
    assert (
        b"payload" not in serialized
        and b"source_path" not in serialized
        and b"notes" not in serialized
    )
    assert card.capabilities.apply.allowed is True


def test_budget_counts_actual_tool_result_wire_once() -> None:
    result = ToolResult(
        structured_content={"x": "é"},
        content=[TextContent(type="text", text="x")],
        meta={"trace": "t"},
    )
    expected = len(serialize_tool_result(result))
    assert ResponseBudget(max_bytes=expected).measure_tool_result(result) == expected
    with pytest.raises(GrooveResponseBudgetExceeded):
        assert_tool_result_budget(result, ResponseBudget(max_bytes=expected - 1))
