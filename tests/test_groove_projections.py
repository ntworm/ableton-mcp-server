from __future__ import annotations

import pytest

from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf
from ableton_mcp_server.groove_intelligence.projections import (
    derive_features,
    derive_grammar,
    derive_hvo,
)
from tests.fixtures.groove_smf import (
    MINIMAL_TYPE1_SMF,
    MULTI_HIT_SMF,
    NO_TEMPO_SMF,
    TIME_SIGNATURE_6_8_SMF,
)


def _vlq(value: int) -> bytes:
    encoded = [value & 0x7F]
    value >>= 7
    while value:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(encoded))


def _chunk(tag: bytes, body: bytes) -> bytes:
    return tag + len(body).to_bytes(4, "big") + body


def _equivalent_6_8_smf(ppq: int) -> bytes:
    scale = ppq // 480
    body = bytearray(b"\x00\xff\x51\x03\x07\xa1\x20")
    body.extend(b"\x00\xff\x58\x04\x06\x03\x18\x08")
    current = 0
    for start, duration, pitch in ((30, 120, 36), (480, 240, 38)):
        scaled_start = start * scale
        body.extend(_vlq(scaled_start - current))
        body.extend((0x99, pitch, 100))
        body.extend(_vlq(duration * scale))
        body.extend((0x89, pitch, 0))
        current = (start + duration) * scale
    declared_length = 6 * ppq
    body.extend(_vlq(declared_length - current))
    body.extend(b"\xff\x2f\x00")
    return _chunk(b"MThd", b"\x00\x00\x00\x01" + ppq.to_bytes(2, "big")) + _chunk(
        b"MTrk", bytes(body)
    )


def test_hvo_keeps_all_colliding_event_ids_and_normalizes_velocity() -> None:
    hvo = derive_hvo(parse_smf(MULTI_HIT_SMF))
    cell = next(cell for cell in hvo.cells if cell.role == "snare")
    assert cell.hit == 1 and cell.velocity == pytest.approx(round(104 / 127, 9), abs=5e-10)
    assert cell.event_ids == [0, 1]
    assert -120 <= cell.offset_ticks <= 120


def test_missing_feature_is_unavailable_not_zero() -> None:
    parsed = parse_smf(NO_TEMPO_SMF)
    features = derive_features(parsed, derive_hvo(parsed))
    assert features.values["tempo_min"].status == "unavailable"
    assert features.values["tempo_min"].value is None


def test_projections_keep_source_digest_and_have_bounded_grammar() -> None:
    parsed = parse_smf(MINIMAL_TYPE1_SMF)
    hvo = derive_hvo(parsed)
    features = derive_features(parsed, hvo)
    grammar = derive_grammar(parsed, hvo)
    assert hvo.source_events_digest == parsed.source_events_digest
    assert features.source_events_digest == parsed.source_events_digest
    assert grammar.source_events_digest == parsed.source_events_digest
    assert all(0 <= token["velocity_bin"] <= 7 for token in grammar.tokens)


def test_hvo_handles_time_signature_denominator_above_four() -> None:
    parsed = parse_smf(TIME_SIGNATURE_6_8_SMF)
    hvo = derive_hvo(parsed)
    features = derive_features(parsed, hvo)
    assert hvo.cells
    assert features.values["bars"].value == 1


def test_projections_are_ppq_invariant_and_meter_aware() -> None:
    parsed_480 = parse_smf(_equivalent_6_8_smf(480))
    parsed_9600 = parse_smf(_equivalent_6_8_smf(9600))
    hvo_480 = derive_hvo(parsed_480)
    hvo_9600 = derive_hvo(parsed_9600)
    features_480 = derive_features(parsed_480, hvo_480)
    features_9600 = derive_features(parsed_9600, hvo_9600)
    grammar_480 = derive_grammar(parsed_480, hvo_480)
    grammar_9600 = derive_grammar(parsed_9600, hvo_9600)

    assert hvo_480.model_dump(exclude={"source_events_digest"}) == hvo_9600.model_dump(
        exclude={"source_events_digest"}
    )
    comparable_features_480 = {
        name: value.model_dump(mode="json")
        for name, value in features_480.values.items()
        if name != "ppq"
    }
    comparable_features_9600 = {
        name: value.model_dump(mode="json")
        for name, value in features_9600.values.items()
        if name != "ppq"
    }
    assert comparable_features_480 == comparable_features_9600
    assert features_480.values["meter"].value == "6/8"
    assert features_480.values["bars"].value == 2
    assert features_480.values["beats"].value == pytest.approx(6.0)
    assert grammar_480.model_dump(exclude={"source_events_digest"}) == grammar_9600.model_dump(
        exclude={"source_events_digest"}
    )
