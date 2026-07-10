from __future__ import annotations

import math
from typing import Annotated, Any

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


class GetRoutingRequest(RequestModel):
    track_index: NonNegativeInt


class GetBrowserCategoriesRequest(EmptyRequest):
    pass


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


TOOL_REQUEST_MODELS: dict[str, type[RequestModel]] = {
    "get_session_info": GetSessionInfoRequest,
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
    "get_device_list": GetDeviceListRequest,
    "get_parameter_value": GetParameterValueRequest,
    "get_routing": GetRoutingRequest,
    "get_browser_categories": GetBrowserCategoriesRequest,
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
}
