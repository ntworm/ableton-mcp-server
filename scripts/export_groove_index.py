"""Export the packaged seed as a single file the Gate 1 helper can load.

The extension ships without Python, SQLite or a network dependency, so the seed
has to reach it as data inside the package. Measured on the 4,000-groove seed
this file is 6.7 MB, which deflates to 2.1 MB inside the .ablx.

Only what the extension can act on is exported: the three searchable axes, the
timing needed to place notes on a grid, and the notes themselves. No path, no
payload, no digest.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ableton_mcp_server.groove_intelligence.midi_lossless import decompress_bounded, parse_smf

DEFAULT_OUT = (
    Path(__file__).resolve().parents[1]
    / "AbletonMCPServer_Extension/groove-brain-gate0/data/grooves.json"
)

# Enough to identify a groove in a list of a few thousand without carrying a
# 64-character digest four thousand times.
ID_PREFIX_LENGTH = 16


def build_export(runtime: Any) -> dict[str, Any]:
    grooves: list[dict[str, Any]] = []
    for artifact_id in sorted(str(item) for item in runtime.index.manifest.artifact_ids):
        card = runtime.card(artifact_id)
        payload = runtime.store.get(artifact_id).payload
        if not payload.blob:
            # A derived-only row carries facets but no MIDI. There is nothing to
            # insert into a clip, so it is not a groove the picker can offer.
            continue
        parsed = parse_smf(
            decompress_bounded(payload.blob, codec=payload.codec, raw_size=payload.raw_size)
        )
        grooves.append(
            {
                "id": artifact_id[:ID_PREFIX_LENGTH],
                "genre": sorted(card.facets.get("genre", [])),
                "bpm": sorted(card.facets.get("bpm", [])),
                "kit": sorted(card.facets.get("kit", [])),
                "bars": card.summary.get("bars"),
                "meter": card.summary.get("meter"),
                "ppq": parsed.format.ppq,
                "notes": [
                    [note.pitch, note.start_ticks, note.duration_ticks, note.velocity]
                    for note in parsed.note_events
                ],
            }
        )
    return {"schema": "groove.export.v1", "grooves": grooves}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    from ableton_mcp_server.server import get_groove_runtime

    export = build_export(get_groove_runtime())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(export, separators=(",", ":")), encoding="utf-8")

    notes = sum(len(groove["notes"]) for groove in export["grooves"])
    print(f"[*] {len(export['grooves'])} grooves, {notes} notes")
    print(f"[*] {args.out} ({args.out.stat().st_size / 1024 / 1024:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
