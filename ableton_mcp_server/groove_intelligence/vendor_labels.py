"""Genre and tempo from the vendor MIDI databases, used only at build time.

``_TAXONOMY_AXES`` has always declared ``genre`` and ``subgenre``; nothing ever
filled them, because a folder name does not carry a genre. The vendor databases
do, for 103,096 files, along with a tempo for 97.8% of them.

The sidecar lives outside the repository and is optional. A build without it
produces a seed with no genre facet, which is exactly what ships today, so its
absence degrades nothing.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_SIDECAR = (
    r"C:\Users\Usuario\AppData\Local\AbletonMCPServer\groove-vendor-labels"
    r"\vendor_labels.jsonl"
)

# Coarse enough to browse, fine enough to be useful. A facet is a search axis;
# the exact tempo stays in the features projection.
_TEMPO_BUCKETS = (
    (60, 79, "bpm_60_79"),
    (80, 99, "bpm_80_99"),
    (100, 119, "bpm_100_119"),
    (120, 139, "bpm_120_139"),
    (140, 159, "bpm_140_159"),
    (160, 179, "bpm_160_179"),
    (180, 260, "bpm_180_plus"),
)


@dataclass(frozen=True)
class VendorLabels:
    by_path: dict[str, dict[str, Any]]

    @classmethod
    def load(cls, path: str | Path = DEFAULT_SIDECAR) -> VendorLabels:
        """Return the labels for ``path``, parsed once per process.

        The sidecar is a hundred thousand lines. A build reads it once, but a
        test suite builds dozens of bundles, and re-parsing per build churns
        enough short-lived objects to crash the interpreter during collection.
        Nothing writes to the result, so one shared instance is correct.
        """

        return _load_cached(str(path))

    def for_path(self, relative_path: str) -> dict[str, Any]:
        return self.by_path.get(relative_path, {})


@lru_cache(maxsize=4)
def _load_cached(path: str) -> VendorLabels:
    source = Path(path)
    if not source.exists():
        return VendorLabels(by_path={})
    records: dict[str, dict[str, Any]] = {}
    with source.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            key = record.get("path")
            if isinstance(key, str):
                records[key] = record
    return VendorLabels(by_path=records)


def genre_facet(record: Mapping[str, Any]) -> tuple[str, ...]:
    genre = record.get("genre")
    if not isinstance(genre, str) or not genre:
        return ()
    normalised = genre.lower().replace("/", "_").replace(" ", "_").replace("-", "_")
    return (normalised,)


def tempo_facet(record: Mapping[str, Any]) -> tuple[str, ...]:
    tempo = record.get("tempo")
    if not isinstance(tempo, int | float) or isinstance(tempo, bool) or not tempo:
        return ()
    for low, high, name in _TEMPO_BUCKETS:
        if low <= tempo <= high:
            return (name,)
    return ()


__all__ = ["VendorLabels", "genre_facet", "tempo_facet"]
