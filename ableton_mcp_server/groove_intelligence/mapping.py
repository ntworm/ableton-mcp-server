"""Deterministic, rights-aware MIDI-to-kit mapping for Phase 3 apply."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from fractions import Fraction
from typing import Annotated, Literal

from pydantic import Field

from ..models import NoteSpec
from .drum_roles import GM_DRUM_ROLE_BY_PITCH
from .midi_lossless import decompress_bounded, parse_smf
from .schema import GrooveModel, MidiArtifactV1, NoteEventV1

CREATE_CLIP_MAX_LENGTH_BEATS = 100_000.0


class KitMappingProfileV1(GrooveModel):
    profile_id: Annotated[str, Field(min_length=1, max_length=64)]
    gm_map: dict[int, int] = Field(default_factory=dict)
    role_map: dict[str, int] = Field(default_factory=dict)
    user_override: dict[int, int] = Field(default_factory=dict)


class CanonicalApplyEventV1(GrooveModel):
    event_id: int = Field(ge=0)
    source_event_id: int = Field(ge=0)
    source_track_index: int = Field(ge=0)
    source_channel: int = Field(ge=0, le=15)
    original_pitch: int = Field(ge=0, le=127)
    resolved_pitch: int = Field(ge=0, le=127)
    note: NoteSpec

class MappingPlanV1(GrooveModel):
    profile_id: str
    selected_track_index: int | None = None
    selected_channel: int | None = None
    emitted_events: tuple[CanonicalApplyEventV1, ...] = ()
    exact_count: int = 0
    fallback_count: int = 0
    unmapped_count: int = 0
    skipped_count: int = 0
    allowed: bool = True
    warning_codes: list[str] = Field(default_factory=list)
    length_beats: float = 0.0

    @property
    def notes(self) -> tuple[NoteSpec, ...]:
        return tuple(item.note for item in self.emitted_events)

    @property
    def events(self) -> tuple[CanonicalApplyEventV1, ...]:
        """Compatibility alias for callers migrating from the draft contract."""

        return self.emitted_events


_ROLE_BY_PITCH = GM_DRUM_ROLE_BY_PITCH


def _default_profile(profile_id: str) -> KitMappingProfileV1:
    if profile_id == "native-compatible":
        return KitMappingProfileV1(
            profile_id=profile_id, gm_map={pitch: pitch for pitch in range(128)}
        )
    if profile_id != "gm-drums-v1":
        raise ValueError(f"unknown kit mapping profile: {profile_id}")
    # The v1 profile is deliberately explicit and bounded.  49 is mapped to
    # the open-hat articulation used by the target drum rack; all other common
    # GM drum pitches retain their pitch unless a role fallback is requested.
    gm_map = {pitch: pitch for pitch in GM_DRUM_ROLE_BY_PITCH}
    gm_map[49] = 46
    return KitMappingProfileV1(profile_id=profile_id, gm_map=gm_map)


def _source_note_events(artifact: MidiArtifactV1) -> list[NoteEventV1]:
    candidate = getattr(artifact, "note_events", None)
    if isinstance(candidate, list) and all(isinstance(item, NoteEventV1) for item in candidate):
        return list(candidate)
    if not artifact.payload.blob:
        return []
    raw = decompress_bounded(
        artifact.payload.blob,
        codec=artifact.payload.codec,
        raw_size=artifact.payload.raw_size,
    )
    return parse_smf(raw).note_events


def _declared_length_ticks(artifact: MidiArtifactV1) -> int:
    timing_length = artifact.timing.get("length_ticks")
    if (
        isinstance(timing_length, int)
        and not isinstance(timing_length, bool)
        and timing_length >= 0
    ):
        return timing_length
    if not artifact.payload.blob:
        return 0
    raw = decompress_bounded(
        artifact.payload.blob,
        codec=artifact.payload.codec,
        raw_size=artifact.payload.raw_size,
    )
    return parse_smf(raw).length_ticks


def _decimal_beats(ticks: int, ppq: int) -> float:
    with localcontext() as context:
        context.prec = 40
        value = (Decimal(ticks) / Decimal(ppq)).quantize(
            Decimal("0.000000001"), rounding=ROUND_HALF_EVEN
        )
        return float(value)


def _resolve_pitch(
    pitch: int,
    profile: KitMappingProfileV1,
    *,
    role: str | None,
) -> tuple[int | None, str]:
    if pitch in profile.user_override:
        return profile.user_override[pitch], "exact"
    if pitch in profile.gm_map:
        return profile.gm_map[pitch], "exact"
    if role is not None and role in profile.role_map:
        return profile.role_map[role], "fallback"
    if role is not None:
        return pitch, "fallback"
    return None, "unmapped"


def map_artifact(
    artifact: MidiArtifactV1,
    profile_id: str,
    *,
    on_unmapped: Literal["reject", "skip"] = "reject",
    source_track_index: int | None = None,
    source_channel: int | None = None,
) -> MappingPlanV1:
    if (source_track_index is None) != (source_channel is None):
        return MappingPlanV1(
            profile_id=profile_id,
            allowed=False,
            warning_codes=["scope_required"],
        )
    profile = _default_profile(profile_id)
    note_events = _source_note_events(artifact)
    note_tracks = {event.track_index for event in note_events}
    note_channels = {event.channel for event in note_events}
    warnings: list[str] = []
    allowed = True
    if source_track_index is None and (len(note_tracks) > 1 or len(note_channels) > 1):
        return MappingPlanV1(profile_id=profile_id, allowed=False, warning_codes=["scope_required"])
    selected = [
        event
        for event in note_events
        if source_track_index is None
        or (event.track_index == source_track_index and event.channel == source_channel)
    ]
    if source_track_index is not None and not selected:
        return MappingPlanV1(
            profile_id=profile_id,
            selected_track_index=source_track_index,
            selected_channel=source_channel,
            allowed=False,
            warning_codes=["scope_invalid"],
        )
    if profile_id == "gm-drums-v1" and any(event.channel != 9 for event in selected):
        allowed = False
        warnings.append("unsupported_channel")
    exact = fallback = unmapped = skipped = 0
    emitted: list[CanonicalApplyEventV1] = []
    ppq = artifact.format.ppq
    length = Fraction(_declared_length_ticks(artifact), ppq)
    for event in selected:
        role = _ROLE_BY_PITCH.get(event.pitch)
        resolved, kind = _resolve_pitch(event.pitch, profile, role=role)
        if resolved is None:
            unmapped += 1
            if on_unmapped == "skip":
                skipped += 1
                continue
            allowed = False
            if "unmapped" not in warnings:
                warnings.append("unmapped")
            continue
        if kind == "exact":
            exact += 1
        else:
            fallback += 1
        start = _decimal_beats(event.start_ticks, ppq)
        duration = max(_decimal_beats(event.duration_ticks, ppq), _decimal_beats(1, ppq))
        length = max(length, Fraction(event.start_ticks + max(event.duration_ticks, 1), ppq))
        note = NoteSpec(
            pitch=resolved,
            start_time=start,
            duration=duration,
            velocity=event.velocity,
        )
        emitted.append(
            CanonicalApplyEventV1(
                event_id=event.event_id,
                source_event_id=event.event_id,
                source_track_index=event.track_index,
                source_channel=event.channel,
                original_pitch=event.pitch,
                resolved_pitch=resolved,
                note=note,
            )
        )
    if len(selected) > 2048:
        allowed = False
        warnings.append("note_limit")
    if length > CREATE_CLIP_MAX_LENGTH_BEATS:
        allowed = False
        warnings.append("loop_length_limit")
    redistribution = str(artifact.provenance.get("redistribution", "derived_only"))
    rights_level = int(artifact.provenance.get("rights_level", 1))
    capabilities = artifact.provenance.get("capabilities", {})
    if (
        redistribution != "full"
        or rights_level < 2
        or not isinstance(capabilities, Mapping)
        or not bool(capabilities.get("apply", False))
    ):
        allowed = False
        warnings.append("rights")
    if not emitted and selected:
        allowed = False
    if warnings:
        warnings = list(dict.fromkeys(warnings))
    return MappingPlanV1(
        profile_id=profile_id,
        selected_track_index=source_track_index,
        selected_channel=source_channel,
        emitted_events=tuple(emitted),
        exact_count=exact,
        fallback_count=fallback,
        unmapped_count=unmapped,
        skipped_count=skipped,
        allowed=allowed,
        warning_codes=warnings,
        length_beats=_decimal_beats(int(length.numerator), int(length.denominator))
        if length
        else 0.0,
    )


__all__ = [
    "CanonicalApplyEventV1",
    "CREATE_CLIP_MAX_LENGTH_BEATS",
    "KitMappingProfileV1",
    "MappingPlanV1",
    "map_artifact",
]
