from __future__ import annotations

import pytest

from ableton_mcp_server.catalog import TOOL_CATALOG
from ableton_mcp_server.certification import CertificationReport, Verification


def test_baseline_probe_names_equal_catalog() -> None:
    """The flattened probe map must cover the full 65-tool baseline surface."""
    from ableton_mcp_server.acceptance import (
        BASELINE_PROBE_GROUPS,
        assert_baseline_probe_coverage,
    )

    assert_baseline_probe_coverage()
    flattened = [name for names in BASELINE_PROBE_GROUPS.values() for name in names]
    assert len(set(flattened)) == 65
    assert len(flattened) == 65  # every tool appears in exactly one group
    assert set(flattened) == {item.name for item in TOOL_CATALOG}


def test_report_rejects_missing_catalog_rows() -> None:
    report = CertificationReport(tool_names=tuple(item.name for item in TOOL_CATALOG))
    report.record(Verification("get_session_info", "live_passed", "ok"))
    with pytest.raises(ValueError, match="64 tools are unclassified"):
        report.finish()


def test_release_ready_rejects_failed_and_host_unavailable() -> None:
    names = ("a", "b")
    report = CertificationReport(tool_names=names)
    report.record(Verification("a", "offline_passed", "pytest"))
    report.record(Verification("b", "host_unavailable", "Song.save missing"))
    assert report.finish()["release_ready"] is False


def test_verification_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="unknown verification status"):
        Verification("get_session_info", "weird", "x")


def test_verification_rejects_blank_evidence() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        Verification("get_session_info", "live_passed", "   ")


def test_report_rejects_tool_outside_catalog() -> None:
    report = CertificationReport(tool_names=("a",))
    with pytest.raises(ValueError, match="not cataloged"):
        report.record(Verification("b", "live_passed", "ok"))


def test_finished_report_contains_immutable_rows_in_catalog_order() -> None:
    names = ("zeta", "alpha", "mu")
    report = CertificationReport(tool_names=names)
    report.record(Verification("zeta", "live_passed", "ok"))
    report.record(Verification("alpha", "host_unavailable", "missing"))
    report.record(Verification("mu", "failed", "broken"))
    finished = report.finish()
    assert [row["tool"] for row in finished["tools"]] == list(names)
    assert finished["release_ready"] is False
    assert finished["tool_count"] == 3
