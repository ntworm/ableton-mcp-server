"""Turn a local ``ableton-mcp acceptance --json`` output into a public report.

The raw output stays on the machine: it holds absolute paths. This keeps, per
tool, the group (from ``BASELINE_PROBE_GROUPS``), the status, and for
``mutations`` rows how the runner certified the write:

* ``read_back``: the probe reads the Set again after the write and compares
  (for example ``create_cue_point`` then ``get_locators``,
  ``ableton_mcp_server/acceptance/runner.py:1255-1264``);
* ``response``: the probe checks only the command's own reply, or nothing
  (``run_batch`` checks its returned payload, ``runner.py:1550-1580``).

Read rows are counted as "reads answered": the runner marks them
``live_passed`` when the call returns (``runner.py:672-687``). The evidence
string is kept only for ``mutations`` rows. The Live version is not in the
runner output; ``--live-version`` takes it from Live's About box.

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

# Each line: the probe that reads the Set after the write (runner.py lines).
READ_BACK = frozenset(
    {
        "create_cue_point",  # get_locators, 1255-1264
        "bulk_create_cue_points",  # get_locators, 1272-1280
        "delete_cue_point",  # get_locators, 1284-1299
        "set_tempo",  # get_session_info, 1306-1311
        "set_current_song_time",  # get_session_info, 1315-1322
        "set_loop_start",  # get_loop_settings, 1326-1331
        "set_loop_length",  # get_loop_settings, 1335-1340
        "set_loop",  # get_loop_settings, 1344-1349
        "create_clip",  # get_clip_info, 1354-1372
        "add_notes_to_clip",  # get_clip_notes, 1390-1422
        "clear_clip_notes",  # get_clip_notes, 1436-1453
        "set_clip_properties",  # get_clip_info, 1467-1486
        "start_playback",  # get_session_info, 1531-1536
        "stop_playback",  # get_session_info, 1540-1545
        "fire_clip",  # get_session_info is_playing, 1597-1612
        "fire_scene",  # get_session_info is_playing, 1621-1630
        "set_track_property",  # get_track_state, 1639-1651
        "set_track_color",  # get_track_state, 1678-1693
        "set_clip_color",  # get_clip_info, 1722-1746
        "rename_track",  # get_track_list, 1751-1768
        "duplicate_session_clip_to_arrangement",  # get_arrangement_clips, 1818-1833
        "move_arrangement_clip",  # get_arrangement_clips, 1906-1924
        "delete_arrangement_clip",  # get_arrangement_clips, 1932-1945
        "delete_clip",  # get_clip_info, 1964-1981
        "set_parameter_value",  # get_parameter_value, 1996-2090
        "live_fade",  # get_track_state, 2150-2210
        "set_warp_state",  # get_warp_state, 2212-2232
        "create_midi_track",  # get_track_list before and after, 2243-2348
        "create_audio_track",  # get_track_list before and after, 2243-2348
        "load_device_to_track",  # get_device_list, probes/load_device.py:66-80
    }
)
# Certified by the command's own reply, or by no check at all.
RESPONSE_ONLY = frozenset(
    {
        "run_batch",  # returned completed/aborted_at, 1550-1580
        "create_clip_automation",  # returned points_written, 1500-1528
        "create_clip_automation_curve",  # no check, 1863-1884
        "add_notes_pattern",  # no check, 1841-1861
        "set_arrangement_clip_properties",  # no check, 1886-1904
        "set_plugin_preset",  # returned selected_preset_index, 2127-2150
        "save_set",  # returned saved plus get_project_metadata, 1180-1233
    }
)


def group_of() -> dict[str, str]:
    return {tool: group for group, tools in BASELINE_PROBE_GROUPS.items() for tool in tools}


def certification_of(tool: str, group: str) -> str | None:
    if group != "mutations":
        return None
    return "read_back" if tool in READ_BACK else "response"


def _rows(raw: dict[str, Any]) -> list[dict[str, Any]]:
    groups = group_of()
    rows = []
    for item in raw["certification"]["tools"]:
        tool, group = str(item["tool"]), groups.get(str(item["tool"]), "unknown")
        row: dict[str, Any] = {"tool": tool, "group": group, "status": item["status"]}
        how = certification_of(tool, group)
        if how:
            row["certified_by"] = how
            row["evidence"] = str(item.get("evidence", ""))
        rows.append(row)
    return rows


def counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    live = [r for r in rows if r["status"] == "live_passed"]
    tally = Counter(r["status"] for r in rows)
    return {
        "mutations_read_back": sum(r.get("certified_by") == "read_back" for r in live),
        "mutations_certified_by_response": sum(r.get("certified_by") == "response" for r in live),
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
