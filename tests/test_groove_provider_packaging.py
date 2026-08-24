from __future__ import annotations

from pathlib import Path

from ableton_mcp_server.groove_intelligence.deterministic import deterministic_generate
from tests.fixtures.groove_provider_payloads import (
    make_deterministic_request,
    make_provider_runtime,
)


def test_deterministic_runtime_needs_no_provider_installation(tmp_path: Path) -> None:
    runtime = make_provider_runtime(tmp_path)
    result = deterministic_generate(
        runtime, make_deterministic_request(provider="deterministic")
    )
    assert str(result.artifact.artifact_id).startswith("ga1_")

