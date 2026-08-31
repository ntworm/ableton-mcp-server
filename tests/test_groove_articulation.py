from ableton_mcp_server.groove_intelligence.articulation import resolve_role
from ableton_mcp_server.groove_intelligence.projections import derive_hvo_v3, derive_hvo
from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf
from tests.fixtures.groove_smf import MULTI_HIT_SMF
import os

def test_resolve_role():
    assert resolve_role("Drums Groove MIDI/000011@SUPERIOR_DRUMMER_3", 22) == "hat_closed"
    assert resolve_role("Drums Groove MIDI/000011@SUPERIOR_DRUMMER_3", 26) == "hat_open"
    assert resolve_role("Drums Groove MIDI/000011@SUPERIOR_DRUMMER_3", 60) == "crash"
    assert resolve_role("Drums Groove MIDI/000011@SUPERIOR_DRUMMER_3", 38) == "snare"
    assert resolve_role("EZX_LATIN_PERCUSSION", 60) == "other_percussion"

def test_derive_hvo_v3():
    parsed = parse_smf(MULTI_HIT_SMF)
    hvo2 = derive_hvo(parsed)
    hvo3 = derive_hvo_v3(parsed, "Drums Groove MIDI/000011@SUPERIOR_DRUMMER_3")
    assert hvo2.grid_ticks == hvo3.grid_ticks
    assert hvo2.source_events_digest == hvo3.source_events_digest
