from __future__ import annotations

import numpy as np
import pytest

from groove_lab.dataset.canonical import CanonicalCell, CanonicalGroove
from groove_lab.dataset.conditions import build_conditions
from groove_lab.dataset.windows import to_windows


def _groove(bars: int, cells: tuple[CanonicalCell, ...]) -> CanonicalGroove:
    return CanonicalGroove(
        cells=cells,
        bpm=120.0,
        meter="4/4",
        bars=bars,
        collection="col",
        source_events_digest="0" * 64,
        canonical_hash="c",
        rhythm_hash="r",
        expression_hash="e",
    )


def test_a_one_bar_file_is_looped_and_flagged() -> None:
    groove = _groove(1, (CanonicalCell("kick", 0, 0, 1, 0.8, 3),))
    windows = to_windows(groove, policy="looped", hop_bars=2)
    assert len(windows) == 1
    window = windows[0]
    assert window.looped is True
    # The single bar appears in both halves of the two-bar window.
    assert window.hit[0, 0] == 1
    assert window.hit[16, 0] == 1


def test_a_one_bar_file_can_instead_be_padded() -> None:
    groove = _groove(1, (CanonicalCell("kick", 0, 0, 1, 0.8, 3),))
    window = to_windows(groove, policy="padded", hop_bars=2)[0]
    assert window.looped is False
    assert window.hit[16, 0] == 0
    # The absent second bar is neither observed nor a target.
    assert window.observed[16:, :].sum() == 0
    assert window.target[16:, :].sum() == 0


def test_a_four_bar_file_yields_two_windows() -> None:
    cells = tuple(CanonicalCell("kick", bar, 0, 1, 0.8, 0) for bar in range(4))
    windows = to_windows(_groove(4, cells), policy="looped", hop_bars=2)
    assert len(windows) == 2


def test_subhits_and_offset_survive_the_tensor() -> None:
    groove = _groove(2, (CanonicalCell("snare", 1, 4, 3, 0.5, -7),))
    window = to_windows(groove, policy="looped", hop_bars=2)[0]
    lane = window.lane_index("snare")
    assert window.subhits[16 + 4, lane] == 3
    assert window.offset[16 + 4, lane] == -7
    assert window.offset.dtype == np.int8
    assert window.subhits.dtype == np.uint8


def test_conditions_have_the_declared_width_and_range() -> None:
    groove = _groove(2, (CanonicalCell("kick", 0, 0, 1, 0.9, 0),))
    window = to_windows(groove, policy="looped", hop_bars=2)[0]
    vector = build_conditions(groove, window, labels={"genre": "Metal"})
    assert vector.shape == (16,)
    assert vector.dtype == np.float32
    assert float(vector.min()) >= 0.0 and float(vector.max()) <= 1.0
    assert vector[10] == 1.0, "index 10 flags that a vendor genre was present"


def test_conditions_report_absence_rather_than_guessing() -> None:
    groove = _groove(2, (CanonicalCell("kick", 0, 0, 1, 0.9, 0),))
    window = to_windows(groove, policy="looped", hop_bars=2)[0]
    vector = build_conditions(groove, window, labels={})
    assert vector[10] == 0.0
    assert float(vector[11:16].sum()) == 0.0


def test_unknown_policy_is_refused() -> None:
    groove = _groove(1, ())
    with pytest.raises(ValueError):
        to_windows(groove, policy="invent-one", hop_bars=2)
