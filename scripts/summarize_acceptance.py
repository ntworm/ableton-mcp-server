"""Turn a local ``ableton-mcp acceptance --json`` output into a public report.

The raw output stays on the machine: it holds absolute paths. This keeps, per
tool, the group (from ``BASELINE_PROBE_GROUPS``), the status, and for
``mutations`` rows how the runner certified the write:

* ``read_back``: the probe reads the Set again after the write and compares
  (for example ``create_cue_point``, then ``get_locators`` in ``run_create_cue``
  of ``ableton_mcp_server/acceptance/runner.py``);
* ``response``: the probe checks only the command's own reply
  (``run_batch`` checks its returned payload in ``run_run_batch``);
* ``no_check``: the probe passes when the call returns without error; it reads
  neither the reply nor the Set (``add_notes_pattern`` in ``run_add_notes_pattern``).

Read rows are counted as "reads answered": the runner marks them
``live_passed`` when the call returns. The evidence string is kept for
``read_back`` and ``response`` rows; ``no_check`` rows drop it, because the
runner's common recorder writes "call and readback completed" there too.
The Live version is not in the runner output; ``--live-version`` takes it from
Live's About box.

Usage::

    python scripts/summarize_acceptance.py raw.json --live-version 12.4.25b1 \
        --set-name TESTE_CODEX --date 2026-11-12 \
        --out docs/reports/2026-11-acceptance-readback.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "scripts"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from report_privacy import require_public  # noqa: E402

from ableton_mcp_server.acceptance.probes import BASELINE_PROBE_GROUPS  # noqa: E402

# Each line: the read after the write, then the probe function in acceptance/runner.py.
READ_BACK = frozenset(
    {
        "create_cue_point",  # get_locators; run_create_cue
        "bulk_create_cue_points",  # get_locators; run_bulk_cue
        "delete_cue_point",  # get_locators; run_delete_cue
        "set_tempo",  # get_session_info; run_set_tempo
        "set_current_song_time",  # get_session_info; run_set_time
        "set_loop_start",  # get_loop_settings; run_set_loop_start
        "set_loop_length",  # get_loop_settings; run_set_loop_length
        "set_loop",  # get_loop_settings; run_set_loop
        "create_clip",  # get_clip_info; run_create_clip
        "add_notes_to_clip",  # get_clip_notes; run_add_notes
        "clear_clip_notes",  # get_clip_notes; run_clear_notes
        "set_clip_properties",  # get_clip_info; run_set_clip_props
        "start_playback",  # get_session_info; run_start_playback
        "stop_playback",  # get_session_info; run_stop_playback
        "fire_clip",  # get_session_info is_playing; run_fire_clip
        "fire_scene",  # get_session_info is_playing; run_fire_scene
        "set_track_property",  # get_track_state; run_set_track_prop
        "set_track_color",  # get_track_state; run_set_track_color
        "set_clip_color",  # get_clip_info; run_set_clip_color
        "rename_track",  # get_track_list; run_rename_track
        # get_arrangement_clips; run_duplicate_to_arrangement
        "duplicate_session_clip_to_arrangement",
        "move_arrangement_clip",  # get_arrangement_clips; run_move_arrangement_clip
        "delete_arrangement_clip",  # get_arrangement_clips; run_delete_arrangement_clip
        "delete_clip",  # get_clip_info; run_delete_clip
        "set_parameter_value",  # get_parameter_value; run_set_parameter_value
        "live_fade",  # get_track_state; run_live_fade
        "set_warp_state",  # get_warp_state; run_set_warp_state
        "create_midi_track",  # get_track_list before and after; _run_track_creation
        "create_audio_track",  # get_track_list before and after; _run_track_creation
        "load_device_to_track",  # get_device_list; probes/load_device.py::_load_and_verify
        "save_set",  # get_project_metadata after a save; run_save_set
    }
)
# Certified by the command's own reply.
RESPONSE_ONLY = frozenset(
    {
        "run_batch",  # returned completed/aborted_at; run_run_batch
        "create_clip_automation",  # returned points_written; run_clip_automation
        "set_plugin_preset",  # returned selected_preset_index; run_set_plugin_preset
    }
)
# Passed when the call returned without error: no reply or Set check.
NO_CHECK = frozenset(
    {
        "create_clip_automation_curve",  # run_create_clip_automation_curve
        "add_notes_pattern",  # run_add_notes_pattern
        "set_arrangement_clip_properties",  # run_set_arrangement_clip_properties
    }
)


def group_of() -> dict[str, str]:
    return {tool: group for group, tools in BASELINE_PROBE_GROUPS.items() for tool in tools}


def certification_of(tool: str, group: str) -> str | None:
    if group != "mutations":
        return None
    for name, tools in (
        ("read_back", READ_BACK),
        ("response", RESPONSE_ONLY),
        ("no_check", NO_CHECK),
    ):
        if tool in tools:
            return name
    return "unclassified"


def _rows(raw: dict[str, Any]) -> list[dict[str, Any]]:
    groups = group_of()
    rows = []
    for item in raw["certification"]["tools"]:
        tool, group = str(item["tool"]), groups.get(str(item["tool"]), "unknown")
        row: dict[str, Any] = {"tool": tool, "group": group, "status": item["status"]}
        how = certification_of(tool, group)
        if how:
            row["certified_by"] = how
            if how != "no_check":
                row["evidence"] = str(item.get("evidence", ""))
        rows.append(row)
    return rows


def counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    live = [r for r in rows if r["status"] == "live_passed"]
    tally = Counter(r["status"] for r in rows)
    return {
        "mutations_read_back": sum(r.get("certified_by") == "read_back" for r in live),
        "mutations_certified_by_response": sum(r.get("certified_by") == "response" for r in live),
        "mutations_without_check": sum(r.get("certified_by") == "no_check" for r in live),
        "reads_answered": sum(
            r["group"] in ("tcp_reads", "websocket_reads", "composed") for r in live
        ),
        **{f"status_{name}": n for name, n in sorted(tally.items())},
    }


def summarize(
    raw: dict[str, Any], *, live_version: str, set_name: str, date: str
) -> dict[str, Any]:
    rows = _rows(raw)
    report = {
        "date": date,
        "set_name": set_name,
        "live_version": live_version,
        "counts": counts(rows),
        "tools": rows,
    }
    require_public(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("raw", type=Path)
    parser.add_argument("--live-version", required=True)
    parser.add_argument("--set-name", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    raw = json.loads(args.raw.read_text(encoding="utf-8-sig"))
    report = summarize(raw, live_version=args.live_version, set_name=args.set_name, date=args.date)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
