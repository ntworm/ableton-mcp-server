"""Evidence that the MCP server opens no connection outside the loopback host.

The test runs the real ``ableton_mcp_server.client.Client`` against two
loopback servers (TCP for the Remote Script, WebSocket for the Extension Host)
that answer through ``tests._strict_fake``. Every tool call goes through the
FastMCP in-memory client, so the server code path is the production one.

Two observers record every destination while the calls run:

* a ``sys.addaudithook`` hook on ``socket.connect``, ``socket.getaddrinfo`` and
  ``socket.gethostbyname``;
* a wrapper on ``asyncio.BaseEventLoop.create_connection``, which is how the
  WebSocket client connects. On Windows the proactor loop connects with an
  overlapped call that raises no ``socket.connect`` audit event, so the
  WebSocket half of the self-check rests on this wrapper.

The test fails if any destination is not loopback, and also if either observer
missed the bridge it is meant to see, so an empty record can never pass.

Not exercised, and stated in the README: ``build_extension`` (runs
``npm install``) and the five ``groove_*`` tools, which need a seed bundle that
the repository does not ship. Their package is covered only by the static test
below. The optional neural provider runs in a child process that these
observers do not see.
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client as FastMCPClient

from ableton_mcp_server import server
from ableton_mcp_server.acceptance.helpers import _synthesize_offline_inputs
from ableton_mcp_server.protocol import ProtocolError, decode_request, encode_response
from tests._strict_fake import StrictFakeBridge, _strict_tcp_dispatch, _strict_ws_dispatch

REPO = Path(__file__).resolve().parents[1]
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_AUDIT_EVENTS = {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname"}
_recording = threading.Event()
_observed: list[tuple[str, str, int | None]] = []


def _audit(event: str, args: tuple[Any, ...]) -> None:
    """Append loopback/remote destinations; never raise inside the hook."""
    if not _recording.is_set() or event not in _AUDIT_EVENTS:
        return
    try:
        if event == "socket.connect":
            address = args[1]
            if isinstance(address, tuple) and len(address) >= 2:
                _observed.append((event, str(address[0]), int(address[1])))
        elif event == "socket.getaddrinfo":
            port = args[1] if isinstance(args[1], int) else None
            _observed.append((event, str(args[0]), port))
        else:
            _observed.append((event, str(args[0]), None))
    except Exception:  # noqa: BLE001 - an audit hook must not break the caller
        return


sys.addaudithook(_audit)


# --------------------------------------------------------------------------- servers


def _serve_tcp_connection(conn: socket.socket, bridge: StrictFakeBridge) -> None:
    buf = b""
    with conn:
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if line.strip():
                    conn.sendall(encode_response(_tcp_answer(line, bridge)))


def _tcp_answer(line: bytes, bridge: StrictFakeBridge) -> dict[str, Any]:
    try:
        command, params = decode_request(line)
    except ProtocolError as error:
        return {"status": "error", "code": "PROTOCOL_ERROR", "message": str(error)}
    try:
        return {"status": "ok", "result": _strict_tcp_dispatch(bridge, command, params)}
    except Exception as error:  # noqa: BLE001 - surface as a bridge error
        return {"status": "error", "code": "DISPATCH_ERROR", "message": str(error)}


def _start_tcp(bridge: StrictFakeBridge) -> tuple[socket.socket, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(4)

    def accept_loop() -> None:
        while True:
            try:
                conn, _ = sock.accept()
            except OSError:
                return
            threading.Thread(target=_serve_tcp_connection, args=(conn, bridge), daemon=True).start()

    threading.Thread(target=accept_loop, daemon=True).start()
    return sock, int(sock.getsockname()[1])


def _ws_answer(raw: str, bridge: StrictFakeBridge) -> str:
    request = json.loads(raw)
    reply: dict[str, Any] = {"jsonrpc": "2.0", "id": request.get("id")}
    try:
        reply["result"] = _strict_ws_dispatch(
            bridge, str(request["method"]), dict(request.get("params") or {})
        )
    except Exception as error:  # noqa: BLE001 - surface as a JSON-RPC error
        reply["error"] = {"code": -32000, "message": str(error)}
    return json.dumps(reply)


def _start_ws(bridge: StrictFakeBridge) -> tuple[asyncio.AbstractEventLoop, Any, int]:
    from websockets.asyncio.server import serve

    loop = asyncio.new_event_loop()
    ready: dict[str, Any] = {}
    started = threading.Event()

    async def handler(ws: Any) -> None:
        async for message in ws:
            await ws.send(_ws_answer(str(message), bridge))

    async def boot() -> None:
        ready["server"] = await serve(handler, "127.0.0.1", 0)
        started.set()

    def run() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(boot())
        loop.run_forever()

    threading.Thread(target=run, daemon=True).start()
    assert started.wait(5), "loopback WebSocket server did not start"
    port = int(next(iter(ready["server"].sockets)).getsockname()[1])
    return loop, ready["server"], port


@pytest.fixture
def loopback_bridges(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, int]]:
    """Real Client pointed at loopback fakes; observers on while the test runs."""
    bridge = StrictFakeBridge()
    tcp_sock, tcp_port = _start_tcp(bridge)
    ws_loop, ws_server, ws_port = _start_ws(bridge)
    monkeypatch.setenv("ABLETON_MCP_SERVER_PORT", str(tcp_port))
    monkeypatch.setenv("ABLETON_MCP_SERVER_WS_PORT", str(ws_port))
    monkeypatch.setattr(server, "_client", None)
    _wrap_create_connection(monkeypatch)
    _observed.clear()
    _recording.set()
    try:
        yield {"tcp": tcp_port, "ws": ws_port}
    finally:
        _recording.clear()
        server._client = None
        tcp_sock.close()
        asyncio.run_coroutine_threadsafe(_stop_ws(ws_server), ws_loop).result(5)
        ws_loop.call_soon_threadsafe(ws_loop.stop)


async def _stop_ws(ws_server: Any) -> None:
    ws_server.close()
    await ws_server.wait_closed()


def _wrap_create_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    original = asyncio.BaseEventLoop.create_connection

    async def recorded(
        self: Any,
        protocol_factory: Any,
        host: Any = None,
        port: Any = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        if _recording.is_set():
            _observed.append(("create_connection", str(host), _as_port(port)))
        return await original(self, protocol_factory, host, port, *args, **kwargs)

    monkeypatch.setattr(asyncio.BaseEventLoop, "create_connection", recorded)


def _as_port(port: Any) -> int | None:
    try:
        return int(port)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- calls


def _offline_calls(tmp_path: Path) -> list[tuple[str, dict[str, Any]]]:
    """Every offline-group tool except build_extension and the groove_* tools."""
    wav = _synthesize_offline_inputs(tmp_path / "wav")
    snapshot_a = {
        "schema_version": 1,
        "captured_at_unix_ms": 1,
        "live_version": "12.0",
        "tempo": 120.0,
        "signature_numerator": 4,
        "signature_denominator": 4,
        "is_playing": False,
        "current_song_time": 0.0,
        "tracks": [{"index": 0, "name": "Bass"}],
        "control_surfaces": [],
        "browser_categories_count": 1,
    }
    return [
        ("get_ableton_logs", {"lines": 5}),
        ("diff_snapshots_tool", {"snap_a": snapshot_a, "snap_b": {**snapshot_a, "tempo": 121.0}}),
        ("scaffold_extension", {"name": "netprobe", "output_directory": str(tmp_path / "ext")}),
        ("analyze_audio", {"path": str(wav["target"])}),
        (
            "find_frequency_masking",
            {"target_path": str(wav["target"]), "reference_path": str(wav["reference"])},
        ),
        ("analyze_mix", {"stems": [str(wav["target"]), str(wav["reference"])]}),
        ("extract_single_cycle", {"path": str(wav["short"])}),
        ("music_generate_drum_groove", {"bars": 2, "seed": 1}),
        ("music_generate_bass", {"bars": 2, "seed": 1, "root_midi": 36}),
        (
            "music_plan_production",
            {"prompt": "offline certification probe", "bars": 8, "bpm": 120.0},
        ),
        (
            "plan_user_journey",
            {"journey_type": "sequence_drums", "traits": "offline certification probe"},
        ),
    ]


def _bridge_calls() -> list[tuple[str, dict[str, Any]]]:
    """One TCP read and one WebSocket read (Drums, track 1, holds an audio clip)."""
    return [("get_track_list", {}), ("get_warp_state", {"track_index": 1, "clip_index": 0})]


def _failure(name: str, result: Any) -> str | None:
    text = "".join(getattr(block, "text", "") for block in result.content)
    if result.is_error:
        return f"{name}: is_error ({text[:200]})"
    if text.startswith("Error:") and not (
        name == "get_ableton_logs" and "could not be resolved" in text
    ):
        return f"{name}: {text[:200]}"
    payload = _json_or_none(text)
    if isinstance(payload, dict) and (
        payload.get("ok") is False or payload.get("status") == "error"
    ):
        return f"{name}: error payload ({text[:200]})"
    return None


def _json_or_none(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None


async def _run_calls(calls: list[tuple[str, dict[str, Any]]]) -> list[str]:
    failures: list[str] = []
    async with FastMCPClient(server.mcp) as client:
        tools = await client.list_tools()
        assert tools, "tools/list returned nothing"
        for name, arguments in calls:
            result = await client.call_tool(name, arguments, raise_on_error=False)
            problem = _failure(name, result)
            if problem:
                failures.append(problem)
    return failures


# --------------------------------------------------------------------------- tests


def test_tool_calls_stay_on_loopback(loopback_bridges: dict[str, int], tmp_path: Path) -> None:
    failures = asyncio.run(_run_calls(_bridge_calls() + _offline_calls(tmp_path)))
    observed = list(_observed)

    assert not failures, f"tool calls returned errors: {failures}"
    remote = [item for item in observed if item[1] not in LOOPBACK]
    assert not remote, f"non-loopback destinations: {remote}"
    tcp_seen = [o for o in observed if o[0] == "socket.connect" and o[2] == loopback_bridges["tcp"]]
    ws_seen = [
        o for o in observed if o[0] == "create_connection" and o[2] == loopback_bridges["ws"]
    ]
    assert tcp_seen, f"socket.connect never observed the TCP bridge: {observed}"
    assert ws_seen, f"create_connection never observed the WebSocket bridge: {observed}"


_BANNED_PYTHON = {"requests", "httpx", "aiohttp", "urllib.request", "http.client", "subprocess"}
_SUBPROCESS_ALLOWED = {
    "ableton_mcp_server/groove_intelligence/neural_subprocess.py",
    "ableton_mcp_server/groove_intelligence/resource_limits.py",
    "ableton_mcp_server/server.py",
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _banned_in(names: set[str]) -> set[str]:
    return {b for b in _BANNED_PYTHON for n in names if n == b or n.startswith(b + ".")}


def test_python_sources_import_no_network_client() -> None:
    offenders: list[str] = []
    for root in ("ableton_mcp_server", "AbletonMCPServer_RemoteScript"):
        for path in sorted((REPO / root).rglob("*.py")):
            relative = path.relative_to(REPO).as_posix()
            banned = _banned_in(_imported_modules(path))
            if relative in _SUBPROCESS_ALLOWED:
                banned.discard("subprocess")
            if banned:
                offenders.append(f"{relative}: {sorted(banned)}")
    assert not offenders, f"network or process imports: {offenders}"


_EXTENSION_PATTERNS = (
    re.compile(r"\bfetch\s*\("),
    re.compile(r"""(?:from\s+|require\s*\(\s*)['"](?:node:)?(?:http|https|net|dgram)['"]"""),
)


def test_bundled_extension_sources_use_no_network_module() -> None:
    offenders: list[str] = []
    for path in sorted((REPO / "AbletonMCPServer_Extension" / "src").rglob("*")):
        if path.suffix not in {".ts", ".js", ".mjs", ".cjs"}:
            continue
        text = path.read_text(encoding="utf-8")
        if any(pattern.search(text) for pattern in _EXTENSION_PATTERNS):
            offenders.append(path.relative_to(REPO).as_posix())
    assert not offenders, f"extension sources with network calls: {offenders}"


_TELEMETRY_PROBE = r"""
import importlib.util, json, os
from ableton_mcp_server import server  # noqa: F401
from opentelemetry import trace
from fastmcp.telemetry import get_tracer
span = get_tracer().start_span("probe")
print(json.dumps({
    "env": {k: os.environ.get(k) for k in
            ("OTEL_SDK_DISABLED", "FASTMCP_TELEMETRY_DISABLED", "MCP_TELEMETRY_DISABLED")},
    "provider": type(trace.get_tracer_provider()).__module__,
    "recording": span.is_recording(),
    "sdk": importlib.util.find_spec("opentelemetry.sdk") is not None,
}))
"""
_TELEMETRY_VARS = ("OTEL_SDK_DISABLED", "FASTMCP_TELEMETRY_DISABLED", "MCP_TELEMETRY_DISABLED")


def _telemetry_state(preset: dict[str, str]) -> dict[str, Any]:
    env = {k: v for k, v in os.environ.items() if k not in _TELEMETRY_VARS}
    env.update(preset)
    out = subprocess.run(
        [sys.executable, "-c", _TELEMETRY_PROBE],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return dict(json.loads(out.stdout.strip().splitlines()[-1]))


def test_telemetry_is_off_by_default_and_user_values_are_kept() -> None:
    default = _telemetry_state({})
    assert default["env"] == dict.fromkeys(_TELEMETRY_VARS, "true")
    assert not default["provider"].startswith("opentelemetry.sdk")
    assert default["recording"] is False
    assert default["sdk"] is False, "an OpenTelemetry SDK is installed in this environment"

    preset = _telemetry_state(dict.fromkeys(_TELEMETRY_VARS, "false"))
    assert preset["env"] == dict.fromkeys(_TELEMETRY_VARS, "false")
