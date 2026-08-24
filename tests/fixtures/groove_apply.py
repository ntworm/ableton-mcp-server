"""Factories used by guarded groove-apply tests."""

from __future__ import annotations

import time
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal
from unittest.mock import Mock

from ableton_mcp_server.client import BridgeContractV1, CapabilitySnapshotV1, Client
from ableton_mcp_server.errors import BridgeEpochMismatchError
from ableton_mcp_server.groove_intelligence.canonical import canonical_json
from ableton_mcp_server.groove_intelligence.index import open_readonly_index
from ableton_mcp_server.groove_intelligence.mcp_models import ApplyRequestV1
from ableton_mcp_server.groove_intelligence.midi_lossless import compress_bounded, parse_smf
from ableton_mcp_server.groove_intelligence.runtime import GrooveRuntime
from ableton_mcp_server.groove_intelligence.schema import (
    ArtifactId,
    MidiArtifactV1,
    SmfFormatV1,
)
from tests.fixtures.groove_bridge import OK_RESPONSE, NewBridgeFixture
from tests.fixtures.groove_bundle import build_pilot_bundle
from tests.fixtures.groove_runtime import MemoryArtifactStore


def _vlq(value: int) -> bytes:
    encoded = [value & 0x7F]
    value >>= 7
    while value:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(encoded))


def _track(notes: list[tuple[int, int]]) -> bytes:
    body = bytearray(b"\x00\xff\x51\x03\x07\xa1\x20")
    for index, (channel, pitch) in enumerate(notes):
        body.extend(_vlq(0 if index == 0 else 120))
        body.extend((0x90 | channel, pitch, 100))
        body.extend(_vlq(120))
        body.extend((0x80 | channel, pitch, 0))
    body.extend(b"\x00\xff\x2f\x00")
    return b"MTrk" + len(body).to_bytes(4, "big") + bytes(body)


def make_drum_artifact(
    note_count: int = 2,
    *,
    track_count: int = 1,
    channels: tuple[int, ...] = (9,),
) -> MidiArtifactV1:
    if track_count < 1 or not channels:
        raise ValueError("track_count and channels must be positive")
    per_track: list[list[tuple[int, int]]] = [[] for _ in range(track_count)]
    for index in range(note_count):
        track = index % track_count
        channel = channels[(track_count - 1 - track) % len(channels)]
        per_track[track].append((channel, 49 if index == 0 else 36))
    raw = (
        b"MThd"
        + (6).to_bytes(4, "big")
        + (1).to_bytes(2, "big")
        + track_count.to_bytes(2, "big")
        + (480).to_bytes(2, "big")
        + b"".join(_track(notes) for notes in per_track)
    )
    payload = compress_bounded(raw, "zlib-raw-midi-v1")
    identity = {
        "raw": payload.sha256,
        "tracks": track_count,
        "notes": note_count,
        "channels": channels,
    }
    artifact_id = ArtifactId("ga1_" + sha256(canonical_json(identity)).hexdigest())
    artifact = MidiArtifactV1(
        artifact_id=artifact_id,
        format=SmfFormatV1(smf_type=1, ppq=480, track_count=track_count),
        timing={"length_ticks": max(480, note_count * 240)},
        payload=payload,
        events_digest=sha256(raw).hexdigest(),
        provenance={
            "redistribution": "full",
            "rights_level": 2,
            "license_id": "fixture-full",
            "capabilities": {"apply": True, "search": True, "evidence": True, "generate": True},
        },
    )
    # The phase-3 draft contract exposed note events as ``artifact.events``;
    # retain that fixture convenience while production artifacts stay bounded
    # and materialize events through the lossless payload parser.
    object.__setattr__(artifact, "events", tuple(parse_smf(raw).note_events))
    return artifact


def make_apply_request(
    artifact_id: str,
    *,
    mode: Literal["preview", "commit"] = "preview",
    expected_empty_slot: bool = True,
    source_track_index: int | None = None,
    source_channel: int | None = None,
) -> ApplyRequestV1:
    return ApplyRequestV1(
        schema_version="groove.apply.request.v1",
        artifact_id=artifact_id,
        track_index=3,
        clip_index=2,
        kit_mapping_profile="gm-drums-v1",
        mode=mode,
        expected_empty_slot=expected_empty_slot,
        source_track_index=source_track_index,
        source_channel=source_channel,
    )


def runtime_with_artifact(
    tmp_path: Path,
    note_count: int = 2,
    *,
    track_count: int = 1,
    channels: tuple[int, ...] = (9,),
) -> GrooveRuntime:
    bundle = build_pilot_bundle(tmp_path)
    index = open_readonly_index(bundle)
    store = MemoryArtifactStore()
    artifact = make_drum_artifact(note_count, track_count=track_count, channels=channels)
    store.put(artifact)
    index.manifest = index.manifest.model_copy(update={"artifact_ids": (artifact.artifact_id,)})
    return GrooveRuntime(index=index, store=store)


def runtime_with_capable_bridge(
    tmp_path: Path,
    response: bytes = OK_RESPONSE,
    *,
    candidate_response: bytes | None = None,
    occupancy_swap: bool = False,
    transport_failure: bool = False,
) -> GrooveRuntime:
    del candidate_response
    runtime = runtime_with_artifact(tmp_path)
    bridge = NewBridgeFixture({"run_batch_preconditions": "v1"})
    client, sock = bridge.connected_client(1, response=None if occupancy_swap else response)
    sock.raise_after_send = transport_failure
    bridge.swap_occupancy = occupancy_swap
    runtime.client = client
    client._fixture_bridge = bridge  # type: ignore[attr-defined]
    client.call_at_epoch = Mock(wraps=client.call_at_epoch)  # type: ignore[method-assign]
    client.get_capability_status = Mock(  # type: ignore[method-assign]
        wraps=client.get_capability_status
    )
    if transport_failure:
        client.cache_capability_snapshot(
            CapabilitySnapshotV1(
                host=client.host,
                port=client.port,
                connection_epoch=1,
                contract=BridgeContractV1(capabilities={"run_batch_preconditions": "v1"}),
                fetched_at=time.monotonic(),
                freshness="fresh",
            )
        )
    return runtime


def runtime_with_real_capability_bridge(
    tmp_path: Path,
    *,
    epoch: int = 7,
    response: bytes = OK_RESPONSE,
) -> tuple[GrooveRuntime, NewBridgeFixture, Client]:
    bridge = NewBridgeFixture({"run_batch_preconditions": "v1"})
    session = bridge.capable_status(epoch=epoch)
    client, fake_socket = bridge.connected_client(
        epoch=epoch, response=response, session_info=session
    )
    runtime = runtime_with_artifact(tmp_path)
    runtime.client = client
    fake_socket.bridge = bridge
    return runtime, bridge, client


def commit_request(
    artifact_id: str, *, source_track_index: int | None = None, source_channel: int | None = None
) -> ApplyRequestV1:
    return make_apply_request(
        artifact_id,
        mode="commit",
        source_track_index=source_track_index,
        source_channel=source_channel,
    )


def committed_response() -> bytes:
    return OK_RESPONSE


def partial_response(clip_ref: str) -> bytes:
    return ('{"status":"ok","result":{"state":"partial","clip_ref":"%s"}}\n' % clip_ref).encode()


def swap_client_socket(runtime: GrooveRuntime, epoch: int) -> None:
    client = runtime.client
    if client is None:
        return
    client._connection_epoch = epoch

    def reject(*_args: Any, **_kwargs: Any) -> Any:
        raise BridgeEpochMismatchError("epoch_mismatch", bytes_sent=0)

    client.call_at_epoch = reject  # type: ignore[method-assign]


def bridge_counters(runtime: GrooveRuntime) -> dict[str, int]:
    client = runtime.client
    socket = getattr(client, "_socket", None)
    bridge = getattr(socket, "bridge", None) or getattr(client, "_fixture_bridge", None)
    if bridge is None:
        return {"sent_bytes": 0, "dispatch_calls": 0, "undo_calls": 0, "call_count": 0}
    return {
        "sent_bytes": bridge.sent_bytes,
        "dispatch_calls": bridge.dispatch_calls,
        "undo_calls": bridge.begin_undo_calls,
        "call_count": socket.send_calls if socket is not None else 1,
    }


__all__ = [
    "OK_RESPONSE",
    "commit_request",
    "committed_response",
    "make_apply_request",
    "make_drum_artifact",
    "partial_response",
    "runtime_with_artifact",
    "runtime_with_capable_bridge",
    "runtime_with_real_capability_bridge",
    "swap_client_socket",
    "bridge_counters",
]
