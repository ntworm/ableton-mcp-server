"""Shared fixtures for the acceptance-runner integration tests.

The runner exercises ``run_offline_probes`` (which spawns the
``scaffold_extension`` → ``npm install`` → ``tsc --noEmit && tsx build.ts``
pipeline) every time the ``offline`` profile is selected. That pipeline
takes several seconds per invocation and would dominate the wall-clock
time of the test suite if every integration test ran it end-to-end.

The canonical environmental test for the offline pipeline lives in
``tests/test_acceptance_audit_p0p1.py::test_p0_1_run_offline_probes_records_build_extension_as_offline_passed``
— it is the single test that exercises the real implementation. Every
other runner-level test uses the ``fast_offline_probes`` fixture below
to inject a deterministic, sub-millisecond implementation. Production
callers (``ableton-mcp acceptance ...``) keep the real implementation
because they pass ``offline_probes=None`` (the default).
"""

from __future__ import annotations

from typing import Any

from ableton_mcp_server.certification import CertificationReport, Verification

_OFFLINE_TOOL_NAMES: tuple[str, ...] = (
    "get_ableton_logs",
    "diff_snapshots_tool",
    "scaffold_extension",
    "build_extension",
    "analyze_audio",
    "find_frequency_masking",
    "analyze_mix",
    "extract_single_cycle",
)


async def fast_offline_probes(
    report: CertificationReport,
    workdir: Any,
) -> None:
    """Inject deterministic ``offline_passed`` rows for every offline tool.

    The fixture records the same eight rows ``run_offline_probes`` would
    record in the green path, without running ``scaffold_extension``,
    ``build_extension``, or any of the audio analysis helpers. Tests
    that need to assert a *failure* path must not use this fixture;
    they should patch ``run_offline_probes`` directly so the failure
    row reaches the report.
    """
    for tool in _OFFLINE_TOOL_NAMES:
        if tool not in report.tool_names:
            continue
        report.record(
            Verification(
                tool=tool,
                status="offline_passed",
                evidence="deterministic injection from fast_offline_probes",
            )
        )
