from __future__ import annotations

from ableton_mcp_server.groove_intelligence.drum_roles import (
    GM_DRUM_ROLE_BY_PITCH,
    GM_DRUM_ROLES,
)
from ableton_mcp_server.groove_intelligence.mapping import _ROLE_BY_PITCH
from ableton_mcp_server.groove_intelligence.midi_lossless import ParsedSmfV1, parse_smf
from ableton_mcp_server.groove_intelligence.projections import (
    ROLE_BY_PITCH,
    ROLES,
    derive_features,
    derive_grammar,
    derive_hvo,
)
from ableton_mcp_server.groove_intelligence.schema import NoteEventV1
from ableton_mcp_server.groove_intelligence.taxonomy import classify_facets


def test_hvo_and_mapping_share_the_expanded_gm_role_source() -> None:
    expected = {
        "kick",
        "snare",
        "rim",
        "clap",
        "hat_closed",
        "hat_open",
        "hat_pedal",
        "tom_low",
        "tom_mid",
        "tom_high",
        "crash",
        "splash",
        "china",
        "ride",
        "ride_bell",
        "tambourine",
        "cowbell",
        "other_percussion",
    }

    assert set(GM_DRUM_ROLES) == expected
    assert ROLE_BY_PITCH is GM_DRUM_ROLE_BY_PITCH
    assert _ROLE_BY_PITCH is GM_DRUM_ROLE_BY_PITCH
    assert set(ROLES) == expected
    assert GM_DRUM_ROLE_BY_PITCH[37] == "rim"
    assert GM_DRUM_ROLE_BY_PITCH[44] == "hat_pedal"
    assert GM_DRUM_ROLE_BY_PITCH[53] == "ride_bell"
    assert GM_DRUM_ROLE_BY_PITCH[60] == "other_percussion"


def test_expanded_roles_reach_grammar_features_and_kit_facet() -> None:
    notes = [
        NoteEventV1(
            event_id=index,
            track_index=1,
            channel=9,
            pitch=pitch,
            velocity=100,
            start_ticks=index * 30,
            duration_ticks=30,
        )
        for index, pitch in enumerate(GM_DRUM_ROLE_BY_PITCH)
    ]
    source = parse_smf(
        b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x01\xe0"
        b"MTrk\x00\x00\x00\x04\x00\xff\x2f\x00"
    )
    parsed = ParsedSmfV1(
        raw_bytes=source.raw_bytes,
        format=source.format,
        events=source.events,
        note_events=notes,
        tracks=source.tracks,
        source_events_digest=source.source_events_digest,
        length_ticks=4 * 480,
        tempos=[],
        meters=[],
    )
    hvo = derive_hvo(parsed)
    features = derive_features(parsed, hvo)
    grammar = derive_grammar(parsed, hvo)
    facets = classify_facets(features, hvo, redistribution="full")

    observed = set(GM_DRUM_ROLES)
    assert {cell.role for cell in hvo.cells} == observed
    assert {str(token["role"]) for token in grammar.tokens} == observed
    assert features.values["roles_present"].value == len(observed)
    assert set(facets.values["kit"]) == observed
