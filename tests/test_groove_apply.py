from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from ableton_mcp_server import server
from ableton_mcp_server.groove_intelligence.apply import apply_artifact
from ableton_mcp_server.groove_intelligence.mcp_models import ApplyRequestV1
from tests.fixtures.groove_apply import (
    bridge_counters,
    commit_request,
    committed_response,
    partial_response,
    runtime_with_capable_bridge,
    runtime_with_real_capability_bridge,
)


def test_apply_request_exposes_bounded_source_selector() -> None:
    request = ApplyRequestV1(
        schema_version="groove.apply.request.v1",
        artifact_id="ga1_" + "a" * 64,
        track_index=0,
        clip_index=0,
        kit_mapping_profile="gm-drums-v1",
        source_track_index=1,
        source_channel=9,
    )
    assert request.source_track_index == 1
    with pytest.raises(ValidationError):
        ApplyRequestV1(
            schema_version="groove.apply.request.v1",
            artifact_id="ga1_" + "a" * 64,
            track_index=0,
            clip_index=0,
            kit_mapping_profile="gm-drums-v1",
            source_track_index=1,
            source_channel=16,
        )


def test_apply_request_requires_selector_pair() -> None:
    with pytest.raises(ValidationError, match="provided together"):
        ApplyRequestV1(
            schema_version="groove.apply.request.v1",
            artifact_id="ga1_" + "a" * 64,
            track_index=0,
            clip_index=0,
            kit_mapping_profile="gm-drums-v1",
            source_track_index=1,
        )


def test_groove_apply_tool_wires_shared_client_for_commit(monkeypatch) -> None:
    runtime = MagicMock()
    bridge_client = MagicMock()
    get_runtime = MagicMock(return_value=runtime)
    get_client = MagicMock(return_value=bridge_client)
    receipt = MagicMock()
    receipt.model_dump.return_value = {
        "schema_version": "groove.apply.receipt.v1",
        "state": "rejected",
    }
    apply_service = MagicMock(return_value=receipt)
    monkeypatch.setattr(server, "get_groove_runtime", get_runtime)
    monkeypatch.setattr(server, "get_client", get_client)
    monkeypatch.setattr(server, "apply_artifact", apply_service)

    server.groove_apply(
        schema_version="groove.apply.request.v1",
        artifact_id="ga1_" + "a" * 64,
        track_index=0,
        clip_index=0,
        kit_mapping_profile="native-compatible",
        mode="commit",
    )

    get_client.assert_called_once_with()
    get_runtime.assert_called_once_with(client=bridge_client)
    apply_service.assert_called_once()


def test_groove_apply_preview_remains_bridge_free(monkeypatch) -> None:
    runtime = MagicMock()
    get_runtime = MagicMock(return_value=runtime)
    get_client = MagicMock()
    receipt = MagicMock()
    receipt.model_dump.return_value = {
        "schema_version": "groove.apply.receipt.v1",
        "state": "preview",
    }
    monkeypatch.setattr(server, "get_groove_runtime", get_runtime)
    monkeypatch.setattr(server, "get_client", get_client)
    monkeypatch.setattr(server, "apply_artifact", MagicMock(return_value=receipt))

    server.groove_apply(
        schema_version="groove.apply.request.v1",
        artifact_id="ga1_" + "a" * 64,
        track_index=0,
        clip_index=0,
        kit_mapping_profile="native-compatible",
        mode="preview",
    )

    get_client.assert_not_called()
    get_runtime.assert_called_once_with(client=None)


def test_preview_is_bridge_free_and_commit_is_single_batch(tmp_path: Path) -> None:
    runtime, bridge, client = runtime_with_real_capability_bridge(
        tmp_path, response=committed_response()
    )
    artifact_id = str(runtime.index.manifest.artifact_ids[0])
    preview = apply_artifact(runtime, make_request(artifact_id, "preview"))
    assert preview.state == "preview" and bridge.dispatch_calls == 0
    committed = apply_artifact(runtime, commit_request(artifact_id))
    assert committed.state == "committed"
    assert bridge.dispatch_calls == 1 and bridge.begin_undo_calls == 1
    assert client.connection_epoch == 7


def test_partial_and_unknown_receipts_are_explicit(tmp_path: Path) -> None:
    runtime = runtime_with_capable_bridge(tmp_path, response=partial_response("clip:3:2"))
    artifact_id = str(runtime.index.manifest.artifact_ids[0])
    partial = apply_artifact(runtime, commit_request(artifact_id))
    assert partial.state == "partial" and partial.clip_ref == "clip:3:2"
    runtime = runtime_with_capable_bridge(tmp_path / "unknown", transport_failure=True)
    artifact_id = str(runtime.index.manifest.artifact_ids[0])
    unknown = apply_artifact(runtime, commit_request(artifact_id))
    assert unknown.state == "unknown" and unknown.recovery_action == "inspect_live_and_do_not_retry"
    assert bridge_counters(runtime)["call_count"] == 1


def test_occupancy_toctou_is_rejected_before_undo(tmp_path: Path) -> None:
    runtime = runtime_with_capable_bridge(tmp_path, occupancy_swap=True)
    artifact_id = str(runtime.index.manifest.artifact_ids[0])
    receipt = apply_artifact(runtime, commit_request(artifact_id))
    counters = bridge_counters(runtime)
    assert receipt.state == "rejected" and receipt.bridge_stage == "precondition"
    assert counters["dispatch_calls"] == 1 and counters["undo_calls"] == 0


def test_apply_rejects_oversized_declared_loop_before_bridge(tmp_path: Path) -> None:
    runtime, bridge, _client = runtime_with_real_capability_bridge(tmp_path)
    artifact_id = str(runtime.index.manifest.artifact_ids[0])
    artifact = runtime.store.get(artifact_id).model_copy(
        update={"timing": {"length_ticks": (100_000 * 480) + 1}}
    )
    runtime.store.put(artifact)

    receipt = apply_artifact(runtime, commit_request(artifact_id))

    assert receipt.state == "rejected"
    assert receipt.error is not None
    assert receipt.error.code == "GROOVE_APPLY_LOOP_LENGTH_LIMIT"
    assert bridge.dispatch_calls == 0


def make_request(artifact_id: str, mode: str) -> ApplyRequestV1:
    return ApplyRequestV1(
        schema_version="groove.apply.request.v1",
        artifact_id=artifact_id,
        track_index=3,
        clip_index=2,
        kit_mapping_profile="gm-drums-v1",
        mode=mode,
    )
