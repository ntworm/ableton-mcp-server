from __future__ import annotations

import dis
import os
import sys
import trace
from pathlib import Path
from types import CodeType

import pytest

ROOT = Path(__file__).resolve().parents[1]
TARGETS = sorted((ROOT / "ableton_mcp_server").glob("*.py")) + [
    ROOT / "AbletonMCPServer_RemoteScript" / "__init__.py"
]


class PathAwareIgnore:
    """Ignore interpreter files without conflating equal module basenames."""

    def __init__(self, directories: list[str]) -> None:
        self.directories = tuple(
            os.path.normcase(os.path.abspath(directory)) for directory in directories
        )

    def names(self, filename: str, _modulename: str) -> int:
        normalized = os.path.normcase(os.path.abspath(filename))
        for directory in self.directories:
            try:
                if os.path.commonpath((normalized, directory)) == directory:
                    return 1
            except ValueError:
                continue
        return 0


def executable_lines(path: Path) -> set[int]:
    code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
    lines: set[int] = set()

    def visit(item: CodeType) -> None:
        lines.update(line for _offset, line in dis.findlinestarts(item) if line > 0)
        for constant in item.co_consts:
            if isinstance(constant, CodeType):
                visit(constant)

    visit(code)
    return lines


def create_tracer() -> trace.Trace:
    # trace.Ignore caches by module basename. Replace it with a path-aware
    # filter so site-packages/__init__.py cannot hide project/__init__.py.
    tracer = trace.Trace(count=True, trace=False)
    tracer.ignore = PathAwareIgnore([sys.prefix, sys.exec_prefix])  # type: ignore[assignment]
    return tracer


def main() -> int:
    tracer = create_tracer()
    pytest_exit = int(tracer.runfunc(pytest.main, ["tests", "-q", "--tb=line"]))
    counts = tracer.results().counts
    target_keys = {str(path.resolve()): path for path in TARGETS}
    hit_by_file: dict[str, set[int]] = {key: set() for key in target_keys}
    for (filename, line), count in counts.items():
        if not count:
            continue
        resolved = str(Path(filename).resolve())
        if resolved in hit_by_file:
            hit_by_file[resolved].add(line)
    total_lines = 0
    total_hit = 0
    for path in TARGETS:
        lines = executable_lines(path)
        resolved = str(path.resolve())
        hit = hit_by_file[resolved]
        covered = len(lines & hit)
        total = len(lines)
        total_hit += covered
        total_lines += total
        percentage = 100.0 * covered / total if total else 100.0
        print(f"{path.relative_to(ROOT)}: {covered}/{total} ({percentage:.1f}%)")
    total_percentage = 100.0 * total_hit / total_lines if total_lines else 100.0
    print(f"TOTAL: {total_hit}/{total_lines} ({total_percentage:.1f}%)")
    if pytest_exit != 0:
        return pytest_exit
    return 0 if total_percentage >= 85.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
