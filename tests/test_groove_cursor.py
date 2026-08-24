from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from ableton_mcp_server.groove_intelligence.search import (
    GrooveCursorInvalid,
    GrooveCursorQueryMismatch,
    decode_cursor,
    search,
)
from tests.fixtures.groove_runtime import make_pilot_runtime, make_search_request


def _legacy_cursor_token(response: object, runtime: object) -> str:
    cursor = decode_cursor(response.next_cursor)  # type: ignore[attr-defined]
    payload = {
        "last_artifact_id": cursor.last_artifact_id,
        "last_score": cursor.last_score,
        "limit": cursor.limit,
        "logical_index_digest": runtime.index.manifest.logical_index_digest,  # type: ignore[attr-defined]
        "ranker_id": "groove-ranker-v1",
        "ranker_manifest_digest": runtime.index.manifest.ranker_manifest_digest,  # type: ignore[attr-defined]
        "ranker_schema": "groove.search.ranker.v1",
        "request_hash": cursor.request_hash,
        "schema_version": "groove.search.cursor.v1",
        "seed_bundle_id": runtime.index.manifest.seed_bundle_id,  # type: ignore[attr-defined]
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    checksum = hashlib.sha256(b"ABLETON-GROOVE-CURSOR-V1\x00" + raw).digest()
    return base64.urlsafe_b64encode(raw + checksum).decode().rstrip("=")


def test_cursor_rejects_query_mismatch_and_noncanonical_padding(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    first_request = make_search_request(
        facets={"feel": ["straight"]},
        required_projection_ids=["groove.hvo.v2"],
        limit=1,
    )
    response = search(runtime, first_request)
    assert response.next_cursor is not None
    bad = make_search_request(
        query="different",
        facets={"feel": ["straight"]},
        required_projection_ids=["groove.hvo.v2"],
        limit=1,
        cursor=response.next_cursor,
    )
    with pytest.raises(GrooveCursorQueryMismatch):
        search(runtime, bad)
    with pytest.raises(GrooveCursorInvalid):
        decode_cursor(response.next_cursor + "=")


def test_cursor_paginates_tied_scores_in_artifact_id_order(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    try:
        first_request = make_search_request(facets={"feel": ["straight"]}, limit=1)
        first = search(runtime, first_request)
        assert first.returned_count == 1
        assert first.next_cursor is not None

        second = search(
            runtime,
            make_search_request(
                facets={"feel": ["straight"]},
                limit=1,
                cursor=first.next_cursor,
            ),
        )

        assert second.returned_count == 1
        assert second.items[0].artifact_id != first.items[0].artifact_id
        assert second.next_cursor is None
    finally:
        runtime.close()


def test_v1_cursor_is_rejected_after_ranker_bump(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    try:
        request = make_search_request(facets={"feel": ["straight"]}, limit=1)
        first = search(runtime, request)
        assert first.next_cursor is not None
        legacy = _legacy_cursor_token(first, runtime)
        with pytest.raises(GrooveCursorInvalid):
            search(
                runtime,
                make_search_request(
                    facets={"feel": ["straight"]}, limit=1, cursor=legacy
                ),
            )
    finally:
        runtime.close()
