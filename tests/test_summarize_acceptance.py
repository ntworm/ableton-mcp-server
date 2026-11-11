"""The public acceptance summary keeps read-back apart and carries no local path."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from ableton_mcp_server.acceptance.probes import BASELINE_PROBE_GROUPS

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


summary = _load("summarize_acceptance")
privacy = _load("report_privacy")


def _raw(*rows: tuple[str, str, str]) -> dict[str, object]:
    return {
        "certification": {"tools": [{"tool": t, "status": s, "evidence": e} for t, s, e in rows]}
    }


def test_every_mutation_tool_is_classified_once() -> None:
    mutations = set(BASELINE_PROBE_GROUPS["mutations"])
    sets = (summary.READ_BACK, summary.RESPONSE_ONLY, summary.NO_CHECK)
    assert sum(len(s) for s in sets) == len(set().union(*sets)), "a tool is in two lists"
    assert mutations == set().union(*sets)


def test_counts_keep_read_back_response_and_reads_apart() -> None:
    raw = _raw(
        ("create_cue_point", "live_passed", "name=Probe time=8.0"),
        ("run_batch", "live_passed", "completed=2 aborted_at=2"),
        ("add_notes_pattern", "live_passed", "call and readback completed"),
        ("get_track_list", "live_passed", "call and readback completed"),
        ("fire_clip", "environment_unavailable", "fire_clip requires --fire-clip flag"),
    )
    report = summary.summarize(raw, live_version="12.4", set_name="TESTE", date="2026-11-12")
    assert report["counts"]["mutations_read_back"] == 1
    assert report["counts"]["mutations_certified_by_response"] == 1
    assert report["counts"]["mutations_without_check"] == 1
    assert report["counts"]["reads_answered"] == 1
    by_tool = {row["tool"]: row for row in report["tools"]}
    assert by_tool["create_cue_point"]["evidence"] == "name=Probe time=8.0"
    assert by_tool["run_batch"]["certified_by"] == "response"
    assert "evidence" not in by_tool["get_track_list"]
    assert set(by_tool["get_track_list"]) == {"tool", "group", "status"}


def test_a_local_path_in_evidence_is_refused() -> None:
    raw = _raw(("create_clip", "live_passed", r"wrote C:\Users\someone\set.als"))
    with pytest.raises(SystemExit):
        summary.summarize(raw, live_version="12.4", set_name="TESTE", date="2026-11-12")


@pytest.mark.parametrize(
    "text",
    [r"C:\temp\x", "/Users/ana/x", "/home/u/projects", "D:/media"],
)
def test_privacy_filter_flags_paths(text: str) -> None:
    assert privacy.personal_path_hits({"k": [text]}, home=Path("/home/u"))


def test_privacy_filter_lets_plain_values_through() -> None:
    assert privacy.personal_path_hits({"tempo": 120, "name": "Batch 1"}, home=Path("/home/u")) == []
