from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from contracts import DEFAULT_HOST, DEFAULT_PORT

from .catalog import TOOL_CATALOG
from .diagnostics import (
    bridge_status,
    bundled_remote_script_path,
    default_remote_scripts_root,
    install_remote_script,
    remote_script_status,
)

# Loaded only by commands that need the Live bridge. Keeping install/status
# commands dependency-light lets setup preview a clean checkout without first
# creating an environment or installing third-party packages. The module-level
# names remain patchable for the CLI tests.
Client: Any = None


def _client_type() -> Any:
    global Client
    if Client is None:
        from .client import Client as client_type

        Client = client_type
    return Client


async def run_live_acceptance(*args: Any, **kwargs: Any) -> Any:
    """Load the acceptance stack only when that subcommand is invoked."""
    from .acceptance import run_live_acceptance as acceptance_runner

    return await acceptance_runner(*args, **kwargs)


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

    acceptance = subparsers.add_parser(
        "acceptance", help="Run guarded read/write checks against a disposable Live Set"
    )
    acceptance.add_argument("--confirm-project-name", required=True)
    acceptance.add_argument("--track-index", required=True, type=int)
    acceptance.add_argument("--clip-index", required=True, type=int)
    acceptance.add_argument(
        "--audio-track-index",
        type=int,
        default=None,
        help="Track index used for warp/audio probes (defaults to track-index)",
    )
    acceptance.add_argument(
        "--audio-clip-index",
        type=int,
        default=None,
        help="Clip-slot index used for warp/audio probes (defaults to clip-index)",
    )
    acceptance.add_argument(
        "--profile",
        action="append",
        default=[],
        help="Acceptance profile name (repeat for multiple). Default: baseline",
    )
    acceptance.add_argument("--fire-clip", action="store_true")
    acceptance.add_argument("--json", action="store_true")

    install = subparsers.add_parser("install-script", help="Install the MIDI Remote Script")
    _add_install_paths(install)
    install.add_argument("--dry-run", action="store_true")

    status = subparsers.add_parser("install-status", help="Compare installed and bundled scripts")
    _add_install_paths(status)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "doctor":
        host = os.environ.get("ABLETON_MCP_SERVER_HOST", DEFAULT_HOST)
        port = int(os.environ.get("ABLETON_MCP_SERVER_PORT", str(DEFAULT_PORT)))
        result = bridge_status(
            _client_type()(host=host, port=port, reconnect=False),
            tool_count=len(TOOL_CATALOG),
        )

        _emit(result, as_json=bool(args.json))
        return 0 if result["bridge_available"] else 1

    if args.command == "acceptance":
        host = os.environ.get("ABLETON_MCP_SERVER_HOST", DEFAULT_HOST)
        port = int(os.environ.get("ABLETON_MCP_SERVER_PORT", str(DEFAULT_PORT)))
        profiles = tuple(args.profile) if args.profile else ("baseline",)
        result = asyncio.run(
            run_live_acceptance(
                _client_type()(host=host, port=port, reconnect=False),
                confirm_project_name=str(args.confirm_project_name),
                track_index=int(args.track_index),
                clip_index=int(args.clip_index),
                audio_track_index=(
                    int(args.audio_track_index)
                    if args.audio_track_index is not None
                    else int(args.track_index)
                ),
                audio_clip_index=(
                    int(args.audio_clip_index)
                    if args.audio_clip_index is not None
                    else int(args.clip_index)
                ),
                profiles=profiles,
                fire_clip=bool(args.fire_clip),
            )
        )
        _emit(result, as_json=bool(args.json))
        cert = result.get("certification") or {}
        release_ready = bool(cert.get("release_ready", False))
        # Only the legacy success path (no certification attached) accepts
        # ``status == "ok"`` as a green light. When a certification is
        # present it owns the gate.
        if cert:
            return 0 if release_ready else 1
        return 0 if result.get("status") == "ok" else 1

    source = bundled_remote_script_path() if args.source is None else args.source
    destination = default_remote_scripts_root() if args.destination is None else args.destination
    if args.command == "install-script":
        result = install_remote_script(source, destination, dry_run=bool(args.dry_run))
        _emit(result, as_json=bool(args.json))
        return 0
    result = remote_script_status(source, destination)
    _emit(result, as_json=bool(args.json))
    return 0 if result["status"] == "current" else 1


if __name__ == "__main__":
    raise SystemExit(main())
