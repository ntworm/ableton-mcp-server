"""Regression tests for the ``resolved`` sub-object envelope (R1 / Wave-3).

Per ``docs/superpowers/specs/2026-08-01-r1-resolved-field.md`` the four mutation
tools ``set_parameter_value``, ``create_clip``, ``set_tempo``, and
``load_device_to_track`` return a canonical ``resolved`` sub-object inside the
``result`` payload on success. The sub-object carries Live-resolved identity
and is **absent** in error envelopes. Name keys are **omitted** when the
bridge cannot resolve the name.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import ableton_mcp_server.server as server
from ableton_mcp_server.errors import BridgeError

# ---------------------------------------------------------------------------
# Fixtures: synthetic Live success envelopes matching the new R1 contract.
# ---------------------------------------------------------------------------


def _device_resolved(
    *, track_index: int = 0, device_index: int = 1, parameter_name: str = "Cutoff"
) -> dict[str, Any]:
    return {
        "kind": "device",
        "track_index": track_index,
        "device_index": device_index,
        "parameter_name": parameter_name,
        "track_name": "Bass",
        "device_name": "Operator",
    }


def _clip_resolved(*, track_index: int = 0, clip_index: int = 1) -> dict[str, Any]:
    return {
        "kind": "clip",
        "track_index": track_index,
        "clip_index": clip_index,
        "track_name": "Bass",
        "clip_id": f"track:{track_index}/clipslot:{clip_index}/clip",
    }


def _tempo_resolved(*, tempo: float = 128.0) -> dict[str, Any]:
    return {"kind": "tempo", "tempo": tempo}


# ---------------------------------------------------------------------------
# Cases 1-4: each mutation tool surfaces the canonical ``resolved`` sub-object.
# ---------------------------------------------------------------------------


@patch("ableton_mcp_server.server.get_client")
def test_set_parameter_value_resolved_sub_object(mock_get_client: MagicMock) -> None:
    resolved = _device_resolved()
    client = MagicMock()
    client.call.return_value = {
        "target": 0.75,
        "value": 0.75,
        "is_quantized": False,
        "resolved": resolved,
    }
    mock_get_client.return_value = client

    result = server.set_parameter_value(0, 1, "Cutoff", 0.75)

    assert result["resolved"] == resolved
    assert result["resolved"]["kind"] == "device"
    for key in (
        "track_index",
        "device_index",
        "parameter_name",
        "track_name",
        "device_name",
    ):
        assert key in result["resolved"]


@patch("ableton_mcp_server.server.get_client")
def test_create_clip_resolved_sub_object(mock_get_client: MagicMock) -> None:
    resolved = _clip_resolved()
    client = MagicMock()
    client.call.return_value = {
        "created": True,
        "clip_id": "track:0/clipslot:1/clip",
        "length_beats": 4.0,
        "resolved": resolved,
    }
    mock_get_client.return_value = client

    result = server.create_clip(0, 1, 4.0)

    assert result["resolved"] == resolved
    assert result["resolved"]["kind"] == "clip"
    for key in ("track_index", "clip_index", "track_name", "clip_id"):
        assert key in result["resolved"]


@patch("ableton_mcp_server.server.get_client")
def test_set_tempo_resolved_sub_object(mock_get_client: MagicMock) -> None:
    client = MagicMock()
    client.call.return_value = {
        "tempo": 128.0,
        "resolved": _tempo_resolved(tempo=128.0),
    }
    mock_get_client.return_value = client

    result = server.set_tempo(128.0)

    assert result["resolved"] == {"kind": "tempo", "tempo": 128.0}
    assert result["tempo"] == 128.0


@pytest.mark.asyncio
@patch("ableton_mcp_server.server._remote_ws", new_callable=AsyncMock)
async def test_load_device_to_track_resolved_sub_object(mock_remote_ws: AsyncMock) -> None:
    mock_remote_ws.return_value = {
        "status": "loaded",
        "track_index": 0,
        "device_name": "Operator",
        "device_index": 1,
        "resolved": {
            "kind": "device",
            "track_index": 0,
            "device_index": 1,
            "track_name": "Bass",
            "device_name": "Operator",
        },
    }

    payload = await server.load_device_to_track(0, device_name="Operator")
    result = json.loads(payload)

    assert result["resolved"]["kind"] == "device"
    for key in ("track_index", "device_index", "track_name", "device_name"):
        assert key in result["resolved"]


# ---------------------------------------------------------------------------
# Case 5: ``resolved`` is absent in error envelopes.
# ---------------------------------------------------------------------------


@patch("ableton_mcp_server.server.get_client")
def test_resolved_absent_on_error(mock_get_client: MagicMock) -> None:
    client = MagicMock()

    def _raise(*_args: Any, **_kwargs: Any) -> Any:
        raise BridgeError("INVALID_PARAMS", "Parameter not found.")

    client.call.side_effect = _raise
    mock_get_client.return_value = client

    result = server.set_parameter_value(0, 1, "Missing", 0.5)

    # The server surfaces a structured MCP error envelope; no ``resolved``
    # field is present because the call did not produce a success ``result``
    # dict. The spec §2 guarantees ``resolved`` is absent in error envelopes.
    assert result.is_error is True
    payload = result.structured_content
    assert payload["status"] == "error"
    assert "resolved" not in payload
    # No spurious top-level ``resolved`` key in the serialized text either.
    assert "resolved" not in result.content[0].text  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Case 6: name keys are omitted when the bridge cannot resolve them.
# ---------------------------------------------------------------------------


def test_resolved_omitted_keys_when_name_unavailable() -> None:
    """When ``track.name`` cannot be read, ``track_name`` is omitted from
    ``resolved`` rather than serialized as an empty string. The spec §2.2
    states the canonical signal is *key absent*.

    Exercises the real Remote Script path: ``cmd_create_clip`` runs against
    a real ``FakeSong`` whose track has an empty ``name``, and the wire
    payload is asserted to omit the key.
    """

    from AbletonMCPServer_RemoteScript import execute_command
    from tests.remote_fakes import FakeApplication, FakeClipSlot, FakeSong

    # Track with empty name simulates the case where ``track.name`` is
    # unavailable or returns an empty string.
    song = FakeSong()
    song.tracks[0].clip_slots = [FakeClipSlot()]
    # Force the cached attribute lookup the LOM style uses.
    song.tracks[0].name = ""

    payload = execute_command(
        song,
        FakeApplication(),
        "create_clip",
        {"track_index": 0, "clip_index": 0, "length_beats": 4.0},
    )

    # Canonical signal: key absent (not empty string).
    assert "track_name" not in payload["resolved"]
    # Required identity keys survive the omission.
    assert payload["resolved"]["kind"] == "clip"
    assert payload["resolved"]["track_index"] == 0
    assert payload["resolved"]["clip_index"] == 0
    assert payload["resolved"]["clip_id"] == "track:0/clipslot:0/clip"

    # Sanity: with a non-empty name, the key IS present.
    song2 = FakeSong()
    song2.tracks[0].clip_slots = [FakeClipSlot()]
    payload_with_name = execute_command(
        song2,
        FakeApplication(),
        "create_clip",
        {"track_index": 0, "clip_index": 0, "length_beats": 4.0},
    )
    assert payload_with_name["resolved"]["track_name"] == "Bass"


# ---------------------------------------------------------------------------
# Case 7: legacy clients ignore ``resolved`` (backward compatibility guard).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("function", "args", "command", "params"),
    [
        (
            server.set_parameter_value,
            (0, 1, "Cutoff", 0.75),
            "set_parameter_value",
            {
                "track_index": 0,
                "device_index": 1,
                "parameter_name": "Cutoff",
                "value": 0.75,
            },
        ),
        (server.set_tempo, (128,), "set_tempo", {"tempo": 128.0}),
        (
            server.create_clip,
            (0, 1, 4.0),
            "create_clip",
            {"track_index": 0, "clip_index": 1, "length_beats": 4.0},
        ),
    ],
)
def test_legacy_clients_ignore_resolved(
    function: Any, args: tuple[Any, ...], command: str, params: dict[str, Any]
) -> None:
    """A legacy client that pattern-matches every non-``resolved`` top-level
    key on the success payload must continue to pass byte-for-byte once R1
    is applied. We snapshot the pre-change keys via the docstring example in
    the spec and assert that all those keys are still present alongside the
    new ``resolved`` sub-object."""

    expected_legacy_keys: dict[str, dict[str, Any]] = {
        "set_parameter_value": {
            "target": 0.75,
            "value": 0.75,
            "is_quantized": False,
        },
        "set_tempo": {"tempo": 128.0},
        "create_clip": {
            "created": True,
            "clip_id": "track:0/clipslot:1/clip",
            "length_beats": 4.0,
        },
    }

    payload = dict(expected_legacy_keys[command])
    payload["resolved"] = {
        "kind": {"set_parameter_value": "device", "set_tempo": "tempo", "create_clip": "clip"}[
            command
        ],
        # arbitrary sub-fields; legacy clients must not care
        "synthetic": True,
    }

    with patch("ableton_mcp_server.server.get_client") as mock_get_client:
        client = MagicMock()
        client.call.return_value = payload
        mock_get_client.return_value = client
        result = function(*args)

    for legacy_key, legacy_value in expected_legacy_keys[command].items():
        assert result[legacy_key] == legacy_value
    assert "resolved" in result  # the new key travels through transparently
    assert result["resolved"]["synthetic"] is True
