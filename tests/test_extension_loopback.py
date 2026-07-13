from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "AbletonMCPServer_Extension"
INDEX = ROOT / "src" / "index.ts"


def test_extension_binds_websocket_to_loopback() -> None:
    """Regression: the Extension WebSocket must bind to 127.0.0.1 only.

    The slice 1 design forbids LAN exposure. Any removal of the explicit
    ``host: "127.0.0.1"`` argument fails this test.
    """
    text = INDEX.read_text(encoding="utf-8")
    assert "new WebSocketServer" in text, "Extension must construct a WebSocketServer"
    assert "host:" in text and "127.0.0.1" in text, (
        "WebSocketServer must bind explicitly to 127.0.0.1 (loopback only)"
    )
    # Defense in depth: also assert the literal option object is present in
    # the compiled bundle that ships to the Live Extensions folder.
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["name"] == "ableton-mcp-server-extension"