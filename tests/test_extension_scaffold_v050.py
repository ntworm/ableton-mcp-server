"""v0.5.1 ``build_extension`` hardening tests — shell=False and structured errors.

The tooling evolved past scaffold_extension in v0.5.1; this file targets
the remaining public tool, ``build_extension``:

- the subprocess contract uses an argument list (no shell)
- the ``no package.json`` envelope echoes the project path
- a non-zero ``npm install`` short-circuits the build pipeline
"""

from __future__ import annotations

import json
from subprocess import CompletedProcess
from typing import Any
from unittest.mock import patch

import ableton_mcp_server.server as server


def _stub_package_json(project: Any) -> None:
    """Lay down a minimal package.json plus extension manifest so the
    entrypoint resolver in ``build_extension`` accepts the directory."""
    (project / "package.json").write_text(
        '{"name": "stub", "main": "dist/index.js"}', encoding="utf-8"
    )
    (project / "dist").mkdir(exist_ok=True)
    (project / "dist" / "index.js").write_text("// stub", encoding="utf-8")


def test_build_extension_returns_structured_error_when_package_json_missing(tmp_path: Any) -> None:
    result = json.loads(server.build_extension(str(tmp_path)))

    assert result["status"] == "error"
    assert result["message"] == "no package.json found"
    assert result["project_path"] == str(tmp_path)


def test_build_extension_invokes_subprocess_with_argument_list(tmp_path: Any) -> None:
    _stub_package_json(tmp_path)

    fake_runs = [
        CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        CompletedProcess(args=[], returncode=0, stdout="built", stderr=""),
    ]

    with patch("ableton_mcp_server.server.subprocess.run", return_value=fake_runs[0]) as run:
        run.side_effect = fake_runs
        result = json.loads(server.build_extension(str(tmp_path)))

    assert result["status"] == "built"
    assert [step["step"] for step in result["steps"]] == ["install", "build"]
    # Two subprocesses invoked, each with an argument list (never a string).
    assert run.call_count == 2
    for call in run.call_args_list:
        cmd = call.args[0]
        assert isinstance(cmd, list), f"subprocess.run got a string: {cmd!r}"
        # shell=True would be a shell-injection footgun; the tool must use the
        # executor variant instead.
        assert call.kwargs.get("shell", False) is False


def test_build_extension_returns_envelope_when_subprocess_fails(tmp_path: Any) -> None:
    # A non-zero returncode from ``npm install`` must short-circuit and return
    # the structured error envelope with the failing step in the report.
    _stub_package_json(tmp_path)

    failed = CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
    with patch("ableton_mcp_server.server.subprocess.run", return_value=failed) as run:
        result = json.loads(server.build_extension(str(tmp_path)))

    assert result["status"] == "error"
    # The failing step must be reported with its returncode so callers can
    # debug. The second step must not have run.
    assert result["steps"][0]["step"] == "install"
    assert result["steps"][0]["returncode"] == 1
    assert run.call_count == 1
