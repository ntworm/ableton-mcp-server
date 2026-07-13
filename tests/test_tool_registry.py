from __future__ import annotations

import pytest

from ableton_mcp_server.models import TOOL_REQUEST_MODELS
from ableton_mcp_server.server import PUBLIC_TOOL_NAMES, mcp


def test_synchronous_acceptance_count_is_available() -> None:
    assert len(mcp.list_tools()) == len(PUBLIC_TOOL_NAMES)
    assert len(mcp.list_tools()) >= 44


@pytest.mark.asyncio
async def test_real_fastmcp_listing_matches_models_and_count_proxy() -> None:
    tools = await mcp.list_tools()
    names = {tool.name for tool in tools}
    assert names == set(PUBLIC_TOOL_NAMES)
    assert names == set(TOOL_REQUEST_MODELS)
    assert len(tools) == len(mcp.list_tools()) == 57
