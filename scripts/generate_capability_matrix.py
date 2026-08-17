from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Make repository modules importable when the script is invoked by path.
sys.path.insert(0, str(Path(__file__).parent.parent))

from ableton_mcp_server.diagnostics import bridge_status  # noqa: E402

CATEGORIES = {
    "Tempo & Transport": [
        "set_tempo",
        "set_current_song_time",
        "start_playback",
        "stop_playback",
        "get_song_length",
    ],
    "Mixer & Tracks": [
        "get_routing",
        "get_track_state",
        "get_track_list",
        "set_track_property",
        "set_track_color",
        "live_fade",
        "create_midi_track",
        "create_audio_track",
        "rename_track",
        "move_track",
        "move_track_to_group",
        "reorder_tracks",
        "ungroup_track",
        "merge_groups",
    ],
    "Devices & Parameters": [
        "get_device_list",
        "get_parameter_value",
        "set_parameter_value",
        "list_device_params",
        "load_device_to_track",
    ],
    "Clips & Scenes": [
        "get_scenes",
        "get_scene_state",
        "fire_scene",
        "get_clip_summary",
        "get_clip_info",
        "create_clip",
        "fire_clip",
        "delete_clip",
        "set_clip_properties",
        "set_clip_color",
        "diagnose_clip_targets",
    ],
    "MIDI Notes & Automation": [
        "get_clip_notes",
        "add_notes_to_clip",
        "clear_clip_notes",
        "create_clip_automation",
        "diagnose_midi_clip",
    ],
    "Locators": [
        "get_locators",
        "create_cue_point",
        "bulk_create_cue_points",
        "delete_cue_point",
    ],
    "Session & Project": [
        "get_session_info",
        "get_session_overview",
        "take_snapshot",
        "get_project_metadata",
        "save_set",
        "quit_ableton",
        "lifecycle_status",
        "get_selected_context",
        "get_composition_structure",
    ],
    "Browser": ["get_browser_categories", "search_browser"],
    "Warping": ["get_warp_state", "set_warp_state"],
    "Batch": ["run_batch"],
    "Diagnostics & State": [
        "get_control_surfaces",
        "get_loop_settings",
        "set_loop",
        "set_loop_start",
        "set_loop_length",
        "diff_snapshots_tool",
        "get_ableton_logs",
        "get_bridge_status",
    ],
    "Extension Management": ["build_extension", "scaffold_extension"],
    "Analysis (Offline)": [
        "analyze_audio",
        "analyze_mix",
        "extract_single_cycle",
        "find_frequency_masking",
    ],
    "Search": ["live_find_track", "live_find_device", "live_find_clip"],
}


class _OfflineClient:
    host = "127.0.0.1"
    port = 9888

    def call(self, *_args: Any, **_kwargs: Any) -> Any:
        raise ConnectionError("offline capability export")


def generate_markdown(status: dict[str, Any] | None = None) -> str:
    capability_status = bridge_status(_OfflineClient()) if status is None else status
    tools_payload = capability_status["tools"]
    counts = capability_status["capability_counts"]
    public_tool_names = {str(tool["name"]) for tool in tools_payload}
    lines = [
        "# API Capability Matrix",
        "",
        "> This document is automatically generated. Do not edit manually.",
        "> It represents the row-by-row source of truth for the capabilities exposed by the "
        "Ableton MCP Server.",
        "",
        "## Overview",
        "",
        f"- **Total Public Tools**: {counts['public_tools']}",
        f"- **Routed Remote Commands**: {counts['routed_commands']}",
        f"- **WebSocket Targets**: {counts['websocket_targets']}",
        "",
        "## Categories",
        "",
    ]

    all_categorized = {tool for tools in CATEGORIES.values() for tool in tools}
    categories = list(CATEGORIES.items())
    uncategorized = public_tool_names - all_categorized
    if uncategorized:
        categories.append(("Other", sorted(uncategorized)))

    tools_by_name = {str(tool["name"]): tool for tool in tools_payload}
    for category, tools in categories:
        valid_tools = [tool for tool in tools if tool in public_tool_names]
        if not valid_tools:
            continue

        lines.extend(
            [
                f"### {category}",
                "",
                "| Tool | Read / Write | Requires Extension | Live Required |",
                "|---|---|---|---|",
            ]
        )
        for tool in sorted(valid_tools):
            capability = tools_by_name[tool]
            rw = "Read-only" if capability["risk"] in ("read", "unavailable") else "Write"
            ext = "Yes" if capability["route"] == "websocket" else "No"
            live_req = "No" if capability["route"] == "local" else "Yes"
            lines.append(f"| `{tool}` | {rw} | {ext} | {live_req} |")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    markdown = generate_markdown()
    output_path = Path(__file__).parent.parent / "docs" / "api_capability_matrix.md"
    output_path.write_text(markdown, encoding="utf-8")
    print(f"Generated {output_path} from bridge_status.")


if __name__ == "__main__":
    main()
