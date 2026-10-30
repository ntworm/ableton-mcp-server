"""Async WebSocket client for the Extension Host bridge (port 9889).

Sends JSON-RPC 2.0 payloads to the Node.js Extension running inside Ableton
Live.  Falls back to ExtensionUnavailableError when the bridge is offline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import websockets
import websockets.asyncio.client

from contracts import DEFAULT_HOST, DEFAULT_WS_PORT

from .errors import BridgeError, ExtensionUnavailableError, error_from_envelope

logger = logging.getLogger("AbletonMCPServer.ws")

_CONNECT_TIMEOUT = 3.0
_RECV_TIMEOUT = 10.0

# Live answers every refused ``Track.insertDevice`` with this one message, so an
# unknown name and a device out of chain order look alike (docs/KNOWN_BUGS.md,
# Category R). The server already picks the position that the chain order allows.
_INSERT_REFUSED = "Failed to insert device"
_INSERT_REFUSED_CAUSES = (
    "Live refuses a name that is not one of its built-in devices, and an instrument or "
    "MIDI effect on an audio, return or main track. An AbletonMCPServer Extension "
    "installed before positional inserts ignores device_index and appends, which Live "
    "refuses for a device that has to go earlier in the chain; reinstall the Extension."
)


def _rpc_error(method: str, message: str, code: object) -> BridgeError:
    """Build the error for a plain JSON-RPC failure, explaining Live's insert refusal."""
    if method == "load_device_to_track" and message == _INSERT_REFUSED:
        message = f"{_INSERT_REFUSED}. {_INSERT_REFUSED_CAUSES}"
    return BridgeError(message, code=f"EXTENSION_RPC_{code}")


class WSClient:
    """Async JSON-RPC 2.0 client for the Extension Host WebSocket bridge."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_WS_PORT,
    ) -> None:
        self.host = host
        self.port = port
        self._request_id = 0

    @property
    def uri(self) -> str:
        return f"ws://{self.host}:{self.port}"

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = _RECV_TIMEOUT,
    ) -> Any:
        """Send a JSON-RPC 2.0 request and return the result.

        Raises:
            ExtensionUnavailableError: when the WebSocket server is unreachable.
            Exception: on JSON-RPC error responses from the extension host.
        """
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": self._next_id(),
        }
        try:
            async with websockets.asyncio.client.connect(
                self.uri,
                open_timeout=_CONNECT_TIMEOUT,
                close_timeout=2.0,
            ) as ws:
                await ws.send(json.dumps(payload))
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        except (
            OSError,
            asyncio.TimeoutError,
            websockets.exceptions.WebSocketException,
        ) as exc:
            logger.warning("Extension Host unreachable at %s: %s", self.uri, exc)
            raise ExtensionUnavailableError(self.port) from exc

        response = json.loads(raw)

        if "error" in response:
            error_data = response["error"]
            details = error_data.get("data") or {}
            if isinstance(details, dict) and isinstance(details.get("code"), str):
                hint = details.get("hint")
                raise error_from_envelope(
                    details["code"],
                    str(error_data.get("message", details["code"])),
                    hint if isinstance(hint, str) else None,
                )
            raise _rpc_error(
                method,
                error_data.get("message", str(error_data)),
                error_data.get("code", -1),
            )

        return response.get("result")
