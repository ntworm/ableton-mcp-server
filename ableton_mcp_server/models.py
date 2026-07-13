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


# v0.5.0 — audio-track mirror of CreateMidiTrackRequest. Naming differs:
# `name` is optional (no default) because callers usually want Live's default
# "Audio" track name; only override when explicitly provided. `index` defaults
# to ``-1`` to match Live's LOM "append" semantics.
class CreateAudioTrackRequest(RequestModel):
    index: int = -1
    name: str | None = Field(default=None, max_length=120)


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


class SetWarpStateRequest(RequestModel):
    track_index: NonNegativeInt
    clip_index: NonNegativeInt
    warping: bool | None = None
    warp_mode: Annotated[str, Field(max_length=32)] | None = None

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

    @model_validator(mode="after")
    def require_change(self) -> SetWarpStateRequest:
        if self.warping is None and self.warp_mode is None:
            raise ValueError("provide warping or warp_mode")
        return self


class LoadDeviceToTrackRequest(RequestModel):
    track_index: NonNegativeInt
    device_name: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    device_uri: Annotated[str, Field(min_length=1, max_length=512)] | None = None

    @model_validator(mode="after")
    def exactly_one_name(self) -> LoadDeviceToTrackRequest:
        values = [
            value for value in (self.device_name, self.device_uri) if value is not None
        ]
        if len(values) != 1:
            raise ValueError("provide exactly one of device_name or deprecated device_uri")
        resolved = values[0].strip()
        if not resolved:
            raise ValueError("device name must be non-empty after trimming")
        self.device_name = resolved
        return self

    @property
    def resolved_name(self) -> str:
        assert self.device_name is not None
        return self.device_name


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


class SaveSetRequest(RequestModel):
    """Request payload for ``save_set``.

    ``require_api`` is ``False`` by default — when the Live host hides
    ``Song.save`` the handler returns a structured GUI-workflow response
    instead of raising. Set ``require_api=True`` to fail fast with a
    ``BAD_INPUT`` error in that case.
    """

    require_api: bool = False


class QuitAbletonRequest(RequestModel):
    save: bool = True
    force_without_save: bool = False
    quit_delay_ticks: Annotated[int, Field(ge=1, le=120)] = 2


class LiveFadeRequest(RequestModel):
    """Request payload for ``live_fade``.

    The handler interpolates one track's mixer volume over ``duration``
    seconds in ``steps`` increments. Provide exactly one of ``target_percent``
    or ``target_value`` — ``target_percent`` is the user-facing fader value
    (100 = unity ≈ 0.85 on the LOM parameter) and ``target_value`` is the raw
    LOM value. ``duration`` is bounded at 60 seconds and ``steps`` is the
    interpolation resolution, both enforced on the MCP layer as well as on the
    Remote Script handler.
    """

    track_index: NonNegativeInt
    target_percent: Annotated[float, Field(ge=0, le=200)] | None = None
    target_value: Annotated[float, Field(ge=0, le=1)] | None = None
    duration: Annotated[float, Field(ge=0, le=60.0)] = 10.0
    steps: Annotated[int, Field(ge=1, le=500)] = 40
    curve: Literal["smoothstep", "linear"] = "smoothstep"
    allow_over_unity: bool = False

    @model_validator(mode="after")
    def _exactly_one_target(self) -> LiveFadeRequest:
        if (self.target_percent is None) == (self.target_value is None):
            raise ValueError(
                "Provide exactly one of target_percent or target_value"
            )
        return self


# ---------------------------------------------------------------------------
# v0.5.0 — Mix analysis (offline, no Live bridge)
# ---------------------------------------------------------------------------


class AnalyzeAudioRequest(RequestModel):
    """Request payload for ``analyze_audio``.

    Reads a local audio file from disk and returns LUFS-I, true-peak, RMS,
    and per-band energy summary. ``path`` must point at a file readable by
    ``soundfile``; unsupported encodings surface a structured error.
    """

    path: str = Field(min_length=1)


class FindFrequencyMaskingRequest(RequestModel):
    """Request payload for ``find_frequency_masking``.

    Compares two files sample-rate-aligned: every octave band whose ``target``
    energy exceeds the ``reference`` by ``threshold_db`` dB or more is
    reported. ``target_path`` and ``reference_path`` must point at distinct
    files.
    """

    target_path: str = Field(min_length=1)
    reference_path: str = Field(min_length=1)
    threshold_db: float = 6.0

    @model_validator(mode="after")
    def _paths_differ(self) -> FindFrequencyMaskingRequest:
        if self.target_path == self.reference_path:
            raise ValueError("target_path and reference_path must differ")
        return self


class AnalyzeMixRequest(RequestModel):
    """Request payload for ``analyze_mix``.

    ``stems`` is the ordered list of local audio files (1..16) to analyze
    individually and then compare pair-wise for masking. The cap mirrors the
    ``MAX_STEMS`` policy enforced in ``ableton_mcp_server.analysis.audio``.
    """

    stems: Annotated[list[str], Field(min_length=1, max_length=16)]


class ExtractSingleCycleRequest(RequestModel):
    """Request payload for ``extract_single_cycle``.

    Searches the first 5 seconds of ``path`` for a candidate single-cycle
    waveform starting at a low-energy zero-crossing. ``frame_size`` is the
    analysis FFT window; the default of 2048 is tuned for bass-range
    material but valid in 64..65536 inclusive.
    """

    path: str = Field(min_length=1)
    frame_size: Annotated[int, Field(ge=64, le=65536)] = 2048


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
    "save_set": SaveSetRequest,
    "quit_ableton": QuitAbletonRequest,
    "live_fade": LiveFadeRequest,
    "create_audio_track": CreateAudioTrackRequest,
    # v0.5.0 — mix analysis
    "analyze_audio": AnalyzeAudioRequest,
    "find_frequency_masking": FindFrequencyMaskingRequest,
    "analyze_mix": AnalyzeMixRequest,
    "extract_single_cycle": ExtractSingleCycleRequest,
}
