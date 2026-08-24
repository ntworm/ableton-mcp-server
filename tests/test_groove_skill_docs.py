from __future__ import annotations

from pathlib import Path


def test_skill_is_guidance_only_and_names_receipt_safety_rules() -> None:
    text = Path(".agents/skills/drum-groove-intelligence/SKILL.md").read_text(encoding="utf-8")
    assert "search -> evidence -> generate/compare -> apply" in text
    assert "artifact_id" in text and "slot vazio" in text
    assert "SQL" in text and "não executa" in text
    assert "subprocess" not in text.lower()


def test_apply_probe_names_guards() -> None:
    source = Path("ableton_mcp_server/acceptance/probes/groove_apply.py").read_text(
        encoding="utf-8"
    )
    assert (
        "confirm_project_name" in source
        and "expected_empty_slot" in source
        and "disposable" in source
    )


def test_tool_count_snapshot_is_catalog_and_acceptance_derived() -> None:
    from ableton_mcp_server.acceptance.probes import ACCEPTANCE_REGISTRY
    from ableton_mcp_server.catalog import TOOL_CATALOG, Route
    from ableton_mcp_server.tool_counts import build_tool_count_snapshot

    snapshot = build_tool_count_snapshot()
    assert snapshot.active_total == len(TOOL_CATALOG)
    assert snapshot.headless_total == sum(item.route is Route.LOCAL for item in TOOL_CATALOG)
    assert snapshot.live_required_total == snapshot.active_total - snapshot.headless_total
    assert snapshot.acceptance_total == len(ACCEPTANCE_REGISTRY)
    assert sum(snapshot.route_counts.values()) == snapshot.active_total
