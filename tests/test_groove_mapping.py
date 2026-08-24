from __future__ import annotations

from pathlib import Path

from ableton_mcp_server.groove_intelligence.mapping import map_artifact
from ableton_mcp_server.groove_intelligence.midi_lossless import (
    compress_bounded,
    decompress_bounded,
    parse_smf,
)
from tests.fixtures.groove_apply import make_drum_artifact
from tests.fixtures.groove_runtime import make_pilot_runtime


def _vlq(value: int) -> bytes:
    encoded = [value & 0x7F]
    value >>= 7
    while value:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(encoded))


def test_mapping_emits_source_note_events_in_order(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    artifact = runtime.store.get(str(runtime.index.manifest.artifact_ids[-1]))
    plan = map_artifact(artifact, "gm-drums-v1")
    assert plan.emitted_events
    assert [item.event_id for item in plan.emitted_events] == sorted(
        item.event_id for item in plan.emitted_events
    )
    assert all(item.note.pitch == item.resolved_pitch for item in plan.emitted_events)


def test_native_compatible_accepts_single_non_gm_channel() -> None:
    artifact = make_drum_artifact(channels=(0,))

    plan = map_artifact(artifact, "native-compatible")

    assert plan.allowed is True
    assert "unsupported_channel" not in plan.warning_codes
    assert plan.exact_count == 2
    assert {item.source_channel for item in plan.emitted_events} == {0}


def test_gm_drums_rejects_single_non_drum_channel() -> None:
    artifact = make_drum_artifact(channels=(0,))

    plan = map_artifact(artifact, "gm-drums-v1")

    assert plan.allowed is False
    assert "unsupported_channel" in plan.warning_codes


def test_mapping_preserves_declared_smf_length_after_final_note() -> None:
    artifact = make_drum_artifact().model_copy(
        update={"timing": {"length_ticks": 16 * 480}}
    )

    plan = map_artifact(artifact, "gm-drums-v1")

    assert plan.length_beats == 16.0


def test_mapping_reads_trailing_silence_from_smf_when_timing_is_missing() -> None:
    artifact = make_drum_artifact()
    raw = decompress_bounded(
        artifact.payload.blob,
        codec=artifact.payload.codec,
        raw_size=artifact.payload.raw_size,
    )
    declared_length = 16 * artifact.format.ppq
    deltas = declared_length - parse_smf(raw).length_ticks
    assert deltas == 7320
    body = raw[22:-4] + _vlq(deltas) + b"\xff\x2f\x00"
    extended = raw[:18] + len(body).to_bytes(4, "big") + body
    artifact = artifact.model_copy(
        update={
            "timing": {},
            "payload": compress_bounded(extended, "zlib-raw-midi-v1"),
        }
    )

    plan = map_artifact(artifact, "gm-drums-v1")

    assert plan.length_beats == 16.0


def test_mapping_rejects_declared_clip_length_above_create_clip_limit() -> None:
    artifact = make_drum_artifact().model_copy(
        update={"timing": {"length_ticks": (100_000 * 480) + 1}}
    )

    plan = map_artifact(artifact, "gm-drums-v1")

    assert plan.allowed is False
    assert "loop_length_limit" in plan.warning_codes
