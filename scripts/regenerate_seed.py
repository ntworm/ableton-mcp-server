"""Rebuild the retrieval seed on the v3 articulation map.

Writes to a staging directory rather than over ``ableton_mcp_server/resources``.
The packaged resource is the file the product loads at startup; overwriting it
before the new bundle has been inspected would leave no working seed if the
build turns out wrong. Promotion is a deliberate copy, done by hand, after the
coverage summary printed here has been read.

The summary is the point of the script. A seed can be built successfully and
still be useless: if the v3 projection never reaches ``classify_facets`` the
bundle is byte-valid and every kit facet still says ``other_percussion``. The
numbers below are what distinguish those two outcomes.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ableton_mcp_server.groove_intelligence.constants import (
    HVO_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION_V3,
    MAX_CURATED_REPRESENTATIVES,
)
from ableton_mcp_server.groove_intelligence.corpus import CorpusCatalog, build_curated_bundle
from ableton_mcp_server.groove_intelligence.vendor_labels import DEFAULT_SIDECAR, VendorLabels

DEFAULT_CORPUS_ROOT = Path(
    r"C:\Users\Usuario\Desktop\AUDIO_PRODUCTION\AUDIO\Superior Drummer 3\Toontrack\Midi"
)
DEFAULT_CATALOG_ROOT = Path(r"C:\Users\Usuario\AppData\Local\AbletonMCPServer\groove-build-v3")
DEFAULT_OUT = Path(r"C:\Users\Usuario\AppData\Local\AbletonMCPServer\seed-v3-staging")

# Decision S2. The byte cap has to leave room for it: the builder shrinks the
# selection silently when the bundle would exceed the cap, so a cap chosen for
# 1,685 representatives would quietly return far fewer than 4,000.
DEFAULT_REPRESENTATIVES = 4000
DEFAULT_BUNDLE_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True)
class Coverage:
    """What the built bundle actually contains, read back from the file."""

    artifacts: int
    projections: dict[str, int]
    artifacts_per_axis: dict[str, int]
    kit_values: Counter[str]
    distinct_genres: int


def _coverage(db_path: Path) -> Coverage:
    """Read back what was written, not what was intended."""

    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        artifacts = int(connection.execute("SELECT count(*) FROM artifacts").fetchone()[0])
        projections = {
            str(version): int(count)
            for version, count in connection.execute(
                "SELECT version, count(*) FROM projections GROUP BY version"
            )
        }
        axes = {
            str(axis): int(count)
            for axis, count in connection.execute(
                "SELECT axis, count(DISTINCT artifact_id) FROM facets GROUP BY axis"
            )
        }
        kits: Counter[str] = Counter()
        for value, count in connection.execute(
            "SELECT value, count(*) FROM facets WHERE axis='kit' GROUP BY value"
        ):
            kits[str(value)] = int(count)
        distinct_genres = int(
            connection.execute(
                "SELECT count(DISTINCT value) FROM facets WHERE axis='genre'"
            ).fetchone()[0]
        )
    finally:
        connection.close()
    return Coverage(
        artifacts=artifacts,
        projections=projections,
        artifacts_per_axis=axes,
        kit_values=kits,
        distinct_genres=distinct_genres,
    )


def _report(coverage: Coverage, requested: int) -> None:
    artifacts = coverage.artifacts
    print(f"[*] artifacts: {artifacts}")
    if artifacts < requested:
        # Never let a silent shrink read as a full build.
        print(
            f"[!] requested {requested} representatives, bundle carries {artifacts}. "
            "The byte cap or the corpus, not the request, decided this."
        )

    for version in (HVO_SCHEMA_VERSION, HVO_SCHEMA_VERSION_V3):
        count = coverage.projections.get(version, 0)
        marker = "ok" if count == artifacts else "MISSING"
        print(f"[*] projection {version}: {count} ({marker})")

    for axis in ("kit", "genre", "bpm"):
        covered = coverage.artifacts_per_axis.get(axis, 0)
        share = (100.0 * covered / artifacts) if artifacts else 0.0
        print(f"[*] axis {axis}: {covered} artifacts ({share:.1f}%)")
    print(f"[*] distinct genres: {coverage.distinct_genres}")

    total_kit = sum(coverage.kit_values.values())
    if total_kit:
        junk = coverage.kit_values.get("other_percussion", 0)
        print(
            f"[*] kit other_percussion: {junk} of {total_kit} facet rows "
            f"({100.0 * junk / total_kit:.1f}%)"
        )
        for value, count in coverage.kit_values.most_common(8):
            print(f"      {value}: {count}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--catalog-root", type=Path, default=DEFAULT_CATALOG_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--representatives", type=int, default=DEFAULT_REPRESENTATIVES)
    parser.add_argument("--max-bundle-bytes", type=int, default=DEFAULT_BUNDLE_BYTES)
    parser.add_argument(
        "--rescan",
        action="store_true",
        help="Re-derive every catalog row instead of reusing unchanged ones.",
    )
    args = parser.parse_args()

    if not 1 <= args.representatives <= MAX_CURATED_REPRESENTATIVES:
        print(
            f"[!] --representatives must be between 1 and {MAX_CURATED_REPRESENTATIVES}",
            file=sys.stderr,
        )
        return 2

    labels = VendorLabels.load()
    if labels.by_path:
        print(f"[*] vendor labels: {len(labels.by_path)} paths from {DEFAULT_SIDECAR}")
    else:
        # Not fatal, but it silently costs the genre and bpm axes, so it is said
        # out loud rather than discovered in the coverage summary.
        print(f"[!] vendor label sidecar is absent at {DEFAULT_SIDECAR}")
        print("[!] the seed will build without the genre and bpm facets")

    started = time.perf_counter()
    catalog_db = args.catalog_root / "catalog_v3.sqlite"
    print(f"[*] catalog: {catalog_db}")
    print(f"[*] corpus: {args.input_root}")

    try:
        with CorpusCatalog(catalog_db, args.input_root) as catalog:
            stats = catalog.scan(retry_errors=args.rescan)
            print(
                f"[*] scanned {stats.discovered} files: "
                f"{stats.valid} valid, {stats.failed} failed"
            )
            result = build_curated_bundle(
                catalog,
                args.out,
                max_files=args.representatives,
                max_bundle_bytes=args.max_bundle_bytes,
            )
    except Exception as error:  # noqa: BLE001 - the caller wants the reason, not a traceback
        print(f"[!] regeneration failed: {error}", file=sys.stderr)
        return 1

    print(f"[*] bundle: {args.out} ({result.bundle_bytes} bytes)")
    print(f"[*] manifest digest: {result.first_digest}")
    print(f"[*] logical index digest: {result.logical_index_digest}")
    if result.reduction_attempts:
        print(f"[!] selection was shrunk {result.reduction_attempts} time(s) to fit the byte cap")

    coverage = _coverage(args.out / "index.sqlite")
    _report(coverage, args.representatives)

    report_path = args.catalog_root / "regeneration-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "requested_representatives": args.representatives,
                "selected_count": result.selected_count,
                "bundle_bytes": result.bundle_bytes,
                "manifest_digest": result.first_digest,
                "logical_index_digest": result.logical_index_digest,
                "reduction_attempts": result.reduction_attempts,
                "vendor_label_paths": len(labels.by_path),
                "coverage": {
                    "artifacts": coverage.artifacts,
                    "projections": coverage.projections,
                    "artifacts_per_axis": coverage.artifacts_per_axis,
                    "distinct_genres": coverage.distinct_genres,
                    "kit_values": dict(coverage.kit_values),
                },
                "elapsed_seconds": round(time.perf_counter() - started, 2),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[*] report: {report_path}")
    print("[*] staging only. Promote by copying index.sqlite and manifest.json by hand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
