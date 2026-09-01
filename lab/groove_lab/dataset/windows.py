"""Cut a CanonicalGroove into two-bar windows and lay them out as tensors.

33.6% of the byte-unique corpus is shorter than two bars, so the short-file
policy is explicit.  ``looped`` repeats the bar and sets a flag the condition
vector carries, because repeating without the flag teaches a two-bar periodicity
the source never had.  ``padded`` leaves the missing bar neither observed nor
targeted.

Dtypes are chosen so the tensor round-trips exactly: ``offset_ticks`` is an
integer in ``[-60, 60]``, so ``int8`` is lossless, and ``subhits`` is a raw count
kept uncapped in ``uint8``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ableton_mcp_server.groove_intelligence.drum_roles import GM_DRUM_ROLES

from .canonical import CanonicalCell, CanonicalGroove

STEPS_PER_BAR = 16
BARS = 2
STEPS = STEPS_PER_BAR * BARS
LANES = len(GM_DRUM_ROLES)
LANE_INDEX = {role: index for index, role in enumerate(GM_DRUM_ROLES)}
POLICIES = ("looped", "padded")


@dataclass
class Window:
    hit: np.ndarray
    subhits: np.ndarray
    velocity: np.ndarray
    offset: np.ndarray
    observed: np.ndarray
    target: np.ndarray
    start_bar: int
    looped: bool

    @staticmethod
    def lane_index(role: str) -> int:
        return LANE_INDEX[role]


def _blank() -> Window:
    return Window(
        hit=np.zeros((STEPS, LANES), dtype=np.uint8),
        subhits=np.zeros((STEPS, LANES), dtype=np.uint8),
        velocity=np.zeros((STEPS, LANES), dtype=np.float32),
        offset=np.zeros((STEPS, LANES), dtype=np.int8),
        observed=np.zeros((STEPS, LANES), dtype=np.uint8),
        target=np.ones((STEPS, LANES), dtype=np.uint8),
        start_bar=0,
        looped=False,
    )


def _place(window: Window, cell: CanonicalCell, row: int) -> None:
    lane = LANE_INDEX.get(cell.role)
    if lane is None or not 0 <= row < STEPS:
        return
    window.hit[row, lane] = 1
    window.subhits[row, lane] = min(cell.subhits, 255)
    window.velocity[row, lane] = cell.velocity
    window.offset[row, lane] = int(np.clip(cell.offset_ticks, -128, 127))


def to_windows(groove: CanonicalGroove, policy: str, hop_bars: int) -> list[Window]:
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES}, got {policy!r}")

    if groove.bars < BARS:
        window = _blank()
        for cell in groove.cells:
            _place(window, cell, cell.bar * STEPS_PER_BAR + cell.step)
        if policy == "looped":
            window.looped = True
            for cell in groove.cells:
                _place(window, cell, STEPS_PER_BAR + cell.step)
        else:
            window.observed[STEPS_PER_BAR:, :] = 0
            window.target[STEPS_PER_BAR:, :] = 0
        return [window]

    windows: list[Window] = []
    for start in range(0, groove.bars - BARS + 1, hop_bars):
        window = _blank()
        window.start_bar = start
        for cell in groove.cells:
            if start <= cell.bar < start + BARS:
                _place(window, cell, (cell.bar - start) * STEPS_PER_BAR + cell.step)
        windows.append(window)
    return windows
