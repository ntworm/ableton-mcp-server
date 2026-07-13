"""Integration test for ``run_live_acceptance`` against a fake bridge.

This test proves that the runner produces exactly the catalogued number of
certification rows, that no row is fabricated as ``environment_unavailable``
to make the report green, and that ``release_ready`` flips to ``False`` the
moment any tool fails.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ableton_mcp_server.acceptance import (
    BASELINE_PROBE_GROUPS,
    run_live_acceptance,
)
from ableton_mcp_server.catalog import TOOL_CATALOG


class FakeBridge:
    """In-process fake that mimics the AcceptanceClient protocol."""

    def __init__(self) -> None:
        self.fail_tool: str | None = None
        self.fail_count = 0
        self.state: dict[str, Any] = {
            "tempo": 120.0,
            "current_song_time": 0.0,
            "loop": False,
            "loop_start": 0.0,
            "loop_length": 4.0,
            "locators": [],
            "clips": {},  # (track, slot) -> {"notes": [], "name": "..."}
            "note_reads": {},  # (track, slot) -> read counter
            "tracks": [
                {"index": 0, "type": "midi", "name": "Bass"},
                {"index": 1, "type": "audio", "name": "Drums"},
                {"index": 2, "type": "audio", "name": "Samp"},
            ],
        }

    def call(
        self,
        command_type: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        if self.fail_tool and command_type == self.fail_tool:
            self.fail_count += 1
            raise RuntimeError(f"forced failure on {command_type}")
        params = params or {}
        return _dispatch_tcp(self, command_type, params)

    async def call_ws(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 2.0,
    ) -> Any:
        if self.fail_tool and method == self.fail_tool:
            self.fail_count += 1
            raise RuntimeError(f"forced failure on {method}")
        params = params or {}
        return _dispatch_ws(self, method, params)


def _dispatch_tcp(bridge: FakeBridge, command_type: str, params: dict[str, Any]) -> Any:
    s = bridge.state
    if command_type == "get_project_metadata":
        return {"song_name": "TESTE_CODEX"}
    if command_type == "get_track_list":
        return list(s["tracks"])
    if command_type == "get_clip_summary":
        track = params.get("track_index", 0)
        slots = []
        for i in range(8):
            clip = s["clips"].get((track, i))
            has_clip = clip is not None
            slots.append({
                "index": i,
                "has_clip": has_clip,
                "is_audio_clip": track > 0,
            })
        return slots
    if command_type == "get_session_info":
        return {"tempo": s["tempo"], "current_song_time": s["current_song_time"]}
    if command_type == "get_loop_settings":
        return {"loop": s["loop"], "loop_start": s["loop_start"],
                "loop_length": s["loop_length"]}
    if command_type == "get_locators":
        return list(s["locators"])
    if command_type == "set_tempo":
        s["tempo"] = params["tempo"]
        return {"tempo": s["tempo"]}
    if command_type == "set_current_song_time":
        s["current_song_time"] = params["time"]
        return {"time": s["current_song_time"]}
    if command_type == "set_loop":
        s["loop"] = params["enabled"]
        return {"loop": s["loop"]}
    if command_type == "set_loop_start":
        s["loop_start"] = params["start_beat"]
        return {"loop_start": s["loop_start"]}
    if command_type == "set_loop_length":
        s["loop_length"] = params["length_beats"]
        return {"loop_length": s["loop_length"]}
    if command_type == "create_cue_point":
        cue = {"name": params["name"], "time": params["time"]}
        s["locators"].append(cue)
        return {"name": cue["name"], "time": cue["time"]}
    if command_type == "delete_cue_point":
        before = len(s["locators"])
        s["locators"] = [c for c in s["locators"]
                         if abs(c["time"] - params["time"]) > 0.01]
        return {"deleted": len(s["locators"]) < before}
    if command_type == "bulk_create_cue_points":
        for item in params["items"]:
            s["locators"].append({"name": item["name"], "time": item["time"]})
        return {"created": len(params["items"])}
    if command_type == "create_clip":
        track, slot = params["track_index"], params["clip_index"]
        s["clips"].setdefault((track, slot), {"notes": [], "name": ""})
        return {"track_index": track, "clip_index": slot}
    if command_type == "add_notes_to_clip":
        track, slot = params["track_index"], params["clip_index"]
        s["clips"].setdefault((track, slot), {"notes": [], "name": ""})
        s["clips"][(track, slot)]["notes"] = list(params["notes"])
        return {"added": len(params["notes"])}
    if command_type == "get_clip_notes":
        track, slot = params["track_index"], params["clip_index"]
        clip = s["clips"].get((track, slot))
        return list(clip["notes"]) if clip else []
    if command_type == "clear_clip_notes":
        track, slot = params["track_index"], params["clip_index"]
        if (track, slot) in s["clips"]:
            s["clips"][(track, slot)]["notes"] = []
        return {"cleared": True}
    if command_type == "set_clip_properties":
        track, slot = params["track_index"], params["clip_index"]
        s["clips"].setdefault((track, slot), {"notes": [], "name": ""})
        s["clips"][(track, slot)]["name"] = params["name"]
        return {"name": params["name"]}
    if command_type == "get_clip_info":
        track, slot = params["track_index"], params["clip_index"]
        clip = s["clips"].get((track, slot), {"name": "", "length": 0.0})
        return {"name": clip.get("name", ""), "length": clip.get("length", 4.0)}
    if command_type == "create_clip_automation":
        return {"points": len(params["points"])}
    if command_type == "start_playback":
        return {"playing": True}
    if command_type == "stop_playback":
        return {"playing": False}
    if command_type == "fire_clip":
        return {"fired": True}
    if command_type == "run_batch":
        return {"completed": 2, "aborted_at": 2, "rolled_back": False}
    if command_type == "fire_scene":
        return {"scene_index": params["scene_index"]}
    if command_type == "set_track_property":
        return {"name": params["name"]}
    if command_type == "rename_track":
        return {"new_name": params["new_name"]}
    if command_type == "delete_clip":
        track, slot = params["track_index"], params["clip_index"]
        s["clips"].pop((track, slot), None)
        return {"deleted": True}
    if command_type == "create_audio_track":
        return {"track_index": -1}
    if command_type == "create_midi_track":
        return {"track_index": -1}
    if command_type == "set_parameter_value":
        return {"value": params["value"]}
    if command_type == "live_fade":
        return {"final_value": 0.5}
    if command_type == "load_device_to_track":
        return {"device_name": params["device_name"]}
    if command_type == "save_set":
        return {"saved": True}
    return {"ok": True}


def _dispatch_ws(bridge: FakeBridge, method: str, params: dict[str, Any]) -> Any:
    if method == "get_warp_state":
        return {"warping": False, "warp_mode": "beats"}
    if method == "set_warp_state":
        return {"warping": params["warping"]}
    return {"ok": True}


def test_fake_runner_returns_65_certification_rows() -> None:
    """Every catalogued tool must produce exactly one verification row."""
    expected = len(TOOL_CATALOG)
    assert expected == 65

    bridge = FakeBridge()
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=2,
            audio_clip_index=0,
            fire_clip=True,
        )
    )
    cert = result["certification"]
    assert cert["tool_count"] == 65
    assert len(cert["tools"]) == 65
    catalog_names = {item.name for item in TOOL_CATALOG}
    assert {row["tool"] for row in cert["tools"]} == catalog_names
    # ``quit_ableton`` is explicitly environment_unavailable in baseline.
    assert any(
        row["tool"] == "quit_ableton"
        and row["status"] == "environment_unavailable"
        for row in cert["tools"]
    )
    # No tool is silently dropped from the report.
    reported = {row["tool"] for row in cert["tools"]}
    assert reported == catalog_names


def test_fake_runner_release_ready_true_when_no_failures() -> None:
    bridge = FakeBridge()
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=2,
            audio_clip_index=0,
        )
    )
    cert = result["certification"]
    assert cert["release_ready"] is True
    assert all(row["status"] != "failed" for row in cert["tools"])


def test_fake_runner_release_ready_false_when_one_tool_fails() -> None:
    bridge = FakeBridge()
    bridge.fail_tool = "set_tempo"
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=2,
            audio_clip_index=0,
        )
    )
    cert = result["certification"]
    assert cert["release_ready"] is False
    failed_names = [row["tool"] for row in cert["tools"]
                    if row["status"] == "failed"]
    assert "set_tempo" in failed_names


def test_fake_runner_baseline_does_not_fabricate_environment_unavailable() -> None:
    """Baseline profile must record every selected tool with real evidence.

    Tools not covered by a partial profile (e.g. ``tcp_reads`` alone) are
    explicitly skipped and the runner reports the missing tools via
    ``CertificationReport.finish()`` rather than silently marking them
    ``environment_unavailable``. The only legitimate
    ``environment_unavailable`` row in the baseline profile is
    ``quit_ableton``, because invoking it would close the host.
    """
    bridge = FakeBridge()
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=2,
            audio_clip_index=0,
        )
    )
    cert = result["certification"]
    assert cert["release_ready"] is True
    statuses = {row["tool"]: row["status"] for row in cert["tools"]}
    # Legitimately unavailable rows: ``quit_ableton`` is the documented
    # environment-unavailable tool; ``fire_clip`` requires the explicit
    # ``--fire-clip`` flag, which this test does not pass.
    unavailable = sorted(
        tool for tool, status in statuses.items()
        if status == "environment_unavailable"
    )
    assert unavailable == ["fire_clip", "quit_ableton"]
    # Every other row must be ``live_passed`` / ``offline_passed``.
    for tool, status in statuses.items():
        if tool in unavailable:
            continue
        assert status in {"live_passed", "offline_passed"}, (
            f"{tool} unexpectedly {status!r}"
        )


def test_baseline_probe_coverage_matches_catalog() -> None:
    """Defensive guard: the probe map must cover every catalogued tool."""
    flat = {name for group in BASELINE_PROBE_GROUPS.values()
            for name in group}
    catalog_names = {item.name for item in TOOL_CATALOG}
    assert flat == catalog_names
    assert len(flat) == 65