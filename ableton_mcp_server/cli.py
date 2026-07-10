from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from contracts import DEFAULT_HOST, DEFAULT_PORT

from .client import Client
from .diagnostics import (
    bridge_status,
    bundled_remote_script_path,
    default_remote_scripts_root,
    install_remote_script,
    remote_script_status,
)


def _emit(result: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    for key, value in result.items():
        print(f"{key}: {value}")


def _add_install_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--json", action="store_true")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ableton-mcp")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Probe the MCP-to-Live bridge")
    doctor.add_argument("--json", action="store_true")

    install = subparsers.add_parser("install-script", help="Install the MIDI Remote Script")
    _add_install_paths(install)

    status = subparsers.add_parser("install-status", help="Compare installed and bundled scripts")
    _add_install_paths(status)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "doctor":
        host = os.environ.get("ABLETON_MCP_SERVER_HOST", DEFAULT_HOST)
        port = int(os.environ.get("ABLETON_MCP_SERVER_PORT", str(DEFAULT_PORT)))
        result = bridge_status(Client(host=host, port=port, reconnect=False))
        _emit(result, as_json=bool(args.json))
        return 0 if result["bridge_available"] else 1

    source = bundled_remote_script_path() if args.source is None else args.source
    destination = (
        default_remote_scripts_root() if args.destination is None else args.destination
    )
    if args.command == "install-script":
        result = install_remote_script(source, destination)
        _emit(result, as_json=bool(args.json))
        return 0
    result = remote_script_status(source, destination)
    _emit(result, as_json=bool(args.json))
    return 0 if result["status"] == "current" else 1


if __name__ == "__main__":
    raise SystemExit(main())
