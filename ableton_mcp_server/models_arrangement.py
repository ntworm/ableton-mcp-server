"""Request models of the arrangement, automation curve, MIDI and track creation tools."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, field_validator

from .models import (
    EmptyRequest,
    NonNegativeBeat,
    NonNegativeInt,
    PositiveBeat,
    RequestModel,
)

# ---------------------------------------------------------------------------
# v0.5.5 — Arrangement timeline
# ---------------------------------------------------------------------------


class GetArrangementClipsRequest(RequestModel):
    track_index: NonNegativeInt


class DuplicateSessionClipToArrangementRequest(RequestModel):
    """Place a Session clip on the timeline at ``time``, in beats from bar 1."""

    track_index: NonNegativeInt
    clip_index: NonNegativeInt
    time: NonNegativeBeat


class DeleteArrangementClipRequest(RequestModel):
    """``clip_index`` indexes ``Track.arrangement_clips``, not a Session slot."""

    track_index: NonNegativeInt
    clip_index: NonNegativeInt


class MoveArrangementClipRequest(DeleteArrangementClipRequest):
    time: NonNegativeBeat


class SetArrangementClipPropertiesRequest(DeleteArrangementClipRequest):
    """At least one of ``name`` or ``muted`` must be present."""

    name: str | None = None
    muted: bool | None = None


# ---------------------------------------------------------------------------
# v0.5.6 — Instrument comprehension and authoring shorthands
# ---------------------------------------------------------------------------


class GetDeviceChainsRequest(RequestModel):
    track_index: NonNegativeInt
    device_index: NonNegativeInt


class GetMidiChainReportRequest(RequestModel):
    track_index: NonNegativeInt


class DescribeInstrumentRequest(RequestModel):
    track_index: NonNegativeInt


class GetClipAutomationRequest(RequestModel):
    """``device_index`` disambiguates a parameter name shared by several devices."""

    track_index: NonNegativeInt
    clip_index: NonNegativeInt
    parameter_name: str
    device_index: NonNegativeInt | None = None
    resolution: Annotated[float, Field(gt=0, le=16)] = 0.25
    # Live nests the controls that matter. ``chain_index`` selects a rack chain;
    # add ``chain_device_index`` for a device inside it, or leave it out to
    # address the chain's own mixer (``volume`` / ``panning``).
    chain_index: NonNegativeInt | None = None
    chain_device_index: NonNegativeInt | None = None


class CurveControlPoint(RequestModel):
    time: NonNegativeBeat
    value: float


class CreateClipAutomationCurveRequest(RequestModel):
    """Few control points in, a dense step envelope out.

    Live's clip envelopes are stepped, so a smooth ramp needs many steps. The
    expansion happens on the server: the caller sends the shape, not its
    hundreds of breakpoints.
    """

    track_index: NonNegativeInt
    clip_index: NonNegativeInt
    parameter_name: str
    control_points: Annotated[list[CurveControlPoint], Field(min_length=2, max_length=200)]
    shape: Literal["linear", "exp", "log", "hold"] = "linear"
    resolution: Annotated[float, Field(gt=0, le=16)] = 0.25
    device_index: NonNegativeInt | None = None
    # Live nests the controls that matter. ``chain_index`` selects a rack chain;
    # add ``chain_device_index`` for a device inside it, or leave it out to
    # address the chain's own mixer (``volume`` / ``panning``).
    chain_index: NonNegativeInt | None = None
    chain_device_index: NonNegativeInt | None = None


class PatternNote(RequestModel):
    pitch: Annotated[int, Field(ge=0, le=127)]
    start_time: NonNegativeBeat
    duration: PositiveBeat
    velocity: Annotated[int, Field(ge=1, le=127)] = 100
    mute: bool = False


class AddNotesPatternRequest(RequestModel):
    """One cell, repeated, so the payload stays the size of the idea."""

    track_index: NonNegativeInt
    clip_index: NonNegativeInt
    cell: Annotated[list[PatternNote], Field(min_length=1, max_length=256)]
    cell_length: PositiveBeat
    repeats: Annotated[int, Field(ge=1, le=128)]
    transpose_per_repeat: Annotated[int, Field(ge=-48, le=48)] = 0
    velocity_scale_per_repeat: Annotated[float, Field(gt=0, le=4)] = 1.0


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
            "C",
            "C#",
            "Db",
            "D",
            "D#",
            "Eb",
            "E",
            "F",
            "F#",
            "Gb",
            "G",
            "G#",
            "Ab",
            "A",
            "A#",
            "Bb",
            "B",
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
            "major",
            "minor",
            "dorian",
            "phrygian",
            "lydian",
            "mixolydian",
            "aeolian",
            "locrian",
            "harmonic_minor",
            "melodic_minor",
            "pentatonic_major",
            "pentatonic_minor",
            "blues",
            "chromatic",
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
