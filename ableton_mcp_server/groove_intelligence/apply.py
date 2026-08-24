"""Guarded artifact-to-clip application with explicit receipts."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any, Literal

from pydantic import Field

from ..client import CapabilitySnapshotV1, Client
from ..errors import (
    BridgeCapabilityRequired,
    BridgeEpochMismatchError,
    BridgeTransportAmbiguousError,
)
from ..protocol import Response
from .canonical import canonical_json
from .mapping import CREATE_CLIP_MAX_LENGTH_BEATS, MappingPlanV1, map_artifact
from .mcp_models import ApplyRequestV1
from .runtime import GrooveRuntime
from .schema import GrooveModel, MidiArtifactV1


class ApplyErrorV1(GrooveModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ApplyReceiptV1(GrooveModel):
    schema_version: Literal["groove.apply.receipt.v1"] = "groove.apply.receipt.v1"
    state: Literal["preview", "rejected", "committed", "partial", "unknown"]
    receipt_id: str | None = None
    artifact_id: str
    bridge_stage: str = "none"
    selected_count: int = 0
    emitted_count: int = 0
    exact_count: int = 0
    fallback_count: int = 0
    unmapped_count: int = 0
    skipped_count: int = 0
    clip_ref: str | None = None
    recovery_action: str | None = None
    error: ApplyErrorV1 | None = None


def _receipt_id(artifact_id: str, state: str, clip_ref: str | None = None) -> str:
    digest = sha256(
        canonical_json({"artifact_id": artifact_id, "state": state, "clip_ref": clip_ref})
    ).hexdigest()
    return f"gar1_{digest}"


def _base(
    plan: MappingPlanV1,
    artifact_id: str,
    *,
    state: Literal["preview", "rejected", "committed", "partial", "unknown"],
    bridge_stage: str = "none",
    error: ApplyErrorV1 | None = None,
    clip_ref: str | None = None,
    recovery_action: str | None = None,
) -> ApplyReceiptV1:
    return ApplyReceiptV1(
        state=state,
        receipt_id=_receipt_id(artifact_id, state, clip_ref)
        if state != "rejected" or error is not None
        else None,
        artifact_id=artifact_id,
        bridge_stage=bridge_stage,
        selected_count=plan.exact_count + plan.fallback_count + plan.unmapped_count,
        emitted_count=len(plan.emitted_events),
        exact_count=plan.exact_count,
        fallback_count=plan.fallback_count,
        unmapped_count=plan.unmapped_count,
        skipped_count=plan.skipped_count,
        clip_ref=clip_ref,
        recovery_action=recovery_action,
        error=error,
    )


def _error_for_plan(plan: MappingPlanV1) -> ApplyErrorV1:
    code = {
        "scope_required": "GROOVE_APPLY_SCOPE_REQUIRED",
        "scope_invalid": "GROOVE_APPLY_SCOPE_INVALID",
        "unsupported_channel": "GROOVE_APPLY_CHANNEL_UNSUPPORTED",
        "rights": "GROOVE_APPLY_RIGHTS_DENIED",
        "note_limit": "GROOVE_APPLY_NOTE_LIMIT",
        "loop_length_limit": "GROOVE_APPLY_LOOP_LENGTH_LIMIT",
        "unmapped": "GROOVE_APPLY_UNMAPPED",
    }
    warning = plan.warning_codes[0] if plan.warning_codes else "mapping_rejected"
    details: dict[str, Any] = {"warning_codes": plan.warning_codes}
    if warning == "loop_length_limit":
        details["max_length_beats"] = CREATE_CLIP_MAX_LENGTH_BEATS
    return ApplyErrorV1(
        code=code.get(warning, "GROOVE_APPLY_MAPPING_REJECTED"),
        message=warning,
        details=details,
    )


def require_fresh_preconditions_capability(client: Client) -> CapabilitySnapshotV1:
    """Require a fresh, exact capability before a mutating batch."""

    contract = client.get_capability_status()
    if contract is None:
        raise BridgeCapabilityRequired()
    snapshot = client.get_capability_snapshot()
    if isinstance(contract, CapabilitySnapshotV1):
        snapshot = contract
    if snapshot is None or snapshot.contract.capabilities.get("run_batch_preconditions") != "v1":
        raise BridgeCapabilityRequired()
    if snapshot.connection_epoch != client.connection_epoch:
        raise BridgeCapabilityRequired("bridge capability belongs to a different connection epoch")
    return snapshot


def _resolve_plan(
    runtime: GrooveRuntime, request: ApplyRequestV1
) -> tuple[MidiArtifactV1, MappingPlanV1]:
    artifact = runtime.store.get(str(request.artifact_id))
    plan = map_artifact(
        artifact,
        request.kit_mapping_profile,
        source_track_index=request.source_track_index,
        source_channel=request.source_channel,
    )
    return artifact, plan


def _note_limit_or_empty(plan: MappingPlanV1, artifact_id: str) -> ApplyReceiptV1 | None:
    if plan.warning_codes and (
        "note_limit" in plan.warning_codes
        or "loop_length_limit" in plan.warning_codes
        or "scope_required" in plan.warning_codes
    ):
        return _base(plan, artifact_id, state="rejected", error=_error_for_plan(plan))
    if not plan.emitted_events:
        return _base(
            plan,
            artifact_id,
            state="rejected",
            error=ApplyErrorV1(
                code="GROOVE_APPLY_NO_NOTES", message="artifact has no applicable note events"
            ),
        )
    if not plan.allowed:
        return _base(plan, artifact_id, state="rejected", error=_error_for_plan(plan))
    return None


def _extract_result(
    result: Any,
) -> tuple[Mapping[str, Any] | None, str | None, Mapping[str, Any] | None]:
    if hasattr(result, "value") and hasattr(result, "epoch_used"):
        result = result.value
    if isinstance(result, Response):
        return None, result.code, result.details
    if isinstance(result, Mapping):
        return result, None, None
    return None, None, None


def _receipt_from_bridge(result: Any, plan: MappingPlanV1, artifact_id: str) -> ApplyReceiptV1:
    payload, code, details = _extract_result(result)
    if code is not None:
        stage = str(
            (details or {}).get(
                "bridge_stage", "precondition" if code.startswith("PRECONDITION") else "batch"
            )
        )
        state: Literal["rejected", "unknown"] = "rejected"
        return _base(
            plan,
            artifact_id,
            state=state,
            bridge_stage=stage,
            error=ApplyErrorV1(
                code=code,
                message=str((details or {}).get("message", code)),
                details=dict(details or {}),
            ),
        )
    if payload is None:
        return _base(
            plan,
            artifact_id,
            state="rejected",
            error=ApplyErrorV1(
                code="GROOVE_APPLY_BAD_RESPONSE", message="bridge response is not an object"
            ),
        )
    state_value = str(payload.get("state", ""))
    clip_ref = payload.get("clip_ref")
    if not isinstance(clip_ref, str):
        clip_ref = None
    if (
        state_value == "partial"
        or payload.get("aborted_at") == 1
        or (
            isinstance(payload.get("results"), list)
            and len(payload["results"]) >= 2
            and payload["results"][0].get("status") == "ok"
            and payload["results"][1].get("status") == "error"
        )
    ):
        if clip_ref is None and isinstance(payload.get("results"), list):
            first = payload["results"][0] if payload["results"] else {}
            if isinstance(first, Mapping) and isinstance(first.get("result"), Mapping):
                candidate = first["result"].get("clip_ref")
                clip_ref = candidate if isinstance(candidate, str) else None
        return _base(
            plan,
            artifact_id,
            state="partial",
            bridge_stage="batch",
            clip_ref=clip_ref,
            recovery_action="inspect_clip_and_remove_or_complete_notes",
        )
    if state_value == "rejected" or payload.get("code", "").startswith("PRECONDITION"):
        error_code = str(payload.get("code", "PRECONDITION_FAILED"))
        return _base(
            plan,
            artifact_id,
            state="rejected",
            bridge_stage=str(payload.get("bridge_stage", "precondition")),
            error=ApplyErrorV1(
                code=error_code,
                message=str(payload.get("message", "bridge rejected precondition")),
                details=dict(payload),
            ),
        )
    return _base(plan, artifact_id, state="committed", bridge_stage="batch", clip_ref=clip_ref)


def apply_artifact(runtime: GrooveRuntime, request: ApplyRequestV1) -> ApplyReceiptV1:
    try:
        artifact, plan = _resolve_plan(runtime, request)
    except KeyError:
        plan = MappingPlanV1(profile_id=request.kit_mapping_profile, allowed=False)
        return _base(
            plan,
            str(request.artifact_id),
            state="rejected",
            error=ApplyErrorV1(
                code="GROOVE_ARTIFACT_NOT_FOUND", message="artifact is not available"
            ),
        )
    early = _note_limit_or_empty(plan, str(artifact.artifact_id))
    if early is not None:
        return early
    if not request.expected_empty_slot:
        return _base(
            plan,
            str(artifact.artifact_id),
            state="rejected",
            error=ApplyErrorV1(
                code="GROOVE_APPLY_EMPTY_SLOT_REQUIRED", message="expected_empty_slot must be true"
            ),
        )
    if request.mode == "preview":
        return _base(plan, str(artifact.artifact_id), state="preview")
    if runtime.client is None:
        return _base(
            plan,
            str(artifact.artifact_id),
            state="rejected",
            bridge_stage="capability",
            error=ApplyErrorV1(
                code="GROOVE_PRECONDITION_UNSUPPORTED", message="bridge client is unavailable"
            ),
        )
    try:
        snapshot = require_fresh_preconditions_capability(runtime.client)
    except BridgeCapabilityRequired as error:
        return _base(
            plan,
            str(artifact.artifact_id),
            state="rejected",
            bridge_stage="capability",
            error=ApplyErrorV1(code=error.code, message=str(error)),
        )
    batch = {
        "preconditions": [
            {
                "type": "slot_empty",
                "version": "v1",
                "params": {"track_index": request.track_index, "clip_index": request.clip_index},
            }
        ],
        "commands": [
            {
                "type": "create_clip",
                "params": {
                    "track_index": request.track_index,
                    "clip_index": request.clip_index,
                    "length_beats": max(plan.length_beats, 1.0 / artifact.format.ppq),
                },
            },
            {
                "type": "add_notes_to_clip",
                "params": {
                    "track_index": request.track_index,
                    "clip_index": request.clip_index,
                    "notes": [
                        event.note.model_dump(exclude_none=True) for event in plan.emitted_events
                    ],
                },
            },
        ],
    }
    try:
        result = runtime.client.call_at_epoch(snapshot.connection_epoch, "run_batch", batch)
    except BridgeTransportAmbiguousError:
        return _base(
            plan,
            str(artifact.artifact_id),
            state="unknown",
            bridge_stage="transport_after_send",
            recovery_action="inspect_live_and_do_not_retry",
        )
    except BridgeEpochMismatchError as error:
        return _base(
            plan,
            str(artifact.artifact_id),
            state="rejected",
            bridge_stage="epoch",
            error=ApplyErrorV1(code=error.code, message=str(error)),
        )
    return _receipt_from_bridge(result, plan, str(artifact.artifact_id))


__all__ = [
    "ApplyErrorV1",
    "ApplyReceiptV1",
    "apply_artifact",
    "require_fresh_preconditions_capability",
]
