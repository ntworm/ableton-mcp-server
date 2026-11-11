"""The batch-cost script reproduces its call counts without Live."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from ableton_mcp_server import server

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "measure_batch_cost.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("measure_batch_cost", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cost(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setattr(server, "_client", None)
    return _load()


def test_fake_run_counts_42_and_4_calls(cost: ModuleType) -> None:
    rows = {}
    for variant in ("A", "B"):
        cost.use_fake_bridge()
        rows[variant] = asyncio.run(cost.measure(variant, "fake"))
    assert rows["A"]["calls"] == 42
    assert rows["B"]["calls"] == 4
    for row in rows.values():
        assert row["errors"] == []
        assert row["argument_chars"] > 0
        assert row["tools_list_chars"] > 0
        assert "result_chars" not in row, "fake results are not Live results"


def test_base_index_skips_returns_and_master(cost: ModuleType) -> None:
    rows = [
        {"type": "midi"},
        {"type": "audio"},
        {"type": "audio"},
        {"type": "return"},
        {"type": "master"},
    ]
    assert cost.base_index(rows) == 3


def test_cue_cells_stay_strictly_inside_the_song(cost: ModuleType) -> None:
    assert cost.cue_times(64.0, []) == [0.0, 8.0, 16.0, 24.0, 32.0, 40.0, 48.0, 56.0]
    with pytest.raises(SystemExit):
        cost.cue_times(64.0, [{"time": 16.0}])
    assert cost.cue_times(80.0, [{"time": 16.0}])[2] == 24.0


def test_both_variants_send_the_same_mutations(cost: ModuleType) -> None:
    times = cost.cue_times(64.0, [])
    unit = cost.plan_variant("A", 3, times)
    batched = cost.plan_variant("B", 3, times)
    commands = [(c["type"], c["params"]) for c in batched[0][1]["commands"]]
    assert commands == unit[:32]
    assert [c for c in unit[32:40]] == [
        ("create_cue_point", item) for item in batched[1][1]["items"]
    ]
    assert unit[-1] == batched[-1] == ("fire_scene", {"scene_index": 0})


def test_markdown_marks_missing_live_columns(cost: ModuleType) -> None:
    table = cost.markdown([{"variant": "A", "calls": 42}])
    assert "| A | 42 | n/a |" in table
