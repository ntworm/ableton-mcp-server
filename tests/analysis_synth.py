"""Deterministic synthesized signals for offline mix-analysis tests."""

from __future__ import annotations

import numpy as np
import soundfile as sf


def write_sine(
    path,
    *,
    frequency_hz: float,
    duration_s: float,
    sample_rate: int = 48000,
    amplitude: float = 0.5,
) -> None:
    samples = int(duration_s * sample_rate)
    t = np.linspace(0.0, duration_s, samples, endpoint=False)
    signal = amplitude * np.sin(2.0 * np.pi * frequency_hz * t)
    sf.write(str(path), signal.astype(np.float32), sample_rate)


def write_kick(
    path,
    *,
    duration_s: float = 0.5,
    sample_rate: int = 48000,
) -> None:
    samples = int(duration_s * sample_rate)
    t = np.linspace(0.0, duration_s, samples, endpoint=False)
    pitch = 60.0 * np.exp(-t * 8.0)
    signal = 0.7 * np.sin(2.0 * np.pi * pitch * t) * np.exp(-t * 4.0)
    sf.write(str(path), signal.astype(np.float32), sample_rate)
