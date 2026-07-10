from __future__ import annotations

from pathlib import Path

from scripts.coverage_check import create_tracer


def test_trace_does_not_drop_project_init_after_ignored_init_name_collision() -> None:
    tracer = create_tracer()
    fake_ignored_init = str(
        Path(__import__("sys").prefix) / "Lib" / "site-packages" / "pkg" / "__init__.py"
    )
    project_init = str(
        Path(__file__).resolve().parents[1] / "AbletonMCPServer_RemoteScript" / "__init__.py"
    )
    assert tracer.ignore.names(fake_ignored_init, "__init__") == 1
    assert tracer.ignore.names(project_init, "__init__") == 0
