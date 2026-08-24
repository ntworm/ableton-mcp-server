from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from ableton_mcp_server import server
from tests.fixtures.groove_runtime import make_pilot_runtime


def test_four_local_tools_do_not_call_bridge(tmp_path: Path, monkeypatch) -> None:
    runtime = make_pilot_runtime(tmp_path)
    monkeypatch.setattr(server, "get_groove_runtime", lambda: runtime)
    mock_get_client = MagicMock()
    monkeypatch.setattr(server, "get_client", mock_get_client)
    artifact_id = runtime.index.manifest.artifact_ids[0]
    server.groove_search(
        schema_version="groove.search.request.v1",
        facets={"feel": ["straight"]},
        limit=1,
    )
    server.groove_evidence(
        schema_version="groove.evidence.request.v1",
        artifact_id=artifact_id,
        include_projections=[],
    )
    mock_get_client.assert_not_called()
