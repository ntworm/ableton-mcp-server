"""Deterministic offline note generation.

Nothing in this package talks to Ableton Live. Every function is pure: the
same request produces the same notes on every machine and every run, which is
what makes the tools provable offline in the certification baseline.
"""

from __future__ import annotations

from .generators import Generation, Traits, generate_bass, generate_drum_groove
from .planner import plan_production

__all__ = [
    "Generation",
    "Traits",
    "generate_bass",
    "generate_drum_groove",
    "plan_production",
]
