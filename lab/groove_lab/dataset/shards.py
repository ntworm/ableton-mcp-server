"""Content-addressed shards of memory-mappable .npy arrays with a JSONL index.

One ``.npy`` per field rather than one ``.npz`` per shard, because ``.npz`` is a
zip archive and cannot be memory mapped.  ``allow_pickle`` is never used, on read
or write: specification 11.3 rules pickle out of the format entirely.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .windows import Window

FIELDS = ("hit", "subhits", "velocity", "offset", "observed", "target")


class ShardWriter:
    def __init__(self, root: Path, rows_per_shard: int) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.rows_per_shard = rows_per_shard
        self._buffer: list[tuple[Window, np.ndarray, tuple[int, int, int]]] = []
        self._records: list[dict[str, Any]] = []
        self._shard_index = 0

    def add(
        self,
        window: Window,
        conditions: np.ndarray,
        ids: tuple[int, int, int],
        record: dict[str, Any],
    ) -> None:
        record = dict(record)
        record["shard"] = f"{self._shard_index:04d}"
        record["row"] = len(self._buffer)
        self._records.append(record)
        self._buffer.append((window, conditions, ids))
        if len(self._buffer) >= self.rows_per_shard:
            self._flush()

    def _flush(self) -> None:
        if not self._buffer:
            return
        directory = self.root / f"{self._shard_index:04d}"
        directory.mkdir(parents=True, exist_ok=True)
        for field in FIELDS:
            stacked = np.stack([getattr(w, field) for w, _c, _i in self._buffer])
            np.save(directory / f"{field}.npy", stacked, allow_pickle=False)
        np.save(
            directory / "conditions.npy",
            np.stack([c for _w, c, _i in self._buffer]).astype(np.float32),
            allow_pickle=False,
        )
        np.save(
            directory / "ids.npy",
            np.array([i for _w, _c, i in self._buffer], dtype=np.uint64),
            allow_pickle=False,
        )
        self._buffer.clear()
        self._shard_index += 1

    def close(self) -> None:
        self._flush()
        with (self.root / "index.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for record in self._records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")


def read_shard(directory: Path) -> dict[str, np.ndarray]:
    directory = Path(directory)
    names = (*FIELDS, "conditions", "ids")
    return {
        name: np.load(directory / f"{name}.npy", mmap_mode="r", allow_pickle=False)
        for name in names
    }
