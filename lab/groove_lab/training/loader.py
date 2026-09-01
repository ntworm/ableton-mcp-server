"""Read the V3 shards without copying them into memory.

The shards are ``.npy`` arrays written for exactly this: ``mmap_mode='r'`` keeps
the 2.4 GB full build off the heap.  The stored ``target`` array marks which
cells are legitimate targets at all — padding from the short-file policy is
already excluded — so it is loaded as ``valid`` and the task sampler intersects
with it rather than overriding it.
"""

from __future__ import annotations

import json
import random
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

FIELDS = ("hit", "subhits", "velocity", "offset", "target", "conditions")


class ShardDataset:
    def __init__(self, root: str | Path, split: str, max_subhits: int) -> None:
        self.root = Path(root) / "shards" / split
        self.max_subhits = max_subhits
        lines = (self.root / "index.jsonl").read_text(encoding="utf-8").splitlines()
        self.index: list[dict[str, Any]] = [json.loads(line) for line in lines]
        self._shards: dict[str, dict[str, np.ndarray]] = {}

    def __len__(self) -> int:
        return len(self.index)

    def _shard(self, name: str) -> dict[str, np.ndarray]:
        if name not in self._shards:
            directory = self.root / name
            self._shards[name] = {
                field: np.load(
                    directory / f"{field}.npy", mmap_mode="r", allow_pickle=False
                )
                for field in FIELDS
            }
        return self._shards[name]

    def __getitem__(self, position: int) -> dict[str, np.ndarray]:
        record = self.index[position]
        shard = self._shard(record["shard"])
        row = record["row"]
        return {
            "hit": np.asarray(shard["hit"][row], dtype=np.float32),
            "subhits": np.clip(
                np.asarray(shard["subhits"][row], dtype=np.int64),
                0,
                self.max_subhits - 1,
            ),
            "velocity": np.asarray(shard["velocity"][row], dtype=np.float32),
            "offset": np.asarray(shard["offset"][row], dtype=np.float32) / 60.0,
            "valid": np.asarray(shard["target"][row], dtype=np.float32),
            "conditions": np.asarray(shard["conditions"][row], dtype=np.float32),
        }

    def batch_indices(self, batch_size: int, seed: int) -> list[list[int]]:
        order = list(range(len(self)))
        random.Random(seed).shuffle(order)
        return [order[i : i + batch_size] for i in range(0, len(order), batch_size)]

    def collate(self, positions: list[int]) -> dict[str, np.ndarray]:
        examples = [self[position] for position in positions]
        return {key: np.stack([e[key] for e in examples]) for key in examples[0]}


@lru_cache(maxsize=8)
def clamp_cost(root: str, split: str, max_subhits: int) -> float:
    """Share of hit cells whose event count the head's class range cannot hold."""

    dataset = ShardDataset(root, split, max_subhits=256)
    over = 0
    total = 0
    for position in range(len(dataset)):
        example = dataset[position]
        counts = example["subhits"][example["hit"] == 1.0]
        total += int(counts.size)
        over += int((counts > max_subhits - 1).sum())
    return over / total if total else 0.0
