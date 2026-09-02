"""What the v3 seed must change, and what it must not.

Written before the regeneration so the difference is a decision rather than a
surprise. The v2 projection is the shipped contract for everything already using
the seed; the v3 projection and the kit facet are what this change is for.
"""

from __future__ import annotations

from ableton_mcp_server.groove_intelligence.articulation import resolve_role
from ableton_mcp_server.groove_intelligence.constants import (
    HVO_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION_V3,
)
from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf
from ableton_mcp_server.groove_intelligence.projections import derive_hvo, derive_hvo_v3

SUPERIOR = "Drums Groove MIDI/000011@SUPERIOR_DRUMMER_3"
LATIN = "Drums Groove MIDI/07@EZX_LATIN_PERCUSSION"


def _chunk(tag: bytes, body: bytes) -> bytes:
    return tag + len(body).to_bytes(4, "big") + body


# Pitch 0x16 is 22: a hi-hat articulation in the vendor libraries, outside the
# General MIDI percussion range, and therefore junk under v2. Pitch 0x24 is 36,
# a General MIDI kick, which must resolve the same way under both.
BAND_SMF = _chunk(b"MThd", b"\x00\x01\x00\x01\x01\xe0") + _chunk(
    b"MTrk",
    b"\x00\x99\x16\x64\x00\x99\x24\x64"
    b"\x81\x70\x89\x16\x00\x00\x89\x24\x00"
    b"\x00\xff\x2f\x00",
)


def test_v2_still_calls_the_band_junk() -> None:
    # This is the defect being fixed, pinned so the fix is visible in the diff.
    hvo = derive_hvo(parse_smf(BAND_SMF))
    assert hvo.schema_version == HVO_SCHEMA_VERSION
    assert "other_percussion" in {cell.role for cell in hvo.cells}


def test_v3_puts_the_band_in_a_hi_hat_lane() -> None:
    hvo = derive_hvo_v3(parse_smf(BAND_SMF), SUPERIOR)
    assert hvo.schema_version == HVO_SCHEMA_VERSION_V3
    roles = {cell.role for cell in hvo.cells}
    assert "other_percussion" not in roles
    assert roles & {"hat_closed", "hat_open", "hat_pedal"}


def test_a_clip_with_no_collection_falls_back_to_general_midi() -> None:
    # A user's own clip pasted from Ableton has no collection. The articulation
    # map describes the vendor libraries, not arbitrary MIDI, so General MIDI is
    # the correct answer and not a degradation.
    assert resolve_role("", 36) == "kick"
    assert resolve_role("", 22) == "other_percussion"


def test_the_same_pitch_still_differs_by_library() -> None:
    assert resolve_role(SUPERIOR, 60) != resolve_role(LATIN, 60)
