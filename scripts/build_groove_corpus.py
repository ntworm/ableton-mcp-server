"""Inventory the authorized MIDI corpus and build a bounded portable seed."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from ableton_mcp_server.groove_intelligence.corpus import (
    CorpusCatalog,
    build_curated_bundle,
)

DEFAULT_SOURCE_ROOT = Path(
    r"C:\Users\Usuario\Desktop\AUDIO_PRODUCTION\AUDIO\Superior Drummer 3\Toontrack\Midi"
)
DEFAULT_CATALOG_ROOT = Path(r"C:\Users\Usuario\AppData\Local\AbletonMCPServer\groove-build-v1")
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "ableton_mcp_server/resources/groove_seed"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--catalog-root", type=Path, default=DEFAULT_CATALOG_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-files", type=int, default=2048)
    parser.add_argument("--max-bundle-bytes", type=int, default=32 * 1024 * 1024)
    parser.add_argument("--retry-errors", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    started = time.perf_counter()
    catalog_db = args.catalog_root / "catalog.sqlite"
    report_path = args.catalog_root / "corpus-report.json"
    try:
        with CorpusCatalog(catalog_db, args.input_root) as catalog:
            stats = catalog.scan(retry_errors=args.retry_errors)
            rows = catalog.rows()
            valid = [row for row in rows if row.status == "ok"]
            errors = Counter(row.error_code for row in rows if row.status == "error")
            result = build_curated_bundle(
                catalog,
                args.output,
                max_files=args.max_files,
                max_bundle_bytes=args.max_bundle_bytes,
            )
            report = {
                "schema_version": "groove.corpus.report.v1",
                "catalog_schema": "groove.corpus.v1",
                "selected_count": result.selected_count,
                "selected_source_bytes": result.selected_source_bytes,
                "bundle_bytes": result.bundle_bytes,
                "bundle_manifest_digest": result.first_digest,
                "logical_index_digest": result.logical_index_digest,
                "repeat_bundle_manifest_digest": result.second_digest,
                "artifact_count": len(result.artifact_ids),
                "inventory": {
                    "discovered": stats.discovered,
                    "processed": stats.processed,
                    "reused": stats.reused,
                    "valid": stats.valid,
                    "failed": stats.failed,
                    "deduplicated": stats.deduplicated,
                    "events": sum(row.event_count for row in valid),
                    "note_events": sum(row.note_count for row in valid),
                    "error_codes": dict(sorted(errors.items())),
                },
                "taxonomy": dict(
                    sorted(
                        Counter(
                            value
                            for row in valid
                            for values in row.facets.values()
                            for value in values
                        ).items()
                    )
                ),
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    except (OSError, ValueError) as error:
        print(json.dumps({"error": type(error).__name__}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
