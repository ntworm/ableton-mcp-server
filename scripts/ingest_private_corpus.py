"""Ingest the private MIDI corpus into a Groove Intelligence seed bundle.

Scans a local library, derives every catalog row, and curates a path-free
SQLite bundle from it. Nothing about the source library survives into the
bundle: no path, no directory name, no absolute reference.

This writes to a staging directory. Promoting over the packaged resource is a
separate, explicit step, because that file is the one the product loads at
startup and a half-written or wrong bundle there leaves no working seed at all.

Overlaps ``regenerate_seed.py`` almost entirely. That one exists to rebuild the
shipped seed on a new articulation map and reports the facet coverage that
proves the rebuild worked; this one is the general ingestion entry point for an
arbitrary corpus root.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from ableton_mcp_server.groove_intelligence.constants import MAX_CURATED_REPRESENTATIVES
from ableton_mcp_server.groove_intelligence.corpus import CorpusCatalog, build_curated_bundle

sys.path.insert(0, str(Path(__file__).resolve().parent))
from regenerate_seed import _coverage, _report  # noqa: E402 - needs the path above

DEFAULT_CORPUS_ROOT = Path(
    r"C:\Users\Usuario\Desktop\AUDIO_PRODUCTION\AUDIO\Superior Drummer 3\Toontrack\Midi"
)
DEFAULT_DB_ROOT = Path(r"C:\Users\Usuario\AppData\Local\AbletonMCPServer\groove-build-v3")
DEFAULT_STAGING = Path(r"C:\Users\Usuario\AppData\Local\AbletonMCPServer\seed-ingest-staging")
PACKAGED_SEED = Path(__file__).resolve().parents[1] / "ableton_mcp_server/resources/groove_seed"

# 512 MB leaves the byte cap well clear of the count cap, so a short bundle
# means the corpus ran out of distinct grooves rather than the builder
# silently shrinking the selection to fit.
BUNDLE_BYTE_CAP = 512 * 1024 * 1024


def _promote(staging: Path, destination: Path) -> None:
    """Copy a built bundle over the packaged resource, backing it up first."""

    backup = destination.parent / (destination.name + ".backup")
    if destination.exists():
        if backup.exists():
            shutil.rmtree(backup)
        shutil.copytree(destination, backup)
        print(f"[*] previous seed backed up to {backup}")
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("index.sqlite", "manifest.json"):
        shutil.copy2(staging / name, destination / name)
    print(f"[*] promoted to {destination}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-root", type=Path, default=DEFAULT_CORPUS_ROOT,
        help="Root folder containing the MIDI packs.",
    )
    parser.add_argument(
        "--catalog-root", type=Path, default=DEFAULT_DB_ROOT,
        help="Working directory for the SQLite catalog.",
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_STAGING,
        help="Where the bundle is built. Never the packaged resource.",
    )
    parser.add_argument(
        "--max-files", type=int, default=MAX_CURATED_REPRESENTATIVES,
        help=(
            "Representatives to carry, 1 to "
            f"{MAX_CURATED_REPRESENTATIVES}. The bundle is a curated selection "
            "over the corpus strata, not a copy of the corpus."
        ),
    )
    parser.add_argument(
        "--promote", action="store_true",
        help="After a successful build, copy over the packaged seed. Backs it up first.",
    )
    args = parser.parse_args()

    if not 1 <= args.max_files <= MAX_CURATED_REPRESENTATIVES:
        # Said here rather than surfaced as a ValueError from deep inside the
        # builder after a scan that can take an hour.
        print(
            f"[!] --max-files must be between 1 and {MAX_CURATED_REPRESENTATIVES}; "
            f"got {args.max_files}",
            file=sys.stderr,
        )
        return 2

    if args.out.resolve() == PACKAGED_SEED.resolve():
        print(
            "[!] --out cannot be the packaged seed. Build to staging and pass --promote.",
            file=sys.stderr,
        )
        return 2

    started = time.perf_counter()
    catalog_db = args.catalog_root / "catalog_v3.sqlite"
    report_path = args.catalog_root / "ingestion-report.json"
    print(f"[*] corpus: {args.input_root}")
    print(f"[*] catalog: {catalog_db}")

    try:
        with CorpusCatalog(catalog_db, args.input_root) as catalog:
            print("[*] scanning the directory tree, which takes a while on a full library")
            stats = catalog.scan(retry_errors=True)
            print(
                f"[*] scanned {stats.discovered} files: "
                f"{stats.valid} valid, {stats.failed} failed"
            )
            print("[*] building the path-free deterministic bundle")
            result = build_curated_bundle(
                catalog,
                args.out,
                max_files=args.max_files,
                max_bundle_bytes=BUNDLE_BYTE_CAP,
            )
    except Exception as error:  # noqa: BLE001 - the operator wants the reason, not a traceback
        print(f"[!] ingestion failed: {error}", file=sys.stderr)
        return 1

    print(f"[*] bundle: {args.out} ({result.bundle_bytes} bytes)")
    print(f"[*] manifest digest: {result.first_digest}")
    if result.reduction_attempts:
        print(f"[!] selection was shrunk {result.reduction_attempts} time(s) to fit the byte cap")

    coverage = _coverage(args.out / "index.sqlite")
    _report(coverage, args.max_files)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "schema": "groove.corpus.v3",
                "requested_representatives": args.max_files,
                "ingested_count": result.selected_count,
                "bundle_size_bytes": result.bundle_bytes,
                "manifest_digest": result.first_digest,
                "logical_index_digest": result.logical_index_digest,
                "stats": {
                    "discovered": stats.discovered,
                    "processed": stats.processed,
                    "valid": stats.valid,
                    "failed": stats.failed,
                },
                "elapsed_seconds": round(time.perf_counter() - started, 2),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[*] report: {report_path}")

    if args.promote:
        _promote(args.out, PACKAGED_SEED)
    else:
        print("[*] staging only. Re-run with --promote, or copy the two files by hand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
