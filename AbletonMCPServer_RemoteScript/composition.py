"""Composition structure reads and MIDI clip diagnostics."""

from __future__ import annotations

from typing import Any

from ._contracts import ERROR_WRONG_TYPE
from .common import RemoteError, _integer_param, _safe
from .lom import _all_tracks, _clip_slot, _note_value, _track_type

# ---------------------------------------------------------------------------
# v0.3.0 — Composition Diagnostics
# ---------------------------------------------------------------------------
_SCALE_INTERVALS = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "aeolian": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "locrian": [0, 1, 3, 5, 6, 8, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "melodic_minor": [0, 2, 3, 5, 7, 9, 11],
    "pentatonic_major": [0, 2, 4, 7, 9],
    "pentatonic_minor": [0, 3, 5, 7, 10],
    "blues": [0, 3, 5, 6, 7, 10],
    "chromatic": list(range(12)),
}

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_ENHARMONIC = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}


def _note_name_to_number(name: str) -> int:
    resolved = _ENHARMONIC.get(name, name)
    return _NOTE_NAMES.index(resolved)


def cmd_get_composition_structure(
    song: Any, _application: Any, _params: dict[str, Any]
) -> dict[str, Any]:
    tracks = []
    unnamed_tracks = []
    for index, track in enumerate(_all_tracks(song)):
        kind = _track_type(song, track)
        name = str(_safe(lambda track=track: track.name, ""))
        has_clips = False
        clip_count = 0
        if kind in ("midi", "audio"):
            for slot in _safe(lambda track=track: track.clip_slots, []):
                if bool(_safe(lambda slot=slot: slot.has_clip, False)):
                    has_clips = True
                    clip_count += 1
        entry = {
            "id": "track:%s" % index,
            "index": index,
            "name": name,
            "type": kind,
            "color": int(_safe(lambda track=track: track.color, 0)),
            "has_clips": has_clips,
            "clip_count": clip_count,
            "device_count": len(list(_safe(lambda track=track: track.devices, []))),
        }
        tracks.append(entry)
        default_names = ("", "MIDI", "Audio", "Master", "A-Return", "B-Return")
        if not name or name.startswith("Track ") or name in default_names:
            unnamed_tracks.append("track:%s" % index)

    return {
        "tracks": tracks,
        "track_count": len(tracks),
        "scenes_count": len(list(song.scenes)),
        "tempo": float(song.tempo),
        "unnamed_tracks": unnamed_tracks,
        "unnamed_tracks_count": len(unnamed_tracks),
    }


def _clip_notes(clip: Any) -> list[dict[str, Any]]:
    raw_notes = clip.get_notes_extended(0, 128, -8192.0, 16384.0)
    notes = []
    for note in raw_notes:
        notes.append(
            {
                "pitch": int(_note_value(note, "pitch", 0)),
                "start_time": float(_note_value(note, "start_time", 0.0)),
                "duration": float(_note_value(note, "duration", 0.0)),
                "velocity": int(_note_value(note, "velocity", 100)),
                "mute": bool(_note_value(note, "mute", False)),
            }
        )
    return notes


def _overlaps_count(notes: list[dict[str, Any]]) -> int:
    overlaps_count = 0
    by_pitch: dict[int, list[dict[str, Any]]] = {}
    for note in notes:
        by_pitch.setdefault(note["pitch"], []).append(note)
    for pitch_notes in by_pitch.values():
        sorted_notes = sorted(pitch_notes, key=lambda n: n["start_time"])
        for i in range(len(sorted_notes) - 1):
            cur = sorted_notes[i]
            nxt = sorted_notes[i + 1]
            if nxt["start_time"] < cur["start_time"] + cur["duration"]:
                overlaps_count += 1
    return overlaps_count


def _notes_outside_scale(
    notes: list[dict[str, Any]], scale_root: str | None, scale_type: str | None
) -> list[dict[str, Any]]:
    notes_outside_scale: list[dict[str, Any]] = []
    if scale_root and scale_type:
        try:
            root_num = _note_name_to_number(scale_root)
        except (ValueError, IndexError):
            root_num = None
        intervals = _SCALE_INTERVALS.get(scale_type.lower())
        if root_num is not None and intervals is not None:
            scale_pitches = set((root_num + i) % 12 for i in intervals)
            for note in notes:
                pc = note["pitch"] % 12
                if pc not in scale_pitches:
                    notes_outside_scale.append(
                        {
                            "pitch": note["pitch"],
                            "start_time": note["start_time"],
                            "note_name": _NOTE_NAMES[pc],
                        }
                    )
    return notes_outside_scale


def _timing_drift_detected(notes: list[dict[str, Any]]) -> bool:
    timing_drift_detected = False
    grid_values = [0.25, 0.5, 1.0]  # 1/16, 1/8, 1/4 beats
    drift_threshold = 0.01
    if notes:
        drift_count = 0
        for note in notes:
            t = note["start_time"]
            aligned_to_any = False
            for grid in grid_values:
                remainder = t % grid
                if remainder < drift_threshold or (grid - remainder) < drift_threshold:
                    aligned_to_any = True
                    break
            if not aligned_to_any:
                drift_count += 1
        timing_drift_detected = drift_count > len(notes) * 0.15
    return timing_drift_detected


def _diagnose_recommendations(
    overlaps_count: int,
    notes_outside_scale: list[dict[str, Any]],
    timing_drift_detected: bool,
    scale_root: str | None,
    scale_type: str | None,
) -> list[str]:
    recommendations = []
    if overlaps_count > 0:
        recommendations.append(
            "%s overlapping note pair(s) found. Consider quantizing or removing duplicates."
            % overlaps_count
        )
    if notes_outside_scale:
        recommendations.append(
            "%s note(s) outside the %s %s scale."
            % (len(notes_outside_scale), scale_root, scale_type)
        )
    if timing_drift_detected:
        recommendations.append(
            "Timing drift detected; some notes are not aligned to standard grid values."
        )
    if not recommendations:
        recommendations.append("No issues found.")
    return recommendations


def cmd_diagnose_midi_clip(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    scale_root = params.get("scale_root")  # optional
    scale_type = params.get("scale_type")  # optional

    _track, slot = _clip_slot(song, track_index, clip_index)
    clip = _safe(lambda: slot.clip, None)
    if clip is None:
        return {
            "has_overlaps": False,
            "overlaps_count": 0,
            "notes_outside_scale": [],
            "timing_drift_detected": False,
            "recommendations": ["Clip slot is empty."],
            "note_count": 0,
        }

    if not bool(_safe(lambda: clip.is_midi_clip, False)):
        raise RemoteError(ERROR_WRONG_TYPE, "Clip is not a MIDI clip.")

    notes = _clip_notes(clip)

    # --- Overlap Detection ---
    overlaps_count = _overlaps_count(notes)

    # --- Scale Conformance ---
    notes_outside_scale = _notes_outside_scale(notes, scale_root, scale_type)

    # --- Timing Drift Detection ---
    timing_drift_detected = _timing_drift_detected(notes)

    # --- Recommendations ---
    recommendations = _diagnose_recommendations(
        overlaps_count,
        notes_outside_scale,
        timing_drift_detected,
        scale_root,
        scale_type,
    )

    return {
        "note_count": len(notes),
        "has_overlaps": overlaps_count > 0,
        "overlaps_count": overlaps_count,
        "notes_outside_scale": notes_outside_scale,
        "timing_drift_detected": timing_drift_detected,
        "recommendations": recommendations,
    }
