from __future__ import annotations

import os as os
import shutil as shutil
import subprocess as subprocess
from collections.abc import Awaitable, Callable, Generator, Mapping, Sequence
from typing import Any

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("FASTMCP_TELEMETRY_DISABLED", "true")
os.environ.setdefault("MCP_TELEMETRY_DISABLED", "true")

from fastmcp import FastMCP
from fastmcp.tools import Tool, ToolResult
from mcp.types import TextContent

from contracts import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_WS_PORT

from . import models
from .catalog import TOOL_CATALOG
from .client import Client
from .diagnostics import bridge_status as bridge_status
from .diagnostics import find_ableton_log_path as find_ableton_log_path
from .errors import BridgeError
from .groove_intelligence import GrooveIndexInvalid
from .groove_intelligence.apply import apply_artifact as apply_artifact
from .groove_intelligence.artifacts import SeedBackedArtifactStore
from .groove_intelligence.canonical import canonical_json
from .groove_intelligence.index import open_readonly_index
from .groove_intelligence.runtime import (
    GrooveResponseBudgetExceeded,
    ResponseBudget,
    serialize_tool_result,
)
from .groove_intelligence.seed_paths import (
    groove_artifact_root,
    seed_unavailable_message,
)
from .groove_intelligence.seed_paths import (
    resolve_groove_seed_bundle as resolve_groove_seed_bundle,
)

PUBLIC_TOOL_NAMES = tuple(spec.name for spec in TOOL_CATALOG)


class CountableToolListing(Awaitable[Sequence[Tool]]):
    """Lazy async FastMCP listing that also supports synchronous ``len``."""

    def __init__(
        self,
        factory: Callable[[], Awaitable[Sequence[Tool]]],
        count: Callable[[], int],
    ) -> None:
        self._factory = factory
        self._count = count

    def __await__(self) -> Generator[Any, None, Sequence[Tool]]:
        return self._factory().__await__()

    def __len__(self) -> int:
        return self._count()


class CountableFastMCP(FastMCP):
    """FastMCP 3.x with a backwards-compatible countable tool listing."""

    def list_tools(  # type: ignore[override]
        self, *, run_middleware: bool = True
    ) -> CountableToolListing:
        return CountableToolListing(
            lambda: super(CountableFastMCP, self).list_tools(run_middleware=run_middleware),
            lambda: len(PUBLIC_TOOL_NAMES),
        )


mcp: CountableFastMCP = CountableFastMCP("AbletonMCPServer")
_client: Client | None = None
DEFAULT_RESPONSE_BUDGET = ResponseBudget()


def get_client() -> Client:
    global _client
    if _client is None:
        host = os.environ.get("ABLETON_MCP_SERVER_HOST", DEFAULT_HOST)
        port = int(os.environ.get("ABLETON_MCP_SERVER_PORT", str(DEFAULT_PORT)))
        ws_port = int(os.environ.get("ABLETON_MCP_SERVER_WS_PORT", str(DEFAULT_WS_PORT)))
        _client = Client(host=host, port=port, ws_port=ws_port, reconnect=True)
    return _client


def get_groove_runtime(*, client: Client | None = None) -> Any:
    """Open the host-selected immutable seed and local derived store."""

    from .groove_intelligence.runtime import GrooveRuntime

    bundle = resolve_groove_seed_bundle()
    try:
        index = open_readonly_index(bundle)
    except (GrooveIndexInvalid, FileNotFoundError) as error:
        raise GrooveIndexInvalid(seed_unavailable_message(bundle, error)) from error
    store = SeedBackedArtifactStore(index, groove_artifact_root())
    return GrooveRuntime(index=index, store=store, client=client)


def truncate_response_value(
    value: Mapping[str, object], *, max_items: int = 32
) -> dict[str, object]:
    bounded = dict(value)
    for key in ("warnings", "limitations", "references"):
        items = bounded.get(key)
        if isinstance(items, list) and len(items) > max_items:
            bounded[key] = items[:max_items]
    return bounded


def _compact_json_value(item: object, max_items: int, budget: ResponseBudget) -> object:
    """Cut lists to MAX_ITEMS and strings to a quarter of the budget, recursively."""
    if isinstance(item, Mapping):
        return {str(key): _compact_json_value(val, max_items, budget) for key, val in item.items()}
    if isinstance(item, (list, tuple)):
        return [_compact_json_value(val, max_items, budget) for val in item[:max_items]]
    if isinstance(item, str):
        max_string_bytes = max(0, budget.max_bytes // 4)
        encoded = item.encode("utf-8")
        if len(encoded) <= max_string_bytes:
            return item
        return encoded[:max_string_bytes].decode("utf-8", errors="ignore")
    return item


def _explicit_json_result(
    value: Mapping[str, object] | Any,
    *,
    is_error: bool = False,
    unwrap_result: bool = False,
    budget: ResponseBudget = DEFAULT_RESPONSE_BUDGET,
) -> ToolResult:
    """Keep JSON values visible without leaking domain errors into FastMCP."""
    original = value
    if isinstance(original, Mapping) and any(
        isinstance(item, str) and len(item) >= budget.max_bytes for item in original.values()
    ):
        raise GrooveResponseBudgetExceeded("response item cannot fit response budget")

    def compact(item: object, max_items: int) -> object:
        return _compact_json_value(item, max_items, budget)

    meta = {"fastmcp": {"wrap_result": True}} if unwrap_result else None
    for max_items in (32, 16, 8, 4, 1, 0):
        if max_items == 0 and isinstance(original, Mapping) and any(
            isinstance(item, list) and item for item in original.values()
        ):
            raise GrooveResponseBudgetExceeded("no response list item fits the budget")
        compact_value = compact(original, max_items)
        structured = {"result": compact_value} if unwrap_result else compact_value
        text_value = compact_value if unwrap_result else structured
        text = canonical_json(text_value).decode("utf-8")
        result = ToolResult(
            content=[TextContent(type="text", text=text)],
            structured_content=structured,
            meta=meta,
            is_error=is_error,
        )
        if len(serialize_tool_result(result)) <= budget.max_bytes:
            return result
    raise GrooveResponseBudgetExceeded("response budget exceeded")


def _remote(
    command: str,
    request: models.RequestModel,
    *,
    exclude_none: bool = False,
    exclude_defaults: bool = False,
) -> Any:
    try:
        result = get_client().call(
            command,
            request.model_dump(
                mode="json", exclude_none=exclude_none, exclude_defaults=exclude_defaults
            ),
        )
    except BridgeError as error:
        return _explicit_json_result(error.to_envelope(), is_error=True)
    if isinstance(result, list) and not result:
        return _explicit_json_result(result, unwrap_result=True)
    return result


async def _remote_ws(method: str, params: dict[str, Any] | None = None) -> Any:
    """Route a command to the Extension Host WebSocket bridge."""
    return await get_client().call_ws(method, params)


# isort: off
# The tools register in this import order, the order they had in this file.
from . import tools_read  # noqa: E402,F401
from . import tools_clips  # noqa: E402,F401
from . import tools_arrangement  # noqa: E402,F401
from . import tools_tracks  # noqa: E402,F401
from . import tools_extension  # noqa: E402,F401
from . import tools_offline  # noqa: E402,F401
from .tools_read import (  # noqa: E402
    diff_snapshots_tool as diff_snapshots_tool,
    get_ableton_logs as get_ableton_logs,
    get_bridge_status as get_bridge_status,
    get_browser_categories as get_browser_categories,
    get_clip_info as get_clip_info,
    get_clip_notes as get_clip_notes,
    get_clip_summary as get_clip_summary,
    get_control_surfaces as get_control_surfaces,
    get_device_list as get_device_list,
    get_locators as get_locators,
    get_loop_settings as get_loop_settings,
    get_parameter_value as get_parameter_value,
    get_plugin_presets as get_plugin_presets,
    get_project_metadata as get_project_metadata,
    get_routing as get_routing,
    get_scene_state as get_scene_state,
    get_scenes as get_scenes,
    get_selected_context as get_selected_context,
    get_session_info as get_session_info,
    get_session_overview as get_session_overview,
    get_song_length as get_song_length,
    get_track_list as get_track_list,
    get_track_state as get_track_state,
    list_device_params as list_device_params,
    live_find_clip as live_find_clip,
    live_find_device as live_find_device,
    live_find_track as live_find_track,
    search_browser as search_browser,
    set_parameter_value as set_parameter_value,
    set_plugin_preset as set_plugin_preset,
    take_snapshot as take_snapshot,
)
from .tools_clips import (  # noqa: E402
    add_notes_to_clip as add_notes_to_clip,
    bulk_create_cue_points as bulk_create_cue_points,
    clear_clip_notes as clear_clip_notes,
    create_clip as create_clip,
    create_cue_point as create_cue_point,
    delete_arrangement_clip as delete_arrangement_clip,
    delete_clip as delete_clip,
    delete_cue_point as delete_cue_point,
    diagnose_clip_targets as diagnose_clip_targets,
    duplicate_session_clip_to_arrangement as duplicate_session_clip_to_arrangement,
    fire_clip as fire_clip,
    fire_scene as fire_scene,
    get_arrangement_clips as get_arrangement_clips,
    run_batch as run_batch,
    set_clip_color as set_clip_color,
    set_current_song_time as set_current_song_time,
    set_loop as set_loop,
    set_loop_length as set_loop_length,
    set_loop_start as set_loop_start,
    set_tempo as set_tempo,
    set_track_color as set_track_color,
    set_track_property as set_track_property,
    start_playback as start_playback,
    stop_playback as stop_playback,
)
from .tools_arrangement import (  # noqa: E402
    add_notes_pattern as add_notes_pattern,
    create_clip_automation_curve as create_clip_automation_curve,
    describe_instrument as describe_instrument,
    get_clip_automation as get_clip_automation,
    get_device_chains as get_device_chains,
    get_midi_chain_report as get_midi_chain_report,
    merge_groups as merge_groups,
    move_arrangement_clip as move_arrangement_clip,
    move_track as move_track,
    move_track_to_group as move_track_to_group,
    reorder_tracks as reorder_tracks,
    set_arrangement_clip_properties as set_arrangement_clip_properties,
    ungroup_track as ungroup_track,
)
from .tools_tracks import (  # noqa: E402
    create_audio_track as create_audio_track,
    create_clip_automation as create_clip_automation,
    create_midi_track as create_midi_track,
    diagnose_midi_clip as diagnose_midi_clip,
    get_composition_structure as get_composition_structure,
    get_warp_state as get_warp_state,
    lifecycle_status as lifecycle_status,
    live_fade as live_fade,
    load_device_to_track as load_device_to_track,
    quit_ableton as quit_ableton,
    rename_track as rename_track,
    save_set as save_set,
    set_clip_properties as set_clip_properties,
    set_warp_state as set_warp_state,
)
from .tools_extension import (  # noqa: E402
    _EXTENSION_BUILD_STEP_NAME as _EXTENSION_BUILD_STEP_NAME,
    _EXTENSION_ENTRYPOINT_REL as _EXTENSION_ENTRYPOINT_REL,
    _EXTENSION_INSTALL_STEP_NAME as _EXTENSION_INSTALL_STEP_NAME,
    _EXTENSION_TEMPLATE_BUILD_TS as _EXTENSION_TEMPLATE_BUILD_TS,
    _EXTENSION_TEMPLATE_EXTENSION_TS as _EXTENSION_TEMPLATE_EXTENSION_TS,
    _EXTENSION_TEMPLATE_TSCONFIG as _EXTENSION_TEMPLATE_TSCONFIG,
    _build_extension_manifest as _build_extension_manifest,
    _build_extension_package_json as _build_extension_package_json,
    _extension_vendor_dir as _extension_vendor_dir,
    _read_extension_vendor_tarballs as _read_extension_vendor_tarballs,
    _resolve_extension_entrypoint as _resolve_extension_entrypoint,
    build_extension as build_extension,
    scaffold_extension as scaffold_extension,
)
from .tools_offline import (  # noqa: E402
    _engine_traits as _engine_traits,
    _groove_compare_from_mapping as _groove_compare_from_mapping,
    _groove_evidence_from_mapping as _groove_evidence_from_mapping,
    _groove_generate_from_mapping as _groove_generate_from_mapping,
    _groove_search_from_mapping as _groove_search_from_mapping,
    _music_payload as _music_payload,
    analyze_audio as analyze_audio,
    analyze_mix as analyze_mix,
    extract_single_cycle as extract_single_cycle,
    find_frequency_masking as find_frequency_masking,
    groove_apply as groove_apply,
    groove_compare as groove_compare,
    groove_evidence as groove_evidence,
    groove_generate as groove_generate,
    groove_search as groove_search,
    music_generate_bass as music_generate_bass,
    music_generate_drum_groove as music_generate_drum_groove,
    music_plan_production as music_plan_production,
    plan_user_journey as plan_user_journey,
)
# isort: on


PUBLIC_TOOL_FUNCTIONS_HEAD = (
    get_session_info,
    get_session_overview,
    get_bridge_status,
    get_track_list,
    get_track_state,
    get_locators,
    take_snapshot,
    get_ableton_logs,
    get_control_surfaces,
    get_scenes,
    get_scene_state,
    get_project_metadata,
    get_loop_settings,
    get_selected_context,
    get_clip_summary,
    get_clip_notes,
    get_clip_info,
    get_device_list,
    get_parameter_value,
    set_parameter_value,
    get_routing,
    get_browser_categories,
    search_browser,
    diff_snapshots_tool,
    get_song_length,
    live_find_track,
    live_find_device,
    live_find_clip,
    list_device_params,
    create_cue_point,
    bulk_create_cue_points,
    delete_cue_point,
    set_current_song_time,
    set_tempo,
    start_playback,
    stop_playback,
    set_loop,
    set_loop_start,
    set_loop_length,
    run_batch,
    add_notes_to_clip,
    fire_clip,
    create_clip,
    delete_clip,
    clear_clip_notes,
    fire_scene,
    set_track_property,
    set_track_color,
    set_clip_color,
    diagnose_clip_targets,
    get_arrangement_clips,
    duplicate_session_clip_to_arrangement,
    delete_arrangement_clip,
    move_arrangement_clip,
    get_device_chains,
    get_midi_chain_report,
    describe_instrument,
    get_clip_automation,
    create_clip_automation_curve,
    add_notes_pattern,
    set_arrangement_clip_properties,
    move_track,
    reorder_tracks,
    move_track_to_group,
    ungroup_track,
    merge_groups,
    set_clip_properties,
    create_clip_automation,
    # v0.5.4 — plugin presets (no Configure step required)
    get_plugin_presets,
    set_plugin_preset,
    # v0.3.0
    get_composition_structure,
    diagnose_midi_clip,
    create_midi_track,
    rename_track,
    get_warp_state,
    set_warp_state,
    load_device_to_track,
    scaffold_extension,
    build_extension,
    # v0.5.0 — set lifecycle
    lifecycle_status,
    save_set,
    quit_ableton,
    live_fade,
    create_audio_track,
)


# Canonical ordered tuple of every public tool callable. Assembled after the
# v0.5.0 offline mix analysis wrappers are defined so all names are in scope.
PUBLIC_TOOL_FUNCTIONS = (
    *PUBLIC_TOOL_FUNCTIONS_HEAD,
    # v0.5.0 — offline mix analysis
    analyze_audio,
    find_frequency_masking,
    analyze_mix,
    extract_single_cycle,
    # v0.6.0 — offline music generation
    music_generate_drum_groove,
    music_generate_bass,
    music_plan_production,
    groove_search,
    groove_evidence,
    groove_generate,
    groove_compare,
    groove_apply,
    plan_user_journey,
)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
