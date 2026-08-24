from __future__ import annotations

import math

import pytest

from ableton_mcp_server.groove_intelligence.canonical import (
    artifact_id_from_identity,
    canonical_json,
    request_hash,
)


def test_canonical_json_normalizes_unicode_numbers_and_key_order() -> None:
    assert canonical_json({"b": "e\u0301", "a": -0.0, "n": 1.2345678912}) == (
        b'{"a":0,"b":"\xc3\xa9","n":1.234567891}'
    )


def test_artifact_id_uses_domain_and_excludes_self_id() -> None:
    identity = {
        "schema_version": "groove.midi-artifact.v1",
        "kind": "source",
        "payload_sha256": "a" * 64,
    }
    first = artifact_id_from_identity(identity)
    assert first.startswith("ga1_") and len(first) == 68
    assert artifact_id_from_identity({**identity, "artifact_id": "ga1_" + "f" * 64}) == first


def test_request_hash_excludes_cursor_but_includes_effective_defaults() -> None:
    page_one = {"schema_version": "groove.search.request.v1", "query": "kick", "limit": 20}
    page_two = {**page_one, "cursor": "opaque-page-two"}
    assert request_hash(page_one) == request_hash(page_two)


def test_canonical_json_rejects_non_finite_numbers() -> None:
    with pytest.raises(ValueError, match="finite"):
        canonical_json({"value": math.nan})
