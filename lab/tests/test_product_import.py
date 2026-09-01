from __future__ import annotations


def test_lab_can_use_the_product_projections() -> None:
    # The dataset pipeline reuses the shipped parser, articulation map and v3
    # projection rather than reimplementing them, so a drift in the product is a
    # failure here rather than a silent divergence in the training data.
    from ableton_mcp_server.groove_intelligence.articulation import resolve_role
    from ableton_mcp_server.groove_intelligence.constants import HVO_SCHEMA_VERSION_V3
    from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf
    from ableton_mcp_server.groove_intelligence.projections import derive_hvo_v3

    assert HVO_SCHEMA_VERSION_V3 == "groove.hvo.v3"
    assert callable(parse_smf)
    assert callable(derive_hvo_v3)
    assert resolve_role("Drums Groove MIDI/does-not-exist", 36) == "kick"
