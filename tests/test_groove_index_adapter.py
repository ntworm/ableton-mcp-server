from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ableton_mcp_server.groove_intelligence import GrooveIndexInvalid
from ableton_mcp_server.groove_intelligence.index import GrooveQueryRejected
from tests.fixtures.groove_runtime import make_pilot_runtime


def test_index_adapter_uses_only_allowlisted_statements(tmp_path: Path) -> None:
    index = make_pilot_runtime(tmp_path).index
    with pytest.raises(GrooveQueryRejected, match="statement not allowlisted"):
        index.execute_for_test("SELECT * FROM artifacts")
    artifact_id = index.manifest.artifact_ids[0]
    assert index.load_projection(artifact_id, "groove.hvo.v2").schema_version == "groove.hvo.v2"
    with pytest.raises(GrooveIndexInvalid):
        index.load_projection(artifact_id, "groove.hvo.v1")


def test_runtime_closes_immutable_seed_connection(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    runtime.close()
    with pytest.raises(sqlite3.ProgrammingError):
        runtime.index.connection.execute("SELECT 1")


def test_runtime_rejects_legacy_projection_references(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    artifact_id = str(runtime.index.manifest.artifact_ids[0])
    artifact = runtime.store.get(artifact_id)
    legacy = artifact.projections[0].model_copy(update={"version": "groove.hvo.v1"})
    runtime.store.put(
        artifact.model_copy(update={"projections": (legacy, *artifact.projections[1:])})
    )
    with pytest.raises(GrooveIndexInvalid, match="unsupported projection reference"):
        runtime.card(artifact_id)
