"""Deterministic production planning.

This module has no language model behind it and does not pretend to have
musical judgement. It extracts what a prompt states literally, lays a
conventional section grid over the requested bar count, and names everything it
could not resolve so the caller can supply it instead of trusting an invention.
"""

from __future__ import annotations

import re
from typing import Any

_BPM_IN_PROMPT = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*(?:bpm|beats per minute)", re.IGNORECASE)

# Proportional section grid. The weights are a conventional pop/electronic
# arrangement, not an inference from the prompt.
_SECTION_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("intro", 1),
    ("verse", 2),
    ("chorus", 2),
    ("breakdown", 1),
    ("chorus", 2),
    ("outro", 1),
)


def plan_production(
    *, prompt: str, bars: int | None, bpm: float | None
) -> dict[str, Any]:
    """Return a deterministic arrangement scaffold plus an honest gap list."""
    resolved_bpm = bpm if bpm is not None else _bpm_from_prompt(prompt)

    unresolved: list[str] = []
    if resolved_bpm is None:
        unresolved.append("bpm")
    if bars is None:
        unresolved.append("bars")

    return {
        "deterministic": True,
        "prompt": prompt,
        "bpm": resolved_bpm,
        "bars": bars,
        "sections": _sections(bars) if bars is not None else [],
        "unresolved": unresolved,
    }


def _bpm_from_prompt(prompt: str) -> float | None:
    match = _BPM_IN_PROMPT.search(prompt)
    return float(match.group(1)) if match else None


def _sections(bars: int) -> list[dict[str, Any]]:
    """Split ``bars`` across the section grid so the parts tile it exactly."""
    total_weight = sum(weight for _, weight in _SECTION_WEIGHTS)
    lengths = [bars * weight // total_weight for _, weight in _SECTION_WEIGHTS]

    # Integer division loses bars; give the remainder to the longest sections
    # first so nothing collapses to zero and the grid still tiles exactly.
    remainder = bars - sum(lengths)
    order = sorted(range(len(lengths)), key=lambda index: -_SECTION_WEIGHTS[index][1])
    for position in range(remainder):
        lengths[order[position % len(order)]] += 1

    sections: list[dict[str, Any]] = []
    start = 0
    for (name, _), length in zip(_SECTION_WEIGHTS, lengths, strict=True):
        sections.append({"name": name, "start_bar": start, "length_bars": length})
        start += length
    return sections
