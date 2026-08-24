# Drum Groove Intelligence Phase 3 — Live Apply and Epoch-Bound Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add late kit mapping and the guarded `groove_apply` tool while extending the existing TCP bridge with exact capability negotiation, connection epochs, atomic `call_at_epoch`, and backward-compatible `run_batch.preconditions`.

**Architecture:** The Remote Script remains the authority for Live state, undo, and precondition evaluation. The Python client owns a lock-protected monotonic TCP epoch, immutable connection snapshot, capability cache keyed by `(host, port, epoch)`, and an epoch-bound call that holds the lock through serialization/send/read/decode. `apply.py` performs local rights/scope/mapping/limit validation, negotiates `bridge.contract.v1`, and sends exactly one guarded batch; receipts preserve `committed`, `partial`, `rejected`, and `unknown` without retry or readback.

**Tech Stack:** Existing Python TCP JSONL bridge, Pydantic v2, FastMCP, Remote Script vendored contracts, pytest. No UI automation, no new transport, and no changes to the WebSocket bridge.

**Spec:** `docs/superpowers/specs/2026-08-20-drum-groove-intelligence-design.md` at `0ea5b3712b32650e861b6e0380860e8133c2e388`.

## Global Constraints

- `groove_apply` is the only new bridge tool; the four phase-2 local tools remain offline.
- Mapping is late; source `original_pitch`/`original_channel` and parent `artifact_id` remain intact. `gm-drums-v1` is allowed only for zero-based channel 9; `native-compatible` accepts the selected source channel and preserves pitch identity.
- `on_unmapped="reject"` is default and fails before Live; `skip` omits unmapped events and reports counts. No silent pitch substitution.
- One apply call selects one track/channel and at most 2,048 events; PPQ conversion is exact rational/half-even to nine decimals; no chunking.
- `commit` requires explicit target and `expected_empty_slot=true`, exact capability `bridge.contract.v1`, one `slot_empty` precondition, one `run_batch`, one undo group, and no retry.
- `preconditions` is optional for legacy batches and defaults to `[]`; unsupported/extra/duplicate preconditions reject before undo on a capable bridge.
- `call_at_epoch` rejects disconnected/mismatched epoch with zero bytes; post-send transport ambiguity becomes `unknown` and never reconnects or retries.
- A bridge response received with `epoch_used=E` remains `committed` or `rejected` even if another thread closes the socket afterward.
- Acceptance uses disposable Set/empty slot only for guarded commit; no real Live or UI is controlled by automated tests.
- At execution time the worker records worktree choice, preserves concurrent edits, and stages only its listed paths.

### Task 1: Backward-compatible preconditions and Remote Script admission guard

**Files:**
- Modify: `ableton_mcp_server/models.py`
- Modify: `contracts.py`
- Modify: `AbletonMCPServer_RemoteScript/__init__.py`
- Regenerate: `AbletonMCPServer_RemoteScript/_contracts.py` via `.\.venv-win\Scripts\python.exe scripts/vendor_contracts.py`
- Modify: `tests/test_models.py`
- Create: `tests/test_groove_preconditions.py`
- Create: `tests/test_remote_preconditions.py`
- Create: `tests/fixtures/groove_bridge.py`
- Modify: `tests/test_vendoring.py`

**Interfaces:**
- Produces `PreconditionSpec(type="slot_empty", version="v1", params={"track_index": int, "clip_index": int})`, `RunBatchRequest(commands, preconditions=[])`, `BridgeContractV1(schema_version="bridge.contract.v1", owner="AbletonMCPServer_RemoteScript", protocol_version="bridge.v1", capabilities={"run_batch_preconditions": "v1"})` exposed only by `get_session_info`, and Remote Script dispatcher functions `_validate_preconditions`, `_evaluate_preconditions`, and `_admit_batch`.

- [ ] **Step 1: Write the failing tests**

```python
def test_run_batch_defaults_preconditions_to_empty_and_rejects_unknown_fields() -> None:
    assert RunBatchRequest(commands=[{"type": "set_tempo", "params": {}}]).preconditions == []
    with pytest.raises(ValidationError):
        RunBatchRequest(commands=[{"type": "set_tempo", "params": {}}], preconditions=[{"type": "slot_empty", "version": "v1", "params": {"track_index": 0, "clip_index": 0}, "extra": 1}])

@pytest.mark.parametrize("preconditions", [
    [{"type": "unknown", "version": "v1", "params": {"track_index": 0, "clip_index": 0}}],
    [{"type": "slot_empty", "version": "v1", "params": {"track_index": 0, "clip_index": 0}}, {"type": "slot_empty", "version": "v1", "params": {"track_index": 0, "clip_index": 0}}],
])
def test_new_bridge_rejects_malformed_preconditions_before_undo(preconditions: list[dict[str, object]]) -> None:
    bridge = NewBridgeFixture(capabilities={"run_batch_preconditions": "v1"})
    response = bridge.dispatch({"type": "run_batch", "commands": [{"type": "set_tempo", "params": {"bpm": 120}}], "preconditions": preconditions})
    assert response["code"] == "PRECONDITION_INVALID" and bridge.sent_bytes == 0 and bridge.begin_undo_calls == 0 and bridge.command_calls == []

def test_bridge_admission_rejects_preconditions_before_undo() -> None:
    bridge = NewBridgeFixture(capabilities=None)
    response = bridge.dispatch({"type": "run_batch", "commands": [{"type": "set_tempo", "params": {"bpm": 120}}], "preconditions": [{"type": "slot_empty", "version": "v1", "params": {"track_index": 0, "clip_index": 0}}]})
    assert response["code"] == "PRECONDITION_UNSUPPORTED"
    assert bridge.begin_undo_calls == 0 and bridge.command_calls == []
    assert bridge.sent_bytes == 0 and bridge.dispatch_calls == 1

def test_all_preconditions_are_validated_and_evaluated_before_undo() -> None:
    bridge = NewBridgeFixture(capabilities={"run_batch_preconditions": "v1"}, occupied={(0, 0)})
    response = bridge.dispatch({"type": "run_batch", "commands": [{"type": "create_clip", "params": {"track_index": 0, "clip_index": 0}}], "preconditions": [{"type": "slot_empty", "version": "v1", "params": {"track_index": 0, "clip_index": 0}}]})
    assert response["code"] == "PRECONDITION_FAILED" and response["details"]["bridge_stage"] == "precondition"
    assert bridge.begin_undo_calls == 0 and bridge.command_calls == []

def test_all_preconditions_report_first_failure_without_short_circuiting() -> None:
    bridge = NewBridgeFixture(capabilities={"run_batch_preconditions": "v1"}, occupied={(0, 0), (1, 1)})
    response = bridge.dispatch({"type": "run_batch", "commands": [{"type": "set_tempo", "params": {"bpm": 120}}], "preconditions": [
        {"type": "slot_empty", "version": "v1", "params": {"track_index": 0, "clip_index": 0}},
        {"type": "slot_empty", "version": "v1", "params": {"track_index": 1, "clip_index": 1}},
    ]})
    assert response["details"]["failed_index"] == 0
    assert bridge.precondition_evaluations == [(0, 0), (1, 1)] and bridge.begin_undo_calls == 0
```

`tests/fixtures/groove_bridge.py` must provide `NewBridgeFixture(capabilities: dict[str, str] | None, occupied: set[tuple[int, int]] | None = None, session_info: dict[str, object] | None = None)`, normalizing `None` to a new set per instance, with counters `begin_undo_calls`, `command_calls`, `sent_bytes`, `dispatch_calls`, and `session_info_calls`; its `get_session_info()` returns the session response containing `bridge_contract`, while its `dispatch` accepts only `run_batch` fields `commands` and `preconditions` (never a `bridge_contract` field), applies the same admission/validation/evaluation order as the Remote Script, and then records commands. It also provides `connected_client(epoch: int, response: bytes | None = None, session_info: dict[str, object] | None = None) -> tuple[Client, FakeSocket]`, `connected_client_object() -> Client`, `capable_status(epoch: int = 1) -> dict[str, object]`, and `precondition_failed_response() -> bytes`, so all epoch/diagnostics/admission tests use deterministic in-memory sockets and never open a real port.

```python
@dataclass
class NewBridgeFixture:
    capabilities: dict[str, str] | None
    occupied: set[tuple[int, int]] | None = None
    session_info: dict[str, object] | None = None
    begin_undo_calls: int = 0
    command_calls: list[dict[str, object]] = field(default_factory=list)
    sent_bytes: int = 0
    dispatch_calls: int = 0
    session_info_calls: int = 0
    precondition_evaluations: list[tuple[int, int]] = field(default_factory=list)
    last_preconditions: list[dict[str, object]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.occupied = set(self.occupied or ())
        self.session_info = self.session_info or self.capable_status()

    def get_session_info(self) -> dict[str, object]:
        self.session_info_calls += 1
        return dict(self.session_info or {})

    def dispatch(self, request: dict[str, object]) -> dict[str, object]:
        self.dispatch_calls += 1
        assert set(request) == {"type", "commands", "preconditions"}
        self.last_preconditions = list(request["preconditions"])
        return dispatch_run_batch_with_admission(self, request)

def connected_client(epoch: int, response: bytes | None = None, session_info: dict[str, object] | None = None) -> tuple[Client, FakeSocket]:
    fake = FakeSocket(response=response, session_info=session_info, epoch=epoch)
    return Client.from_test_socket(fake, epoch=epoch), fake
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_preconditions.py tests/test_remote_preconditions.py`
Expected: FAIL because `RunBatchRequest` has no `preconditions`, no bridge contract, and the dispatcher ignores the field.

- [ ] **Step 3: Write minimal implementation**

Add bounded `PreconditionSpec` with max 16 items, exact `slot_empty/v1`, non-negative session-bounded indices, no duplicates, and `extra="forbid"`. In the Remote Script, perform admission before `_begin_undo`, validate every item without short-circuiting, evaluate every item on the Live dispatcher, return first failing index/details with `bridge_stage="precondition"`, and only then begin undo. Add optional exact `bridge_contract` to `get_session_info`; preserve all existing top-level bridge-status fields. The `run_batch` request schema remains exactly `commands` plus optional `preconditions`; it never accepts or validates a `bridge_contract` field. Regenerate `_contracts.py` and run the vendoring check.

```python
class PreconditionSpec(RequestModel):
    type: Literal["slot_empty"]
    version: Literal["v1"]
    params: SlotEmptyParams

class RunBatchRequest(RequestModel):
    commands: Annotated[list[CommandSpec], Field(min_length=1, max_length=100)]
    preconditions: Annotated[list[PreconditionSpec], Field(max_length=16)] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_precondition_uniqueness(self) -> RunBatchRequest:
        keys = [(item.type, item.version, item.params.track_index, item.params.clip_index) for item in self.preconditions]
        if len(keys) != len(set(keys)):
            raise ValueError("preconditions must not contain duplicates")
        return self
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_preconditions.py tests/test_remote_preconditions.py tests/test_models.py tests/test_vendoring.py`
Expected: PASS; legacy batches remain unchanged, unsupported fields reject before undo, capable preconditions protect the slot, and vendored contracts match.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/models.py contracts.py AbletonMCPServer_RemoteScript/__init__.py AbletonMCPServer_RemoteScript/_contracts.py tests/test_models.py tests/test_groove_preconditions.py tests/test_remote_preconditions.py tests/test_vendoring.py
git commit -m "feat: add guarded run batch preconditions"
```

### Task 2: Epoch-safe client, capability cache, and diagnostics contract validation

**Files:**
- Modify: `ableton_mcp_server/errors.py`
- Modify: `ableton_mcp_server/client.py`
- Modify: `ableton_mcp_server/diagnostics.py`
- Modify: `tests/test_client.py`
- Create: `tests/test_client_epoch.py`
- Modify: `tests/test_diagnostics.py`
- Modify: `tests/test_capability_matrix.py`

**Interfaces:**
- Produces `CapabilitySnapshotV1(host: str, port: int, connection_epoch: int, contract: BridgeContractV1, fetched_at: float, freshness: Literal["fresh", "stale"])`, `ConnectionSnapshot(host: str, port: int, connected: bool, connection_epoch: int)`, `AtEpochCallResultV1[T](value: T, receipt: ApplyReceiptV1 | None, epoch_used: int, transport_state: Literal["received"])`, `BridgeEpochMismatchError(reason: Literal["disconnected", "epoch_mismatch"], bytes_sent=0)`, `BridgePreSendError(bytes_sent=0)`, `BridgeTransportAmbiguousError(outcome="unknown", transmission="possible", bytes_sent="unknown")`, `Client.connection_snapshot`, `Client.connection_epoch`, `Client.cache_capability_snapshot(snapshot: CapabilitySnapshotV1) -> None`, `Client.get_capability_snapshot(now: float | None = None) -> CapabilitySnapshotV1 | None`, `Client.capability_for_epoch(expected_epoch: int, now: float | None = None) -> CapabilitySnapshotV1`, `Client.get_capability_status(now: float | None = None) -> BridgeContractV1 | None`, and `Client.call_at_epoch(expected_epoch: int, action: str, params: Mapping[str, Any] | None = None, *, timeout: float | None = None) -> AtEpochCallResultV1[Any]`. `Client.get_capability_status` must fetch `get_session_info` through the real client, pass the response through `diagnostics.bridge_status`, and return no capability on malformed owner/schema/protocol; the apply admission then raises `BridgeCapabilityRequired`. The fixture's malformed-capability test must use this path, never put `bridge_contract` into a `run_batch` request. Count tests import `Route` and `Risk` from `ableton_mcp_server.catalog` plus canonical contract sets from `contracts.py`.

- [ ] **Step 1: Write the failing tests**

```python
from ableton_mcp_server import diagnostics
from ableton_mcp_server.errors import BridgeCapabilityRequired
from ableton_mcp_server.groove_intelligence.apply import require_fresh_preconditions_capability

def test_call_at_epoch_holds_lock_and_rejects_epoch_mismatch_before_send() -> None:
    client, fake_socket = connected_client(epoch=4)
    with pytest.raises(BridgeEpochMismatchError) as error:
        client.call_at_epoch(3, "run_batch", {"commands": []})
    assert error.value.reason == "epoch_mismatch" and error.value.bytes_sent == 0 and fake_socket.sent == []

def test_possible_send_failure_closes_and_becomes_unknown_without_retry() -> None:
    client, fake_socket = connected_client(epoch=4)
    fake_socket.raise_after_send = True
    with pytest.raises(BridgeTransportAmbiguousError):
        client.call_at_epoch(4, "run_batch", {"commands": []})
    assert client.connection_epoch == 5 and fake_socket.send_calls == 1

def test_pre_send_serialization_failure_is_distinct_and_zero_byte() -> None:
    client, fake_socket = connected_client(epoch=4)
    with pytest.raises(BridgePreSendError) as error:
        client.call_at_epoch(4, "run_batch", {"commands": [object()]})
    assert error.value.bytes_sent == 0 and fake_socket.sent == [] and client.connection_epoch == 4

def test_received_business_rejection_keeps_epoch_after_concurrent_close() -> None:
    client, fake_socket = connected_client(epoch=8, response=precondition_failed_response())
    result = client.call_at_epoch(8, "run_batch", {"commands": []})
    client.close()
    assert result.epoch_used == 8 and result.receipt.state == "rejected"

def test_legacy_run_batch_without_preconditions_remains_backward_compatible() -> None:
    bridge = NewBridgeFixture(capabilities=None)
    response = bridge.dispatch({"type": "run_batch", "commands": [{"type": "set_tempo", "params": {"bpm": 120}}]})
    assert response["code"] == "OK" and bridge.begin_undo_calls == 1 and bridge.command_calls

def test_capability_cache_is_epoch_keyed_and_stale_never_authorizes_apply() -> None:
    client = connected_client_object()
    client.cache_capability_snapshot(CapabilitySnapshotV1(host="127.0.0.1", port=9877, connection_epoch=1, contract=BridgeContractV1.model_validate(capable_status()["bridge_contract"]), fetched_at=100.0, freshness="fresh"))
    client.close()
    assert client.get_capability_snapshot(now=101.0) is None

def test_capable_disconnect_reconnect_same_endpoint_invalidates_epoch_snapshot() -> None:
    client, fake_socket = connected_client(epoch=4)
    client.cache_capability_snapshot(CapabilitySnapshotV1(host="127.0.0.1", port=9877, connection_epoch=4, contract=BridgeContractV1.model_validate(capable_status(4)["bridge_contract"]), fetched_at=100.0, freshness="fresh"))
    client.close()
    fake_socket.reconnect(epoch=5)
    assert client.get_capability_snapshot(now=101.0) is None

@pytest.mark.parametrize("field,value", [("owner", "Other"), ("schema_version", "bridge.contract.v0"), ("protocol_version", "bridge.v0")])
def test_malformed_session_capability_traverses_get_session_info_bridge_status_and_admission(field: str, value: str) -> None:
    fixture = NewBridgeFixture(capabilities={"run_batch_preconditions": "v1"})
    session = fixture.capable_status().copy()
    contract = dict(session["bridge_contract"])
    contract[field] = value
    session["bridge_contract"] = contract
    client, fake_socket = connected_client(epoch=1, session_info=session)
    status = diagnostics.bridge_status(client)
    assert status["bridge_available"] is False and status["error"]["code"] == "CAPABILITY_INVALID"
    with pytest.raises(BridgeCapabilityRequired):
        require_fresh_preconditions_capability(client)
    assert fake_socket.session_info_calls >= 1 and fake_socket.sent == []

```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_client_epoch.py`
Expected: FAIL because `connection_epoch`, typed errors, `call_at_epoch`, and capability cache do not exist.

- [ ] **Step 3: Write minimal implementation**

Use the existing `_lock` for every lifecycle transition. Start epoch at `0`; increment under lock after successful connect and whenever an existing socket is discarded by close/timeout/read error/reconnect; idempotent close with no socket does not increment. `call_at_epoch` must not call `call`, validates connected/socket/epoch before encoding, holds the lock through send/read/decode, returns `AtEpochCallResultV1` for both success and business error envelopes, raises pre-send errors with zero bytes, and closes/increments/raises ambiguous transport errors after possible send without reconnect. Cache status by host/port/epoch with monotonic TTL 5 s; reject stale/endpoint/epoch changes. `diagnostics.bridge_status` validates exact `bridge_contract` owner/schema/protocol/capability and copies it top-level without changing legacy fields. Replace every current-total assertion in `tests/test_capability_matrix.py` and `tests/test_diagnostics.py` with `len(TOOL_CATALOG)`, `sum(spec.route is Route.LOCAL for spec in TOOL_CATALOG)`, `len(READ_COMMANDS | ALLOWED_MUTATIONS)`, `len(WEBSOCKET_TARGET_COMMANDS)`, `len(READ_ONLY_COMMANDS)`, and `sum(spec.risk is Risk.UNAVAILABLE for spec in TOOL_CATALOG)` as applicable. Keep only stable contract-set invariants; do not encode 91, 82, 73, 5, or any future public total.

```python
def call_at_epoch(self, expected_epoch: int, action: str, params: Mapping[str, Any] | None = None, *, timeout: float | None = None) -> AtEpochCallResultV1[Any]:
    with self._lock:
        if not self._connected or self._socket is None:
            raise BridgeEpochMismatchError("disconnected", bytes_sent=0)
        if self._connection_epoch != expected_epoch:
            raise BridgeEpochMismatchError("epoch_mismatch", bytes_sent=0)
        try:
            encoded = encode_request(action, dict(params or {}))
        except (TypeError, ValueError, ProtocolError) as error:
            raise BridgePreSendError(bytes_sent=0) from error
        try:
            self._socket.sendall(encoded)
            response = decode_response(self._read_line(timeout or request_timeout_seconds(action, dict(params or {}))))
        except (TimeoutError, ConnectionError, OSError, ProtocolError) as error:
            self._close_locked(increment=True)
            raise BridgeTransportAmbiguousError("transport state is unknown after send") from error
        if response.status == "ok":
            return AtEpochCallResultV1(value=response.result, receipt=extract_receipt(response.result), epoch_used=self._connection_epoch, transport_state="received")
        return AtEpochCallResultV1(value=response, receipt=extract_receipt(response), epoch_used=self._connection_epoch, transport_state="received")
```

```python
def test_capability_counts_are_catalog_and_contract_derived() -> None:
    result = _status()
    counts = result["capability_counts"]
    assert counts["public_tools"] == len(TOOL_CATALOG)
    assert counts["live_required_tools"] == len(TOOL_CATALOG) - sum(spec.route is Route.LOCAL for spec in TOOL_CATALOG)
    assert counts["routed_commands"] == len(READ_COMMANDS | ALLOWED_MUTATIONS)
    assert counts["websocket_targets"] == len(WEBSOCKET_TARGET_COMMANDS)
    assert counts["read_only_blocked"] == len(READ_ONLY_COMMANDS)
    assert counts["capability_unavailable"] == sum(spec.risk is Risk.UNAVAILABLE for spec in TOOL_CATALOG)

def test_broken_bridge_still_reports_catalog_derived_tool_count() -> None:
    result = bridge_status(_BrokenClient(), tool_count=0)
    assert len(result["tools"]) == len(TOOL_CATALOG)
    assert result["capability_counts"]["public_tools"] == len(TOOL_CATALOG)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_client_epoch.py tests/test_client.py tests/test_diagnostics.py tests/test_capability_matrix.py`
Expected: PASS with zero-byte epoch/pre-send guards, no retry after possible send, epoch-stable received results, cache invalidation, exact contract validation, and unchanged legacy diagnostics fields.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/errors.py ableton_mcp_server/client.py ableton_mcp_server/diagnostics.py tests/test_client.py tests/test_client_epoch.py tests/test_diagnostics.py tests/test_capability_matrix.py
git commit -m "feat: bind bridge calls and capabilities to connection epochs"
```

### Task 3: Late mapping, apply receipts, and the `groove_apply` MCP wrapper

**Files:**
- Create: `ableton_mcp_server/groove_intelligence/mapping.py`
- Create: `ableton_mcp_server/groove_intelligence/apply.py`
- Create: `tests/fixtures/groove_apply.py`
- Modify: `ableton_mcp_server/groove_intelligence/mcp_models.py`
- Modify: `ableton_mcp_server/models.py`
- Modify: `ableton_mcp_server/catalog.py`
- Modify: `ableton_mcp_server/server.py`
- Create: `tests/test_groove_mapping.py`
- Create: `tests/test_groove_apply.py`

**Interfaces:**
- Consumes phase-2 `GrooveRuntime`, `MidiArtifactV1`, `Client.call_at_epoch`, exact bridge capability status, and `NoteSpec`.
- Produces `KitMappingProfileV1`, `CanonicalApplyEventV1(source_event_id: int, source_track_index: int, source_channel: int, note: NoteSpec)`, `MappingPlanV1(selected_track_index: int | None, selected_channel: int | None, emitted_events: tuple[CanonicalApplyEventV1, ...])`, `ApplyRequestV1`, `ApplyReceiptV1`, `GROOVE_REQUEST_MODEL_BY_TOOL["groove_apply"]`, `map_artifact(artifact: MidiArtifactV1, profile_id: str, *, on_unmapped: Literal["reject", "skip"] = "reject", source_track_index: int | None = None, source_channel: int | None = None) -> MappingPlanV1`, `require_fresh_preconditions_capability(client: Client) -> CapabilitySnapshotV1`, `apply_artifact(runtime: GrooveRuntime, request: ApplyRequestV1) -> ApplyReceiptV1`, and `server.groove_apply` with `schema_version="groove.apply.request.v1"`. `ApplyRequestV1` and the wrapper expose optional `source_track_index: int | None = None` and `source_channel: int | None = None`; they are jointly required when the artifact has multiple tracks or channels and select exactly one source track/channel. `require_fresh_preconditions_capability` is the bridge admission/precondition dispatcher: it raises `BridgeCapabilityRequired` for a missing exact capability before any call, while `call_at_epoch` remains transport-epoch-only. The fixture module owns exact factories `make_drum_artifact(note_count: int = 2, *, track_count: int = 1, channels: tuple[int, ...] = (9,)) -> MidiArtifactV1`, `make_apply_request(artifact_id: str, *, mode: Literal["preview", "commit"] = "preview", expected_empty_slot: bool = True, source_track_index: int | None = None, source_channel: int | None = None) -> ApplyRequestV1`, `runtime_with_artifact(tmp_path: Path, note_count: int = 2, *, track_count: int = 1, channels: tuple[int, ...] = (9,)) -> GrooveRuntime`, `runtime_with_capable_bridge(tmp_path: Path, response: bytes = OK_RESPONSE, *, candidate_response: bytes | None = None, occupancy_swap: bool = False, transport_failure: bool = False) -> GrooveRuntime`, `runtime_with_real_capability_bridge(tmp_path: Path, *, epoch: int = 7, response: bytes = OK_RESPONSE) -> tuple[GrooveRuntime, NewBridgeFixture, Client]`, `commit_request(artifact_id: str, *, source_track_index: int | None = None, source_channel: int | None = None) -> ApplyRequestV1`, `committed_response() -> bytes`, `partial_response(clip_ref: str) -> bytes`, `swap_client_socket(runtime: GrooveRuntime, epoch: int) -> None`, and `bridge_counters(runtime: GrooveRuntime) -> Mapping[str, int]`; tests import factories and never use module-level `DRUM_ARTIFACT`, `COMMIT_REQUEST`, or runtime singletons.


- [ ] **Step 1: Write the failing tests**

```python
def test_mapping_preserves_original_pitch_and_reports_unmapped_reject() -> None:
    plan = map_artifact(make_drum_artifact(), "gm-drums-v1", on_unmapped="reject")
    assert plan.events[0].original_pitch == 49 and plan.events[0].resolved_pitch == 46
    assert plan.exact_count == 1 and plan.unmapped_count == 1
    assert plan.allowed is False and plan.warning_codes == ["unmapped"]

def test_preview_never_calls_bridge_and_rejects_2049_notes(tmp_path: Path) -> None:
    runtime = runtime_with_artifact(tmp_path, note_count=2049)
    result = apply_artifact(runtime, make_apply_request(runtime.index.manifest.artifact_ids[0], mode="preview"))
    assert result.state == "rejected" and result.bridge_stage == "none"
    runtime.client.call_at_epoch.assert_not_called()

def test_multitrack_source_selection_is_required_and_selects_one_track_channel(tmp_path: Path) -> None:
    runtime = runtime_with_artifact(tmp_path, track_count=2, channels=(9, 10))
    artifact_id = runtime.index.manifest.artifact_ids[0]
    missing = apply_artifact(runtime, make_apply_request(artifact_id, mode="preview"))
    assert missing.state == "rejected" and missing.error.code == "GROOVE_APPLY_SCOPE_REQUIRED"
    artifact = runtime.store.get(artifact_id)
    plan = map_artifact(artifact, "gm-drums-v1", source_track_index=1, source_channel=9)
    assert plan.selected_track_index == 1 and plan.selected_channel == 9
    selected_ids = {event.event_id for event in artifact.events if event.track_index == 1 and event.channel == 9}
    assert selected_ids
    assert all(event.source_event_id in selected_ids for event in plan.emitted_events)
    assert all(event.source_track_index == 1 and event.source_channel == 9 for event in plan.emitted_events)
    assert [event.note for event in plan.emitted_events] == list(plan.notes)
    selected = apply_artifact(runtime, make_apply_request(artifact_id, mode="preview", source_track_index=1, source_channel=9))
    assert selected.state == "preview"

def test_source_track_and_channel_must_be_provided_together(tmp_path: Path) -> None:
    runtime = runtime_with_artifact(tmp_path, track_count=2, channels=(9, 10))
    artifact_id = runtime.index.manifest.artifact_ids[0]
    with pytest.raises(ValidationError, match="source_track_index.*source_channel|source_channel.*source_track_index"):
        make_apply_request(artifact_id, mode="preview", source_track_index=1)

def test_apply_admission_rejects_missing_capability_before_call_at_epoch(tmp_path: Path) -> None:
    runtime = runtime_with_capable_bridge(tmp_path)
    runtime.client.get_capability_status.return_value = None
    with pytest.raises(BridgeCapabilityRequired):
        require_fresh_preconditions_capability(runtime.client)
    counters = bridge_counters(runtime)
    assert counters["sent_bytes"] == 0 and counters["dispatch_calls"] == 0 and counters["undo_calls"] == 0

def test_commit_sends_one_preconditioned_batch_and_preserves_partial_and_unknown(tmp_path: Path) -> None:
    runtime = runtime_with_capable_bridge(tmp_path)
    receipt = apply_artifact(runtime, commit_request(runtime.index.manifest.artifact_ids[0]))
    call = runtime.client.call_at_epoch.call_args
    assert call.args[1] == "run_batch"
    assert call.args[2]["preconditions"] == [{"type": "slot_empty", "version": "v1", "params": {"track_index": 3, "clip_index": 2}}]
    assert [item["type"] for item in call.args[2]["commands"]] == ["create_clip", "add_notes_to_clip"]
    assert runtime.client.call_at_epoch.call_count == 1

def test_commit_toctou_socket_swap_is_rejected_before_send_and_preserves_receipt(tmp_path: Path) -> None:
    runtime = runtime_with_capable_bridge(tmp_path)
    old_epoch = runtime.client.connection_epoch
    swap_client_socket(runtime, old_epoch + 1)
    receipt = apply_artifact(runtime, commit_request(runtime.index.manifest.artifact_ids[0]))
    assert receipt.state == "rejected" and receipt.bridge_stage == "epoch"
    counters = bridge_counters(runtime)
    assert counters["sent_bytes"] == 0 and counters["dispatch_calls"] == 0 and counters["undo_calls"] == 0

def test_close_after_received_receipt_keeps_committed_state(tmp_path: Path) -> None:
    runtime = runtime_with_capable_bridge(tmp_path, response=committed_response())
    receipt = apply_artifact(runtime, commit_request(runtime.index.manifest.artifact_ids[0]))
    runtime.client.close()
    assert receipt.state == "committed" and receipt.receipt_id is not None

def test_occupancy_toctou_is_rejected_by_bridge_without_undo(tmp_path: Path) -> None:
    runtime = runtime_with_capable_bridge(tmp_path, occupancy_swap=True)
    receipt = apply_artifact(runtime, commit_request(runtime.index.manifest.artifact_ids[0]))
    counters = bridge_counters(runtime)
    assert receipt.state == "rejected" and receipt.bridge_stage == "precondition"
    assert counters["sent_bytes"] > 0 and counters["dispatch_calls"] == 1 and counters["undo_calls"] == 0

def test_create_success_add_failure_is_partial_with_clip_ref_and_recovery(tmp_path: Path) -> None:
    runtime = runtime_with_capable_bridge(tmp_path, response=partial_response("clip:3:2"))
    receipt = apply_artifact(runtime, commit_request(runtime.index.manifest.artifact_ids[0]))
    counters = bridge_counters(runtime)
    assert receipt.state == "partial" and receipt.clip_ref == "clip:3:2"
    assert receipt.recovery_action == "inspect_clip_and_remove_or_complete_notes"
    assert counters["sent_bytes"] > 0 and counters["dispatch_calls"] == 1 and counters["undo_calls"] == 1

def test_post_send_unknown_preserves_counts_clip_ref_and_recovery_without_retry(tmp_path: Path) -> None:
    runtime = runtime_with_capable_bridge(tmp_path, transport_failure=True)
    receipt = apply_artifact(runtime, commit_request(runtime.index.manifest.artifact_ids[0]))
    counters = bridge_counters(runtime)
    assert receipt.state == "unknown" and receipt.clip_ref is None
    assert receipt.recovery_action == "inspect_live_and_do_not_retry"
    assert counters["sent_bytes"] > 0 and counters["dispatch_calls"] == 1 and counters["undo_calls"] == 1 and counters["call_count"] == 1

def test_positive_apply_uses_real_session_info_capability_cache_and_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ableton_mcp_server import diagnostics
    from ableton_mcp_server import server
    runtime, bridge, client = runtime_with_real_capability_bridge(tmp_path, epoch=7, response=committed_response())
    status = diagnostics.bridge_status(client)
    assert status["bridge_available"] is True
    capability = client.get_capability_status(now=100.0)
    snapshot = client.get_capability_snapshot(now=100.1)
    assert capability is not None and snapshot is not None
    assert snapshot.connection_epoch == 7 and capability.schema_version == "bridge.contract.v1"
    monkeypatch.setattr(server, "get_groove_runtime", lambda: runtime)
    request = commit_request(runtime.index.manifest.artifact_ids[0])
    result = server.groove_apply(**request.model_dump())
    assert result.structured_content["state"] == "committed"
    assert bridge.session_info_calls >= 1 and bridge.dispatch_calls == 1 and bridge.sent_bytes > 0
    assert bridge.begin_undo_calls == 1 and bridge.last_preconditions == [{"type": "slot_empty", "version": "v1", "params": {"track_index": 3, "clip_index": 2}}]
    assert client.connection_epoch == 7

@pytest.mark.asyncio
async def test_five_tool_wire_schemas_include_groove_apply(tmp_path: Path) -> None:
    from tests.fixtures.groove_mcp_wire import assert_client_schema_constraints, discover_client_wire_schemas, normalize_wire_schema, schema_constraint
    wire = await discover_client_wire_schemas(server.mcp)
    assert {"groove_search", "groove_evidence", "groove_generate", "groove_compare", "groove_apply"} <= set(wire)
    for name, model in GROOVE_REQUEST_MODEL_BY_TOOL.items():
        assert_client_schema_constraints(wire[name], model)
        normalized = normalize_wire_schema(wire[name])
        assert normalized["properties"]["schema_version"]["enum"] == [model.model_fields["schema_version"].default]
        assert wire[name]["additionalProperties"] is False
    assert schema_constraint(wire["groove_apply"], "source_track_index", "minimum") == 0
    assert schema_constraint(wire["groove_apply"], "source_channel", "minimum") == 0
    assert schema_constraint(wire["groove_apply"], "source_channel", "maximum") == 15
    assert {"source_track_index", "source_channel"} <= set(wire["groove_apply"]["properties"])
    assert "source_track_index" not in wire["groove_apply"]["required"] and "source_channel" not in wire["groove_apply"]["required"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_mapping.py tests/test_groove_apply.py`
Expected: FAIL because mapping/apply models and wrapper do not exist.

- [ ] **Step 3: Write minimal implementation**

Resolve `user_override`, exact profile mapping, HVO role, profile GM map, then role fallback in deterministic order. Preserve originals and count exact/fallback/unmapped/skipped. `map_artifact` first filters source `MidiArtifactV1.events` by the paired selector and creates one `CanonicalApplyEventV1` per selected source event, retaining its source event id, track, channel, and generated `NoteSpec`; `MappingPlanV1.notes` is derived from `emitted_events` in that same order. It never selects by a metadata-only count or by artifact-id ordering. Require `source_track_index` and `source_channel` together for multi-track/multi-channel artifacts and select only that source; a single-track/single-channel artifact may omit both selectors. Reject a selected non-channel-9 source only for `gm-drums-v1`; `native-compatible` preserves pitches on the selected source channel. Reject rights below full, >2,048 selected notes, invalid scope, occupied preflight, or missing expected-empty declaration before bridge calls. Convert `absolute_ticks`/`duration_ticks` by `Decimal`/`Fraction` with half-even nine-place serialization. For commit, obtain fresh capability, capture stable epoch, perform optional preflight, build one `run_batch` with one matching precondition and two commands from `plan.emitted_events`, call `call_at_epoch(E, "run_batch", batch)`, and map bridge errors/stages to the receipt without retry.
The bridge fixture must model the exact receipt matrix: occupancy TOCTOU returns `rejected` after one dispatch with zero undo; a create-success/add-fail envelope returns `partial` with `clip_ref`, note counts, and `inspect_clip_and_remove_or_complete_notes`; a post-send read/transport failure returns `unknown` with no fabricated `clip_ref`, one dispatch/undo, and `inspect_live_and_do_not_retry`. Pre-send validation and preview retain zero bytes/dispatch/undo. No branch retries or performs a readback.

The real positive-handshake factory is also owned here; it must not replace the
client with a mock capability method:

```python
def runtime_with_real_capability_bridge(tmp_path: Path, *, epoch: int = 7, response: bytes = OK_RESPONSE) -> tuple[GrooveRuntime, NewBridgeFixture, Client]:
    bridge = NewBridgeFixture(capabilities={"run_batch_preconditions": "v1"})
    session = bridge.capable_status(epoch=epoch)
    client, fake_socket = bridge.connected_client(epoch=epoch, response=response, session_info=session)
    runtime = runtime_with_artifact(tmp_path)
    runtime.client = client
    fake_socket.bridge = bridge
    return runtime, bridge, client
```

`diagnostics.bridge_status(client)` in the positive test therefore consumes the
fixture's actual `get_session_info` response, parses its
`diagnostics.bridge_status`, and populates the same capability cache later used
by `get_capability_status` and apply admission. The test must not monkeypatch
either capability method or inject a bridge contract into `run_batch`.

Expose the fifth wrapper with the same visible schema discipline as phase 2:

```python
from typing import Annotated
from pydantic import Field, NonNegativeInt, model_validator
from ableton_mcp_server.groove_intelligence.mcp_models import ArtifactId, RequestModel

class ApplyRequestV1(RequestModel):
    schema_version: Literal["groove.apply.request.v1"]
    artifact_id: ArtifactId
    track_index: NonNegativeInt
    clip_index: NonNegativeInt
    kit_mapping_profile: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")]
    source_track_index: NonNegativeInt | None = None
    source_channel: Annotated[int, Field(ge=0, le=15)] | None = None
    mode: Literal["preview", "commit"] = "preview"
    expected_empty_slot: bool = True

    @model_validator(mode="after")
    def validate_source_selector_pair(self) -> ApplyRequestV1:
        if (self.source_track_index is None) != (self.source_channel is None):
            raise ValueError("source_track_index and source_channel must be provided together")
        return self

@mcp.tool()
def groove_apply(schema_version: Literal["groove.apply.request.v1"], artifact_id: ArtifactId, track_index: NonNegativeInt, clip_index: NonNegativeInt, kit_mapping_profile: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")], source_track_index: NonNegativeInt | None = None, source_channel: Annotated[int, Field(ge=0, le=15)] | None = None, mode: Literal["preview", "commit"] = "preview", expected_empty_slot: bool = True) -> ToolResult:
    request = ApplyRequestV1.model_validate(locals())
    return _explicit_json_result(apply_artifact(get_groove_runtime(), request).model_dump(exclude_none=True))
```
Add `groove_apply` as the fifth public tool while preserving the catalog as the count source. Extend the phase-2 registry's required-name set to include `groove_apply`; phase-3 Task 4 owns the acceptance/docs consumers and relevant-file stale-count gate. No consumer may restore a literal current total.

```python
def apply_artifact(runtime: GrooveRuntime, request: ApplyRequestV1) -> ApplyReceiptV1:
    plan = resolve_and_validate_mapping(runtime, request)
    if request.mode == "preview":
        return preview_receipt(plan)
    status = require_fresh_preconditions_capability(runtime.client)
    epoch = status.connection_epoch
    batch = {"preconditions": [{"type": "slot_empty", "version": "v1", "params": {"track_index": request.track_index, "clip_index": request.clip_index}}], "commands": [{"type": "create_clip", "params": {"track_index": request.track_index, "clip_index": request.clip_index, "length_beats": plan.length_beats}}, {"type": "add_notes_to_clip", "params": {"track_index": request.track_index, "clip_index": request.clip_index, "notes": [note.model_dump(exclude_none=True) for note in plan.notes]}}]}
    try:
        result = runtime.client.call_at_epoch(epoch, "run_batch", batch)
    except BridgeTransportAmbiguousError:
        return unknown_receipt(plan, bridge_stage="transport_after_send")
    return receipt_from_batch(result, plan)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_mapping.py tests/test_groove_apply.py tests/test_music_tools.py tests/test_models.py tests/test_catalog.py tests/test_tool_registry.py`
Expected: PASS with preview zero bridge calls; scope/channel/rights/slot/2,049-note rejection before undo; one capable batch; `committed`, `partial`, `rejected`, and `unknown` counts/recovery; no retry; and all legacy tools green.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/groove_intelligence/mapping.py ableton_mcp_server/groove_intelligence/apply.py ableton_mcp_server/groove_intelligence/mcp_models.py ableton_mcp_server/models.py ableton_mcp_server/catalog.py ableton_mcp_server/server.py tests/test_groove_mapping.py tests/test_groove_apply.py
git commit -m "feat: add guarded groove apply and late kit mapping"
```

### Task 4: Acceptance probes, thin skill, and operational documentation

**Files:**
- Modify: `ableton_mcp_server/acceptance/probes/offline.py`
- Modify: `ableton_mcp_server/acceptance/probes/composed.py`
- Modify: `ableton_mcp_server/acceptance/probes/__init__.py`
- Create: `ableton_mcp_server/acceptance/probes/groove_apply.py`
- Modify: `ableton_mcp_server/acceptance/runner.py`
- Modify: `scripts/generate_capability_matrix.py`
- Create: `ableton_mcp_server/tool_counts.py`
- Create: `.agents/skills/drum-groove-intelligence/SKILL.md`
- Modify: `docs/TOOL_REFERENCE.md`
- Modify: `docs/api_capability_matrix.md`
- Modify: `docs/CERTIFICATION.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/index.html`
- Modify: `README.md`
- Modify: `tests/test_packaging.py`
- Modify: `tests/test_acceptance_runner_integration.py`
- Modify: `tests/test_acceptance_audit_p0p1.py`
- Modify: `tests/test_certification.py`
- Modify: `tests/test_acceptance_helpers.py`
- Modify: `tests/test_capability_matrix.py`
- Modify: `tests/test_diagnostics.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_catalog.py`
- Modify: `tests/test_models.py`
- Modify: `tests/test_server_tools.py`
- Modify: `tests/test_tool_registry.py`
- Create: `tests/test_groove_skill_docs.py`

**Interfaces:**
- Produces an offline probe row for preview/search/evidence/generate/compare and a guarded commit probe that requires disposable Set, explicit project name, empty slot, and one batch.
- Produces thin skill instructions that only describe MCP chaining and receipts; it never executes SQL/BLOB/build/corpus/provider/Live operations.
- Produces one runtime-derived `ToolCountSnapshotV1` from `TOOL_CATALOG` plus the canonical acceptance registry, and catalog-derived documentation/acceptance counts from that snapshot/`bridge_status`. The exact helper is `build_tool_count_snapshot(catalog: Sequence[ToolSpec] = TOOL_CATALOG, acceptance_registry: Sequence[AcceptanceRowV1] = ACCEPTANCE_REGISTRY) -> ToolCountSnapshotV1` in `ableton_mcp_server/tool_counts.py`; it returns `active_total`, `headless_total`, `live_required_total`, `certified_total`, `acceptance_total`, and `route_counts`. `ACCEPTANCE_REGISTRY` is the one-row-per-tool registry owned by `acceptance.probes.__init__`; the helper asserts every row name is in the catalog and every certified name is unique. Runtime diagnostics, CLI, certification, generated matrix, and tests consume this snapshot rather than independent arithmetic.
- `AcceptanceRowV1(tool_name: str, group: str, certified: bool)` and `ACCEPTANCE_REGISTRY: tuple[AcceptanceRowV1, ...]` are declared in `ableton_mcp_server/acceptance/probes/__init__.py`; each catalog name appears exactly once, including the five groove tools. `ToolCountSnapshotV1.route_counts` is keyed by the string values of `Route` (`local`, `tcp`, `websocket`, `composed`) so generated docs can name a route without a second mapping.
- The count inventory is exact and includes active total/headless/live/certified/route surfaces: `ableton_mcp_server/{tool_counts, catalog, server, diagnostics, cli, certification}.py`, `scripts/generate_capability_matrix.py`, `ableton_mcp_server/acceptance/{probes/composed.py,probes/offline.py,probes/__init__.py,runner.py}`, `tests/test_cli.py`, `tests/test_packaging.py`, `tests/test_acceptance_helpers.py`, `tests/test_acceptance_runner_integration.py`, `tests/test_acceptance_audit_p0p1.py`, `tests/test_certification.py`, `tests/test_catalog.py`, `tests/test_models.py`, `tests/test_capability_matrix.py`, `tests/test_diagnostics.py`, `tests/test_server_tools.py`, `tests/test_tool_registry.py`, and `README.md`, `docs/{index.html,ARCHITECTURE.md,api_capability_matrix.md,CERTIFICATION.md,TOOL_REFERENCE.md}`. `TOOL_REFERENCE.md`'s release value 88, `CERTIFICATION.md`'s baseline 65, and `ARCHITECTURE.md`'s 65/56 are retained only on lines carrying machine-detectable `<!-- HISTORICAL_TOOL_COUNT: <n>; baseline=<id> -->` markers. Every active number carries `<!-- TOOL_COUNT: active_total -->`, `headless_total`, `live_required_total`, `certified_total`, `acceptance_total`, or `route=<name>` on the same line. The gate rejects every numeric tool claim without one of those markers; it is not a special-case search for 91.

- [ ] **Step 1: Write the failing tests**

```python
def test_skill_is_guidance_only_and_names_receipt_safety_rules() -> None:
    text = Path(".agents/skills/drum-groove-intelligence/SKILL.md").read_text(encoding="utf-8")
    assert "search -> evidence -> generate/compare -> apply" in text
    assert "artifact_id" in text and "slot vazio" in text
    assert "SQL" in text and "não executa" in text
    assert "subprocess" not in text.lower()

def test_apply_acceptance_probe_requires_disposable_set_and_empty_slot() -> None:
    source = Path("ableton_mcp_server/acceptance/probes/groove_apply.py").read_text(encoding="utf-8")
    assert "confirm_project_name" in source and "expected_empty_slot" in source and "disposable" in source

def test_capability_probe_rejects_bridge_without_exact_contract() -> None:
    row = run_apply_preview_with_bridge(contract=None)
    assert row["status"] == "offline_passed" and row["result"]["state"] == "rejected"
    assert row["result"]["error"]["code"] == "GROOVE_PRECONDITION_UNSUPPORTED"

def test_tool_count_snapshot_is_catalog_and_acceptance_derived() -> None:
    from ableton_mcp_server.tool_counts import build_tool_count_snapshot
    from ableton_mcp_server.catalog import TOOL_CATALOG, Route
    from ableton_mcp_server.acceptance.probes import ACCEPTANCE_REGISTRY

    snapshot = build_tool_count_snapshot()
    assert snapshot.active_total == len(TOOL_CATALOG)
    assert snapshot.headless_total == sum(item.route is Route.LOCAL for item in TOOL_CATALOG)
    assert snapshot.live_required_total == snapshot.active_total - snapshot.headless_total
    assert snapshot.acceptance_total == len(ACCEPTANCE_REGISTRY)
    assert sum(snapshot.route_counts.values()) == snapshot.active_total
    assert snapshot.certified_total == sum(row.certified for row in ACCEPTANCE_REGISTRY)

def test_active_numeric_tool_claims_are_marked_or_rejected() -> None:
    from ableton_mcp_server.tool_counts import build_tool_count_snapshot
    import re

    docs = [Path("README.md"), Path("docs/index.html"), Path("docs/ARCHITECTURE.md"), Path("docs/api_capability_matrix.md"), Path("docs/CERTIFICATION.md"), Path("docs/TOOL_REFERENCE.md")]
    snapshot = build_tool_count_snapshot()
    active_markers = {
        "active_total": snapshot.active_total,
        "headless_total": snapshot.headless_total,
        "live_required_total": snapshot.live_required_total,
        "certified_total": snapshot.certified_total,
        "acceptance_total": snapshot.acceptance_total,
    }
    claim = re.compile(r"(?<![0-9])([0-9]+)[ -](?:MCP )?tools?\b", re.IGNORECASE)
    marker = re.compile(r"<!-- (?:TOOL_COUNT: (?:active_total|headless_total|live_required_total|certified_total|acceptance_total|route=[a-z_]+)|HISTORICAL_TOOL_COUNT: [0-9]+; baseline=[^ ]+) -->")
    for path in docs:
        for line in path.read_text(encoding="utf-8").splitlines():
            match = claim.search(line)
            if not match:
                continue
            assert marker.search(line), f"unmarked active tool claim in {path}: {line}"
            if "TOOL_COUNT:" in line:
                key = re.search(r"TOOL_COUNT: ([a-z_]+)", line)
                if key and key.group(1) in active_markers:
                    assert int(match.group(1)) == active_markers[key.group(1)]

def test_count_gate_covers_all_active_surfaces_and_allows_only_marked_history() -> None:
    from ableton_mcp_server.tool_counts import build_tool_count_snapshot
    snapshot = build_tool_count_snapshot()
    assert snapshot.active_total >= 5
    assert snapshot.route_counts
    for path in (Path("ableton_mcp_server/acceptance/probes/composed.py"), Path("scripts/generate_capability_matrix.py")):
        source = path.read_text(encoding="utf-8")
        assert "build_tool_count_snapshot" in source or "TOOL_CATALOG" in source
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_skill_docs.py tests/test_acceptance_runner_integration.py tests/test_acceptance_audit_p0p1.py tests/test_certification.py tests/test_packaging.py tests/test_acceptance_helpers.py`
Expected: FAIL because the skill, groove apply probe, acceptance registry, and runtime count snapshot do not exist and the docs still contain unmarked active claims.

- [ ] **Step 3: Write minimal implementation**

Register the new apply probe group and ensure all five groove tools have one
authoritative acceptance row in `ACCEPTANCE_REGISTRY`. Preview probes run
offline; guarded commit is skipped unless exact owner confirmation, disposable
Set marker, project-name confirmation, empty target slot, and capability probe
all pass. Update exact `get_session_info` fixture equality in
`tests/test_acceptance_audit_p0p1.py` for capable/legacy bridge shapes; do not
weaken equality to subset checks. Create `ableton_mcp_server/tool_counts.py`
with the one snapshot implementation and make diagnostics, CLI, certification,
the acceptance runner, `acceptance.probes.composed`, and
`scripts/generate_capability_matrix.py` consume it. The snapshot is:

```python
@dataclass(frozen=True)
class ToolCountSnapshotV1:
    active_total: int
    headless_total: int
    live_required_total: int
    certified_total: int
    acceptance_total: int
    route_counts: Mapping[str, int]

def build_tool_count_snapshot(catalog: Sequence[ToolSpec] = TOOL_CATALOG, acceptance_registry: Sequence[AcceptanceRowV1] = ACCEPTANCE_REGISTRY) -> ToolCountSnapshotV1:
    catalog_names = {item.name for item in catalog}
    acceptance_names = [row.tool_name for row in acceptance_registry]
    if not set(acceptance_names) <= catalog_names or len(acceptance_names) != len(set(acceptance_names)):
        raise ValueError("acceptance registry must contain unique catalog tools")
    routes = Counter(item.route.value for item in catalog)
    certified = sum(1 for row in acceptance_registry if row.certified)
    headless = routes.get(Route.LOCAL.value, 0)
    return ToolCountSnapshotV1(len(catalog), headless, len(catalog) - headless, certified, len(acceptance_registry), dict(sorted(routes.items())))
```

Replace every fixed current count in the inventory with the appropriate
snapshot key or required-name set. Generate docs with exact same-line markers:
`<!-- TOOL_COUNT: active_total -->`, `headless_total`, `live_required_total`,
`certified_total`, `acceptance_total`, or `route=<name>`. Preserve the release
claims 88 in `TOOL_REFERENCE.md`, 65 in `CERTIFICATION.md`, and 65/56 in
`ARCHITECTURE.md` only as same-line
`<!-- HISTORICAL_TOOL_COUNT: <n>; baseline=<release-id> -->`; remove/replace
unversioned 91/75 claims in README and `docs/index.html`. The parser test scans
all six docs for every `N tool(s)` claim and fails unless it has an active or
historical marker; therefore the gate rejects any unmatched active number, not
only 91. Generated `docs/api_capability_matrix.md` writes the snapshot keys and
route rows, while static docs use the marker associated with their generated
key. Add docs for routes, card limits, no path dependency, bridge capability,
receipt recovery, stale path-id/session semantics, and `run_batch` non-rollback.
Write the skill in Brazilian Portuguese as a short orientation layer with only
the five MCP names, opaqueness of artifact ids, provenance/fallback
requirements, explicit target/empty-slot confirmation, and unresolved
mapping/rights reporting.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_*.py tests/test_acceptance_runner_integration.py tests/test_acceptance_audit_p0p1.py tests/test_certification.py tests/test_packaging.py tests/test_acceptance_helpers.py tests/test_capability_matrix.py tests/test_diagnostics.py tests/test_server_tools.py tests/test_tool_registry.py tests/test_catalog.py tests/test_models.py tests/test_cli.py tests/test_music_brain.py tests/test_music_tools.py`; `.\.venv-win\Scripts\python.exe -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests`; `.\.venv-win\Scripts\python.exe -m mypy --strict ableton_mcp_server`; `git diff --check -- docs/TOOL_REFERENCE.md docs/api_capability_matrix.md docs/CERTIFICATION.md docs/ARCHITECTURE.md docs/index.html README.md .agents/skills/drum-groove-intelligence/SKILL.md`
Expected: PASS; preview/acceptance proves no Live call, guarded commit states are evidenced, exact capable/legacy bridge fixtures pass, docs/skill contain no private path or executable operation.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/tool_counts.py ableton_mcp_server/acceptance/probes/offline.py ableton_mcp_server/acceptance/probes/composed.py ableton_mcp_server/acceptance/probes/__init__.py ableton_mcp_server/acceptance/probes/groove_apply.py ableton_mcp_server/acceptance/runner.py scripts/generate_capability_matrix.py .agents/skills/drum-groove-intelligence/SKILL.md docs/TOOL_REFERENCE.md docs/api_capability_matrix.md docs/CERTIFICATION.md docs/ARCHITECTURE.md docs/index.html README.md tests/test_packaging.py tests/test_acceptance_helpers.py tests/test_acceptance_runner_integration.py tests/test_acceptance_audit_p0p1.py tests/test_certification.py tests/test_groove_skill_docs.py tests/test_capability_matrix.py tests/test_diagnostics.py tests/test_cli.py tests/test_catalog.py tests/test_models.py tests/test_server_tools.py tests/test_tool_registry.py
git commit -m "docs: certify guarded groove apply workflow"
```

### Task 5: Phase terminal evidence and handoff

**Files:**
- Modify: no target-repository files. The parent creates `C:/Users/Usuario/repos/workflow-main/Lunacy/runs/drum-groove-intelligence/phases/03-generation-mcp/reports/terminal.md` and `C:/Users/Usuario/repos/workflow-main/Lunacy/runs/drum-groove-intelligence/phases/03-generation-mcp/evidence/phase3-tests.txt` as uncommitted control-plane artifacts after the worker handoff; the phase worker does not create or stage them.

**Interfaces:**
- Consumes Tasks 1–4 and fresh bridge/apply evidence.
- Returns exact command output and exit codes to the parent. The parent publishes `FINAL` only when precondition admission, capability/epoch/call-at-epoch, mapping, apply receipts, acceptance probes, docs, and legacy compatibility all pass; otherwise it records `BLOCKED` with no provider activation.

- [ ] **Step 1: Write the failing gate command**

```powershell
.\.venv-win\Scripts\python.exe -m pytest -q tests/test_client_epoch.py tests/test_remote_preconditions.py tests/test_groove_apply.py
if ($LASTEXITCODE -ne 0) { throw 'phase-3 gate is red' }
```

- [ ] **Step 2: Run it before report publication**

Run: `Test-Path C:/Users/Usuario/repos/workflow-main/Lunacy/runs/drum-groove-intelligence/phases/03-generation-mcp/reports/terminal.md`
Expected: `False` before the parent publishes the phase report.

- [ ] **Step 3: Publish fresh report and evidence**

Return target HEAD, phase commits, worktree choice, exact bridge fixture results (zero bytes, epoch mismatch, pre-send, ambiguous, close-after-receipt, capable/legacy), apply state/count/recovery matrix, acceptance probe ids, doc/skill checks, and confirmation that no UI automation or retry occurred to the parent. The parent writes the two control-plane artifacts.

- [ ] **Step 4: Verify report, plan placeholders, and scope**

Run: `git diff --check -- docs/superpowers/plans`; `rg -n -e 'T(O)DO|T(B)D|FIX(M)E|PLACE(HOLDER)|similar[[:space:]]+to|implement[[:space:]]+later' docs/superpowers/plans/2026-08-20-drum-groove-intelligence-phase-3-apply-bridge.md`; `git status --short --branch`
Expected: whitespace and placeholder scans are empty; status lists only intentional phase-3 target changes plus separately reported concurrent work.

- [ ] **Step 5: Commit phase-3 target files**

```powershell
git add ableton_mcp_server AbletonMCPServer_RemoteScript contracts.py tests docs README.md .agents/skills/drum-groove-intelligence
git commit -m "feat: complete guarded groove apply phase"
```
