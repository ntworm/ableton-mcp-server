from __future__ import annotations

import argparse
from typing import Any

from ableton_mcp_server.client import Client
from contracts import DEFAULT_HOST, DEFAULT_PORT


def run_check(port: int) -> bool:
    client = Client(host=DEFAULT_HOST, port=port, reconnect=False)
    checks: list[tuple[str, dict[str, Any]]] = [
        ("get_session_info", {}),
        ("get_track_list", {}),
        ("get_locators", {}),
        ("get_control_surfaces", {}),
        ("get_scenes", {}),
        ("get_project_metadata", {}),
        ("get_loop_settings", {}),
        ("get_selected_context", {}),
        ("get_browser_categories", {}),
        ("get_song_length", {}),
        ("take_snapshot", {}),
    ]
    failures = 0
    try:
        client.connect()
        tracks = client.call("get_track_list", {})
        if tracks:
            track_index = int(tracks[0]["index"])
            track_id = str(tracks[0]["id"])
            checks.extend(
                [
                    ("get_track_state", {"track_index": track_index}),
                    ("get_device_list", {"track_index": track_index}),
                    ("get_clip_summary", {"track_index": track_index}),
                    ("get_routing", {"track_index": track_index}),
                    ("list_device_params", {"track_id": track_id}),
                    ("live_find_track", {"query": str(tracks[0]["name"])}),
                ]
            )
        print(f"Connected to {DEFAULT_HOST}:{port}")
        for command, params in checks:
            try:
                result = client.call(command, params, timeout=3.0)
                kind = type(result).__name__
                print(f"PASS {command}: {kind}")
            except Exception as error:
                failures += 1
                print(f"FAIL {command}: {error}")
    except Exception as error:
        print(f"FAIL connect: {error}")
        return False
    finally:
        client.close()
    print(f"Summary: {len(checks) - failures} passed, {failures} failed")
    return failures == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    return 0 if run_check(args.port) else 1


if __name__ == "__main__":
    raise SystemExit(main())
