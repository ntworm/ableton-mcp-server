"""Turn a generated grid into a real MIDI file, so it can be heard.

Uses the product's own serializer rather than a second implementation, so what a
listener hears is what the product would write.  Lanes map back to General MIDI
pitches, which is the reverse of the articulation map and is only correct in that
direction: the map is many-to-one, so this picks the canonical GM pitch per lane.
"""

from __future__ import annotations

import numpy as np
from ableton_mcp_server.groove_intelligence.drum_roles import GM_DRUM_ROLES
from ableton_mcp_server.groove_intelligence.midi_lossless import serialize_note_smf
from ableton_mcp_server.groove_intelligence.schema import NoteEventV1

PPQ = 480
STEP_TICKS = PPQ // 4
STEPS = 32
OFFSET_SCALE = 60.0  # the canonical half-cell, matching the dataset's int8 range
DURATION_TICKS = STEP_TICKS // 2

# One canonical General MIDI pitch per canonical lane.
LANE_PITCH = {
    "kick": 36,
    "snare": 38,
    "rim": 37,
    "clap": 39,
    "hat_closed": 42,
    "hat_open": 46,
    "hat_pedal": 44,
    "tom_low": 41,
    "tom_mid": 47,
    "tom_high": 50,
    "crash": 49,
    "splash": 55,
    "china": 52,
    "ride": 51,
    "ride_bell": 53,
    "tambourine": 54,
    "cowbell": 56,
    "other_percussion": 39,
}


def grid_to_midi(grid: dict[str, np.ndarray], bpm: float) -> bytes:
    notes: list[NoteEventV1] = []
    event_id = 0
    for row, lane in sorted(map(tuple, np.argwhere(grid["hit"] > 0.5))):
        pitch = LANE_PITCH[GM_DRUM_ROLES[lane]]
        start = row * STEP_TICKS + int(
            round(float(grid["offset"][row, lane]) * OFFSET_SCALE)
        )
        velocity = int(round(float(grid["velocity"][row, lane]) * 127))
        notes.append(
            NoteEventV1(
                event_id=event_id,
                track_index=0,
                channel=9,
                pitch=pitch,
                velocity=max(1, min(127, velocity)),
                start_ticks=max(0, start),
                duration_ticks=DURATION_TICKS,
            )
        )
        event_id += 1
    return serialize_note_smf(
        notes,
        ppq=PPQ,
        length_ticks=STEPS * STEP_TICKS,
        tempos=[
            {
                "track_index": 0,
                "absolute_ticks": 0,
                "microseconds": int(round(60_000_000 / bpm)),
            }
        ],
    )
