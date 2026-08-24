from __future__ import annotations

import pytest

from ableton_mcp_server.client import (
    BridgeContractV1,
    CapabilitySnapshotV1,
    Client,
)
from ableton_mcp_server.errors import (
    BridgeEpochMismatchError,
    BridgePreSendError,
    BridgeTransportAmbiguousError,
)


class EpochSocket:
    def __init__(self, response: bytes = b"", *, raise_after_send: bool = False) -> None:
        self.response = bytearray(response)
        self.sent: list[bytes] = []
        self.raise_after_send = raise_after_send
        self.closed = False

    def settimeout(self, _timeout: float) -> None:
        return None

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)
        if self.raise_after_send:
            raise ConnectionError("after send")

    def recv(self, size: int) -> bytes:
        if not self.response:
            return b""
        data = self.response[:size]
        del self.response[:size]
        return bytes(data)

    def close(self) -> None:
        self.closed = True


def connected_client(
    epoch: int = 4, response: bytes = b'{"status":"ok","result":{}}\n'
) -> tuple[Client, EpochSocket]:
    client = Client(reconnect=False)
    sock = EpochSocket(response)
    client._socket = sock
    client._connected = True
    client._connection_epoch = epoch
    return client, sock


def test_call_at_epoch_rejects_mismatch_before_send() -> None:
    client, sock = connected_client()
    with pytest.raises(BridgeEpochMismatchError) as error:
        client.call_at_epoch(3, "run_batch", {"commands": []})
    assert error.value.reason == "epoch_mismatch" and error.value.bytes_sent == 0
    assert sock.sent == []


def test_pre_send_serialization_failure_is_zero_byte() -> None:
    client, sock = connected_client()
    with pytest.raises(BridgePreSendError) as error:
        client.call_at_epoch(4, "run_batch", {"commands": [object()]})
    assert error.value.bytes_sent == 0 and sock.sent == [] and client.connection_epoch == 4


def test_possible_send_failure_is_unknown_without_retry() -> None:
    client, sock = connected_client()
    sock.raise_after_send = True
    with pytest.raises(BridgeTransportAmbiguousError):
        client.call_at_epoch(4, "run_batch", {"commands": []})
    assert client.connection_epoch == 5 and len(sock.sent) == 1


def test_capability_snapshot_is_invalidated_by_epoch() -> None:
    client, _sock = connected_client()
    contract = BridgeContractV1()
    client.cache_capability_snapshot(
        CapabilitySnapshotV1(
            host=client.host,
            port=client.port,
            connection_epoch=4,
            contract=contract,
            fetched_at=100.0,
            freshness="fresh",
        )
    )
    assert client.get_capability_snapshot(now=101.0) is not None
    client.close()
    assert client.get_capability_snapshot(now=101.0) is None


def test_capability_status_requires_exact_precondition_contract() -> None:
    client, sock = connected_client(
        response=b'{"status":"ok","result":{"bridge_contract":{"schema_version":"bridge.contract.v0","owner":"Other","protocol_version":"bridge.v0","capabilities":{}}}}\n'
    )
    assert client.get_capability_status(now=100.0) is None
    assert len(sock.sent) == 1
