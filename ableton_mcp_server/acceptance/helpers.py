"""Pure helper functions used by the acceptance runner.

None of these touch the bridge. They live here so the runner and the
restore engine can both reach them without a dependency on the
monolithic ``run_live_acceptance`` body.
"""

from __future__ import annotations

import math
import struct
import wave
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .safety import AcceptanceSafetyError

# Source of truth: ``AbletonMCPServer_RemoteScript/__init__.py``
# line ~1896. The Remote Script maps ``target_percent=100`` to
# ``LIVE_FADE_UNITY_VALUE`` on the user-facing fader — Live's
# mixer volume parameter sits below unity so that 100% maps to
# 0dB. The runner is a client-side component that does NOT
# import the Remote Script (different process boundary), so the
# constant is duplicated here. The drift guard in
# ``tests/test_acceptance_live_fade_percent.py`` asserts both
# sides agree at test time.
LIVE_FADE_UNITY_VALUE = 0.8500000238418579


def _test_tempo(original: float, offset: float) -> float:
    """Pick the next valid tempo within Live's 999 BPM ceiling."""
    candidate = original + offset
    if candidate <= 999.0:
        return candidate
    return original - offset


def _acceptance_safe_cue_times(
    song_length: float,
    locators: list[Mapping[str, Any]],
    grid: float = 8.0,
) -> tuple[float, float]:
    """Pick two distinct, grid-aligned locator times that stay inside
    ``song_length`` and avoid the existing locators.

    Returns ``(cue_time, bulk_cue_time)``. Raises ``AcceptanceSafetyError``
    before any mutation when the grid does not leave two safe cells, or
    when ``song_length`` is non-positive.
    """
    if song_length is None or not isinstance(song_length, (int, float)):
        raise AcceptanceSafetyError(f"song_length must be a positive number, got {song_length!r}")
    song_length_f = float(song_length)
    if song_length_f <= 0.0:
        raise AcceptanceSafetyError(f"song_length must be positive, got {song_length_f}")
    if grid <= 0.0:
        raise AcceptanceSafetyError(f"grid must be positive, got {grid}")

    occupied = set()
    for item in locators:
        try:
            occupied.add(round(float(item.get("time", -1.0)) / grid) * grid)
        except (TypeError, ValueError):
            continue

    # Walk the grid in descending order so we pick times that are
    # guaranteed to be inside song_length. Two free cells are required.
    chosen: list[float] = []
    step_count = int(song_length_f // grid)
    for index in range(step_count, -1, -1):
        candidate = round(float(index) * grid, 6)
        if candidate > song_length_f + 1e-6:
            continue
        if candidate in occupied:
            continue
        chosen.append(candidate)
        if len(chosen) == 2:
            break

    if len(chosen) < 2:
        raise AcceptanceSafetyError(
            f"could not find two safe cue times within song_length="
            f"{song_length_f} on a {grid}-beat grid "
            f"(occupied={sorted(occupied)})"
        )

    cue_time, bulk_cue_time = chosen[0], chosen[1]
    # The legacy hard-coded pair (256, 320) is the regression we are
    # removing; surface it explicitly when the song_length is large
    # enough that the legacy pair would have been accepted but the
    # new helper rejects it for some other reason.
    if cue_time == 256.0 and bulk_cue_time == 320.0:
        raise AcceptanceSafetyError(
            "cue helper must not return the legacy hard-coded pair (256, 320)"
        )
    return cue_time, bulk_cue_time


def _parameter_tolerance(min_val: float, max_val: float) -> float:
    """Range-proportional tolerance with a numeric precision floor (1e-12)."""
    return max(1e-12, abs(max_val - min_val) * 0.01)


def _write_sine_wav(
    path: Path, *, hz: float, amplitude: float, seconds: float, sample_rate: int = 44100
) -> Path:
    nframes = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(nframes):
            sample = amplitude * math.sin(2.0 * math.pi * hz * (index / sample_rate))
            wav.writeframes(struct.pack("<h", int(sample * 32767)))
    return path


def _synthesize_offline_inputs(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    return {
        "target": _write_sine_wav(directory / "target.wav", hz=1000.0, amplitude=0.8, seconds=1.0),
        "reference": _write_sine_wav(
            directory / "reference.wav", hz=1000.0, amplitude=0.2, seconds=1.0
        ),
        "short": _write_sine_wav(directory / "short.wav", hz=440.0, amplitude=0.5, seconds=0.5),
        "long": _write_sine_wav(directory / "long.wav", hz=440.0, amplitude=0.25, seconds=1.0),
    }


def _baseline_tool_names() -> tuple[str, ...]:
    """Flat tuple of every public tool name registered in ``server.PUBLIC_TOOL_NAMES``."""
    from ..server import PUBLIC_TOOL_NAMES

    return tuple(PUBLIC_TOOL_NAMES)
