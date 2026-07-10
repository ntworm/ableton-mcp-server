from __future__ import annotations

import ast
from pathlib import Path

from AbletonMCPServer_RemoteScript import execute_command
from tests.remote_fakes import FakeApplication, FakeSong


def test_remote_script_never_blocks_live_ui_with_sleep() -> None:
    source = Path("AbletonMCPServer_RemoteScript/__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    blocking_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "time"
        and node.func.attr == "sleep"
    ]
    assert blocking_calls == []


def test_all_transport_mutations_return_observed_values() -> None:
    song = FakeSong()
    app = FakeApplication()
    assert execute_command(song, app, "set_current_song_time", {"time": 12.0}) == {
        "current_song_time": 12.0
    }
    assert execute_command(song, app, "set_loop_start", {"start_beat": 4.0}) == {"loop_start": 4.0}
    assert execute_command(song, app, "set_loop_length", {"length_beats": 8.0}) == {
        "loop_length": 8.0
    }
