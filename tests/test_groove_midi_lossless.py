from __future__ import annotations

import zlib

import pytest

from ableton_mcp_server.groove_intelligence import GrooveBlobRejected, GrooveMidiError
from ableton_mcp_server.groove_intelligence.midi_lossless import (
    decompress_bounded,
    parse_smf,
    serialize_note_smf,
)
from tests.fixtures.groove_smf import (
    HIGH_EXPANSION_BLOB,
    HIGH_EXPANSION_RAW,
    MALFORMED_COMPRESSED_BLOB,
    MALFORMED_RUNNING_STATUS,
    MINIMAL_TYPE1_SMF,
    WRAPPED_COMPRESSED_BLOB,
)


def test_parser_preserves_source_bytes_and_pairs_notes() -> None:
    parsed = parse_smf(MINIMAL_TYPE1_SMF)
    assert parsed.raw_bytes == MINIMAL_TYPE1_SMF
    assert parsed.format.ppq == 480
    assert parsed.note_events[0].pitch == 36
    assert parsed.note_events[0].duration_ticks == 240
    assert parsed.events[0].absolute_ticks == 0


def test_event_ids_are_stable_track_local_allocations() -> None:
    first = parse_smf(MINIMAL_TYPE1_SMF)
    second = parse_smf(MINIMAL_TYPE1_SMF)
    assert [event.event_id for event in first.events] == [event.event_id for event in second.events]
    assert first.note_events[0].event_id == (1 << 32) | 0


def test_parser_rejects_malformed_running_status() -> None:
    with pytest.raises(GrooveMidiError, match="running status"):
        parse_smf(MALFORMED_RUNNING_STATUS)


def test_parser_rejects_input_size_limit() -> None:
    with pytest.raises(GrooveMidiError, match="input size limit"):
        parse_smf(b"\x00" * (8 * 1024 * 1024 + 1))


def test_valid_high_expansion_stream_is_rejected_by_ratio() -> None:
    assert zlib.decompress(HIGH_EXPANSION_BLOB, wbits=-15) == HIGH_EXPANSION_RAW
    with pytest.raises(GrooveBlobRejected, match="^decompression ratio exceeded$"):
        decompress_bounded(
            HIGH_EXPANSION_BLOB,
            codec="zlib-raw-midi-v1",
            raw_size=len(HIGH_EXPANSION_RAW),
            max_ratio=2,
        )


def test_raw_size_guard_is_distinct_from_ratio_and_malformed() -> None:
    with pytest.raises(GrooveBlobRejected, match="^raw size limit exceeded$"):
        decompress_bounded(
            HIGH_EXPANSION_BLOB,
            codec="zlib-raw-midi-v1",
            raw_size=len(HIGH_EXPANSION_RAW),
            max_raw=len(HIGH_EXPANSION_RAW) - 1,
            max_ratio=1000,
        )


def test_distinct_malformed_compressed_stream_is_rejected() -> None:
    with pytest.raises(GrooveBlobRejected, match="^malformed compressed stream$"):
        decompress_bounded(
            MALFORMED_COMPRESSED_BLOB,
            codec="zlib-raw-midi-v1",
            raw_size=len(HIGH_EXPANSION_RAW),
        )


def test_v1_rejects_wrapped_codec_even_when_payload_is_valid() -> None:
    with pytest.raises(GrooveBlobRejected, match="^unsupported compression codec$"):
        decompress_bounded(
            WRAPPED_COMPRESSED_BLOB,
            codec="zlib-wrapped-midi-v1",
            raw_size=len(HIGH_EXPANSION_RAW),
        )


def test_serializer_emits_time_signature_at_tick_zero() -> None:
    raw = serialize_note_smf(
        (),
        ppq=480,
        length_ticks=2_880,
        meter=(6, 3),
        tempos=({"absolute_ticks": 0, "microseconds": 500_000},),
    )

    parsed = parse_smf(raw)

    assert parsed.meters == [
        {
            "track_index": 0,
            "absolute_ticks": 0,
            "numerator": 6,
            "denominator_power": 3,
        }
    ]
    assert parsed.tempos[0]["absolute_ticks"] == 0
    assert parsed.tempos[0]["microseconds"] == 500_000
