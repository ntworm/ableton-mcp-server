"""Turn a tensor window back into cells and prove the two agree exactly.

Gate G3 draws a line between two different things.  Notes the chosen grid cannot
represent are a measured, budgeted loss.  Notes the tensor loses on the way back
out are a bug, and this module is what makes the second impossible to miss.
"""

from __future__ import annotations

import numpy as np

from ableton_mcp_server.groove_intelligence.drum_roles import GM_DRUM_ROLES

from .canonical import CanonicalCell
from .windows import STEPS_PER_BAR, Window


def cells_from_window(window: Window) -> tuple[CanonicalCell, ...]:
    rows, lanes = np.nonzero(window.hit)
    return tuple(
        CanonicalCell(
            role=GM_DRUM_ROLES[lane],
            bar=int(row) // STEPS_PER_BAR,
            step=int(row) % STEPS_PER_BAR,
            subhits=int(window.subhits[row, lane]),
            velocity=float(window.velocity[row, lane]),
            offset_ticks=int(window.offset[row, lane]),
        )
        for row, lane in zip(rows, lanes, strict=True)
    )


def roundtrip_is_exact(window: Window, cells: tuple[CanonicalCell, ...]) -> bool:
    return cells_from_window(window) == tuple(
        sorted(
            cells,
            key=lambda c: (
                c.bar * STEPS_PER_BAR + c.step,
                GM_DRUM_ROLES.index(c.role),
            ),
        )
    )
