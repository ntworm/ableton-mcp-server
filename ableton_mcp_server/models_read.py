"""Request models of the session, track, clip and hierarchy tools."""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .models import (
    EmptyRequest,
    NonNegativeBeat,
    NonNegativeInt,
    PackedRgb,
    PaletteIndex,
    RequestModel,
)


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


class SetTrackColorRequest(RequestModel):
    """Exactly one of ``color_index`` (palette slot) or ``color`` (packed RGB).

    ``color_index`` addresses Live's 70-swatch colour palette; ``color`` is the
    ``0x00rrggbb`` value documented for ``Track.color``. Requiring exactly one
    keeps the write single-valued, so the readback has one unambiguous target.
    """

    track_index: NonNegativeInt
    color_index: PaletteIndex | None = None
    color: PackedRgb | None = None

    @model_validator(mode="after")
    def exactly_one_colour_source(self) -> SetTrackColorRequest:
        provided = [value for value in (self.color_index, self.color) if value is not None]
        if len(provided) != 1:
            raise ValueError("provide exactly one of color_index or color")
        return self


class SetClipColorRequest(RequestModel):
    """Colour one Session or Arrangement clip.

    ``scope`` selects the lane. Session clips are addressed by clip-slot
    index; Arrangement clips by their position in ``Track.arrangement_clips``.
    Run ``diagnose_clip_targets`` first if you are unsure which clips the
    connected Live host exposes.
    """

    track_index: NonNegativeInt
    clip_index: NonNegativeInt
    scope: Literal["session", "arrangement"] = "session"
    color_index: PaletteIndex | None = None
    color: PackedRgb | None = None

    @model_validator(mode="after")
    def exactly_one_colour_source(self) -> SetClipColorRequest:
        provided = [value for value in (self.color_index, self.color) if value is not None]
        if len(provided) != 1:
            raise ValueError("provide exactly one of color_index or color")
        return self


class DiagnoseClipTargetsRequest(RequestModel):
    """``track_index`` omitted means every track in the Set."""

    track_index: NonNegativeInt | None = None


# ---------------------------------------------------------------------------
# Track hierarchy requests
#
# These are fully validated even though Live's public API cannot perform any
# of them: a caller must be able to tell "my request was malformed" from "no
# API can do this". The bridge answers a well-formed request with a typed
# CAPABILITY_UNAVAILABLE carrying the evidence, and never mutates the Set.
# ---------------------------------------------------------------------------


class MoveTrackRequest(RequestModel):
    track_index: NonNegativeInt
    destination_index: NonNegativeInt


class ReorderTracksRequest(RequestModel):
    order: list[NonNegativeInt] = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def order_has_no_duplicates(self) -> ReorderTracksRequest:
        if len(set(self.order)) != len(self.order):
            raise ValueError("order must not repeat a track index")
        return self


class MoveTrackToGroupRequest(RequestModel):
    track_index: NonNegativeInt
    group_track_index: NonNegativeInt

    @model_validator(mode="after")
    def group_is_not_itself(self) -> MoveTrackToGroupRequest:
        if self.track_index == self.group_track_index:
            raise ValueError("a track cannot be moved into itself")
        return self


class UngroupTrackRequest(RequestModel):
    track_index: NonNegativeInt


class MergeGroupsRequest(RequestModel):
    source_group_index: NonNegativeInt
    destination_group_index: NonNegativeInt
    # Deleting the emptied source is never performed by this bridge; the flag
    # exists so an explicit request for it is rejected loudly instead of being
    # silently ignored.
    delete_empty_source: bool = False

    @model_validator(mode="after")
    def groups_differ(self) -> MergeGroupsRequest:
        if self.source_group_index == self.destination_group_index:
            raise ValueError("source and destination groups must differ")
        return self


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
    # A track can carry the same parameter name on several devices — every rack
    # has a "Macro 1". Without this the bridge refuses with AMBIGUOUS_MATCH
    # instead of guessing which device the caller meant.
    device_index: NonNegativeInt | None = None

    @field_validator("parameter_name")
    @classmethod
    def strip_automation_parameter(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("parameter_name must be non-empty")
        return value

    # Live nests the controls that matter. ``chain_index`` selects a rack chain;
    # add ``chain_device_index`` for a device inside it, or leave it out to
    # address the chain's own mixer (``volume`` / ``panning``).
    chain_index: NonNegativeInt | None = None
    chain_device_index: NonNegativeInt | None = None
