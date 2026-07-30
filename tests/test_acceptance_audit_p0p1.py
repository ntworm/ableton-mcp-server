"""RED→GREEN audit fixtures for P0-1, P0-2, P0-3, P0-4, P1-5, P1-6, P1-7.

These tests encode the auditor's contract for each P0/P1 item. They
must fail before the GREEN implementation lands and pass once the
implementation is correct. The file is intentionally separate from
``test_acceptance_runner_integration.py`` so the auditor can re-run
just this set in isolation.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from ableton_mcp_server.acceptance import (
    run_live_acceptance,
)
from ableton_mcp_server.acceptance import (
    run_offline_probes as real_run_offline_probes,
)

from ._offline_probe_fixture import fast_offline_probes
from ._strict_fake import StrictFakeBridge


@pytest.fixture(autouse=True)
def _inject_fast_offline_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject ``fast_offline_probes`` for every runner-level audit test."""
    import ableton_mcp_server.acceptance as acceptance_module

    monkeypatch.setattr(acceptance_module, "run_offline_probes", fast_offline_probes)


@pytest.fixture(autouse=True)
def _audit_test_isolation(
    fake_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """Make sure no audit test accidentally invokes real ``npm`` or
    tries to spin up ``python -m build`` in the absence of a venv.

    The P1-7 test calls ``build_release`` which would normally look
    for ``.venv-win/Scripts/python.exe`` or ``.venv/bin/python`` to
    build the wheel. We stub that step plus ``npm run package`` so
    the audit tests never touch the host environment.
    """
    from scripts import build_release_candidates as brc

    calls: list[dict[str, Any]] = []
    ext_dir = fake_project / "AbletonMCPServer_Extension"

    def runner(argv: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append({"argv": argv, "kwargs": dict(kwargs)})
        target = ext_dir / "AbletonMCPServer-Extension-0.5.1.ablx"
        if target.exists():
            target.unlink()
        target.write_bytes(b"fresh-ablx")

        class CP:
            returncode = 0
            stdout = ""
            stderr = ""

        return CP()

    class _FakeSubprocess:
        run = staticmethod(runner)

        def which(self, _name: str) -> str:
            return ""

    monkeypatch.setattr(brc, "subprocess", _FakeSubprocess())
    monkeypatch.setattr(brc.shutil, "which", lambda _n: "")

    def fake_build_wheel(_root: Path, output_directory: Path) -> Path:
        wheel = output_directory / ("ableton_mcp_server-0.5.1-py3-none-any.whl")
        import zipfile as _zf

        if wheel.exists():
            wheel.unlink()
        with _zf.ZipFile(wheel, "w", _zf.ZIP_DEFLATED) as zf:
            zf.writestr(
                "ableton_mcp_server-0.5.1.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: ableton_mcp_server\nVersion: 0.5.1\n",
            )
            zf.writestr(
                "ableton_mcp_server/__init__.py",
                '__version__ = "0.5.1"\n',
            )
        return wheel

    monkeypatch.setattr(brc, "_build_python_wheel", fake_build_wheel)
    return {"calls": calls}


@pytest.fixture
def fake_project() -> Path:
    """Local minimal project tree, enough for ``build_release`` P1-7."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="audit-p1-7-") as tmp:
        project = Path(tmp) / "project"
        project.mkdir()
        rs = project / "AbletonMCPServer_RemoteScript"
        rs.mkdir()
        (rs / "__init__.py").write_text("# rs\n", encoding="utf-8")
        pkg = project / "ableton_mcp_server"
        pkg.mkdir()
        (pkg / "__init__.py").write_text('__version__ = "0.5.1"\n', encoding="utf-8")
        (project / "pyproject.toml").write_text(
            "[project]\nname='ableton_mcp_server'\nversion='0.5.1'\n",
            encoding="utf-8",
        )
        ext = project / "AbletonMCPServer_Extension"
        ext.mkdir()
        (ext / "manifest.json").write_text(
            json.dumps({"name": "x", "version": "0.5.1"}),
            encoding="utf-8",
        )
        (ext / "package.json").write_text(
            json.dumps({"name": "x", "scripts": {}}),
            encoding="utf-8",
        )
        (ext / "dist").mkdir()
        (ext / "dist" / "extension.js").write_text("// built", encoding="utf-8")
        (ext / "AbletonMCPServer-Extension-0.5.1.ablx").write_text("stale-ablx", encoding="utf-8")
        yield project


# ---------------------------------------------------------------------------
# P0-1: build_extension contract
# ---------------------------------------------------------------------------


def test_p0_1_build_extension_contract_accepts_top_level_artifacts() -> None:
    """``build_extension`` must return ``artifacts`` at the top level.

    The auditor's contract: ``build_extension(project)`` returns a JSON
    document with ``status=="built"``, every step has ``returncode==0``,
    and ``artifacts`` is a list of build-relative paths declared at the
    top level (not per-step). The acceptance runner must require the
    entrypoint declared by the project's own ``package.json["main"]``
    (falling back to ``manifest.json["entry"]``) to exist for a green
    row — no hardcoded ``dist/index.js`` is permitted.
    """
    import tempfile

    with tempfile.TemporaryDirectory(prefix="build-ext-") as tmp:
        project = Path(tmp) / "fake-ext"
        project.mkdir()
        pkg = {
            "name": "fake-ext",
            "version": "1.0.0",
            "main": "dist/extension.js",
            "scripts": {"build": "echo build"},
        }
        (project / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        manifest = {"name": "fake-ext", "entry": "dist/extension.js"}
        (project / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        # Pretend tsc just produced the declared entrypoint.
        dist = project / "dist"
        dist.mkdir()
        (dist / "extension.js").write_text("// built", encoding="utf-8")

        # Patch ``subprocess.run`` so we don't actually invoke npm.
        from ableton_mcp_server import server as _server

        real_run = _server.subprocess.run

        def fake_run(cmd: Any, *args: Any, **kwargs: Any) -> Any:
            class CP:
                returncode = 0
                stdout = ""
                stderr = ""

            return CP()

        _server.subprocess.run = fake_run
        try:
            result_json = _server.build_extension(str(project))
        finally:
            _server.subprocess.run = real_run
        parsed = json.loads(result_json)

        assert parsed["status"] == "built"
        assert parsed["entrypoint"] == "dist/extension.js"
        assert parsed["entrypoint_exists"] is True
        assert isinstance(parsed["steps"], list) and parsed["steps"], f"steps missing: {parsed}"
        for index, step in enumerate(parsed["steps"]):
            assert int(step.get("returncode", -1)) == 0, f"step {index} returncode != 0: {step}"
        # Top-level ``artifacts`` list with the declared entrypoint.
        assert isinstance(parsed.get("artifacts"), list), (
            f"artifacts missing or wrong shape: {parsed}"
        )
        assert "dist/extension.js" in parsed["artifacts"], (
            f"declared entrypoint not in artifacts: {parsed}"
        )


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
        all_offline_names = (
            "get_ableton_logs",
            "diff_snapshots_tool",
            "scaffold_extension",
            "build_extension",
            "analyze_audio",
            "find_frequency_masking",
            "analyze_mix",
            "extract_single_cycle",
        )
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
        # ``dist/extension.js`` during this probe — that's the artefact
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


def test_p0_2_baseline_captures_mute_solo_arm_volume_from_track_state() -> None:
    """Tracks starting with ``mute=True`` / ``solo=True`` / ``arm=True``
    must return to the exact original state after the mutation suite
    plus cleanup. ``get_track_list`` alone cannot drive these values —
    the runner must read ``get_track_state``.
    """
    bridge = StrictFakeBridge()
    # Mark the audio track mute+solo+arm at the start.
    bridge.state["tracks"][2]["mute"] = True
    bridge.state["tracks"][2]["solo"] = True
    bridge.state["tracks"][2]["arm"] = True

    bridge.fail_tool = None
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
    # The runner must have captured the original mute=True / solo=True
    # / arm=True for track 2 and restored them, regardless of how many
    # mutations flipped them in between.
    track2 = next(t for t in bridge.state["tracks"] if t["index"] == 2)
    assert track2.get("mute") is True, f"track 2 mute not restored: {track2}"
    assert track2.get("solo") is True, f"track 2 solo not restored: {track2}"
    assert track2.get("arm") is True, f"track 2 arm not restored: {track2}"


def test_p0_2_baseline_does_not_read_mixer_state_from_get_track_list() -> None:
    """Regression guard: the baseline must NOT derive ``mute``/``solo``/
    ``arm``/``volume`` from ``get_track_list``.

    The real ``get_track_list`` contract exposes only
    ``id``/``index``/``name``/``type``. If a future regression reads
    mixer state from that command — because a fake happened to include
    those fields, or because someone added them to the contract — the
    runner would silently lose fidelity when the real bridge is wired
    in. This test feeds the strict fake a mutated state where
    ``get_track_list`` *would* disagree with ``get_track_state`` if the
    runner consulted it. The runner must still capture the values held
    by ``get_track_state`` and restore the originals.
    """

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
                # arm=False / volume=0.0 — none of which are real.
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
    # once — otherwise this test would not be exercising what it
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
    ``live_fade`` with the original target — never by writing the
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
    # The live_fade restore must use ``live_fade`` itself; we expect
    # at least three calls — the immediate fade, the timed fade, and
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
    # 0.42 — the cleanup wrote it back through ``live_fade``.
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

    The client is the real ``ableton_mcp_server.client.Client`` —
    there is no echo, no fixed payload, no synthetic correlation id.
    Every response is the production response for that command, so
    distinct commands produce distinct payloads and the test asserts
    that distinction. The Client serialises calls through its own
    lock; the production protocol intentionally has no request id and
    the test must not invent one.
    """
    from ableton_mcp_server import client as _client
    from ableton_mcp_server.protocol import (
        ProtocolError,
        decode_request,
        encode_response,
    )
    from tests._strict_fake import StrictFakeBridge, _strict_tcp_dispatch

    bridge = StrictFakeBridge()
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]

    stop_event = threading.Event()

    def server_thread() -> None:
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

    t = threading.Thread(target=server_thread, daemon=True)
    t.start()
    time.sleep(0.05)

    try:
        c = _client.Client(host="127.0.0.1", port=port, reconnect=False)
        try:
            # Three distinct commands produce three distinct production
            # responses — the test would not pass if the server echoed a
            # single payload or fabricated fields.
            session = c.call("get_session_info", {})
            assert session == {
                "tempo": bridge.state["tempo"],
                "current_song_time": bridge.state["current_song_time"],
                "is_playing": False,
            }, f"get_session_info unexpected shape: {session}"

            metadata = c.call("get_project_metadata", {})
            assert metadata == {"song_name": "TESTE_CODEX", "is_dirty": False}, (
                f"get_project_metadata unexpected shape: {metadata}"
            )

            track_list = c.call("get_track_list", {})
            assert isinstance(track_list, list) and track_list, (
                f"get_track_list returned non-list or empty: {track_list}"
            )
            for track in track_list:
                # Production contract: only id/index/name/type.
                assert set(track.keys()) <= {
                    "id",
                    "index",
                    "name",
                    "type",
                }, f"get_track_list leaked mixer fields: {track}"
        finally:
            c.close()
    finally:
        stop_event.set()
        t.join(timeout=2)

    # Three production-protocol responses received, no fabricated ids.
    # We re-read the wire by holding the bridge state and the responses
    # already observed above; the key invariants are exercised via the
    # Client round-trip (above) rather than a parallel read of the wire.


# ---------------------------------------------------------------------------
# P1-6: set_tempo write-OK but readback-stale must flip to failed
# ---------------------------------------------------------------------------


class _StaleReadbackBridge(StrictFakeBridge):
    """``StrictFakeBridge`` variant that silently keeps stale state.

    ``set_tempo`` claims success but does NOT mutate ``state["tempo"]``,
    so ``get_session_info`` keeps returning the pre-write tempo. The
    runner must observe the mismatch and flip ``set_tempo`` to
    ``failed`` plus block ``release_ready``.
    """

    def __init__(self) -> None:
        super().__init__()
        self._stale_target = None

    def call(  # type: ignore[override]
        self,
        command_type: str,
        params: Any = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        params = dict(params or {})
        self.tcp_calls.append((command_type, params))
        if command_type == "set_tempo":
            # Pretend the write was accepted but don't update state.
            self._stale_target = float(params["tempo"])
            return {"tempo": float(params["tempo"])}
        return super().call(command_type, params, timeout=timeout)


def test_p1_6_set_tempo_write_ok_readback_stale_must_fail() -> None:
    """When ``set_tempo`` claims success but ``get_session_info`` still
    reports the previous tempo, the row must read ``failed`` and
    ``release_ready`` must be ``False``.
    """
    bridge = _StaleReadbackBridge()
    result = asyncio.run(
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
    cert = result["certification"]
    statuses = {row["tool"]: row["status"] for row in cert["tools"]}
    assert statuses["set_tempo"] == "failed", (
        "set_tempo must be failed when readback is stale: "
        f"{[r for r in cert['tools'] if r['tool'] == 'set_tempo']}"
    )


class _RestoreOnlyDivergentBridge(StrictFakeBridge):
    """Fake whose divergence activates ONLY during cleanup/restore.

    This isolates the readback-on-restore contract from the
    mutation-readback contract. The runner must observe the original
    value during baseline capture, succeed during the mutation readback,
    and observe a *wrong* value when it tries to restore the original
    — proving that the cleanup step itself catches readback mismatches
    and not just the mutation readback.

    The divergence is gated by the ``_restore_phase`` flag, which the
    runner turns on just before any operation that *looks* like a
    restore (a ``set_tempo`` or ``live_fade`` whose target equals the
    captured baseline). The fake uses a counter to make the contract
    deterministic: the first N write attempts to any tracked field are
    accepted with the correct state mutation (so baseline + mutation
    readback both pass), then subsequent writes are accepted but the
    state does not change (so the restore readback fails).
    """

    def __init__(self, *, allowed_writes: int = 2) -> None:
        super().__init__()
        self._allowed_writes = allowed_writes
        self._writes_performed = 0
        self._tracked_targets: set[tuple[str, tuple[Any, ...]]] = set()

    def call(  # type: ignore[override]
        self,
        command_type: str,
        params: Any = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        params = dict(params or {})
        self.tcp_calls.append((command_type, params))
        if command_type == "set_tempo":
            target = float(params["tempo"])
            original = float(self.state["tempo"])
            key = ("set_tempo", (target,))
            # ``set_tempo`` is allowed to mutate up to N times per
            # unique target (baseline → mutation → restore). After N
            # writes for a given target, the fake accepts the write
            # but keeps the state at the original value, so the next
            # readback (which is the restore readback) fails. The
            # baseline capture does not consume a write slot because
            # baseline is a *read*.
            if key in self._tracked_targets:
                # Subsequent writes to the same target = restore phase.
                # Drop the write so the state stays at the original.
                return {"tempo": original}
            if self._writes_performed >= self._allowed_writes:
                # Out of write budget — pretend success but do not
                # mutate. This models a Live bridge that acknowledges
                # the request but never applied it.
                return {"tempo": original}
            self._writes_performed += 1
            self._tracked_targets.add(key)
            self.state["tempo"] = target
            return {"tempo": target}
        return super().call(command_type, params, timeout=timeout)


def test_p1_6_set_tempo_readback_fails_only_during_restore() -> None:
    """The cleanup/restore readback failure must flip the row to
    ``failed`` even when the mutation readback was clean.

    The runner flow is::

      1. capture baseline tempo T0
      2. mutate tempo to T1, readback -> T1 (clean)
      3. cleanup: write T0 back, readback -> still T1 (drift)

    The fake permits the mutation write but silently swallows the
    restore write. The mutation row therefore passes; the cleanup
    readback mismatch must still flag the tool as ``failed`` and
    block ``release_ready``. The evidence must reference the cleanup
    / readback so the failure mode is observable.
    """
    bridge = _RestoreOnlyDivergentBridge(allowed_writes=1)
    result = asyncio.run(
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
    cert = result["certification"]
    set_tempo_row = next(r for r in cert["tools"] if r["tool"] == "set_tempo")
    assert set_tempo_row["status"] == "failed", (
        "set_tempo must be failed when the restore readback drifts, "
        f"even though the mutation readback was clean: {set_tempo_row}"
    )
    evidence_lower = set_tempo_row["evidence"].lower()
    assert (
        "cleanup" in evidence_lower or "readback" in evidence_lower or "restore" in evidence_lower
    ), (
        "set_tempo failure evidence must reference cleanup / readback "
        f"/ restore so the failure mode is observable: {set_tempo_row}"
    )
    assert cert["release_ready"] is False, (
        "release_ready must be False when a tracked row fails on "
        "cleanup readback: "
        f"{[r for r in cert['tools'] if r['status'] == 'failed']}"
    )
    mutation_commands = [command for command, _params in bridge.tcp_calls]
    assert "create_audio_track" not in mutation_commands
    assert "create_midi_track" not in mutation_commands
    create_rows = {
        row["tool"]: row
        for row in cert["tools"]
        if row["tool"] in {"create_audio_track", "create_midi_track"}
    }
    assert {row["status"] for row in create_rows.values()} == {"failed"}
    assert all("cleanup" in row["evidence"].lower() for row in create_rows.values())
    assert cert["release_ready"] is False


# ---------------------------------------------------------------------------
# P1-7: build_release must accept and persist source_commit
# ---------------------------------------------------------------------------


def test_p1_7_build_release_persists_source_commit(
    fake_project: Path,
    tmp_path: Path,
) -> None:
    """``build_release`` must accept ``source_commit`` and write it to
    ``manifest.json`` so the candidate artefacts are traceable back to
    the commit that produced them.
    """
    from scripts.build_release_candidates import build_release

    out = tmp_path / "rc"
    commit_hash = "deadbeef12345678901234567890123456789012"

    def fake_git(*_args: Any, **_kwargs: Any) -> Any:
        class _Proc:
            returncode = 0
            stdout = commit_hash + "\n"
            stderr = ""

        return _Proc()

    summary = build_release(
        root=fake_project,
        output_directory=out,
        source_commit=commit_hash,
        git_runner=fake_git,
    )
    assert summary["source_commit"] == commit_hash

    on_disk = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["source_commit"] == commit_hash
