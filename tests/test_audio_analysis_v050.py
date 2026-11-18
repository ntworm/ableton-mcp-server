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
        band["excess_db"] is not None and band["excess_db"] >= 6.0 for band in result["bands"]
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


def test_masking_detects_two_overlapping_1khz_tones(tmp_path) -> None:
    target = tmp_path / "target.wav"
    reference = tmp_path / "reference.wav"
    write_sine(target, frequency_hz=1000.0, duration_s=1.0, amplitude=0.8)
    write_sine(reference, frequency_hz=1000.0, duration_s=1.0, amplitude=0.2)

    result = find_frequency_masking(str(target), str(reference), threshold_db=6.0)

    assert result["score"] == pytest.approx(12.04, abs=1.5)
    assert any(item["overlap_ratio"] > 0.8 for item in result["bands"])


def test_masking_trims_to_shared_duration(tmp_path) -> None:
    short = tmp_path / "short.wav"
    long_ = tmp_path / "long.wav"
    write_sine(short, frequency_hz=440.0, duration_s=0.5, amplitude=0.5)
    write_sine(long_, frequency_hz=440.0, duration_s=1.0, amplitude=0.25)

    assert find_frequency_masking(str(short), str(long_))["score"] > 0


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


def test_analyze_mix_suggests_trim_towards_target_lufs(tmp_path) -> None:
    """A 0.5 amplitude sine sits near -18.8 LUFS, so -14 LUFS needs +4.8 dB."""
    stem = tmp_path / "stem.wav"
    write_sine(stem, frequency_hz=440.0, duration_s=0.5, amplitude=0.5)

    result = analyze_mix([str(stem)], target_lufs=-14.0)

    metrics = result["stems"][0]
    assert result["target_lufs"] == -14.0
    assert metrics["suggested_trim_db"] == pytest.approx(4.8, abs=0.1)
    assert metrics["peak_after_trim_dbfs"] == pytest.approx(-1.22, abs=0.05)
    assert metrics["clip_risk"] is False
    assert "reason" not in metrics


def test_analyze_mix_plan_lists_the_stems_in_request_order(tmp_path) -> None:
    stem_a = tmp_path / "a.wav"
    stem_b = tmp_path / "b.wav"
    write_sine(stem_a, frequency_hz=440.0, duration_s=0.5, amplitude=0.5)
    write_sine(stem_b, frequency_hz=1000.0, duration_s=0.5, amplitude=0.25)

    result = analyze_mix([str(stem_a), str(stem_b)], target_lufs=-18.0)

    plan = result["plan"]
    assert [entry["name"] for entry in plan] == [str(stem_a), str(stem_b)]
    assert plan[0]["suggested_trim_db"] == pytest.approx(0.8, abs=0.1)
    assert plan[1]["suggested_trim_db"] == pytest.approx(12.8, abs=0.1)
    assert plan[0]["clip_risk"] is False
    assert plan[1]["clip_risk"] is True
    assert result["stems"][0]["suggested_trim_db"] == plan[0]["suggested_trim_db"]
    assert result["stems"][1]["suggested_trim_db"] == plan[1]["suggested_trim_db"]


def test_analyze_mix_reports_a_silent_stem_without_a_trim(tmp_path) -> None:
    silent = tmp_path / "silent.wav"
    write_sine(silent, frequency_hz=440.0, duration_s=0.2, amplitude=0.0)
    loud = tmp_path / "loud.wav"
    write_sine(loud, frequency_hz=1000.0, duration_s=0.2, amplitude=0.5)

    result = analyze_mix([str(silent), str(loud)], target_lufs=-18.0)

    metrics = result["stems"][0]
    assert metrics["suggested_trim_db"] is None
    assert metrics["peak_after_trim_dbfs"] is None
    assert metrics["clip_risk"] is False
    assert metrics["reason"] == "silent"
    plan_entry = result["plan"][0]
    assert plan_entry["suggested_trim_db"] is None
    assert plan_entry["reason"] == "silent"


def test_analyze_mix_flags_clip_risk_after_the_suggested_trim(tmp_path) -> None:
    """A 0.9 amplitude sine peaks near -0.9 dBFS, so any boost risks clipping."""
    stem = tmp_path / "hot.wav"
    write_sine(stem, frequency_hz=440.0, duration_s=0.5, amplitude=0.9)

    result = analyze_mix([str(stem)], target_lufs=-6.0)

    metrics = result["stems"][0]
    assert metrics["suggested_trim_db"] == pytest.approx(2.5, abs=0.1)
    assert metrics["peak_after_trim_dbfs"] > -1.0
    assert metrics["clip_risk"] is True
    assert result["plan"][0]["clip_risk"] is True


@pytest.mark.parametrize("target_lufs", [-40.1, -5.9, -100.0, 0.0])
def test_analyze_mix_rejects_a_target_lufs_outside_the_supported_range(
    tmp_path, target_lufs
) -> None:
    stem = tmp_path / "stem.wav"
    write_sine(stem, frequency_hz=440.0, duration_s=0.2, amplitude=0.5)

    with pytest.raises(ValueError):
        analyze_mix([str(stem)], target_lufs=target_lufs)


@pytest.mark.parametrize("target_lufs", [-40.0, -6.0])
def test_analyze_mix_accepts_the_target_lufs_bounds(tmp_path, target_lufs) -> None:
    stem = tmp_path / "stem.wav"
    write_sine(stem, frequency_hz=440.0, duration_s=0.2, amplitude=0.5)

    result = analyze_mix([str(stem)], target_lufs=target_lufs)

    assert result["target_lufs"] == target_lufs
    assert len(result["plan"]) == 1


def test_analyze_mix_without_target_lufs_is_unchanged(tmp_path) -> None:
    stem_a = tmp_path / "a.wav"
    stem_b = tmp_path / "b.wav"
    write_sine(stem_a, frequency_hz=440.0, duration_s=0.5, amplitude=0.5)
    write_sine(stem_b, frequency_hz=2000.0, duration_s=0.5, amplitude=0.25)

    result = analyze_mix([str(stem_a), str(stem_b)])

    assert result == {
        "stems": [
            {"name": str(stem_a), **analyze_audio(str(stem_a))},
            {"name": str(stem_b), **analyze_audio(str(stem_b))},
        ],
        "pairwise_masking": [
            {
                "target": str(stem_a),
                "reference": str(stem_b),
                "score": find_frequency_masking(
                    str(stem_a), str(stem_b), threshold_db=3.0
                )["score"],
            }
        ],
        "max_stems": 16,
    }
    assert "plan" not in result
    assert "target_lufs" not in result


def test_analyze_mix_tool_passes_target_lufs_through(tmp_path) -> None:
    """The MCP wrapper forwards the target and never claims a Live write."""
    from ableton_mcp_server.tools_offline import analyze_mix as analyze_mix_tool

    stem = tmp_path / "stem.wav"
    write_sine(stem, frequency_hz=440.0, duration_s=0.5, amplitude=0.5)

    result = analyze_mix_tool(stems=[str(stem)], target_lufs=-14.0)

    payload = result.structured_content
    assert payload["target_lufs"] == -14.0
    assert payload["plan"][0]["suggested_trim_db"] == pytest.approx(4.8, abs=0.1)
    assert "never changes the Live set" in (analyze_mix_tool.__doc__ or "")
