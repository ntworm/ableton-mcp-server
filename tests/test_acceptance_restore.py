"""Unit tests for ``ableton_mcp_server.acceptance.restore``.

Covers ``RestoreEngine`` register / run_all happy path, sync vs async
restores, failure capture, and registration order preservation.
"""

from __future__ import annotations

import pytest

from ableton_mcp_server.acceptance.restore import RestoreEngine, RestoreOp


class _FakeClient:
    """Minimal stub satisfying the AcceptanceClient protocol shape."""

    host = "127.0.0.1"
    port = 0

    def call(self, command_type: str, params=None, *, timeout=None):  # noqa: ARG002
        return None

    async def call_ws(self, method: str, params=None, *, timeout: float = 2.0):  # noqa: ARG002
        return None


class TestRestoreEngineBasics:
    def test_empty_engine_runs_clean(self) -> None:
        import asyncio

        engine = RestoreEngine(_FakeClient(), artifacts={})
        failures = asyncio.run(engine.run_all())
        assert failures == []
        assert engine.failures == []
        assert engine.ops == ()

    def test_register_appends_in_order(self) -> None:
        engine = RestoreEngine(_FakeClient(), artifacts={})
        engine.register(label="a", tool="t1", restore=lambda: None, verify=lambda _o: None)
        engine.register(label="b", tool="t2", restore=lambda: None, verify=lambda _o: None)
        engine.register(label="c", tool="t3", restore=lambda: None, verify=lambda _o: None)
        ops = engine.ops
        assert len(ops) == 3
        assert [op.label for op in ops] == ["a", "b", "c"]
        assert [op.tool for op in ops] == ["t1", "t2", "t3"]


class TestRestoreEngineExecution:
    def _run(self, coro):
        import asyncio

        return asyncio.run(coro)

    def test_sync_restore_and_verify_called(self) -> None:
        called: list[str] = []

        def restore() -> str:
            called.append("restore")
            return "observed"

        def verify(observed: str) -> None:
            called.append(f"verify:{observed}")

        engine = RestoreEngine(_FakeClient(), artifacts={})
        engine.register(label="x", tool="t", restore=restore, verify=verify)
        self._run(engine.run_all())
        assert called == ["restore", "verify:observed"]
        assert engine.failures == []

    def test_async_restore_and_verify_called(self) -> None:
        called: list[str] = []

        async def restore() -> str:
            called.append("restore")
            return "async-observed"

        async def verify(observed: str) -> None:
            called.append(f"verify:{observed}")

        engine = RestoreEngine(_FakeClient(), artifacts={})
        engine.register(label="x", tool="t", restore=restore, verify=verify)
        self._run(engine.run_all())
        assert called == ["restore", "verify:async-observed"]
        assert engine.failures == []

    def test_sync_and_async_interleave_in_registration_order(self) -> None:
        called: list[str] = []

        def sync_restore() -> None:
            called.append("sync-r")

        def sync_verify(_o: object) -> None:
            called.append("sync-v")

        async def async_restore() -> None:
            called.append("async-r")

        async def async_verify(_o: object) -> None:
            called.append("async-v")

        engine = RestoreEngine(_FakeClient(), artifacts={})
        engine.register(label="s", tool="t1", restore=sync_restore, verify=sync_verify)
        engine.register(label="a", tool="t2", restore=async_restore, verify=async_verify)
        self._run(engine.run_all())
        # Each restore completes (incl. its verify) before the next runs.
        assert called == ["sync-r", "sync-v", "async-r", "async-v"]

    def test_restore_failure_captured_and_does_not_abort(self) -> None:
        called: list[str] = []

        def failing_restore() -> None:
            called.append("failing")
            raise RuntimeError("kaboom")

        def good_restore() -> None:
            called.append("good")

        def verify(_o: object) -> None:
            return None

        engine = RestoreEngine(_FakeClient(), artifacts={})
        engine.register(label="bad", tool="t1", restore=failing_restore, verify=verify)
        engine.register(label="ok", tool="t2", restore=good_restore, verify=verify)
        failures = self._run(engine.run_all())
        assert called == ["failing", "good"], "second restore must still run"
        assert len(failures) == 1
        assert failures[0][0] == "bad"
        assert "RuntimeError" in failures[0][1]
        assert "kaboom" in failures[0][1]

    def test_verify_failure_captured(self) -> None:
        def restore() -> str:
            return "x"

        def verify(_o: object) -> None:
            raise AssertionError("verify failed")

        engine = RestoreEngine(_FakeClient(), artifacts={})
        engine.register(label="v", tool="t", restore=restore, verify=verify)
        failures = self._run(engine.run_all())
        assert len(failures) == 1
        assert failures[0][0] == "v"
        assert "AssertionError" in failures[0][1]

    def test_failures_property_kept_until_next_run_all(self) -> None:
        engine = RestoreEngine(_FakeClient(), artifacts={})

        def failing() -> None:
            raise RuntimeError("once")

        def good() -> None:
            return None

        engine.register(label="bad", tool="t1", restore=failing, verify=lambda _o: None)
        self._run(engine.run_all())
        assert len(engine.failures) == 1

        # Second run with the failing op removed: failures reset.
        engine._ops.clear()
        engine.register(label="ok", tool="t2", restore=good, verify=lambda _o: None)
        self._run(engine.run_all())
        assert engine.failures == []

    def test_artifacts_passed_through(self) -> None:
        artifacts: dict[str, object] = {"initial": True}
        engine = RestoreEngine(_FakeClient(), artifacts=artifacts)
        # The engine shares the dict; mutations through restore would be visible.
        assert engine._artifacts is artifacts  # type: ignore[attr-defined]


class TestRestoreOp:
    def test_op_is_frozen(self) -> None:
        op = RestoreOp(label="x", tool="t", restore=lambda: None, verify=lambda _o: None)
        with pytest.raises((AttributeError, Exception)):
            op.label = "y"  # type: ignore[misc]

    def test_op_fields_accessible(self) -> None:
        def r() -> object:
            return "r"

        def v(_o: object) -> None:
            return None

        op = RestoreOp(label="x", tool="t", restore=r, verify=v)
        assert op.label == "x"
        assert op.tool == "t"
        assert op.restore is r
        assert op.verify is v
