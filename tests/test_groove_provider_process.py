from __future__ import annotations

import io
from pathlib import Path

import pytest

from ableton_mcp_server.groove_intelligence.neural_subprocess import (
    NeuralSubprocessProvider,
    ProviderProtocolError,
    build_allowlisted_environment,
    decode_frame,
    encode_frame,
)
from tests.fixtures.groove_provider_payloads import (
    make_condition_card,
    make_provider_limits,
    make_provider_registry,
)


def test_frames_reject_unknown_method_depth_and_256k_limit() -> None:
    with pytest.raises(ProviderProtocolError):
        decode_frame(io.BytesIO(encode_frame({"method": "exec"})))
    with pytest.raises(ProviderProtocolError):
        encode_frame({"method": "generate", "nested": [[[[[[[[[1]]]]]]]]]} )
    with pytest.raises(ProviderProtocolError):
        encode_frame({"method": "generate", "payload": "x" * (256 * 1024)})


def test_provider_environment_is_minimal() -> None:
    env = build_allowlisted_environment(
        {"PATH": "minimal", "TEMP": "temp", "TMP": "tmp", "TOKEN": "secret"}
    )
    assert env["PATH"] == "minimal"
    assert env["PYTHONNOUSERSITE"] == "1"
    assert "TOKEN" not in env
    assert set(env) <= {"PATH", "TEMP", "TMP", "PYTHONNOUSERSITE", "LC_ALL", "LANG"}


def test_provider_uses_fixed_argv_no_shell_and_strips_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 123
        returncode = 0

        def __init__(self) -> None:
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO()
            self.stderr = io.BytesIO()

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            return 0

        def poll(self) -> int:
            return 0

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            return None

    def fake_popen(argv: list[str], **kwargs: object) -> FakeProcess:
        captured["argv"] = argv
        captured.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "ableton_mcp_server.groove_intelligence.neural_subprocess.select_resource_enforcer",
        lambda: _NoopEnforcer(),
    )
    provider = NeuralSubprocessProvider(
        registry=make_provider_registry(tmp_path), provider_id="fixture"
    )
    condition = make_condition_card(tmp_path)
    result = provider.generate(
        condition, condition.parent_artifact_ids, 7, make_provider_limits()
    )
    assert captured["shell"] is False
    assert captured["argv"] == ["echo_provider.py", "--provider-host"]
    env = captured["env"]
    assert isinstance(env, dict) and "TOKEN" not in env and env["PYTHONNOUSERSITE"] == "1"
    assert result.code.value in {"protocol_violation", "output_invalid", "internal"}


class _NoopEnforcer:
    def enforce(self, process: object, limits: object) -> object:
        del limits
        return process

    def terminate(self, handle: object) -> None:
        del handle
