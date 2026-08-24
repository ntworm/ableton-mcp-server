from __future__ import annotations

import pytest

from ableton_mcp_server import server
from ableton_mcp_server.groove_intelligence.runtime import (
    GrooveResponseBudgetExceeded,
    serialize_tool_result,
)


def test_actual_emitted_tool_result_budget_is_bounded_and_uses_text_content() -> None:
    result = server._explicit_json_result({"value": "x" * (524288 - 4096)})
    assert all(block.type == "text" for block in result.content)
    assert len(serialize_tool_result(result)) <= 524288
    with pytest.raises(GrooveResponseBudgetExceeded):
        server._explicit_json_result({"value": "x" * 524288})


def test_actual_emitted_tool_result_truncates_bounded_lists_before_budget_check() -> None:
    result = server._explicit_json_result({"warnings": [f"w-{index}" for index in range(20000)]})
    assert len(result.structured_content["warnings"]) < 20000
    assert len(serialize_tool_result(result)) <= 524288


def test_budget_truncation_is_utf8_byte_aware_and_keeps_one_fitting_item() -> None:
    result = server._explicit_json_result({"warnings": ["é" * 200000] * 32})
    assert len(result.structured_content["warnings"]) == 1
    assert len(serialize_tool_result(result)) <= 524288


def test_budget_rejects_when_no_list_item_can_fit() -> None:
    oversized_item = {f"field-{index}": "x" * 400 for index in range(2000)}
    with pytest.raises(GrooveResponseBudgetExceeded):
        server._explicit_json_result({"warnings": [oversized_item]})
