from __future__ import annotations

from ableton_mcp_server.groove_intelligence.rights import (
    RightsRecordV1,
    meet_rights,
)


def test_rights_meet_never_promotes_and_blocks_missing_parent() -> None:
    result = meet_rights(
        [RightsRecordV1(level="full"), RightsRecordV1(level="derived_only")],
        operation="apply",
        mapping_level="full",
    )
    assert result.level == "derived_only" and result.capability_apply is False
    missing = meet_rights(
        [RightsRecordV1(level="full", provenance_valid=False)],
        operation="generate",
        mapping_level="full",
    )
    assert missing.level == "blocked" and missing.reason == "license_missing"

