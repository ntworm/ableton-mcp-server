"""Request models of the device, browser, cue, transport, batch and note tools."""

from __future__ import annotations

import math
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator, model_validator

from contracts import ALLOWED_MUTATIONS

from .models import (
    EmptyRequest,
    NonNegativeBeat,
    NonNegativeInt,
    PositiveBeat,
    RequestModel,
)


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

    # Live nests the controls that matter. ``chain_index`` selects a rack chain;
    # add ``chain_device_index`` for a device inside it, or leave it out to
    # address the chain's own mixer (``volume`` / ``panning``).
    chain_index: NonNegativeInt | None = None
    chain_device_index: NonNegativeInt | None = None


class SetParameterValueRequest(GetParameterValueRequest):
    value: float

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("value must be finite")
        return value

    # Live nests the controls that matter. ``chain_index`` selects a rack chain;
    # add ``chain_device_index`` for a device inside it, or leave it out to
    # address the chain's own mixer (``volume`` / ``panning``).
    chain_index: NonNegativeInt | None = None
    chain_device_index: NonNegativeInt | None = None


class GetPluginPresetsRequest(RequestModel):
    track_index: NonNegativeInt
    device_index: NonNegativeInt


class SetPluginPresetRequest(GetPluginPresetsRequest):
    """Select one plugin preset by index or by exact name.

    Requiring exactly one selector keeps the write single-valued, so the
    readback has one unambiguous target — the same rule the colour writes use.
    """

    preset_index: NonNegativeInt | None = None
    preset_name: Annotated[str, Field(min_length=1, max_length=256)] | None = None

    @field_validator("preset_name")
    @classmethod
    def strip_preset_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("preset_name must be non-empty")
        return value

    @model_validator(mode="after")
    def exactly_one_selector(self) -> SetPluginPresetRequest:
        provided = [self.preset_index is not None, self.preset_name is not None]
        if sum(provided) != 1:
            raise ValueError("provide exactly one of preset_index or preset_name")
        return self


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


class LiveFindDeviceRequest(RequestModel):
    track_index: NonNegativeInt
    query: Annotated[str, Field(min_length=1, max_length=256)]

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must be non-empty")
        return value


class LiveFindClipRequest(RequestModel):
    track_index: NonNegativeInt
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
    dry_run: bool = False

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


class SlotEmptyParams(RequestModel):
    track_index: NonNegativeInt
    clip_index: NonNegativeInt


class PreconditionSpec(RequestModel):
    type: Literal["slot_empty"]
    version: Literal["v1"]
    params: SlotEmptyParams


class RunBatchRequest(RequestModel):
    commands: Annotated[list[CommandSpec], Field(min_length=1, max_length=100)]
    preconditions: Annotated[list[PreconditionSpec], Field(max_length=16)] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_commands(self) -> RunBatchRequest:
        for command in self.commands:
            if command.type == "run_batch":
                raise ValueError("run_batch cannot contain run_batch")
            if command.type not in ALLOWED_MUTATIONS:
                raise ValueError(f"{command.type!r} is not an allowed mutation")
        keys = [
            (item.type, item.version, item.params.track_index, item.params.clip_index)
            for item in self.preconditions
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("preconditions must not contain duplicates")
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
    dry_run: bool = False
