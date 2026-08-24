"""Build a deterministic groove pilot seed from an explicit file manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ableton_mcp_server.groove_intelligence import GrooveBuildError
from ableton_mcp_server.groove_intelligence.build import build_seed_bundle
from ableton_mcp_server.groove_intelligence.constants import MAX_PILOT_FILES
from ableton_mcp_server.groove_intelligence.schema import BuildInput


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a bounded, deterministic groove seed from listed MIDI files."
    )
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _declared_inputs(input_root: Path, manifest_path: Path) -> list[BuildInput]:
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GrooveBuildError("pilot manifest is invalid") from error
    files = document.get("files") if isinstance(document, dict) else None
    if not isinstance(files, list) or not files:
        raise GrooveBuildError("pilot manifest must contain a non-empty files list")
    if len(files) > MAX_PILOT_FILES:
        raise GrooveBuildError("pilot limit of 5000 files exceeded")
    declared: list[BuildInput] = []
    for entry in files:
        if isinstance(entry, str):
            relative_path = entry
            metadata: dict[str, Any] = {}
        elif isinstance(entry, dict) and isinstance(entry.get("path"), str):
            relative_path = entry["path"]
            metadata = entry
        else:
            raise GrooveBuildError("pilot manifest contains an invalid file entry")
        if Path(relative_path).is_absolute():
            raise GrooveBuildError("pilot manifest paths must be relative")
        declared.append(
            BuildInput(
                path=input_root / relative_path,
                source_kind=str(metadata.get("source_kind", "author")),
                license_id=str(metadata.get("license_id", "pilot-private")),
                redistribution=str(metadata.get("redistribution", "full")),  # type: ignore[arg-type]
            )
        )
    return declared


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        declared = _declared_inputs(args.input_root, args.manifest)
        manifest = build_seed_bundle(
            input_root=args.input_root,
            inputs=declared,
            output_dir=args.output,
            build_config={"pilot": "v1"},
        )
    except GrooveBuildError as error:
        print(json.dumps({"error": str(error)}, separators=(",", ":")), file=sys.stderr)
        return 2
    result = {
        "bundle_manifest_digest": manifest.bundle_manifest_digest,
        "logical_index_digest": manifest.logical_index_digest,
        "artifact_ids": [str(artifact_id) for artifact_id in manifest.artifact_ids],
        "input_count": len(manifest.inputs),
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
