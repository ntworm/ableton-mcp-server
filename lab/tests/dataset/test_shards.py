from __future__ import annotations

import dataclasses
import json

import numpy as np

from groove_lab.dataset.roundtrip import cells_from_window, roundtrip_is_exact
from groove_lab.dataset.shards import ShardWriter, read_shard
from groove_lab.dataset.windows import LANES, STEPS, Window


def _window(seed: int) -> Window:
    rng = np.random.default_rng(seed)
    hit = (rng.random((STEPS, LANES)) > 0.9).astype(np.uint8)
    return Window(
        hit=hit,
        subhits=(hit * rng.integers(1, 4, (STEPS, LANES))).astype(np.uint8),
        velocity=(hit * rng.random((STEPS, LANES))).astype(np.float32),
        offset=(hit * rng.integers(-60, 61, (STEPS, LANES))).astype(np.int8),
        observed=np.zeros((STEPS, LANES), dtype=np.uint8),
        target=np.ones((STEPS, LANES), dtype=np.uint8),
        start_bar=0,
        looped=False,
    )


def test_shard_round_trips_every_field_exactly(tmp_path) -> None:
    writer = ShardWriter(tmp_path / "train", rows_per_shard=2)
    for index in range(5):
        writer.add(
            _window(index),
            conditions=np.zeros(16, dtype=np.float32),
            ids=(index, index, index),
            record={"source_id": str(index)},
        )
    writer.close()

    lines = (tmp_path / "train" / "index.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines]
    assert len(rows) == 5

    for index in range(5):
        original = _window(index)
        shard = read_shard(tmp_path / "train" / rows[index]["shard"])
        row = rows[index]["row"]
        assert np.array_equal(shard["hit"][row], original.hit)
        assert np.array_equal(shard["subhits"][row], original.subhits)
        assert np.array_equal(shard["offset"][row], original.offset)
        assert np.array_equal(shard["velocity"][row], original.velocity)


def test_arrays_are_memory_mappable_and_not_pickled(tmp_path) -> None:
    writer = ShardWriter(tmp_path / "train", rows_per_shard=4)
    writer.add(_window(0), np.zeros(16, dtype=np.float32), (0, 0, 0), {"source_id": "0"})
    writer.close()
    path = tmp_path / "train" / "0000" / "hit.npy"
    mapped = np.load(path, mmap_mode="r", allow_pickle=False)
    assert mapped.shape[1:] == (STEPS, LANES)


def test_roundtrip_reports_exactness() -> None:
    window = _window(3)
    cells = cells_from_window(window)
    assert roundtrip_is_exact(window, cells)
    # Losing one subhit must be detected.
    broken = list(cells)
    assert broken, "the fixture must produce at least one cell"
    broken[0] = dataclasses.replace(broken[0], subhits=99)
    assert not roundtrip_is_exact(window, tuple(broken))
