from __future__ import annotations

import math
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from contracts import ALLOWED_MUTATIONS

NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeBeat = Annotated[float, Field(ge=0, le=100000)]
PositiveBeat = Annotated[float, Field(gt=0, le=100000)]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyRequest(RequestModel):
    pass


class GetSessionInfoRequest(EmptyRequest):
    pass


class GetBridgeStatusRequest(EmptyRequest):
    pass


class GetTrackListRequest(EmptyRequest):
    pass


class GetTrackStateRequest(RequestModel):
    track_index: NonNegativeInt


class GetLocatorsRequest(EmptyRequest):
    pass


class TakeSnapshotRequest(EmptyRequest):
    pass


class GetAbletonLogsRequest(RequestModel):
    lines: Annotated[int, Field(ge=1, le=5000)] = 100


class GetControlSurfacesRequest(EmptyRequest):
    pass


class GetScenesRequest(EmptyRequest):
    pass


class GetSceneStateRequest(RequestModel):
    scene_index: NonNegativeInt


class GetProjectMetadataRequest(EmptyRequest):
    pass


class GetLoopSettingsRequest(EmptyRequest):
    pass


class GetSelectedContextRequest(EmptyRequest):
    pass


class GetClipSummaryRequest(RequestModel):
    track_index: NonNegativeInt


class GetClipNotesRequest(RequestModel):
    track_index: NonNegativeInt
    clip_index: NonNegativeInt


class GetClipInfoRequest(GetClipNotesRequest):
    pass


class GetSessionOverviewRequest(EmptyRequest):
    pass


class DeleteClipRequest(GetClipNotesRequest):
    pass


class ClearClipNotesRequest(GetClipNotesRequest):
    pass


class FireSceneRequest(RequestModel):
    scene_index: NonNegativeInt


class SetTrackPropertyRequest(RequestModel):
    track_index: NonNegativeInt
    property: Literal["mute", "solo", "arm"]
    value: bool


class SetClipPropertiesRequest(GetClipNotesRequest):
    loop_start: NonNegativeBeat | None = None
    loop_end: NonNegativeBeat | None = None
    name: Annotated[str, Field(min_length=1, max_length=256)] | None = None

    @field_validator("name")
    @classmethod
    def strip_clip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("name must be non-empty")
        return value

    @model_validator(mode="after")
    def validate_requested_changes(self) -> SetClipPropertiesRequest:
        if self.loop_start is None and self.loop_end is None and self.name is None:
            raise ValueError("at least one clip property must be provided")
        if (
            self.loop_start is not None
            and self.loop_end is not None
            and self.loop_start >= self.loop_end
        ):
            raise ValueError("loop_start must be less than loop_end")
        return self


class AutomationPoint(RequestModel):
    time: NonNegativeBeat
    value: float

    @field_validator("value")
    @classmethod
    def finite_automation_value(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("automation value must be finite")
        return value


class CreateClipAutomationRequest(GetClipNotesRequest):
    parameter_name: Annotated[str, Field(min_length=1, max_length=256)]
    automation_points: Annotated[list[AutomationPoint], Field(min_length=1, max_length=500)]

    @field_validator("parameter_name")
    @classmethod
    def strip_automation_parameter(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("parameter_name must be non-empty")
        return value


class GetDeviceListRequest(RequestModel):
    track_index: NonNegativeInt


class GetParameterValueRequest(RequestModel):
    track_index: NonNegativeInt
    device_index: NonNegativeInt
    parameter_name: Annotated[str, Field(min_length=1, max_length=256)]

    @field_validator("parameter_name")
    @classmethod
    def strip_parameter_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("parameter_name must be non-empty")
        return value


class SetParameterValueRequest(GetParameterValueRequest):
    value: float

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("value must be finite")
        return value


class GetRoutingRequest(RequestModel):
    track_index: NonNegativeInt


class GetBrowserCategoriesRequest(EmptyRequest):
    pass


class SearchBrowserRequest(RequestModel):
    query: Annotated[str, Field(min_length=1, max_length=256)]
    category_type: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    limit: Annotated[int, Field(ge=1, le=200)] = 50

    @field_validator("query", "category_type")
    @classmethod
    def strip_browser_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("browser text fields must be non-empty")
        return value


class DiffSnapshotsRequest(RequestModel):
    snap_a: dict[str, Any]
    snap_b: dict[str, Any]


class GetSongLengthRequest(EmptyRequest):
    pass


class LiveFindTrackRequest(RequestModel):
    query: Annotated[str, Field(min_length=1, max_length=256)]

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must be non-empty")
        return value


class ListDeviceParamsRequest(RequestModel):
    track_id: Annotated[str, Field(pattern=r"^track:\d+$")]


class CuePointSpec(RequestModel):
    name: Annotated[str, Field(min_length=1, max_length=256)]
    time: NonNegativeBeat

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must be non-empty")
        return value

    @field_validator("time")
    @classmethod
    def finite_time(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("time must be finite")
        return value


class CreateCuePointRequest(CuePointSpec):
    pass


class BulkCuePointsRequest(RequestModel):
    items: Annotated[list[CuePointSpec], Field(min_length=1, max_length=500)]


class DeleteCuePointRequest(RequestModel):
    time: NonNegativeBeat


class SetCurrentSongTimeRequest(RequestModel):
    time: NonNegativeBeat


class SetTempoRequest(RequestModel):
    tempo: Annotated[float, Field(ge=20, le=999)]

    @field_validator("tempo")
    @classmethod
    def finite_tempo(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("tempo must be finite")
        return value


class StartPlaybackRequest(EmptyRequest):
    pass


class StopPlaybackRequest(EmptyRequest):
    pass


class SetLoopRequest(RequestModel):
    enabled: bool


class SetLoopStartRequest(RequestModel):
    start_beat: NonNegativeBeat


class SetLoopLengthRequest(RequestModel):
    length_beats: PositiveBeat


class CommandSpec(RequestModel):
    type: Annotated[str, Field(min_length=1, max_length=128)]
    params: dict[str, Any] = Field(default_factory=dict)


class RunBatchRequest(RequestModel):
    commands: Annotated[list[CommandSpec], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def validate_commands(self) -> RunBatchRequest:
        for command in self.commands:
            if command.type == "run_batch":
                raise ValueError("run_batch cannot contain run_batch")
            if command.type not in ALLOWED_MUTATIONS:
                raise ValueError(f"{command.type!r} is not an allowed mutation")
        return self


class NoteSpec(RequestModel):
    pitch: Annotated[int, Field(ge=0, le=127)]
    start_time: NonNegativeBeat
    duration: PositiveBeat
    velocity: Annotated[int, Field(ge=1, le=127)] = 100
    mute: bool = False
    probability: Annotated[float, Field(ge=0, le=1)] | None = None
    release_velocity: Annotated[float, Field(ge=0, le=127)] | None = None
    velocity_deviation: Annotated[float, Field(ge=-127, le=127)] | None = None


class AddNotesToClipRequest(RequestModel):
    track_index: NonNegativeInt
    clip_index: NonNegativeInt
    notes: Annotated[list[NoteSpec], Field(min_length=1, max_length=2048)]


class FireClipRequest(RequestModel):
    track_index: NonNegativeInt
    clip_index: NonNegativeInt


class CreateClipRequest(RequestModel):
    track_index: NonNegativeInt
    clip_index: NonNegativeInt
    length_beats: PositiveBeat


# ---------------------------------------------------------------------------
# v0.3.0 — Composition Diagnostics
# ---------------------------------------------------------------------------


class GetCompositionStructureRequest(EmptyRequest):
    pass


class DiagnoseMidiClipRequest(RequestModel):
    track_index: NonNegativeInt
    clip_index: NonNegativeInt
    scale_root: Annotated[str, Field(max_length=3)] | None = None
    scale_type: Annotated[str, Field(max_length=32)] | None = None

    @field_validator("scale_root")
    @classmethod
    def normalize_scale_root(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if value not in (
            "C", "C#", "Db", "D", "D#", "Eb", "E", "F",
            "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B",
        ):
            raise ValueError(f"Invalid scale root: {value!r}")
        return value

    @field_validator("scale_type")
    @classmethod
    def normalize_scale_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if value not in (
            "major", "minor", "dorian", "phrygian", "lydian",
            "mixolydian", "aeolian", "locrian", "harmonic_minor",
            "melodic_minor", "pentatonic_major", "pentatonic_minor",
            "blues", "chromatic",
        ):
            raise ValueError(f"Invalid scale type: {value!r}")
        return value


# ---------------------------------------------------------------------------
# v0.3.0 — Guarded Creative Mutations
# ---------------------------------------------------------------------------


class CreateMidiTrackRequest(RequestModel):
    name: Annotated[str, Field(min_length=1, max_length=128)] = "MIDI Track"
    index: int | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must be non-empty")
        return value


class RenameTrackRequest(RequestModel):
    track_index: NonNegativeInt
    new_name: Annotated[str, Field(min_length=1, max_length=128)]

    @field_validator("new_name")
    @classmethod
    def strip_new_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("new_name must be non-empty")
        return value


# ---------------------------------------------------------------------------
# v0.3.0 — WebSocket Bridge (Warp & Devices)
# ---------------------------------------------------------------------------


class GetWarpStateRequest(RequestModel):
    track_index: NonNegativeInt
    clip_index: NonNegativeInt


class WarpMarkerSpec(RequestModel):
    sample_time: Annotated[float, Field(ge=0)]
    beat_time: Annotated[float, Field(ge=0)]


class SetWarpStateRequest(RequestModel):
    track_index: NonNegativeInt
    clip_index: NonNegativeInt
    warping: bool | None = None
    warp_mode: Annotated[str, Field(max_length=32)] | None = None
    warp_markers: list[WarpMarkerSpec] | None = None

    @field_validator("warp_mode")
    @classmethod
    def validate_warp_mode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        valid = ("beats", "tones", "texture", "re-pitch", "complex", "complex_pro")
        normalized = value.strip().lower().replace(" ", "_")
        if normalized not in valid:
            raise ValueError(f"Invalid warp mode: {value!r}. Valid: {valid}")
        return normalized


class LoadDeviceToTrackRequest(RequestModel):
    track_index: NonNegativeInt
    device_uri: Annotated[str, Field(min_length=1, max_length=512)]

    @field_validator("device_uri")
    @classmethod
    def strip_device_uri(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("device_uri must be non-empty")
        return value


# ---------------------------------------------------------------------------
# v0.3.0 — Extension Scaffolding
# ---------------------------------------------------------------------------


class ScaffoldExtensionRequest(RequestModel):
    name: Annotated[str, Field(min_length=1, max_length=128)]
    author: Annotated[str, Field(min_length=1, max_length=128)] = "ntworm"
    output_directory: Annotated[str, Field(min_length=1, max_length=1024)]


class BuildExtensionRequest(RequestModel):
    project_path: Annotated[str, Field(min_length=1, max_length=1024)]


# ---------------------------------------------------------------------------
# v0.5.0 — Set lifecycle
# ---------------------------------------------------------------------------


class GetLifecycleStatusRequest(EmptyRequest):
    pass


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
    "set_clip_properties": SetClipPropertiesRequest,
    "create_clip_automation": CreateClipAutomationRequest,
    "get_device_list": GetDeviceListRequest,
    "get_parameter_value": GetParameterValueRequest,
    "set_parameter_value": SetParameterValueRequest,
    "get_routing": GetRoutingRequest,
    "get_browser_categories": GetBrowserCategoriesRequest,
    "search_browser": SearchBrowserRequest,
    "diff_snapshots_tool": DiffSnapshotsRequest,
    "get_song_length": GetSongLengthRequest,
    "live_find_track": LiveFindTrackRequest,
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
}
