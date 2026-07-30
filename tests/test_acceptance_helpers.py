"""Unit tests for ``ableton_mcp_server.acceptance.helpers``.

Covers ``LIVE_FADE_UNITY_VALUE``, ``_test_tempo``, the
``_acceptance_safe_cue_times`` regression guards (song_length=232,
legacy 256/320 pair), ``_parameter_tolerance`` floor, and the wav
synth helpers.
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from ableton_mcp_server.acceptance.helpers import (
    LIVE_FADE_UNITY_VALUE,
    _acceptance_safe_cue_times,
    _baseline_tool_names,
    _parameter_tolerance,
    _synthesize_offline_inputs,
    _test_tempo,
    _write_sine_wav,
)
from ableton_mcp_server.acceptance.safety import AcceptanceSafetyError


class TestLiveFadeUnityValue:
    def test_value_matches_remote_script(self) -> None:
        # 0.85 (Live mixer volume unity in 0..1 range).
        assert pytest.approx(0.8500000238418579) == LIVE_FADE_UNITY_VALUE

    def test_value_is_positive_float(self) -> None:
        assert isinstance(LIVE_FADE_UNITY_VALUE, float)
        assert 0.0 < LIVE_FADE_UNITY_VALUE <= 1.0


class TestTestTempo:
    def test_offset_within_ceiling(self) -> None:
        # 120 + 1 = 121 → within 999 cap.
        assert _test_tempo(120.0, 1.0) == 121.0

    def test_offset_exceeds_ceiling_subtracts(self) -> None:
        # 999 + 1 = 1000 → cap exceeded → fall back to subtract.
        assert _test_tempo(999.0, 1.0) == 998.0

    def test_offset_at_boundary(self) -> None:
        # 998 + 1 = 999 → equals cap → accept.
        assert _test_tempo(998.0, 1.0) == 999.0

    def test_zero_offset(self) -> None:
        assert _test_tempo(120.0, 0.0) == 120.0


class TestAcceptanceSafeCueTimes:
    def test_returns_two_distinct_grid_aligned_times(self) -> None:
        cue_time, bulk_cue_time = _acceptance_safe_cue_times(232.0, [])
        assert cue_time != bulk_cue_time
        # Both are multiples of 8.0
        assert cue_time % 8.0 == pytest.approx(0.0)
        assert bulk_cue_time % 8.0 == pytest.approx(0.0)

    def test_with_song_length_232_avoids_256_320_legacy(self) -> None:
        # Regression guard: legacy hard-coded pair was (256, 320) which
        # exceeded song_length=232. New helper walks the grid in
        # descending order and must pick values inside song_length.
        cue_time, bulk_cue_time = _acceptance_safe_cue_times(232.0, [])
        assert cue_time <= 232.0
        assert bulk_cue_time <= 232.0
        assert (cue_time, bulk_cue_time) != (256.0, 320.0)

    def test_rejects_non_positive_song_length(self) -> None:
        with pytest.raises(AcceptanceSafetyError, match="must be positive"):
            _acceptance_safe_cue_times(0.0, [])
        with pytest.raises(AcceptanceSafetyError, match="must be positive"):
            _acceptance_safe_cue_times(-1.0, [])

    def test_rejects_none_song_length(self) -> None:
        with pytest.raises(AcceptanceSafetyError, match="positive number"):
            _acceptance_safe_cue_times(None, [])

    def test_rejects_string_song_length(self) -> None:
        with pytest.raises(AcceptanceSafetyError, match="positive number"):
            _acceptance_safe_cue_times("232", [])

    def test_rejects_non_positive_grid(self) -> None:
        with pytest.raises(AcceptanceSafetyError, match="grid must be positive"):
            _acceptance_safe_cue_times(232.0, [], grid=0.0)
        with pytest.raises(AcceptanceSafetyError, match="grid must be positive"):
            _acceptance_safe_cue_times(232.0, [], grid=-1.0)

    def test_avoids_occupied_cells(self) -> None:
        # Mark every grid-aligned cell as occupied so the helper cannot
        # find two safe cells and must raise.
        occupied = [{"time": float(i) * 8.0} for i in range(30)]
        with pytest.raises(AcceptanceSafetyError, match="could not find two safe cue times"):
            _acceptance_safe_cue_times(232.0, occupied)

    def test_skips_invalid_locator_times(self) -> None:
        # Garbage entries should not crash the helper.
        cue_time, bulk_cue_time = _acceptance_safe_cue_times(
            232.0,
            [{"time": "garbage"}, {"time": None}],
        )
        assert cue_time != bulk_cue_time

    def test_legacy_pair_returned_in_descending_order(self) -> None:
        """The legacy (256, 320) guard requires ascending order.

        With the descending walk introduced by commit 6773830,
        ``cue_time > bulk_cue_time`` always; the legacy guard cannot
        fire and is documented as a defensive regression marker.
        """
        occupied = []
        for i in range(0, 50):
            t = float(i) * 8.0
            if t not in (256.0, 320.0):
                occupied.append({"time": t})
        # song_length must include 320 → 320+grid.
        cue_time, bulk_cue_time = _acceptance_safe_cue_times(324.0, occupied, grid=8.0)
        # Descending walk → first chosen is largest.
        assert cue_time == 320.0
        assert bulk_cue_time == 256.0


class TestParameterTolerance:
    def test_zero_range_uses_floor(self) -> None:
        # abs(0)*0.01 == 0 → max(1e-12, 0) == 1e-12.
        assert _parameter_tolerance(0.0, 0.0) == pytest.approx(1e-12)

    def test_unit_range(self) -> None:
        assert _parameter_tolerance(0.0, 1.0) == pytest.approx(0.01)

    def test_large_range(self) -> None:
        assert _parameter_tolerance(-100.0, 100.0) == pytest.approx(2.0)


class TestWriteSineWav:
    def test_creates_wav_with_expected_metadata(self, tmp_path: Path) -> None:
        out = tmp_path / "tone.wav"
        _write_sine_wav(out, hz=440.0, amplitude=0.5, seconds=0.1, sample_rate=44100)
        with wave.open(str(out), "rb") as w:
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2
            assert w.getframerate() == 44100
            assert w.getnframes() == pytest.approx(4410)

    def test_amplitude_clamps_to_16bit_range(self, tmp_path: Path) -> None:
        out = tmp_path / "tone.wav"
        # amplitude=1.0 should not clip — max sample int = 32767.
        _write_sine_wav(out, hz=440.0, amplitude=1.0, seconds=0.01, sample_rate=44100)
        with wave.open(str(out), "rb") as w:
            frames = w.readframes(w.getnframes())
            samples = [
                int.from_bytes(frames[i : i + 2], "little", signed=True)
                for i in range(0, len(frames), 2)
            ]
            assert all(-32767 <= s <= 32767 for s in samples)


class TestSynthesizeOfflineInputs:
    def test_creates_four_wav_files(self, tmp_path: Path) -> None:
        inputs = _synthesize_offline_inputs(tmp_path)
        assert set(inputs.keys()) == {"target", "reference", "short", "long"}
        for path in inputs.values():
            assert path.is_file()
            assert path.suffix == ".wav"

    def test_creates_directory_if_missing(self, tmp_path: Path) -> None:
        sub = tmp_path / "nested" / "wav"
        inputs = _synthesize_offline_inputs(sub)
        assert sub.is_dir()
        for path in inputs.values():
            assert path.is_file()


class TestBaselineToolNames:
    """``_baseline_tool_names`` reads ``server.PUBLIC_TOOL_NAMES``."""

    def test_returns_non_empty_tuple(self) -> None:
        names = _baseline_tool_names()
        assert isinstance(names, tuple)
        assert len(names) >= 1

    def test_no_duplicates(self) -> None:
        names = _baseline_tool_names()
        assert len(names) == len(set(names))