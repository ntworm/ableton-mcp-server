"""v0.5.0 offline mix-analysis module tests (LUFS, masking, single-cycle)."""
from __future__ import annotations

import numpy as np
import pytest
import soundfile

from ableton_mcp_server.analysis import (
    analyze_audio,
    analyze_mix,
    extract_single_cycle,
    find_frequency_masking,
)
from tests.analysis_synth import write_sine


def test_analyze_audio_returns_lufs_rms_and_per_band(tmp_path) -> None:
    sine_path = tmp_path / "sine_440.wav"
    write_sine(sine_path, frequency_hz=440.0, duration_s=0.5)

    result = analyze_audio(str(sine_path))

    assert result["lufs_i"] < 0
    assert result["rms_dbfs"] < 0
    bands = result["bands"]
    assert bands["mid_db"] > bands["low_db"]
    assert result["sample_rate"] == 48000
    assert result["duration_s"] == pytest.approx(0.5, abs=1e-3)


def test_analyze_audio_rejects_missing_file(tmp_path) -> None:
    """Module raises on missing path; the MCP wrapper catches this and
    returns a structured envelope."""
    missing = tmp_path / "does_not_exist.wav"

    with pytest.raises((OSError, soundfile.LibsndfileError)):
        analyze_audio(str(missing))


def _write_broadband(path, *, amplitude: float, seed: int) -> None:
    import soundfile as sf

    rng = np.random.default_rng(seed=seed)
    samples = rng.normal(0.0, amplitude, size=48000).astype(np.float32)
    sf.write(str(path), samples, 48000)


def test_find_frequency_masking_reports_excess_band(tmp_path) -> None:
    target = tmp_path / "loud.wav"
    reference = tmp_path / "quiet.wav"
    _write_broadband(target, amplitude=0.9, seed=1)
    _write_broadband(reference, amplitude=0.05, seed=2)

    result = find_frequency_masking(str(target), str(reference), threshold_db=6.0)

    assert any(
        band["excess_db"] is not None and band["excess_db"] >= 6.0
        for band in result["bands"]
    )
    assert result["score"] >= 6.0


def test_find_frequency_masking_returns_empty_when_no_excess(tmp_path) -> None:
    a = tmp_path / "noise_a.wav"
    b = tmp_path / "noise_b.wav"
    _write_broadband(a, amplitude=0.5, seed=3)
    _write_broadband(b, amplitude=0.5, seed=4)

    result = find_frequency_masking(str(a), str(b), threshold_db=6.0)

    assert result["score"] == 0.0
    assert all(band["excess_db"] is None for band in result["bands"])


def test_find_frequency_masking_rejects_mismatched_sample_rates(tmp_path) -> None:
    target = tmp_path / "target_44k.wav"
    reference = tmp_path / "reference_48k.wav"
    write_sine(target, frequency_hz=1000.0, duration_s=0.5, sample_rate=44100)
    write_sine(reference, frequency_hz=1000.0, duration_s=0.5, sample_rate=48000)

    with pytest.raises(ValueError):
        find_frequency_masking(str(target), str(reference))


def test_analyze_mix_returns_pairwise_masking(tmp_path) -> None:
    stem_a = tmp_path / "stem_a.wav"
    stem_b = tmp_path / "stem_b.wav"
    write_sine(stem_a, frequency_hz=440.0, duration_s=0.5, amplitude=0.9)
    write_sine(stem_b, frequency_hz=2000.0, duration_s=0.5, amplitude=0.9)

    result = analyze_mix([str(stem_a), str(stem_b)])

    assert len(result["stems"]) == 2
    assert len(result["pairwise_masking"]) == 1
    assert result["max_stems"] == 16


def test_analyze_mix_caps_stem_count(tmp_path) -> None:
    paths = []
    for i in range(17):
        p = tmp_path / f"stem_{i}.wav"
        write_sine(p, frequency_hz=440.0 + i, duration_s=0.2, amplitude=0.5)
        paths.append(str(p))

    with pytest.raises(ValueError):
        analyze_mix(paths)


def test_extract_single_cycle_finds_periodic_signal(tmp_path) -> None:
    sine_path = tmp_path / "sine_440.wav"
    write_sine(sine_path, frequency_hz=440.0, duration_s=1.0)

    result = extract_single_cycle(str(sine_path), frame_size=2048)

    assert result["ok"] is True
    assert result["pitch_hz"] == pytest.approx(440.0, abs=2.0)
    assert result["cycle_samples"] > 0
    assert isinstance(result["cycle"], list)


def test_extract_single_cycle_returns_failure_when_aperiodic(tmp_path) -> None:
    noise_path = tmp_path / "noise.wav"
    rng = np.random.default_rng(seed=42)
    noise = rng.normal(0.0, 0.5, size=48000).astype(np.float32)
    import soundfile as sf

    sf.write(str(noise_path), noise, 48000)

    result = extract_single_cycle(str(noise_path), frame_size=2048)

    assert result["ok"] is False
    assert "reason" in result
    assert result["reason"]
