"""Measure the drum corpus so the articulation map can be derived from evidence.

For every collection in the catalog this records, over the byte-unique files:

* the pitch histogram;
* the strongest same-tick co-occurrence pairs;
* a rhythmic profile per pitch: how many notes per file, how tightly spaced the
  onsets are, how much of the mass sits on eighth-note positions, and how much
  clusters at the end of the bar.

The rhythmic profile is what separates a closed hi-hat from a pedal or an open
one without guessing, by comparing each pitch against the General MIDI hi-hat
pitches that appear in the same corpus.

Output: ``scripts/measurement_output.json``.  Deterministic: files are ordered by
digest and the JSON is written with sorted keys.
"""

from __future__ import annotations

import collections
import json
import multiprocessing
import sqlite3
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf  # noqa: E402
from ableton_mcp_server.groove_intelligence.projections import _grid_position  # noqa: E402

CORPUS_ROOT = Path(
    r"C:\Users\Usuario\Desktop\AUDIO_PRODUCTION\AUDIO\Superior Drummer 3\Toontrack\Midi"
)
DB_PATH = Path(r"C:\Users\Usuario\AppData\Local\AbletonMCPServer\groove-build-v2\catalog_v2.sqlite")
OUTPUT = REPO_ROOT / "scripts" / "measurement_output.json"

STEPS_PER_BAR = 16
CHUNK_SIZE = 2000
WORKERS = 8

Histogram = dict[str, "collections.Counter[int]"]
PairCounter = dict[str, "collections.Counter[tuple[int, int]]"]
ProfileAccumulator = dict[str, dict[int, dict[str, Any]]]


def _blank_profile() -> dict[str, Any]:
    return {"files": 0, "notes": 0, "gaps": collections.Counter(), "steps": collections.Counter()}


def _process_chunk(
    rows: list[tuple[str, str]],
) -> tuple[dict[str, dict[int, int]], dict[str, dict[str, int]], ProfileAccumulator, int]:
    histogram: Histogram = collections.defaultdict(collections.Counter)
    pairs: PairCounter = collections.defaultdict(collections.Counter)
    profiles: ProfileAccumulator = collections.defaultdict(dict)

    for relative_path, collection in rows:
        try:
            parsed = parse_smf((CORPUS_ROOT / relative_path).read_bytes())
        except Exception:  # noqa: BLE001 - a corrupt file must not stop the sweep
            continue

        positions: dict[int, list[int]] = collections.defaultdict(list)
        by_tick: dict[int, list[int]] = collections.defaultdict(list)
        for note in parsed.note_events:
            histogram[collection][note.pitch] += 1
            bar, step, _offset = _grid_position(parsed, note.start_ticks)
            positions[note.pitch].append(bar * STEPS_PER_BAR + step)
            by_tick[note.start_ticks].append(note.pitch)

        for group in by_tick.values():
            if len(group) < 2:
                continue
            unique = sorted(set(group))
            for i, first in enumerate(unique):
                for second in unique[i + 1 :]:
                    pairs[collection][(first, second)] += 1

        for pitch, steps in positions.items():
            steps.sort()
            slot = profiles[collection].setdefault(pitch, _blank_profile())
            slot["files"] += 1
            slot["notes"] += len(steps)
            for value in steps:
                slot["steps"][value % STEPS_PER_BAR] += 1
            for previous, current in zip(steps, steps[1:], strict=False):
                if current > previous:
                    slot["gaps"][min(current - previous, 32)] += 1

    plain_hist = {k: dict(v) for k, v in histogram.items()}
    plain_pairs = {k: {f"{a}:{b}": n for (a, b), n in v.items()} for k, v in pairs.items()}
    return plain_hist, plain_pairs, profiles, len(rows)


def _merge_profile(target: dict[str, Any], source: dict[str, Any]) -> None:
    target["files"] += source["files"]
    target["notes"] += source["notes"]
    target["gaps"].update(source["gaps"])
    target["steps"].update(source["steps"])


def _summarise_profile(slot: dict[str, Any]) -> dict[str, Any]:
    gaps: collections.Counter[int] = slot["gaps"]
    steps: collections.Counter[int] = slot["steps"]
    total_gaps = sum(gaps.values())
    total_steps = sum(steps.values())

    median_gap = 0
    if total_gaps:
        seen = 0
        for value in sorted(gaps):
            seen += gaps[value]
            if seen * 2 >= total_gaps:
                median_gap = value
                break

    return {
        "files": slot["files"],
        "notes": slot["notes"],
        "notes_per_file": round(slot["notes"] / slot["files"], 4) if slot["files"] else 0.0,
        "median_gap_steps": median_gap,
        "gap_one_share": round(gaps[1] / total_gaps, 6) if total_gaps else 0.0,
        "gap_two_or_less_share": (
            round(sum(gaps[g] for g in (1, 2)) / total_gaps, 6) if total_gaps else 0.0
        ),
        "eighth_share": (
            round(sum(steps[s] for s in range(0, STEPS_PER_BAR, 2)) / total_steps, 6)
            if total_steps
            else 0.0
        ),
        "bar_end_share": (
            round((steps[14] + steps[15]) / total_steps, 6) if total_steps else 0.0
        ),
    }


def main() -> None:
    connection = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    rows: list[tuple[str, str]] = connection.execute(
        "select relative_path, stratum from files where status='ok' and source_digest != '' "
        "group by source_digest order by source_digest"
    ).fetchall()
    connection.close()
    print(f"byte-unique files: {len(rows)}", flush=True)

    chunks = [rows[i : i + CHUNK_SIZE] for i in range(0, len(rows), CHUNK_SIZE)]
    histogram: Histogram = collections.defaultdict(collections.Counter)
    pairs: PairCounter = collections.defaultdict(collections.Counter)
    profiles: ProfileAccumulator = collections.defaultdict(dict)

    done = 0
    with multiprocessing.Pool(WORKERS) as pool:
        for chunk_hist, chunk_pairs, chunk_profiles, count in pool.imap_unordered(
            _process_chunk, chunks
        ):
            for collection, counts in chunk_hist.items():
                histogram[collection].update(counts)
            for collection, counts in chunk_pairs.items():
                for key, value in counts.items():
                    first, second = key.split(":")
                    pairs[collection][(int(first), int(second))] += value
            for collection, per_pitch in chunk_profiles.items():
                for pitch, slot in per_pitch.items():
                    target = profiles[collection].setdefault(pitch, _blank_profile())
                    _merge_profile(target, slot)
            done += count
            print(f"processed {done}/{len(rows)}", flush=True)

    results: dict[str, Any] = {}
    for collection in sorted(histogram):
        counts = histogram[collection]
        total_notes = sum(counts.values())
        if not total_notes:
            continue
        results[collection] = {
            "total_notes": total_notes,
            "pitch_histogram": {str(p): c for p, c in sorted(counts.items())},
            "co_occurrence_top50": [
                {"pitches": [a, b], "count": n}
                for (a, b), n in sorted(
                    pairs[collection].items(), key=lambda item: (-item[1], item[0])
                )[:50]
            ],
            "pitch_profiles": {
                str(pitch): _summarise_profile(slot)
                for pitch, slot in sorted(profiles[collection].items())
            },
        }

    OUTPUT.write_text(
        json.dumps(results, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"collections: {len(results)}", flush=True)
    print(f"notes: {sum(v['total_notes'] for v in results.values())}", flush=True)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
