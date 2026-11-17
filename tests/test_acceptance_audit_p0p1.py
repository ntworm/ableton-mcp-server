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
from pathlib import Path
from typing import Any

import pytest

from ableton_mcp_server.acceptance import run_live_acceptance

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
        _write_fake_extension_project(project)
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
        _assert_build_extension_steps(parsed)
        _assert_build_extension_artifacts(parsed)


def _write_fake_extension_project(project: Path) -> None:
    """Write a fake extension project that declares its own entrypoint."""
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


def _assert_build_extension_steps(parsed: dict[str, Any]) -> None:
    """Assert the build reported a built status, its entrypoint and clean steps."""
    assert parsed["status"] == "built"
    assert parsed["entrypoint"] == "dist/extension.js"
    assert parsed["entrypoint_exists"] is True
    assert isinstance(parsed["steps"], list) and parsed["steps"], f"steps missing: {parsed}"
    for index, step in enumerate(parsed["steps"]):
        assert int(step.get("returncode", -1)) == 0, f"step {index} returncode != 0: {step}"


def _assert_build_extension_artifacts(parsed: dict[str, Any]) -> None:
    """Assert the top-level ``artifacts`` list carries the declared entrypoint."""
    # Top-level ``artifacts`` list with the declared entrypoint.
    assert isinstance(parsed.get("artifacts"), list), (
        f"artifacts missing or wrong shape: {parsed}"
    )
    assert "dist/extension.js" in parsed["artifacts"], (
        f"declared entrypoint not in artifacts: {parsed}"
    )


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
    _assert_set_tempo_failed_on_restore_readback(cert)
    assert cert["release_ready"] is False, (
        "release_ready must be False when a tracked row fails on "
        "cleanup readback: "
        f"{[r for r in cert['tools'] if r['status'] == 'failed']}"
    )
    mutation_commands = [command for command, _params in bridge.tcp_calls]
    assert "create_audio_track" not in mutation_commands
    assert "create_midi_track" not in mutation_commands
    _assert_track_creation_rows_failed_on_cleanup(cert)
    assert cert["release_ready"] is False


def _assert_set_tempo_failed_on_restore_readback(cert: dict[str, Any]) -> None:
    """Assert ``set_tempo`` failed because the restore readback drifted."""
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


def _assert_track_creation_rows_failed_on_cleanup(cert: dict[str, Any]) -> None:
    """Assert both track creation rows failed on the cleanup readback."""
    create_rows = {
        row["tool"]: row
        for row in cert["tools"]
        if row["tool"] in {"create_audio_track", "create_midi_track"}
    }
    assert {row["status"] for row in create_rows.values()} == {"failed"}
    assert all("cleanup" in row["evidence"].lower() for row in create_rows.values())


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


def __getattr__(name: str) -> Any:
    """Expose the tests moved to ``test_acceptance_audit_p0p1_part2``.

    The lookup is lazy so the two modules never import each other while
    they load, and so pytest does not collect the same test twice.
    """

    from . import test_acceptance_audit_p0p1_part2 as _part2

    return getattr(_part2, name)
