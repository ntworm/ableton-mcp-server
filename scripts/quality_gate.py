"""Portable structure gate for Python, copied as is: quality-gate.json names what to measure,
quality-baseline.json keeps the debt that only goes down, and the limits are constants here."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple, Tuple

LIMITS = {"complexity": 10, "function_lines": 60, "file_lines": 500}
BASELINE_NAME = "quality-baseline.json"
CONFIG_NAME = "quality-gate.json"
FUNCTION_METRICS = ("complexity", "function_lines")
Violation = Tuple[str, str, int, int, bool]
_COUNTED_NODES = (
    ast.Assert, ast.AsyncFor, ast.AsyncWith, ast.ExceptHandler,
    ast.For, ast.If, ast.IfExp, ast.While, ast.With,
)
_MATCH = getattr(ast, "Match", ())
_DRIVE_LETTER = re.compile(r"[A-Za-z]:")


class ConfigError(Exception):
    """The configuration file is missing or invalid."""


class Config(NamedTuple):
    """Paths to measure and paths to exclude, read from the configuration."""

    paths: tuple[str, ...]
    exclude: tuple[str, ...]


def _path_entry(entry: object, kind: str) -> str:
    """Validates one relative POSIX path of the configuration."""
    if not isinstance(entry, str) or not entry:
        raise ConfigError(f"'{kind}' entries must be non-empty strings")
    if "\\" in entry:
        raise ConfigError(f"invalid path '{entry}': backslashes are not allowed")
    if entry.startswith("/"):
        raise ConfigError(f"invalid path '{entry}': the path must be relative")
    if _DRIVE_LETTER.match(entry):
        raise ConfigError(f"invalid path '{entry}': drive letters are not allowed")
    if any(part in ("", ".", "..") for part in entry.split("/")):
        raise ConfigError(f"invalid path '{entry}': empty, '.' and '..' are not allowed")
    return entry


def _read_config_file(path: Path) -> dict:
    """Reads the configuration file and returns its JSON object."""
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise ConfigError("file not found") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"cannot be read: {exc}") from None
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ConfigError(f"invalid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise ConfigError("the file must hold a JSON object")
    return data


def load_config(root: Path) -> Config:
    """Reads and validates the configuration file of the repository."""
    root = Path(root)
    data = _read_config_file(root / CONFIG_NAME)
    for key in ("paths", "exclude"):
        if key not in data:
            raise ConfigError(f"missing key '{key}'")
    unknown = sorted(set(data) - {"paths", "exclude"})
    if unknown:
        raise ConfigError(f"unknown key '{unknown[0]}'")
    paths = data["paths"]
    exclude = data["exclude"]
    if not isinstance(paths, list):
        raise ConfigError("'paths' must be a list")
    if not isinstance(exclude, list):
        raise ConfigError("'exclude' must be a list")
    if not paths:
        raise ConfigError("'paths' must not be empty")
    measured = tuple(_path_entry(entry, "paths") for entry in paths)
    skipped = tuple(_path_entry(entry, "exclude") for entry in exclude)
    for entry in measured:
        if not (root / entry).exists():
            raise ConfigError(f"path '{entry}' does not exist under the root")
    return Config(paths=measured, exclude=skipped)


def _read_text(path: Path) -> str:
    """Reads a text file; invalid bytes become replacement characters."""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _parse_tree(path: Path) -> ast.Module | None:
    """Parses the file; returns None when there is a syntax error."""
    try:
        return ast.parse(_read_text(path), filename=str(path))
    except SyntaxError as exc:
        print(f"quality_gate: file ignored (syntax error): {path}: {exc}", file=sys.stderr)
        return None


class _FunctionCollector(ast.NodeVisitor):
    """Collects functions with a qualified name."""

    def __init__(self) -> None:
        self.stack: list[str] = []
        self.found: list[tuple[str, ast.AST]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _visit_function(self, node: ast.AST) -> None:
        self.found.append((".".join([*self.stack, node.name]), node))
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function


def _complexity_node(node: ast.AST) -> int:
    """Counts the decision points of a node without entering defs or classes."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return 0
    total = 0
    if isinstance(node, _COUNTED_NODES):
        total += 1
    elif isinstance(node, ast.BoolOp):
        total += len(node.values) - 1
    elif isinstance(node, ast.comprehension):
        total += len(node.ifs)
    elif isinstance(node, _MATCH):
        total += len(node.cases)
    for child in ast.iter_child_nodes(node):
        total += _complexity_node(child)
    return total


def _function_metrics(node: ast.AST) -> dict[str, int]:
    """Complexity and number of lines of one function."""
    complexity = 1
    for statement in node.body:
        complexity += _complexity_node(statement)
    return {"complexity": complexity, "function_lines": node.end_lineno - node.lineno + 1}


def _tracked_files(root: Path, config: Config) -> set[str] | None:
    """Files git tracks under the config paths; None outside git or when git lists none."""
    command = ["git", "ls-files", "-z", "--", *config.paths]
    try:
        result = subprocess.run(command, cwd=root, capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return {name for name in result.stdout.decode("utf-8", "replace").split("\0") if name} or None


def _iter_source_files(root: Path, config: Config) -> list[Path]:
    """Lists the files to measure, without duplicates and excluded paths."""
    tracked = _tracked_files(root, config)
    found: dict[str, Path] = {}
    for entry in config.paths:
        base = root / entry
        candidates = sorted(base.rglob("*.py")) if base.is_dir() else [base]
        for path in candidates:
            relative = path.relative_to(root).as_posix()
            if "__pycache__" in relative.split("/") or (tracked is not None and relative not in tracked):
                continue
            if any(relative == item or relative.startswith(item + "/") for item in config.exclude):
                continue
            found[relative] = path
    return [found[key] for key in sorted(found)]


def measure(root: Path, config: Config | None = None) -> dict:
    """Measures the code under root and returns the files and the functions.

    The result is {"files": {path: lines}, "functions": {key: metrics}}; without
    a config the configuration file of the repository is read.
    """
    root = Path(root)
    if config is None:
        config = load_config(root)
    functions: dict[str, dict[str, int]] = {}
    files: dict[str, int] = {}
    for path in _iter_source_files(root, config):
        key = path.relative_to(root).as_posix()
        files[key] = len(_read_text(path).splitlines())
        tree = _parse_tree(path)
        if tree is None:
            continue
        collector = _FunctionCollector()
        collector.visit(tree)
        for qualname, node in collector.found:
            function_key = f"{key}::{qualname}"
            metrics = _function_metrics(node)
            known = functions.get(function_key, {})
            merged = {name: max(known.get(name, 0), value) for name, value in metrics.items()}
            functions[function_key] = merged
    return {"files": dict(sorted(files.items())), "functions": dict(sorted(functions.items()))}


def _section(baseline: dict, name: str) -> dict:
    """Section of the baseline; an empty dictionary when it is missing."""
    section = baseline.get(name)
    return section if isinstance(section, dict) else {}


def _metrics(entry: object) -> dict[str, int]:
    """Normalizes a baseline entry into a dictionary of metrics."""
    if isinstance(entry, dict):
        return {name: int(value) for name, value in entry.items()}
    return {"file_lines": int(entry)}


def _load_baseline(root: Path) -> dict | None:
    """Reads the baseline from disk; None when the file is not a JSON object."""
    path = root / BASELINE_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"quality_gate: invalid {BASELINE_NAME}: {exc}", file=sys.stderr)
        return None
    if not isinstance(data, dict):
        print(f"quality_gate: invalid {BASELINE_NAME}: not a JSON object", file=sys.stderr)
        return None
    return data


def _baseline_payload(measured: dict) -> dict:
    """Builds the baseline with only the metrics above the limit."""
    functions = {}
    for key, metrics in measured["functions"].items():
        stored = {name: metrics[name] for name in FUNCTION_METRICS if metrics[name] > LIMITS[name]}
        if stored:
            functions[key] = stored
    limit = LIMITS["file_lines"]
    files = {path: lines for path, lines in measured["files"].items() if lines > limit}
    return {"version": 1, "limits": dict(LIMITS), "functions": functions, "files": files}


def _write_baseline(root: Path, payload: dict) -> None:
    """Writes the baseline with sorted keys, indent 2 and a final newline."""
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with (root / BASELINE_NAME).open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _allowed(metric: str, stored: object) -> tuple[int, bool]:
    """Allowed value of a metric and whether it came from the baseline."""
    if isinstance(stored, dict) and metric in stored:
        return int(stored[metric]), True
    if metric == "file_lines" and isinstance(stored, int):
        return stored, True
    return LIMITS[metric], False


def _violations(measured: dict, baseline: dict) -> list[Violation]:
    """Compares the measurement with the baseline and lists the violations."""
    base_functions = _section(baseline, "functions")
    base_files = _section(baseline, "files")
    found: list[Violation] = []
    for key, metrics in sorted(measured["functions"].items()):
        entry = base_functions.get(key, {})
        for metric in FUNCTION_METRICS:
            value = metrics[metric]
            allowed, from_baseline = _allowed(metric, entry)
            if value > allowed:
                found.append((key, metric, value, allowed, from_baseline))
    for path, value in sorted(measured["files"].items()):
        allowed, from_baseline = _allowed("file_lines", base_files.get(path))
        if value > allowed:
            found.append((path, "file_lines", value, allowed, from_baseline))
    return found


def _format_violation(violation: Violation) -> str:
    """Builds the line of one violation."""
    key, metric, value, allowed, from_baseline = violation
    line = f"{key} {metric} {value} > {allowed}"
    return line + " (baseline)" if from_baseline else line


def _mode_default(root: Path, config: Config) -> int:
    """Measures the code and compares it with the baseline."""
    measured = measure(root, config)
    violations = _violations(measured, _load_baseline(root) or {})
    for violation in violations:
        print(_format_violation(violation))
    if violations:
        return 1
    print(f"quality_gate: ok ({len(measured['functions'])} functions, {len(measured['files'])} files)")
    return 0


def _strict_keys(root: Path, targets: list[str], measured: dict) -> list[str] | None:
    """Normalizes the targets of the strict mode; None when one does not fit."""
    keys = []
    for target in targets:
        path = Path(target)
        if not path.is_absolute():
            path = root / path
        try:
            key = path.resolve().relative_to(root).as_posix()
        except ValueError:
            print(f"quality_gate: file outside the root: {target}", file=sys.stderr)
            return None
        if key not in measured["files"]:
            print(f"quality_gate: file not measured: {key}", file=sys.stderr)
            return None
        keys.append(key)
    return keys


def _strict_violations(measured: dict, keys: list[str]) -> list[Violation]:
    """Lists the violations of the strict mode, without the baseline."""
    prefixes = tuple(f"{key}::" for key in keys)
    source = measured["functions"]
    functions = {name: metrics for name, metrics in source.items() if name.startswith(prefixes)}
    files = {key: measured["files"][key] for key in keys}
    return _violations({"files": files, "functions": functions}, {})


def _mode_strict(root: Path, config: Config, targets: list[str]) -> int:
    """Applies the limits, without baseline, to the given files only."""
    measured = measure(root, config)
    keys = _strict_keys(root, targets, measured)
    if keys is None:
        return 2
    violations = _strict_violations(measured, keys)
    for violation in violations:
        print(_format_violation(violation))
    if violations:
        return 1
    print("quality_gate: ok (strict)")
    return 0


def _mode_init(root: Path, config: Config) -> int:
    """Creates the baseline with the current measurement."""
    if (root / BASELINE_NAME).exists():
        print(f"quality_gate: --init does not overwrite the existing {BASELINE_NAME}")
        return 1
    _write_baseline(root, _baseline_payload(measure(root, config)))
    print(f"quality_gate: baseline created: {BASELINE_NAME}")
    return 0


def _baseline_changes(old: dict, new: dict) -> list[str]:
    """Lines of change between the old baseline and the new one."""
    lines = []
    for section in ("functions", "files"):
        old_section = _section(old, section)
        new_section = _section(new, section)
        for key, entry in sorted(old_section.items()):
            current = new_section.get(key)
            if current is None:
                lines.append(f"quality_gate: entry removed: {key}")
                continue
            current_metrics = _metrics(current)
            for metric, value in sorted(_metrics(entry).items()):
                if metric not in current_metrics:
                    lines.append(f"quality_gate: metric removed: {key} {metric}")
                elif current_metrics[metric] < value:
                    new_value = current_metrics[metric]
                    lines.append(f"quality_gate: lowered {key} {metric} {value} -> {new_value}")
    return lines


def _mode_update(root: Path, config: Config) -> int:
    """Lowers the baseline; it never raises a value nor creates an entry."""
    baseline = _load_baseline(root) or {}
    measured = measure(root, config)
    violations = _violations(measured, baseline)
    for violation in violations:
        print(_format_violation(violation))
    if violations:
        print("quality_gate: --update does not raise a value nor create an entry")
        return 1
    payload = _baseline_payload(measured)
    for line in _baseline_changes(baseline, payload):
        print(line)
    _write_baseline(root, payload)
    print("removed entries do not come back to the baseline")
    return 0


def _read_ref_baseline(root: Path, ref: str) -> dict | None:
    """Reads the baseline at the git ref; None when git really fails."""
    command = ["git", "show", f"{ref}:{BASELINE_NAME}"]
    try:
        result = subprocess.run(command, cwd=root, capture_output=True, env={**os.environ, "LC_ALL": "C"})
    except OSError as exc:
        print(f"quality_gate: git is unavailable: {exc}", file=sys.stderr)
        return None
    message = result.stderr.decode("utf-8", "replace")
    if result.returncode != 0:
        if "does not exist in" in message or "exists on disk, but not in" in message:
            return {}
        print(f"quality_gate: git error: {message.strip()}", file=sys.stderr)
        return None
    text = result.stdout.decode("utf-8", "replace").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except ValueError as exc:
        print(f"quality_gate: invalid baseline at the ref: {exc}", file=sys.stderr)
        return None
    return data if isinstance(data, dict) else None


def _ratchet_lines(tree: dict, ref: dict) -> list[str]:
    """Lines of the baseline of the tree that grew against the baseline of the ref."""
    lines = []
    ref_limits = _section(ref, "limits")
    for metric, value in sorted(_section(tree, "limits").items()):
        ref_value = ref_limits.get(metric, 0)
        if value > ref_value:
            lines.append(f"quality_gate: limit above ref: {metric} {value} > {ref_value}")
    for section in ("functions", "files"):
        ref_section = _section(ref, section)
        for key, entry in sorted(_section(tree, section).items()):
            if key not in ref_section:
                lines.append(f"quality_gate: new baseline entry: {key}")
                continue
            ref_entry = _metrics(ref_section[key])
            for metric, value in sorted(_metrics(entry).items()):
                if metric not in ref_entry:
                    lines.append(f"quality_gate: new baseline metric: {key} {metric}")
                elif value > ref_entry[metric]:
                    ref_value = ref_entry[metric]
                    lines.append(f"quality_gate: above ref: {key} {metric} {value} > {ref_value}")
    return lines


def _mode_ratchet(root: Path, ref: str) -> int:
    """Compares the baseline of the tree with the baseline of the git ref."""
    ref_payload = _read_ref_baseline(root, ref)
    tree = _load_baseline(root)
    if ref_payload is None or tree is None:
        return 2
    lines = _ratchet_lines(tree, ref_payload)
    for line in lines:
        print(line)
    if lines:
        return 1
    print(f"quality_gate: ratchet ok (ref {ref})")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Builds the command line parser."""
    parser = argparse.ArgumentParser(prog="quality_gate", description="Structure gate for Python code.")
    parser.add_argument("--root", default=None, help="root of the measured repository")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--strict", nargs="+", metavar="FILE", help="limits without baseline")
    modes.add_argument("--init", action="store_true", help="creates the measured baseline")
    modes.add_argument("--update", action="store_true", help="lowers the baseline without raising a value")
    modes.add_argument("--ratchet-ref", metavar="REF", help="compares with the baseline of the ref")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point of the command line."""
    args = _build_parser().parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path.cwd().resolve()
    try:
        config = load_config(root)
    except ConfigError as exc:
        print(f"quality_gate: invalid config {root / CONFIG_NAME}: {exc}", file=sys.stderr)
        return 2
    if args.ratchet_ref:
        return _mode_ratchet(root, args.ratchet_ref)
    if args.init:
        return _mode_init(root, config)
    if args.update:
        return _mode_update(root, config)
    if args.strict:
        return _mode_strict(root, config, args.strict)
    return _mode_default(root, config)


if __name__ == "__main__":
    raise SystemExit(main())
