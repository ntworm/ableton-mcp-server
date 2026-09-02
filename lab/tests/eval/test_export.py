from __future__ import annotations

import numpy as np
from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf

from groove_lab.eval.export import grid_to_midi


def _grid(cells: list[tuple[int, int]], offset: float = 0.0) -> dict[str, np.ndarray]:
    hit = np.zeros((32, 18), dtype=np.float32)
    for row, lane in cells:
        hit[row, lane] = 1.0
    return {
        "hit": hit,
        "velocity": np.where(hit > 0, 0.8, 0.0).astype(np.float32),
        "offset": np.where(hit > 0, offset, 0.0).astype(np.float32),
        "subhits": hit.astype(np.int64),
    }


def test_a_grid_round_trips_through_a_real_smf() -> None:
    parsed = parse_smf(grid_to_midi(_grid([(0, 0), (8, 1)]), bpm=120.0))
    assert len(parsed.note_events) == 2
    assert {note.pitch for note in parsed.note_events} == {36, 38}


def test_offsets_move_notes_off_the_grid() -> None:
    first = parse_smf(grid_to_midi(_grid([(4, 0)]), bpm=120.0)).note_events[0]
    second = parse_smf(grid_to_midi(_grid([(4, 0)], offset=0.5), bpm=120.0)).note_events[0]
    assert second.start_ticks > first.start_ticks


def test_a_silent_grid_produces_a_valid_empty_file() -> None:
    assert parse_smf(grid_to_midi(_grid([]), bpm=120.0)).note_events == []
