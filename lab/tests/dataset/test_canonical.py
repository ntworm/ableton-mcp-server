from __future__ import annotations

from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf

from groove_lab.dataset.canonical import build_canonical, note_mass_lost
from tests.fixtures.groove_smf import MULTI_HIT_SMF, NO_TEMPO_SMF


def _chunk(tag: bytes, body: bytes) -> bytes:
    return tag + len(body).to_bytes(4, "big") + body


# Two notes on the same pitch at the same tick: one HVO cell, two subhits.
COLLIDING_SMF = _chunk(b"MThd", b"\x00\x01\x00\x01\x01\xe0") + _chunk(
    b"MTrk",
    b"\x00\x99\x24\x64\x00\x99\x24\x50"
    b"\x81\x70\x89\x24\x00\x00\x89\x24\x00"
    b"\x00\xff\x2f\x00",
)


def test_subhits_counts_every_event_in_a_cell() -> None:
    groove = build_canonical(parse_smf(COLLIDING_SMF), collection="unmapped")
    cells = [cell for cell in groove.cells if cell.subhits > 1]
    assert cells, "a colliding cell must report more than one subhit"
    assert cells[0].subhits == 2


def test_note_mass_lost_is_zero_when_subhits_are_kept() -> None:
    parsed = parse_smf(COLLIDING_SMF)
    groove = build_canonical(parsed, collection="unmapped")
    assert note_mass_lost(parsed, groove) == 0.0


def test_hashes_separate_rhythm_from_expression() -> None:
    quiet = build_canonical(parse_smf(NO_TEMPO_SMF), collection="unmapped")
    same = build_canonical(parse_smf(NO_TEMPO_SMF), collection="unmapped")
    other = build_canonical(parse_smf(MULTI_HIT_SMF), collection="unmapped")

    assert quiet.canonical_hash == same.canonical_hash
    assert quiet.rhythm_hash == same.rhythm_hash
    assert quiet.rhythm_hash != other.rhythm_hash
    assert len(quiet.canonical_hash) == 64


def test_tempo_comes_from_the_smf_not_the_path() -> None:
    groove = build_canonical(parse_smf(NO_TEMPO_SMF), collection="unmapped")
    assert groove.bpm is None or groove.bpm > 0
