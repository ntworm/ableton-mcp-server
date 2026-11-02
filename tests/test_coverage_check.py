from __future__ import annotations

import dis
import sys
from pathlib import Path
from types import CodeType

from scripts.coverage_check import create_tracer, executable_lines

_ANNOTATED_SOURCE = "def f(\n    x: int,\n) -> None:\n    pass\n"


def _annotation_only_lines(code: CodeType) -> set[int]:
    """Lines that only the PEP 649 annotation helpers contribute."""
    helpers: list[CodeType] = []
    body: list[CodeType] = []

    def visit(item: CodeType) -> None:
        (helpers if item.co_name == "__annotate__" else body).append(item)
        for constant in item.co_consts:
            if isinstance(constant, CodeType):
                visit(constant)

    def starts(items: list[CodeType]) -> set[int]:
        return {line for item in items for _o, line in dis.findlinestarts(item) if line}

    visit(code)
    return starts(helpers) - starts(body)


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


def test_executable_lines_ignores_python_314_none_line_entries() -> None:
    server = Path(__file__).resolve().parents[1] / "ableton_mcp_server" / "server.py"
    lines = executable_lines(server)
    assert lines
    assert all(isinstance(line, int) and line > 0 for line in lines)


def test_executable_lines_ignores_the_annotation_helpers(tmp_path: Path) -> None:
    path = tmp_path / "annotated_module.py"
    path.write_text(_ANNOTATED_SOURCE, encoding="utf-8")
    code = compile(_ANNOTATED_SOURCE, str(path), "exec")
    lines = executable_lines(path)
    annotation_only = _annotation_only_lines(code)
    if sys.version_info < (3, 14):
        # Without PEP 649 helpers the annotations are evaluated inline.
        assert lines
        return
    assert annotation_only
    assert not lines & annotation_only
