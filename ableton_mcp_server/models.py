from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from contracts import (
    TRACK_COLOR_INDEX_MAX,
    TRACK_COLOR_INDEX_MIN,
    TRACK_COLOR_RGB_MAX,
    TRACK_COLOR_RGB_MIN,
)

from .groove_intelligence.mcp_models import ApplyRequestV1
from .groove_intelligence.mcp_models import (
    CompareRequestV1 as GrooveCompareRequest,
)
from .groove_intelligence.mcp_models import (
    EvidenceRequestV1 as GrooveEvidenceRequest,
)
from .groove_intelligence.mcp_models import (
    GenerateRequestV1 as GrooveGenerateRequest,
)
from .groove_intelligence.mcp_models import (
    SearchRequestV1 as GrooveSearchRequest,
)

NonNegativeInt = Annotated[int, Field(ge=0)]
PaletteIndex = Annotated[int, Field(ge=TRACK_COLOR_INDEX_MIN, le=TRACK_COLOR_INDEX_MAX)]
PackedRgb = Annotated[int, Field(ge=TRACK_COLOR_RGB_MIN, le=TRACK_COLOR_RGB_MAX)]
NonNegativeBeat = Annotated[float, Field(ge=0, le=100000)]
PositiveBeat = Annotated[float, Field(gt=0, le=100000)]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyRequest(RequestModel):
    pass


# isort: off
# The request models live in these modules, in the order they had in this file.
from . import models_read  # noqa: E402,F401
from . import models_devices  # noqa: E402,F401
from . import models_arrangement  # noqa: E402,F401
from . import models_offline  # noqa: E402,F401
from .models_read import (  # noqa: E402
    AutomationPoint as AutomationPoint,
    ClearClipNotesRequest as ClearClipNotesRequest,
    CreateClipAutomationRequest as CreateClipAutomationRequest,
    DeleteClipRequest as DeleteClipRequest,
    DiagnoseClipTargetsRequest as DiagnoseClipTargetsRequest,
    FireSceneRequest as FireSceneRequest,
    GetAbletonLogsRequest as GetAbletonLogsRequest,
    GetBridgeStatusRequest as GetBridgeStatusRequest,
    GetClipInfoRequest as GetClipInfoRequest,
    GetClipNotesRequest as GetClipNotesRequest,
    GetClipSummaryRequest as GetClipSummaryRequest,
    GetControlSurfacesRequest as GetControlSurfacesRequest,
    GetLocatorsRequest as GetLocatorsRequest,
    GetLoopSettingsRequest as GetLoopSettingsRequest,
    GetProjectMetadataRequest as GetProjectMetadataRequest,
    GetSceneStateRequest as GetSceneStateRequest,
    GetScenesRequest as GetScenesRequest,
    GetSelectedContextRequest as GetSelectedContextRequest,
    GetSessionInfoRequest as GetSessionInfoRequest,
    GetSessionOverviewRequest as GetSessionOverviewRequest,
    GetTrackListRequest as GetTrackListRequest,
    GetTrackStateRequest as GetTrackStateRequest,
    MergeGroupsRequest as MergeGroupsRequest,
    MoveTrackRequest as MoveTrackRequest,
    MoveTrackToGroupRequest as MoveTrackToGroupRequest,
    ReorderTracksRequest as ReorderTracksRequest,
    SetClipColorRequest as SetClipColorRequest,
    SetClipPropertiesRequest as SetClipPropertiesRequest,
    SetTrackColorRequest as SetTrackColorRequest,
    SetTrackPropertyRequest as SetTrackPropertyRequest,
    TakeSnapshotRequest as TakeSnapshotRequest,
    UngroupTrackRequest as UngroupTrackRequest,
)
from .models_devices import (  # noqa: E402
    AddNotesToClipRequest as AddNotesToClipRequest,
    BulkCuePointsRequest as BulkCuePointsRequest,
    CommandSpec as CommandSpec,
    CreateClipRequest as CreateClipRequest,
    CreateCuePointRequest as CreateCuePointRequest,
    CuePointSpec as CuePointSpec,
    DeleteCuePointRequest as DeleteCuePointRequest,
    DiffSnapshotsRequest as DiffSnapshotsRequest,
    FireClipRequest as FireClipRequest,
    GetBrowserCategoriesRequest as GetBrowserCategoriesRequest,
    GetDeviceListRequest as GetDeviceListRequest,
    GetParameterValueRequest as GetParameterValueRequest,
    GetPluginPresetsRequest as GetPluginPresetsRequest,
    GetRoutingRequest as GetRoutingRequest,
    GetSongLengthRequest as GetSongLengthRequest,
    ListDeviceParamsRequest as ListDeviceParamsRequest,
    LiveFindClipRequest as LiveFindClipRequest,
    LiveFindDeviceRequest as LiveFindDeviceRequest,
    LiveFindTrackRequest as LiveFindTrackRequest,
    NoteSpec as NoteSpec,
    PreconditionSpec as PreconditionSpec,
    RunBatchRequest as RunBatchRequest,
    SearchBrowserRequest as SearchBrowserRequest,
    SetCurrentSongTimeRequest as SetCurrentSongTimeRequest,
    SetLoopLengthRequest as SetLoopLengthRequest,
    SetLoopRequest as SetLoopRequest,
    SetLoopStartRequest as SetLoopStartRequest,
    SetParameterValueRequest as SetParameterValueRequest,
    SetPluginPresetRequest as SetPluginPresetRequest,
    SetTempoRequest as SetTempoRequest,
    SlotEmptyParams as SlotEmptyParams,
    StartPlaybackRequest as StartPlaybackRequest,
    StopPlaybackRequest as StopPlaybackRequest,
)
from .models_arrangement import (  # noqa: E402
    AddNotesPatternRequest as AddNotesPatternRequest,
    CreateAudioTrackRequest as CreateAudioTrackRequest,
    CreateClipAutomationCurveRequest as CreateClipAutomationCurveRequest,
    CreateMidiTrackRequest as CreateMidiTrackRequest,
    CurveControlPoint as CurveControlPoint,
    DeleteArrangementClipRequest as DeleteArrangementClipRequest,
    DescribeInstrumentRequest as DescribeInstrumentRequest,
    DiagnoseMidiClipRequest as DiagnoseMidiClipRequest,
    DuplicateSessionClipToArrangementRequest as DuplicateSessionClipToArrangementRequest,
    GetArrangementClipsRequest as GetArrangementClipsRequest,
    GetClipAutomationRequest as GetClipAutomationRequest,
    GetCompositionStructureRequest as GetCompositionStructureRequest,
    GetDeviceChainsRequest as GetDeviceChainsRequest,
    GetMidiChainReportRequest as GetMidiChainReportRequest,
    MoveArrangementClipRequest as MoveArrangementClipRequest,
    PatternNote as PatternNote,
    RenameTrackRequest as RenameTrackRequest,
    SetArrangementClipPropertiesRequest as SetArrangementClipPropertiesRequest,
)
from .models_offline import (  # noqa: E402
    AnalyzeAudioRequest as AnalyzeAudioRequest,
    AnalyzeMixRequest as AnalyzeMixRequest,
    BuildExtensionRequest as BuildExtensionRequest,
    ExtractSingleCycleRequest as ExtractSingleCycleRequest,
    FindFrequencyMaskingRequest as FindFrequencyMaskingRequest,
    GetLifecycleStatusRequest as GetLifecycleStatusRequest,
    GetWarpStateRequest as GetWarpStateRequest,
    LiveFadeRequest as LiveFadeRequest,
    LoadDeviceToTrackRequest as LoadDeviceToTrackRequest,
    MusicGenerateBassRequest as MusicGenerateBassRequest,
    MusicGenerateDrumGrooveRequest as MusicGenerateDrumGrooveRequest,
    MusicPlanProductionRequest as MusicPlanProductionRequest,
    MusicTraits as MusicTraits,
    PlanUserJourneyRequest as PlanUserJourneyRequest,
    QuitAbletonRequest as QuitAbletonRequest,
    SaveSetRequest as SaveSetRequest,
    ScaffoldExtensionRequest as ScaffoldExtensionRequest,
    SetWarpStateRequest as SetWarpStateRequest,
)
# isort: on


TOOL_REQUEST_MODELS: dict[str, type[RequestModel]] = {
    "get_session_info": GetSessionInfoRequest,
    "get_bridge_status": GetBridgeStatusRequest,
    "get_track_list": GetTrackListRequest,
    "get_track_state": GetTrackStateRequest,
    "get_locators": GetLocatorsRequest,
    "take_snapshot": TakeSnapshotRequest,
    "get_ableton_logs": GetAbletonLogsRequest,
    "get_control_surfaces": GetControlSurfacesRequest,
    "get_scenes": GetScenesRequest,
    "get_scene_state": GetSceneStateRequest,
    "get_project_metadata": GetProjectMetadataRequest,
    "get_loop_settings": GetLoopSettingsRequest,
    "get_selected_context": GetSelectedContextRequest,
    "get_clip_summary": GetClipSummaryRequest,
    "get_clip_notes": GetClipNotesRequest,
    "get_clip_info": GetClipInfoRequest,
    "get_session_overview": GetSessionOverviewRequest,
    "delete_clip": DeleteClipRequest,
    "clear_clip_notes": ClearClipNotesRequest,
    "fire_scene": FireSceneRequest,
    "set_track_property": SetTrackPropertyRequest,
    "set_track_color": SetTrackColorRequest,
    "set_clip_color": SetClipColorRequest,
    "diagnose_clip_targets": DiagnoseClipTargetsRequest,
    "get_arrangement_clips": GetArrangementClipsRequest,
    "duplicate_session_clip_to_arrangement": DuplicateSessionClipToArrangementRequest,
    "delete_arrangement_clip": DeleteArrangementClipRequest,
    "move_arrangement_clip": MoveArrangementClipRequest,
    "set_arrangement_clip_properties": SetArrangementClipPropertiesRequest,
    "get_device_chains": GetDeviceChainsRequest,
    "get_midi_chain_report": GetMidiChainReportRequest,
    "describe_instrument": DescribeInstrumentRequest,
    "get_clip_automation": GetClipAutomationRequest,
    "create_clip_automation_curve": CreateClipAutomationCurveRequest,
    "add_notes_pattern": AddNotesPatternRequest,
    "move_track": MoveTrackRequest,
    "reorder_tracks": ReorderTracksRequest,
    "move_track_to_group": MoveTrackToGroupRequest,
    "ungroup_track": UngroupTrackRequest,
    "merge_groups": MergeGroupsRequest,
    "set_clip_properties": SetClipPropertiesRequest,
    "create_clip_automation": CreateClipAutomationRequest,
    "get_device_list": GetDeviceListRequest,
    "get_parameter_value": GetParameterValueRequest,
    "set_parameter_value": SetParameterValueRequest,
    "get_plugin_presets": GetPluginPresetsRequest,
    "set_plugin_preset": SetPluginPresetRequest,
    "get_routing": GetRoutingRequest,
    "get_browser_categories": GetBrowserCategoriesRequest,
    "search_browser": SearchBrowserRequest,
    "diff_snapshots_tool": DiffSnapshotsRequest,
    "get_song_length": GetSongLengthRequest,
    "live_find_track": LiveFindTrackRequest,
    "live_find_device": LiveFindDeviceRequest,
    "live_find_clip": LiveFindClipRequest,
    "list_device_params": ListDeviceParamsRequest,
    "create_cue_point": CreateCuePointRequest,
    "bulk_create_cue_points": BulkCuePointsRequest,
    "delete_cue_point": DeleteCuePointRequest,
    "set_current_song_time": SetCurrentSongTimeRequest,
    "set_tempo": SetTempoRequest,
    "start_playback": StartPlaybackRequest,
    "stop_playback": StopPlaybackRequest,
    "set_loop": SetLoopRequest,
    "set_loop_start": SetLoopStartRequest,
    "set_loop_length": SetLoopLengthRequest,
    "run_batch": RunBatchRequest,
    "add_notes_to_clip": AddNotesToClipRequest,
    "fire_clip": FireClipRequest,
    "create_clip": CreateClipRequest,
    # v0.3.0
    "get_composition_structure": GetCompositionStructureRequest,
    "diagnose_midi_clip": DiagnoseMidiClipRequest,
    "create_midi_track": CreateMidiTrackRequest,
    "rename_track": RenameTrackRequest,
    "get_warp_state": GetWarpStateRequest,
    "set_warp_state": SetWarpStateRequest,
    "load_device_to_track": LoadDeviceToTrackRequest,
    "scaffold_extension": ScaffoldExtensionRequest,
    "build_extension": BuildExtensionRequest,
    # v0.5.0
    "lifecycle_status": GetLifecycleStatusRequest,
    "save_set": SaveSetRequest,
    "quit_ableton": QuitAbletonRequest,
    "live_fade": LiveFadeRequest,
    "create_audio_track": CreateAudioTrackRequest,
    # v0.5.0 — mix analysis
    "analyze_audio": AnalyzeAudioRequest,
    "find_frequency_masking": FindFrequencyMaskingRequest,
    "analyze_mix": AnalyzeMixRequest,
    "extract_single_cycle": ExtractSingleCycleRequest,
    # v0.6.0 — offline music generation
    "music_generate_drum_groove": MusicGenerateDrumGrooveRequest,
    "music_generate_bass": MusicGenerateBassRequest,
    "music_plan_production": MusicPlanProductionRequest,
    "plan_user_journey": PlanUserJourneyRequest,
}

TOOL_REQUEST_MODELS.update(
    {
        "groove_search": GrooveSearchRequest,  # type: ignore[dict-item]
        "groove_evidence": GrooveEvidenceRequest,  # type: ignore[dict-item]
        "groove_generate": GrooveGenerateRequest,  # type: ignore[dict-item]
        "groove_compare": GrooveCompareRequest,  # type: ignore[dict-item]
        "groove_apply": ApplyRequestV1,  # type: ignore[dict-item]
    }
)
