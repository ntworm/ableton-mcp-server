from __future__ import annotations

import time

from groove_lab.budget import LIMITS, Measurement, measure, verdict


def test_limits_match_the_provider_contract() -> None:
    assert LIMITS["generation_seconds"] == 5.0
    assert LIMITS["cpu_seconds"] == 2.0
    assert LIMITS["startup_seconds"] == 2.0
    assert LIMITS["shutdown_seconds"] == 1.0
    assert LIMITS["memory_mib"] == 512
    assert LIMITS["max_response_bytes"] == 262144
    assert LIMITS["max_events"] == 2048


def test_measure_records_wall_and_cpu_time() -> None:
    def burn() -> None:
        deadline = time.process_time() + 0.05
        while time.process_time() < deadline:
            pass

    result = measure(burn)
    assert isinstance(result, Measurement)
    assert result.wall_seconds >= 0.04
    assert result.cpu_seconds >= 0.04
    assert result.peak_memory_mib > 0


def test_verdict_fails_on_the_binding_limit() -> None:
    passing = {"cpu_seconds": 1.0, "generation_seconds": 1.0, "memory_mib": 100}
    failing = {"cpu_seconds": 2.5, "generation_seconds": 1.0, "memory_mib": 100}
    assert verdict(passing) == []
    assert verdict(failing) == ["cpu_seconds"]
