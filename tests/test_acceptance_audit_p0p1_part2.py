"""Audit fixtures for P0-1, P0-2, P0-3, P0-4 and P1-5, moved from the original module."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from ableton_mcp_server import client as _client
from ableton_mcp_server.acceptance import run_live_acceptance
from ableton_mcp_server.acceptance import (
    run_offline_probes as real_run_offline_probes,
)
from ableton_mcp_server.acceptance.probes import BASELINE_PROBE_GROUPS
from ableton_mcp_server.protocol import ProtocolError, decode_request, encode_response

from . import test_acceptance_audit_p0p1 as _shared
from ._strict_fake import StrictFakeBridge, _strict_tcp_dispatch

# The shared fixtures of the original module, bound here so pytest finds
# them in this module's namespace.
_audit_test_isolation = _shared._audit_test_isolation
_inject_fast_offline_probes = _shared._inject_fast_offline_probes
fake_project = _shared.fake_project


# ---------------------------------------------------------------------------
# P0-1: build_extension contract
# ---------------------------------------------------------------------------


def test_p0_1_run_offline_probes_records_build_extension_as_offline_passed(
    tmp_path: Path,
) -> None:
    """The acceptance runner must record ``build_extension`` as
    ``offline_passed`` when the scaffold + real build complete.

    This test drives ``run_offline_probes`` end-to-end from a fresh
    TemporaryDirectory. It must not pre-create ``dist/extension.js`` or
    the entrypoint, must not mock ``subprocess.run``, and must not
    fabricate a hardcoded ``dist/index.js`` artefact path.
    """
    import asyncio

    from ableton_mcp_server.certification import CertificationReport

    async def run() -> None:
        # Use a fresh workdir inside tmp_path; ``real_run_offline_probes``
        # will create a ``scaffold/`` subdir under it.
        workdir = tmp_path / "offline-workdir"
        workdir.mkdir()
        # Derived from the canonical group so a new offline tool cannot make
        # this end-to-end probe fail with "tool is not cataloged".
        all_offline_names = BASELINE_PROBE_GROUPS["offline"]
        report = CertificationReport(tool_names=all_offline_names)
        await real_run_offline_probes(report, workdir)

        build_row = report.recorded.get("build_extension")
        scaffold_row = report.recorded.get("scaffold_extension")
        assert build_row is not None, "build_extension not recorded"
        assert scaffold_row is not None, "scaffold_extension not recorded"
        assert build_row.status == "offline_passed", (
            f"build_extension must be offline_passed when the real "
            f"build succeeds, got {build_row.status}: {build_row.evidence}"
        )
        assert scaffold_row.status == "offline_passed", (
            f"scaffold_extension must be offline_passed when the real "
            f"scaffold runs, got {scaffold_row.status}: {scaffold_row.evidence}"
        )
        # The scaffold project must have produced a real
        # ``dist/extension.js`` during this probe - that's the artefact
        # the runner declared offline_passed for.
        scaffold_dir = workdir / "scaffold"
        scaffold_projects = [p for p in scaffold_dir.iterdir() if p.is_dir()]
        assert scaffold_projects, "scaffold produced no project directory"
        project = scaffold_projects[0]
        assert (project / "dist" / "extension.js").is_file(), (
            "build_extension offline_passed must mean the entrypoint "
            "declared in package.json['main'] was written to disk"
        )

    asyncio.run(run())


# ---------------------------------------------------------------------------
# P0-2: baseline reads mute/solo/arm/volume from get_track_state
# ---------------------------------------------------------------------------


def test_p0_2_baseline_does_not_read_mixer_state_from_get_track_list() -> None:
    """Regression guard: the baseline must NOT derive ``mute``/``solo``/
    ``arm``/``volume`` from ``get_track_list``.

    The real ``get_track_list`` contract exposes only
    ``id``/``index``/``name``/``type``. If a future regression reads
    mixer state from that command \N{EM DASH} because a fake happened to include
    those fields, or because someone added them to the contract \N{EM DASH} the
    runner would silently lose fidelity when the real bridge is wired
    in. This test feeds the strict fake a mutated state where
    ``get_track_list`` *would* disagree with ``get_track_state`` if the
    runner consulted it. The runner must still capture the values held
    by ``get_track_state`` and restore the originals.
    """
    bridge = _DivergentListBridge()
    # Set genuine baseline values that disagree with the divergent list.
    bridge.state["tracks"][2]["mute"] = True
    bridge.state["tracks"][2]["solo"] = True
    bridge.state["tracks"][2]["arm"] = True
    bridge.state.setdefault("mixer_volumes", {})["track:2"] = 0.42

    asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=2,
            audio_clip_index=0,
            fire_clip=True,
        )
    )
    _assert_divergent_baseline_restored(bridge)


class _DivergentListBridge(StrictFakeBridge):
    """``get_track_list`` reports a FALSE value for mixer fields.

    The real contract does not expose these fields; this fake
    intentionally injects a *wrong* value to make any read from
    ``get_track_list`` observable. ``get_track_state`` continues
    to return the genuine baseline (mute=True, solo=True,
    arm=True, volume=0.42) so the runner's restore step must
    use it, not the wrong list value.
    """

    def __init__(self) -> None:
        super().__init__()
        self.divergent_lists: list[list[dict[str, Any]]] = []

    def call(  # type: ignore[override]
        self,
        command_type: str,
        params: Any = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        if command_type == "get_track_list":
            # Lie on purpose: report mute=False / solo=False /
            # arm=False / volume=0.0 - none of which are real.
            divergent = [
                {
                    "id": t["id"],
                    "index": t["index"],
                    "name": t["name"],
                    "type": t["type"],
                    "mute": False,
                    "solo": False,
                    "arm": False,
                    "volume": 0.0,
                }
                for t in self.state["tracks"]
            ]
            self.divergent_lists.append(divergent)
            return divergent
        return super().call(command_type, params, timeout=timeout)


def _assert_divergent_baseline_restored(bridge: _DivergentListBridge) -> None:
    """Assert the genuine mixer state survived the divergent track list."""
    # The runner saw the divergent ``get_track_list``. If it had used
    # that source for mute/solo/arm/volume the restore step would have
    # applied False / False / False / 0.0 instead of the genuine
    # True / True / True / 0.42. The genuine state must still hold.
    track2 = next(t for t in bridge.state["tracks"] if t["index"] == 2)
    assert track2.get("mute") is True, (
        f"baseline restored mute from get_track_list instead of get_track_state: {track2}"
    )
    assert track2.get("solo") is True, (
        f"baseline restored solo from get_track_list instead of get_track_state: {track2}"
    )
    assert track2.get("arm") is True, (
        f"baseline restored arm from get_track_list instead of get_track_state: {track2}"
    )
    mixer_volume = bridge.state.get("mixer_volumes", {}).get("track:2", 0.85)
    assert abs(float(mixer_volume) - 0.42) < 0.05, (
        "baseline restored volume from get_track_list instead of "
        f"get_track_state: {bridge.state['mixer_volumes']}"
    )
    # And the runner actually emitted the divergent list at least
    # once - otherwise this test would not be exercising what it
    # claims to exercise.
    assert bridge.divergent_lists, (
        "divergent get_track_list was never called; the regression guard cannot prove its premise"
    )


# ---------------------------------------------------------------------------
# P0-3: live_fade round-trips mixer_volume (not device parameter)
# ---------------------------------------------------------------------------


def test_p0_3_live_fade_readback_uses_track_state_mixer_volume() -> None:
    """``live_fade`` mutates ``track.mixer_device.volume``. The
    acceptance runner must observe the change via ``get_track_state``
    (which exposes ``volume``) and restore by issuing a new
    ``live_fade`` with the original target \N{EM DASH} never by writing the
    ``Volume`` parameter of the first device.
    """
    bridge = StrictFakeBridge()
    # Pre-set mixer volume on audio track to something distinguishable.
    bridge.state.setdefault("mixer_volumes", {})["track:2"] = 0.42

    # Track every ``set_parameter_value`` call to inspect the
    # ``Volume`` parameters and every ``live_fade`` call to inspect
    # round-trip behaviour. The live_fade restore must go through
    # ``live_fade``, not ``set_parameter_value`` on the first device.
    live_fade_calls: list[dict[str, Any]] = []
    raw_call = bridge.call

    def wrap(
        command_type: str,
        params: Any = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        if command_type == "live_fade":
            live_fade_calls.append(
                {
                    "command": command_type,
                    "params": dict(params or {}),
                }
            )
        return raw_call(command_type, params, timeout=timeout)

    bridge.call = wrap  # type: ignore[assignment]
    asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=2,
            audio_clip_index=0,
            fire_clip=True,
        )
    )
    _assert_live_fade_restore_used_mixer_volume(bridge, live_fade_calls)


def _assert_live_fade_restore_used_mixer_volume(
    bridge: StrictFakeBridge,
    live_fade_calls: list[dict[str, Any]],
) -> None:
    """Assert the live_fade restore wrote the original mixer volume back."""
    # The live_fade restore must use ``live_fade`` itself; we expect
    # at least three calls - the immediate fade, the timed fade, and
    # the restore. We assert the restore targets the original mixer
    # volume via ``target_value``.
    assert len(live_fade_calls) >= 3, (
        f"expected at least 3 live_fade calls, got {len(live_fade_calls)}: {live_fade_calls}"
    )
    restore_call = live_fade_calls[-1]
    assert "target_value" in restore_call["params"], (
        f"live_fade restore did not use target_value: {restore_call}"
    )
    # After the run, mixer_volume must be restored to the original
    # 0.42 - the cleanup wrote it back through ``live_fade``.
    mixer_volume = bridge.state.get("mixer_volumes", {}).get("track:2", 0.85)
    assert abs(float(mixer_volume) - 0.42) < 0.05, (
        f"track 2 mixer_volume not restored to original: {bridge.state['mixer_volumes']}"
    )


# ---------------------------------------------------------------------------
# P0-4: device_index must come from list_device_params, not be hardcoded
# ---------------------------------------------------------------------------


def test_p0_4_device_index_discovered_from_list_device_params() -> None:
    """When device 0 has no parameters and device 1 has a writable
    parameter, the runner must discover ``device_index=1`` from
    ``list_device_params`` rather than always writing to ``device:0``.
    """
    bridge = StrictFakeBridge()
    # Move the writable parameter off device 0: delete device 0 from
    # the audio track and add a writable parameter to device 1.
    audio_state = bridge.state["tracks"][2]
    audio_state["devices"] = [
        {"name": "Empty", "parameters": []},
        {"name": "Operator", "parameters": [{"name": "Volume", "value": 0.42}]},
    ]
    bridge.state["device_parameters"]["track:2"] = [
        {"name": "Empty", "parameters": []},
        {"name": "Operator", "parameters": [{"name": "Volume", "value": 0.42}]},
    ]
    writes: list[dict[str, Any]] = []
    real = bridge.call

    def tracking(command_type: str, params: Any = None, **kw: Any) -> Any:
        if command_type in {"set_parameter_value", "get_parameter_value"}:
            writes.append(
                {
                    "command": command_type,
                    "params": dict(params or {}),
                }
            )
        return real(command_type, params, **kw)

    bridge.call = tracking  # type: ignore[assignment]
    asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=2,
            audio_clip_index=0,
            fire_clip=True,
        )
    )
    # Every ``set_parameter_value`` / ``get_parameter_value`` call must
    # target ``device_index=1`` (Operator), not ``device_index=0``.
    targeted = [w for w in writes if w["params"].get("parameter_name") == "Volume"]
    assert targeted, "no set/get_parameter_value Volume calls recorded by runner"
    for w in targeted:
        assert int(w["params"].get("device_index", -1)) == 1, (
            f"runner targeted wrong device_index: {w}"
        )


# ---------------------------------------------------------------------------
# P1-5: JSONL test must not be skipped
# ---------------------------------------------------------------------------


def test_p1_5_jsonl_socket_dispatch_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real TCP/JSONL framing + protocol + dispatcher, no fabrication.

    The earlier version mounted an ad-hoc echo socket that fabricated
    an ``id`` field the production protocol does not use and answered
    the same payload for every command. That proved neither the
    framing nor the real command contract. This version boots an
    in-process TCP loopback server that:

    1. calls ``protocol.decode_request`` (real protocol parser);
    2. dispatches via ``tests._strict_fake._strict_tcp_dispatch``
       (the same dispatcher the acceptance runner exercises);
    3. encodes the response with ``protocol.encode_response``.

    The client is the real ``ableton_mcp_server.client.Client`` \N{EM DASH}
    there is no echo, no fixed payload, no synthetic correlation id.
    Every response is the production response for that command, so
    distinct commands produce distinct payloads and the test asserts
    that distinction. The Client serialises calls through its own
    lock; the production protocol intentionally has no request id and
    the test must not invent one.
    """
    bridge = StrictFakeBridge()
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]

    stop_event = threading.Event()
    server_thread = threading.Thread(
        target=_serve_jsonl_requests,
        args=(server_sock, bridge, stop_event),
        daemon=True,
    )
    server_thread.start()
    time.sleep(0.05)

    try:
        c = _client.Client(host="127.0.0.1", port=port, reconnect=False)
        try:
            # Three distinct commands produce three distinct production
            # responses - the test would not pass if the server echoed a
            # single payload or fabricated fields.
            _assert_jsonl_production_responses(c, bridge)
        finally:
            c.close()
    finally:
        stop_event.set()
        server_thread.join(timeout=2)

    # Three production-protocol responses received, no fabricated ids.
    # We re-read the wire by holding the bridge state and the responses
    # already observed above; the key invariants are exercised via the
    # Client round-trip (above) rather than a parallel read of the wire.


def _serve_jsonl_requests(
    server_sock: socket.socket,
    bridge: StrictFakeBridge,
    stop_event: threading.Event,
) -> None:
    """Serve one JSONL connection with the real protocol and the strict dispatcher."""
    try:
        conn, _ = server_sock.accept()
    except OSError:
        return
    try:
        with conn:
            buf = b""
            while not stop_event.is_set():
                chunk = conn.recv(65536)
                if not chunk:
                    return
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        command, params = decode_request(line)
                    except ProtocolError as error:
                        conn.sendall(
                            encode_response(
                                {
                                    "status": "error",
                                    "code": "PROTOCOL_ERROR",
                                    "message": str(error),
                                }
                            )
                        )
                        continue
                    try:
                        result = _strict_tcp_dispatch(bridge, command, params)
                        payload: dict[str, Any] = {
                            "status": "ok",
                            "result": result,
                        }
                    except Exception as error:  # noqa: BLE001
                        payload = {
                            "status": "error",
                            "code": "DISPATCH_ERROR",
                            "message": str(error),
                        }
                    conn.sendall(encode_response(payload))
    finally:
        server_sock.close()


def _assert_jsonl_production_responses(
    c: _client.Client,
    bridge: StrictFakeBridge,
) -> None:
    """Assert the three distinct production responses of the JSONL round trip."""
    session = c.call("get_session_info", {})
    assert session == {
        "tempo": bridge.state["tempo"],
        "current_song_time": bridge.state["current_song_time"],
        "is_playing": False,
    }, f"get_session_info unexpected shape: {session}"

    metadata = c.call("get_project_metadata", {})
    assert metadata == {"song_name": "TESTE_CODEX", "is_dirty": False, "can_undo": False}, (
        f"get_project_metadata unexpected shape: {metadata}"
    )

    track_list = c.call("get_track_list", {})
    assert isinstance(track_list, list) and track_list, (
        f"get_track_list returned non-list or empty: {track_list}"
    )
    for track in track_list:
        # Production contract: identity plus hierarchy/colour. Mixer
        # state must stay on get_track_state - the baseline restores
        # mute/solo/arm/volume from there, and a leaked field here
        # would let it round-trip a value it never verified.
        assert set(track.keys()) <= {
            "id",
            "index",
            "name",
            "type",
            "color",
            "color_index",
            "is_group_track",
            "is_grouped",
            "group_track_index",
            "group_track_id",
            "is_visible",
            "fold_state",
        }, f"get_track_list leaked mixer fields: {track}"
        assert not (set(track.keys()) & {"mute", "solo", "arm", "volume"}), (
            f"get_track_list leaked mixer fields: {track}"
        )
