"""Orchestrate a dataset build and describe it well enough to reproduce it.

The order of operations is not negotiable, and it is the order specification 12.3
sets out: cluster before splitting, split by whole cluster, then verify leakage
from the content hashes alone so a bug in the clustering cannot hide a bug in the
split.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import platform
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from ableton_mcp_server.groove_intelligence.articulation import resolve_role
from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf

from .canonical import (
    build_canonical,
    expression_mass_averaged,
    note_mass_lost,
    notes_fused_share,
)
from .clusters import build_clusters, component_sizes
from .conditions import build_conditions
from .config import BuildConfig
from .roundtrip import cells_from_window, roundtrip_is_exact
from .shards import ShardWriter
from .splits import assign_splits, verify_no_leakage
from .windows import to_windows

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG = Path(
    r"C:\Users\Usuario\AppData\Local\AbletonMCPServer\groove-build-v2\catalog_v2.sqlite"
)
CORPUS_ROOT = Path(
    r"C:\Users\Usuario\Desktop\AUDIO_PRODUCTION\AUDIO\Superior Drummer 3\Toontrack\Midi"
)
VENDOR_LABELS = Path(
    r"C:\Users\Usuario\AppData\Local\AbletonMCPServer\groove-vendor-labels\vendor_labels.jsonl"
)
MEASUREMENT = REPO_ROOT / "scripts" / "measurement_output.json"
UNRESOLVED = "other_percussion"
SPLIT_NAMES = ("train", "validation", "test")


@dataclasses.dataclass
class DatasetManifest:
    config: dict[str, Any]
    config_digest: str
    counts: dict[str, int]
    cluster_sizes: dict[str, int]
    representation_loss: float
    notes_fused_share: float
    expression_mass_averaged: float
    unresolved_note_share: float
    excluded_collections: list[str]
    shard_digests: dict[str, str]
    environment: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def manifest_digest(manifest: DatasetManifest) -> str:
    """Hash everything that defines the data, and nothing that defines the machine."""

    payload = manifest.as_dict()
    payload.pop("environment", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _vendor_labels() -> dict[str, dict[str, Any]]:
    if not VENDOR_LABELS.exists():
        return {}
    labels: dict[str, dict[str, Any]] = {}
    with VENDOR_LABELS.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            labels[record["path"]] = record
    return labels


def _excluded_collections(config: BuildConfig) -> tuple[set[str], float]:
    """Collections above the gate G1 unresolved ceiling, and the corpus-wide share."""

    measurement = json.loads(MEASUREMENT.read_text(encoding="utf-8"))
    excluded: set[str] = set()
    total = 0
    unresolved = 0
    for collection, record in measurement.items():
        collection_total = 0
        collection_unresolved = 0
        for raw_pitch, count in record["pitch_histogram"].items():
            pitch = int(raw_pitch)
            collection_total += count
            if resolve_role(collection, pitch) == UNRESOLVED:
                collection_unresolved += count
        total += collection_total
        unresolved += collection_unresolved
        if collection_total and (
            collection_unresolved / collection_total > config.max_unresolved_note_share
        ):
            excluded.add(collection)
    return excluded, (unresolved / total if total else 0.0)


def _selected_files(excluded: set[str], fraction: float) -> list[tuple[str, str]]:
    """A deterministic prefix of byte-unique files, ordered by digest."""

    connection = sqlite3.connect(f"file:{CATALOG}?mode=ro", uri=True)
    rows = connection.execute(
        "select relative_path, stratum from files "
        "where status='ok' and source_digest != '' "
        "group by source_digest order by source_digest"
    ).fetchall()
    connection.close()
    kept = [(path, stratum) for path, stratum in rows if stratum not in excluded]
    return kept[: max(1, int(len(kept) * fraction))]


def _directory_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    if not directory.exists():
        return digest.hexdigest()
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def build_dataset(
    fraction: float, config: BuildConfig, workspace: Path
) -> DatasetManifest:
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    labels = _vendor_labels()
    excluded, unresolved_share = _excluded_collections(config)
    selected = _selected_files(excluded, fraction)

    grooves: dict[str, tuple[str, str, Any]] = {}
    records: list[dict[str, str]] = []
    lost_numerator = 0.0
    fused_numerator = 0.0
    averaged_numerator = 0.0
    lost_denominator = 0.0
    for relative, collection in selected:
        raw = (CORPUS_ROOT / relative).read_bytes()
        parsed = parse_smf(raw)
        groove = build_canonical(parsed, collection)
        source_id = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:32]
        grooves[source_id] = (relative, collection, groove)
        records.append(
            {
                "source_id": source_id,
                "byte_hash": hashlib.sha256(raw).hexdigest(),
                "canonical_hash": groove.canonical_hash,
                "rhythm_hash": groove.rhythm_hash,
                "collection": collection,
            }
        )
        notes = len(parsed.note_events)
        lost_numerator += note_mass_lost(parsed, groove) * notes
        fused_numerator += notes_fused_share(parsed, groove) * notes
        averaged_numerator += expression_mass_averaged(parsed, groove) * notes
        lost_denominator += notes

    clusters = build_clusters(records, max_share=config.max_cluster_share)
    for record in records:
        record["cluster_id"] = clusters[record["source_id"]]
    splits = assign_splits(records, config.split_ratios, config.seed)
    verify_no_leakage(records, splits)

    writers = {
        name: ShardWriter(workspace / "shards" / name, config.rows_per_shard)
        for name in SPLIT_NAMES
    }
    counts: Counter[str] = Counter()
    for index, (source_id, (relative, collection, groove)) in enumerate(
        sorted(grooves.items())
    ):
        split = splits[source_id]
        for window in to_windows(
            groove, config.short_file_policy, config.window_hop_bars
        ):
            if not roundtrip_is_exact(window, cells_from_window(window)):
                raise RuntimeError(f"round-trip failed for {source_id}")
            writers[split].add(
                window,
                conditions=build_conditions(groove, window, labels.get(relative, {})),
                ids=(index, int(clusters[source_id][:8], 16), index),
                record={
                    "source_id": source_id,
                    "cluster_id": clusters[source_id],
                    "collection": collection,
                    "looped": window.looped,
                    "start_bar": window.start_bar,
                },
            )
            counts[split] += 1
    for writer in writers.values():
        writer.close()

    sizes = component_sizes(clusters)
    manifest = DatasetManifest(
        config=config.as_dict(),
        config_digest=config.digest(),
        counts={name: counts.get(name, 0) for name in SPLIT_NAMES},
        cluster_sizes={
            "largest": max(sizes.values(), default=0),
            "count": len(sizes),
        },
        representation_loss=round(
            lost_numerator / lost_denominator if lost_denominator else 0.0, 6
        ),
        notes_fused_share=round(
            fused_numerator / lost_denominator if lost_denominator else 0.0, 6
        ),
        expression_mass_averaged=round(
            averaged_numerator / lost_denominator if lost_denominator else 0.0, 6
        ),
        unresolved_note_share=round(unresolved_share, 6),
        excluded_collections=sorted(excluded),
        shard_digests={
            name: _directory_digest(workspace / "shards" / name) for name in SPLIT_NAMES
        },
        environment={
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
    )
    (workspace / "manifest.json").write_text(
        json.dumps(manifest.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


__all__ = [
    "DatasetManifest",
    "build_dataset",
    "manifest_digest",
]
