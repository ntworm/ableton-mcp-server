"""Measure a callable against the provider's seven hard limits.

The values mirror ``ProviderLimitsV1`` in
``ableton_mcp_server/groove_intelligence/provider.py``.  They are declared with
``le=`` in that schema, so they are ceilings that configuration cannot raise, and
this module treats them the same way.

``cpu_seconds`` is CPU time summed across threads, which is what
``time.process_time`` reports for the current process.  With eight intra-op
threads, half a second of wall time is four CPU-seconds and already over budget.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import psutil

LIMITS: dict[str, float] = {
    "generation_seconds": 5.0,
    "cpu_seconds": 2.0,
    "startup_seconds": 2.0,
    "shutdown_seconds": 1.0,
    "memory_mib": 512,
    "max_response_bytes": 262144,
    "max_events": 2048,
}


@dataclass
class Measurement:
    wall_seconds: float
    cpu_seconds: float
    peak_memory_mib: float


def measure(action: Callable[[], object]) -> Measurement:
    process = psutil.Process()
    before_memory = process.memory_info().rss
    wall_start = time.perf_counter()
    cpu_start = time.process_time()

    action()

    cpu_seconds = time.process_time() - cpu_start
    wall_seconds = time.perf_counter() - wall_start
    after_memory = process.memory_info().rss
    return Measurement(
        wall_seconds=wall_seconds,
        cpu_seconds=cpu_seconds,
        peak_memory_mib=max(before_memory, after_memory) / (1024 * 1024),
    )


def verdict(values: dict[str, float]) -> list[str]:
    """Return the names of the limits ``values`` breaks, in declaration order."""

    return [name for name, ceiling in LIMITS.items() if name in values and values[name] > ceiling]
