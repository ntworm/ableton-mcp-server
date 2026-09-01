from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ableton_mcp_server.groove_intelligence.articulation import (
    collection_confidence,
    mapped_collections,
    resolve_role,
)
from ableton_mcp_server.groove_intelligence.canonical import canonical_json, sha256_hex
from ableton_mcp_server.groove_intelligence.constants import (
    HVO_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION_V3,
)
from ableton_mcp_server.groove_intelligence.drum_roles import (
    GM_DRUM_ROLE_BY_PITCH,
    GM_DRUM_ROLES,
)
from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf
from ableton_mcp_server.groove_intelligence.projections import derive_hvo, derive_hvo_v3
from ableton_mcp_server.groove_intelligence.schema import HvoProjectionV1
from tests.fixtures.groove_smf import MINIMAL_TYPE1_SMF, MULTI_HIT_SMF, NO_TEMPO_SMF

# Collections are keyed by the full catalog stratum.  Using a bare product name
# would fall through to General MIDI and make these assertions pass for the
# wrong reason.
MAPPED = "Drums Groove MIDI/000011@SUPERIOR_DRUMMER_3"
LATIN = "Drums Groove MIDI/07@EZX_LATIN_PERCUSSION"
UNMAPPED = "Drums Groove MIDI/does-not-exist"

HAT_ROLES = {"hat_closed", "hat_open", "hat_pedal"}
MAP_PATH = (
    Path(__file__).resolve().parents[1]
    / "ableton_mcp_server"
    / "groove_intelligence"
    / "articulation_map.json"
)


def _chunk(tag: bytes, body: bytes) -> bytes:
    return tag + len(body).to_bytes(4, "big") + body


# Pitch 0x16 is 22, inside the hi-hat band the libraries use below General MIDI.
# Pitch 0x26 is 38, a General MIDI snare, and must resolve the same way in both
# projections.
BAND_AND_SNARE_SMF = _chunk(b"MThd", b"\x00\x01\x00\x01\x01\xe0") + _chunk(
    b"MTrk",
    b"\x00\x99\x16\x64\x00\x99\x26\x64"
    b"\x81\x70\x89\x16\x00\x00\x89\x26\x00"
    b"\x00\xff\x2f\x00",
)


def _roles(projection: HvoProjectionV1) -> set[str]:
    return {cell.role for cell in projection.cells}


def test_map_is_keyed_per_collection_with_real_evidence() -> None:
    raw = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    assert raw, "articulation map is empty"

    tables = {json.dumps(entry["pitches"], sort_keys=True) for entry in raw.values()}
    assert len(tables) > 1, "one pitch table copied across collections is not a per-collection map"

    confidences = {entry["confidence"] for entry in raw.values()}
    assert confidences <= {"high", "medium", "low"}
    assert confidences != {"high"}, "a map that is high confidence everywhere states nothing"

    # Small collections can legitimately share wording when they carry the same
    # single pitch with the same counts.  What must not happen is one boilerplate
    # string standing in for evidence across the map.
    evidence = Counter(entry["evidence"] for entry in raw.values())
    most_common, repeats = evidence.most_common(1)[0]
    assert repeats <= max(2, len(raw) // 20), (
        f"one evidence string covers {repeats} of {len(raw)} entries: {most_common[:120]}"
    )
    assert len(evidence) >= len(raw) * 0.9, "evidence is not specific enough per collection"


def test_map_only_assigns_canonical_roles() -> None:
    raw = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    assigned = {role for entry in raw.values() for role in entry["pitches"].values()}
    unexpected = assigned - set(GM_DRUM_ROLES)
    assert not unexpected, f"map assigns roles outside the ontology: {unexpected}"


def test_map_never_downgrades_a_resolved_general_midi_pitch() -> None:
    # The vendor kit vocabulary is coarser than General MIDI in places: one Ride
    # piece covers the bell, one Crash covers splash and china.  An override is
    # only ever allowed where General MIDI leaves the pitch unresolved, so a
    # coarser vendor answer can never replace a finer one.
    raw = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    for collection, entry in raw.items():
        for pitch, role in entry["pitches"].items():
            gm_role = GM_DRUM_ROLE_BY_PITCH.get(int(pitch), "other_percussion")
            assert gm_role == "other_percussion", (
                f"{collection} pitch {pitch} overrides General MIDI {gm_role} with {role}"
            )


def test_the_same_pitch_resolves_differently_per_library() -> None:
    # Pitch 60 is a hi-hat in Superior Drummer 3 and the General MIDI hi bongo in
    # EZX Latin Percussion.  This is the whole reason the map is keyed by
    # collection, and it is why 60-63 were never crashes.
    assert resolve_role(MAPPED, 60) in HAT_ROLES
    assert resolve_role(LATIN, 60) == "other_percussion"
    assert resolve_role(MAPPED, 60) != resolve_role(LATIN, 60)


def test_no_collection_maps_the_cymbal_band_to_crash() -> None:
    for collection in sorted(mapped_collections()):
        for pitch in (60, 61, 62, 63):
            assert resolve_role(collection, pitch) != "crash"


def test_mapped_collection_resolves_the_band_to_hi_hat_lanes() -> None:
    assert collection_confidence(MAPPED) in {"high", "medium"}
    assert resolve_role(MAPPED, 22) in HAT_ROLES
    # General MIDI pitches are never overridden by the map.
    assert resolve_role(MAPPED, 36) == "kick"
    assert resolve_role(MAPPED, 38) == "snare"


def test_unmapped_collection_matches_general_midi_exactly() -> None:
    assert collection_confidence(UNMAPPED) is None
    for pitch in range(128):
        expected = GM_DRUM_ROLE_BY_PITCH.get(pitch, "other_percussion")
        assert resolve_role(UNMAPPED, pitch) == expected


def test_v2_projection_is_byte_stable() -> None:
    # Golden digests.  Any change to derive_hvo or to the General MIDI role map
    # breaks this, which is the point: groove.hvo.v2 feeds the shipped retrieval
    # seed and its digests are recorded in the seed manifest.
    expected = {
        "minimal": "085dc22efa7817c3a4d2379e6ae64d3417a6380346d84e038f4965b03f2bdf3f",
        "multi_hit": "cbb5e5f61f9995e6270b95c1a0f9958fd55fb51efd0bab938629c4af50d2935a",
        "no_tempo": "027d29c95b18229558947f39b7161bd2d8acf2c1d32bf3941c41270ae8e713b6",
    }
    actual = {
        "minimal": sha256_hex(
            canonical_json(derive_hvo(parse_smf(MINIMAL_TYPE1_SMF)).model_dump())
        ),
        "multi_hit": sha256_hex(canonical_json(derive_hvo(parse_smf(MULTI_HIT_SMF)).model_dump())),
        "no_tempo": sha256_hex(canonical_json(derive_hvo(parse_smf(NO_TEMPO_SMF)).model_dump())),
    }
    assert actual == expected


def test_v2_leaves_the_band_unresolved_and_stays_stamped_v2() -> None:
    hvo = derive_hvo(parse_smf(BAND_AND_SNARE_SMF))
    assert hvo.schema_version == HVO_SCHEMA_VERSION
    assert _roles(hvo) == {"other_percussion", "snare"}


def test_v3_is_stamped_and_differs_only_where_the_map_says() -> None:
    parsed = parse_smf(BAND_AND_SNARE_SMF)
    v2 = derive_hvo(parsed)
    v3 = derive_hvo_v3(parsed, MAPPED)

    assert v3.schema_version == HVO_SCHEMA_VERSION_V3
    assert v3.grid_ticks == v2.grid_ticks
    assert v3.source_events_digest == v2.source_events_digest
    assert len(v3.cells) == len(v2.cells)

    assert "other_percussion" in _roles(v2)
    assert "other_percussion" not in _roles(v3)
    assert _roles(v3) - {"snare"} <= HAT_ROLES

    v2_snare = [cell.model_dump() for cell in v2.cells if cell.role == "snare"]
    v3_snare = [cell.model_dump() for cell in v3.cells if cell.role == "snare"]
    assert v2_snare == v3_snare


def test_v3_equals_v2_for_an_unmapped_collection() -> None:
    parsed = parse_smf(BAND_AND_SNARE_SMF)
    v2 = derive_hvo(parsed)
    v3 = derive_hvo_v3(parsed, UNMAPPED)
    assert v3.model_dump(exclude={"schema_version"}) == v2.model_dump(exclude={"schema_version"})
