"""Request models of the warp, device loading, extension, lifecycle and offline tools."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .models import (
    EmptyRequest,
    NonNegativeInt,
    RequestModel,
)

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
        values = [value for value in (self.device_name, self.device_uri) if value is not None]
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
            raise ValueError("Provide exactly one of target_percent or target_value")
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


# ---------------------------------------------------------------------------
# v0.6.0 — Offline music generation
# ---------------------------------------------------------------------------


class MusicTraits(RequestModel):
    """Trait vector for generation: four axes, each owning exactly one verb.

    ``electro`` builds the grid — it sets the subdivision and opens the hat
    palette. ``space`` subtracts from it, dropping events and lengthening the
    survivors. ``weirdness`` deviates what is left through ghost notes, timing
    jitter and octave leaps, all bounded. ``groove`` displaces in time and
    accents the backbeat without adding or removing a single note.

    No axis does two jobs, which is what keeps a combination predictable. They
    are applied in that fixed order, and the response names the axes that
    actually changed the output under ``traits_applied``.
    """

    groove: Annotated[float, Field(ge=0, le=1)] = 0.0
    electro: Annotated[float, Field(ge=0, le=1)] = 0.0
    weirdness: Annotated[float, Field(ge=0, le=1)] = 0.0
    space: Annotated[float, Field(ge=0, le=1)] = 0.0


class MusicGenerateDrumGrooveRequest(RequestModel):
    """Request payload for ``music_generate_drum_groove``.

    Generation is pure and keyed on ``seed``: the same ``bars``/``seed`` pair
    returns the same notes forever. ``apply`` is the only part that reaches
    Live, and it requires an explicit empty Session slot.
    """

    bars: Annotated[int, Field(ge=1, le=64)] = 4
    seed: int = 1
    traits: MusicTraits | None = None
    apply: bool = False
    track_index: NonNegativeInt | None = None
    clip_index: NonNegativeInt | None = None

    @model_validator(mode="after")
    def validate_apply_target(self) -> MusicGenerateDrumGrooveRequest:
        if self.apply and (self.track_index is None or self.clip_index is None):
            raise ValueError("track_index and clip_index are required when apply is True")
        return self


class MusicGenerateBassRequest(MusicGenerateDrumGrooveRequest):
    """Request payload for ``music_generate_bass``.

    Every generated note is ``root_midi`` in some octave, so the line cannot
    imply a harmony the caller did not ask for.
    """

    root_midi: Annotated[int, Field(ge=0, le=127)] = 36


class MusicPlanProductionRequest(RequestModel):
    """Request payload for ``music_plan_production``.

    There is no language model behind this tool. It reads what the prompt
    states literally, lays a conventional section grid over ``bars``, and names
    what it could not resolve.
    """

    prompt: Annotated[str, Field(min_length=3, max_length=4000)]
    bars: Annotated[int, Field(ge=1, le=512)] | None = None
    bpm: Annotated[float, Field(ge=40, le=300)] | None = None


class PlanUserJourneyRequest(RequestModel):
    """Request payload for ``plan_user_journey``.

    ``journey_type`` is closed because the plan is a fixed stage grid per
    journey, not a generated one. ``traits`` is free text that the tool only
    inspects and echoes; nothing downstream executes it.
    """

    journey_type: Literal[
        "sequence_drums", "compose_melody", "compose_harmony", "design_sound"
    ]
    traits: Annotated[str, Field(max_length=2000)]
