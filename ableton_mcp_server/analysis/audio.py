"""Offline mix analysis utilities.

This module is dependency-free of Live, the Remote Script, or the bridge. It
reads local audio files through ``soundfile`` and computes LUFS-I
approximations, true-peak, RMS, per-band energy summaries, masking scores,
and single-cycle wavetable candidates. All public functions return plain
dicts; the MCP layer wraps them in tools.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import soundfile as sf

LUFS_BLOCK_S = 0.4
LOW_HZ = 250.0
HIGH_HZ = 4000.0
MAX_STEMS = 16
SINGLE_CYCLE_DEFAULT_FRAME = 2048
SINGLE_CYCLE_PROBE_S = 5.0


def _load_mono(path: str) -> tuple[np.ndarray, int]:
    data, sr = sf.read(path, always_2d=False)
    if isinstance(data, np.ndarray) and data.ndim > 1:
        data = data.mean(axis=1)
    return data.astype(np.float64), int(sr)


def _rms_dbfs(samples: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(samples + 1e-12))))
    return 20.0 * math.log10(rms) if rms > 0 else -120.0


def _true_peak_dbfs(samples: np.ndarray) -> float:
    oversampled = np.repeat(samples, 4)
    peak = float(np.max(np.abs(oversampled)))
    return 20.0 * math.log10(peak) if peak > 0 else -120.0


def _lufs_i_approx(samples: np.ndarray, sample_rate: int) -> float:
    mean_square = float(np.mean(np.square(samples + 1e-12)))
    return 20.0 * math.log10(mean_square) - 0.691


def _bands(samples: np.ndarray, sample_rate: int) -> dict[str, float]:
    spectrum = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(samples.size, d=1.0 / sample_rate)
    low_mask = freqs < LOW_HZ
    mid_mask = (freqs >= LOW_HZ) & (freqs < HIGH_HZ)
    high_mask = freqs >= HIGH_HZ
    low = float(np.mean(spectrum[low_mask] ** 2)) if np.any(low_mask) else 0.0
    mid = float(np.mean(spectrum[mid_mask] ** 2)) if np.any(mid_mask) else 0.0
    high = float(np.mean(spectrum[high_mask] ** 2)) if np.any(high_mask) else 0.0
    return {
        "low_db": 10.0 * math.log10(low + 1e-12),
        "mid_db": 10.0 * math.log10(mid + 1e-12),
        "high_db": 10.0 * math.log10(high + 1e-12),
    }


def analyze_audio(path: str) -> dict[str, Any]:
    samples, sample_rate = _load_mono(path)
    return {
        "duration_s": float(samples.size / sample_rate),
        "sample_rate": sample_rate,
        "lufs_i": _lufs_i_approx(samples, sample_rate),
        "rms_dbfs": _rms_dbfs(samples),
        "peak_dbfs": _true_peak_dbfs(samples),
        "bands": _bands(samples, sample_rate),
    }


def _band_mask(freqs, target_db, reference_db, low_hz, high_hz, threshold_db):
    mask = (freqs >= low_hz) & (freqs < high_hz)
    if not np.any(mask):
        return {
            "start_hz": low_hz,
            "end_hz": high_hz,
            "target_db": -120.0,
            "reference_db": -120.0,
            "excess_db": None,
        }
    target_band = float(np.mean(target_db[mask]))
    reference_band = float(np.mean(reference_db[mask]))
    excess = target_band - reference_band
    return {
        "start_hz": low_hz,
        "end_hz": high_hz,
        "target_db": target_band,
        "reference_db": reference_band,
        "excess_db": excess if excess >= threshold_db else None,
    }


def find_frequency_masking(
    target_path: str,
    reference_path: str,
    threshold_db: float = 6.0,
) -> dict[str, Any]:
    target, sr_t = _load_mono(target_path)
    reference, sr_r = _load_mono(reference_path)
    if sr_t != sr_r:
        raise ValueError("sample rate mismatch between target and reference")
    spec_t = np.abs(np.fft.rfft(target))
    spec_r = np.abs(np.fft.rfft(reference))
    freqs = np.fft.rfftfreq(target.size, d=1.0 / sr_t)
    log_t = 20.0 * np.log10(spec_t + 1e-12)
    log_r = 20.0 * np.log10(spec_r + 1e-12)
    bands = [
        _band_mask(freqs, log_t, log_r, 0.0, LOW_HZ, threshold_db),
        _band_mask(freqs, log_t, log_r, LOW_HZ, HIGH_HZ, threshold_db),
        _band_mask(freqs, log_t, log_r, HIGH_HZ, sr_t / 2, threshold_db),
    ]
    excess = [b["excess_db"] for b in bands if b["excess_db"] is not None]
    return {"bands": bands, "score": float(max(excess) if excess else 0.0)}


def analyze_mix(stems: Sequence[str]) -> dict[str, Any]:
    if len(stems) > MAX_STEMS:
        raise ValueError(f"too many stems (>{MAX_STEMS}); split the request")
    stem_metrics = [{"name": stem, **analyze_audio(stem)} for stem in stems]
    pairwise = []
    for i, stem_a in enumerate(stems):
        for stem_b in stems[i + 1 :]:
            result = find_frequency_masking(stem_a, stem_b, threshold_db=3.0)
            pairwise.append(
                {"target": stem_a, "reference": stem_b, "score": result["score"]}
            )
    return {
        "stems": stem_metrics,
        "pairwise_masking": pairwise,
        "max_stems": MAX_STEMS,
    }


# Minimum lag to search for periodicity. Lag 1 of a smooth periodic signal
# is almost identical to lag 0 (autocorrelation of consecutive samples is
# near 1.0), so we skip the first trivial offset.
SINGLE_CYCLE_MIN_LAG = 2
# Minimum normalized autocorrelation at the detected peak required to call
# the signal periodic. Periodic signals reach ~0.99 here; white noise reaches
# ~0.02. The threshold sits comfortably between the two regimes.
SINGLE_CYCLE_CLARITY = 0.5


def extract_single_cycle(
    path: str, frame_size: int = SINGLE_CYCLE_DEFAULT_FRAME
) -> dict[str, Any]:
    samples, sample_rate = _load_mono(path)
    probe_samples = min(int(SINGLE_CYCLE_PROBE_S * sample_rate), samples.size)
    head = samples[:probe_samples]
    if head.size < frame_size:
        return {"ok": False, "reason": "file shorter than frame_size"}
    autocorr = np.correlate(head, head, mode="full")
    autocorr = autocorr[autocorr.size // 2 :]
    search_start = SINGLE_CYCLE_MIN_LAG
    if search_start >= frame_size:
        return {"ok": False, "reason": "frame_size too small to search for period"}
    peak = int(np.argmax(autocorr[search_start:frame_size]) + search_start)
    if peak <= 0 or autocorr[0] <= 0:
        return {"ok": False, "reason": "no clear periodicity"}
    clarity = float(autocorr[peak]) / float(autocorr[0])
    if clarity < SINGLE_CYCLE_CLARITY:
        return {"ok": False, "reason": "no clear periodicity"}
    pitch_hz = sample_rate / peak
    cycle = samples[:peak].astype(np.float32)
    return {
        "ok": True,
        "frame_size": frame_size,
        "cycle_samples": int(peak),
        "pitch_hz": float(pitch_hz),
        "cycle": cycle.tolist(),
    }
