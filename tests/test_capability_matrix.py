"""R4 — capability matrix exposed via bridge_status.

These cases assert the cross-counts documented in
``docs/superpowers/specs/2026-08-01-r4-capability-matrix.md`` §5 and guard
against silent drift between ``TOOL_CATALOG`` and the wire-facing
``bridge_status`` payload.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ableton_mcp_server.catalog import TOOL_CATALOG
from ableton_mcp_server.diagnostics import bridge_status
from ableton_mcp_server.server import PUBLIC_TOOL_NAMES
from contracts import (
    ALLOWED_MUTATIONS,
    READ_COMMANDS,
    READ_ONLY_COMMANDS,
    WEBSOCKET_TARGET_COMMANDS,
)


class _HealthyClient:
    host = "127.0.0.1"
    port = 9888

    def call(
        self,
        command_type: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float = 2.0,
    ) -> Any:
        assert command_type == "get_session_info"
        assert params in ({}, None)
        return {"tempo": 120.0, "is_playing": False}


def _status() -> dict[str, Any]:
    return bridge_status(_HealthyClient(), tool_count=len(PUBLIC_TOOL_NAMES))


def test_bridge_status_tools_length_is_77() -> None:
    """§5 case 1: tools list length matches the public catalog."""
    result = _status()
    assert len(result["tools"]) == 77


def test_bridge_status_tool_dict_schema() -> None:
    """§5 case 2: every entry has the six §2(a) fields with correct types
    and tool names are unique."""
    expected_fields = {"name", "domain", "route", "risk", "acceptance", "reversible"}
    result = _status()
    names: list[str] = []
    for entry in result["tools"]:
        assert set(entry.keys()) == expected_fields, (
            f"Each tool dict must contain exactly the six §2(a) fields; got {sorted(entry.keys())}"
        )
        assert isinstance(entry["name"], str)
        assert isinstance(entry["domain"], str)
        assert isinstance(entry["route"], str)
        assert isinstance(entry["risk"], str)
        assert isinstance(entry["acceptance"], str)
        assert isinstance(entry["reversible"], bool)
        names.append(entry["name"])
    assert len(names) == len(set(names)), "Tool names in bridge_status must be unique"


def test_capability_counts_match_invariants() -> None:
    """§5 case 3: the six documented counts are exactly the catalog/contracts
    values. ``live_required_tools`` is ``77 - 8`` because every tool whose
    route is LOCAL (six LOCAL_READS plus two LOCAL_WRITES) does not require
    an Ableton Live process."""
    result = _status()
    counts = result["capability_counts"]
    assert counts == {
        "public_tools": 77,
        "routed_commands": 62,
        "websocket_targets": 3,
        "read_only_blocked": 5,
        "feature_flags": 5,
        "live_required_tools": 69,
        "capability_unavailable": 5,
    }


def test_websocket_targets_match_catalog_route() -> None:
    """§5 case 4: names whose route is websocket equal the contracts set."""
    result = _status()
    websocket_names = {entry["name"] for entry in result["tools"] if entry["route"] == "websocket"}
    assert websocket_names == set(WEBSOCKET_TARGET_COMMANDS)


def test_routed_commands_cover_reads_and_mutations() -> None:
    """§5 case 5: routed_commands equals the union cardinality."""
    result = _status()
    assert len(READ_COMMANDS) + len(ALLOWED_MUTATIONS) == 62
    assert result["capability_counts"]["routed_commands"] == 62


def test_read_only_blocked_are_disjoint_from_routed() -> None:
    """§5 case 6: every READ_ONLY_COMMANDS entry must be blocked, i.e.
    absent from the routed union READ_COMMANDS | ALLOWED_MUTATIONS.
    The spec phrased this as a subset check; the canonical structural
    invariant is disjointness (the value is named read_only_blocked
    for a reason -- these ops are rejected, not routed)."""
    result = _status()
    routed = READ_COMMANDS | ALLOWED_MUTATIONS
    assert READ_ONLY_COMMANDS.isdisjoint(routed), (
        "READ_ONLY_COMMANDS must be disjoint from READ_COMMANDS|"
        "ALLOWED_MUTATIONS; any overlap means a blocked op is reachable."
    )
    assert result["capability_counts"]["read_only_blocked"] == len(READ_ONLY_COMMANDS)


def test_features_list_is_frozen() -> None:
    """§5 case 7: features equals the literal list compiled into
    diagnostics.bridge_status; any drift fails loudly."""
    result = _status()
    assert result["features"] == [
        "device_parameter_write",
        "session_clip_automation",
        "session_clip_mutations",
        "bounded_browser_search",
        "extended_midi_notes",
    ]


def test_tool_count_agrees_with_capability_counts() -> None:
    """§5 case 8: the legacy tool_count field must equal the new
    public_tools count, regardless of how the caller populated it."""
    result = _status()
    assert result["tool_count"] == result["capability_counts"]["public_tools"]

    stale_caller_result = bridge_status(_HealthyClient(), tool_count=0)
    assert stale_caller_result["tool_count"] == len(TOOL_CATALOG)


def test_capability_source_names_canonical_modules() -> None:
    """Provenance: each capability_counts key points at its canonical source."""
    result = _status()
    source = result["capability_source"]
    assert source["catalog"] == "ableton_mcp_server.catalog:TOOL_CATALOG"
    assert source["routed_commands"] == "contracts:READ_COMMANDS|ALLOWED_MUTATIONS"
    assert source["websocket_targets"] == "contracts:WEBSOCKET_TARGET_COMMANDS"
    assert source["read_only"] == "contracts:READ_ONLY_COMMANDS"
    assert source["features"] == "ableton_mcp_server.diagnostics.bridge_status:features"


def test_bridge_status_survives_live_probe_failure() -> None:
    """The matrix keys must be present even when the TCP probe fails —
    consumers should be able to enumerate the catalog without Live running
    (the spec §4 acceptance criterion)."""

    class _BrokenClient(_HealthyClient):
        def call(
            self,
            command_type: str,
            params: Mapping[str, Any] | None = None,
            *,
            timeout: float = 2.0,
        ) -> Any:
            raise ConnectionError("connection refused")

    result = bridge_status(_BrokenClient(), tool_count=77)
    assert result["status"] == "error"
    assert result["bridge_available"] is False
    assert len(result["tools"]) == 77
    assert result["capability_counts"]["public_tools"] == 77


def test_tools_match_public_catalog_in_order() -> None:
    """The wire list must enumerate every spec in TOOL_CATALOG and no
    extras — a guard against accidental duplicates or omissions."""
    result = _status()
    wire_names = [entry["name"] for entry in result["tools"]]
    assert wire_names == [spec.name for spec in TOOL_CATALOG]
    assert set(wire_names) == set(PUBLIC_TOOL_NAMES)


def test_capability_matrix_markdown_is_up_to_date() -> None:
    """Ensure that docs/api_capability_matrix.md is up-to-date with the code."""
    from pathlib import Path

    from scripts.generate_capability_matrix import generate_markdown

    expected_md = generate_markdown()

    docs_dir = Path(__file__).parent.parent / "docs"
    matrix_file = docs_dir / "api_capability_matrix.md"

    if not matrix_file.exists():
        raise AssertionError(f"Capability matrix file missing at {matrix_file}")

    actual_md = matrix_file.read_text(encoding="utf-8")

    assert "\\n" not in expected_md
    assert expected_md.startswith("# API Capability Matrix\n\n")
    assert "| `build_extension` | Write | No | No |" in expected_md
    assert expected_md == actual_md, (
        "Capability matrix is out of date. "
        "Please run `python scripts/generate_capability_matrix.py` to update it."
    )


def test_capability_matrix_generator_uses_bridge_status_as_its_only_capability_source() -> None:
    """The generated document must not recreate catalog/contract joins in parallel."""
    from pathlib import Path

    generator = (
        Path(__file__).parent.parent / "scripts" / "generate_capability_matrix.py"
    ).read_text(encoding="utf-8")

    assert "from ableton_mcp_server.diagnostics import bridge_status" in generator
    assert "from ableton_mcp_server.catalog" not in generator
    assert "from ableton_mcp_server.server" not in generator
    assert "from contracts" not in generator
