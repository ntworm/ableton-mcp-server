from ableton_mcp_server import models, server
from ableton_mcp_server.catalog import TOOL_CATALOG, AcceptanceMode, Risk, Route
from contracts import ALLOWED_MUTATIONS, READ_COMMANDS, WEBSOCKET_TARGET_COMMANDS


def test_baseline_catalog_is_complete_and_unique() -> None:
    names = tuple(item.name for item in TOOL_CATALOG)
    assert len(names) == len(set(names)) == 77
    assert names == server.PUBLIC_TOOL_NAMES
    assert set(names) == set(models.TOOL_REQUEST_MODELS)


def test_wire_routes_and_risks_match_contracts() -> None:
    by_name = {item.name: item for item in TOOL_CATALOG}
    for name in READ_COMMANDS:
        assert by_name[name].route in {Route.TCP, Route.WEBSOCKET}
        assert by_name[name].risk is Risk.READ
    for name in ALLOWED_MUTATIONS:
        assert by_name[name].risk is not Risk.READ
    assert set(WEBSOCKET_TARGET_COMMANDS) == {
        item.name for item in TOOL_CATALOG if item.route is Route.WEBSOCKET
    }
    assert by_name["quit_ableton"].acceptance is AcceptanceMode.MANUAL
    assert by_name["build_extension"].acceptance is AcceptanceMode.ENVIRONMENT
