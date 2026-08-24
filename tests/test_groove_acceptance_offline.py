from __future__ import annotations

from pathlib import Path

import pytest

from ableton_mcp_server.acceptance.probes.offline import run
from ableton_mcp_server.catalog import TOOL_CATALOG
from ableton_mcp_server.certification import CertificationReport, Verification
from tests.fixtures.groove_runtime import make_pilot_acceptance_inputs


@pytest.mark.asyncio
async def test_offline_probe_records_five_groove_tools_without_bridge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, requests = make_pilot_acceptance_inputs(tmp_path)
    report = CertificationReport(tool_names=tuple(item.name for item in TOOL_CATALOG))
    bridge_calls: list[str] = []
    monkeypatch.setattr(
        "ableton_mcp_server.acceptance.probes.offline.get_client",
        lambda: bridge_calls.append("bridge"),
    )
    await run(report, tmp_path, runtime=runtime, requests=requests)
    rows = {name: row for name, row in report.recorded.items() if name.startswith("groove_")}
    assert set(rows) == {
        "groove_search",
        "groove_evidence",
        "groove_generate",
        "groove_compare",
        "groove_apply",
    }
    assert all(row.status == "offline_passed" for row in rows.values())
    assert bridge_calls == []


@pytest.mark.asyncio
async def test_canonical_offline_runner_uses_packaged_seed_without_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bundled seed is the default; an environment override is optional."""
    from ableton_mcp_server.acceptance import runner

    monkeypatch.delenv("ABLETON_GROOVE_SEED_BUNDLE", raising=False)
    report = CertificationReport(tool_names=tuple(item.name for item in TOOL_CATALOG))
    real_record_call = runner._record_call

    async def groove_only_record_call(
        target_report: CertificationReport,
        tool: str,
        action: object,
        *,
        passed: str = "offline_passed",
    ) -> object:
        if tool.startswith("groove_"):
            return await real_record_call(target_report, tool, action, passed=passed)  # type: ignore[arg-type]
        target_report.record(Verification(tool, passed, "test skipped unrelated probe"))
        return None

    monkeypatch.setattr(runner, "_record_call", groove_only_record_call)
    await runner.run_offline_probes(report, tmp_path)

    rows = {name: row for name, row in report.recorded.items() if name.startswith("groove_")}
    assert set(rows) == {
        "groove_search",
        "groove_evidence",
        "groove_generate",
        "groove_compare",
        "groove_apply",
    }
    assert all(row.status == "offline_passed" for row in rows.values())
