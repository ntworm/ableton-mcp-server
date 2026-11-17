"""Render the gate G1 coverage report from the corpus measurement.

Reports note mass per canonical role before and after the articulation map, and
the unresolved share per collection.  Gate G1 excludes any collection that still
leaves more than ``GATE_THRESHOLD`` of its note mass in ``other_percussion``.

Input: ``scripts/measurement_output.json``.
Output: ``scripts/measurement_report.md``.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ableton_mcp_server.groove_intelligence.articulation import (  # noqa: E402
    collection_confidence,
    resolve_role,
)
from ableton_mcp_server.groove_intelligence.drum_roles import (  # noqa: E402
    GM_DRUM_ROLE_BY_PITCH,
)

MEASUREMENT = REPO_ROOT / "scripts" / "measurement_output.json"
OUTPUT = REPO_ROOT / "scripts" / "measurement_report.md"
GATE_THRESHOLD = 0.10
UNRESOLVED = "other_percussion"


def _collect_rows(
    measurement: dict[str, dict[str, Any]],
) -> tuple[
    Counter[str],
    Counter[str],
    Counter[int],
    list[tuple[str, int, float, float, str]],
]:
    """Measure the note mass per role before and after the articulation map."""
    before: Counter[str] = Counter()
    after: Counter[str] = Counter()
    unresolved_pitches: Counter[int] = Counter()
    rows: list[tuple[str, int, float, float, str]] = []

    for collection, record in measurement.items():
        total = int(record["total_notes"])
        raw_unresolved = 0
        mapped_unresolved = 0
        for raw_pitch, count in record["pitch_histogram"].items():
            pitch = int(raw_pitch)
            gm_role = GM_DRUM_ROLE_BY_PITCH.get(pitch, UNRESOLVED)
            mapped_role = resolve_role(collection, pitch)
            before[gm_role] += count
            after[mapped_role] += count
            if gm_role == UNRESOLVED:
                raw_unresolved += count
            if mapped_role == UNRESOLVED:
                mapped_unresolved += count
                unresolved_pitches[pitch] += count
        rows.append(
            (
                collection,
                total,
                raw_unresolved / total if total else 0.0,
                mapped_unresolved / total if total else 0.0,
                collection_confidence(collection) or "unmapped",
            )
        )

    return before, after, unresolved_pitches, rows


def _hat_mass(
    before: Counter[str], after: Counter[str], corpus_total: int
) -> tuple[float, float]:
    """Return the combined hi-hat note mass before and after the articulation map."""
    hats = ("hat_closed", "hat_open", "hat_pedal")
    hat_before = sum(before[r] for r in hats) / corpus_total
    hat_after = sum(after[r] for r in hats) / corpus_total
    return hat_before, hat_after


def _role_lines(
    before: Counter[str], after: Counter[str], corpus_total: int
) -> list[str]:
    """Return the note mass per canonical role, before and after the map."""
    lines = [
        "## Note mass per canonical role",
        "",
        "| Role | Before | After | Change |",
        "|---|---|---|---|",
    ]
    for role in sorted(set(before) | set(after), key=lambda r: -after[r]):
        b = before[role] / corpus_total
        a = after[role] / corpus_total
        lines.append(f"| `{role}` | {b:.2%} | {a:.2%} | {(a - b) * 100:+.2f} pp |")
    return lines


def _hat_lines(
    before: Counter[str], after: Counter[str], corpus_total: int
) -> list[str]:
    """Return the hi-hat mass and the unresolved share of the corpus."""
    hat_before, hat_after = _hat_mass(before, after, corpus_total)
    return [
        "",
        f"Hi-hat lanes combined move from {hat_before:.2%} to {hat_after:.2%} of note mass, "
        f"and `{UNRESOLVED}` from {before[UNRESOLVED] / corpus_total:.2%} to "
        f"{after[UNRESOLVED] / corpus_total:.2%}.",
    ]


def _unresolved_lines(
    unresolved_pitches: Counter[int], corpus_total: int
) -> list[str]:
    """Return the largest unresolved pitches of the corpus."""
    lines = [
        "",
        "## Largest remaining unresolved pitches",
        "",
        "| Pitch | Notes | Share of corpus |",
        "|---|---|---|",
    ]
    for pitch, count in unresolved_pitches.most_common(15):
        lines.append(f"| {pitch} | {count} | {count / corpus_total:.2%} |")
    lines.append("")
    lines.append(
        "Pitches 60-63 dominate this list. They carry too much mass to be crashes and mean "
        "different instruments in different libraries, so they stay unresolved until the "
        "vendor maps settle them."
    )
    return lines


def _excluded_lines(
    rows: list[tuple[str, int, float, float, str]],
    excluded: list[tuple[str, int, float, float, str]],
) -> list[str]:
    """Return the collections the gate excludes, with their unresolved share."""
    lines = [
        "",
        f"## Gate G1: unresolved above {GATE_THRESHOLD:.0%} excludes a collection",
        "",
        f"Excluded: **{len(excluded)}** of {len(rows)} collections.",
        "",
        "| Collection | Notes | Unresolved before | Unresolved after | Map | Gate |",
        "|---|---|---|---|---|---|",
    ]
    for collection, total, raw, mapped, confidence in sorted(rows, key=lambda r: -r[3]):
        verdict = "EXCLUDED" if mapped > GATE_THRESHOLD else "passes"
        lines.append(
            f"| `{collection}` | {total} | {raw:.1%} | {mapped:.1%} | {confidence} | {verdict} |"
        )
    return lines


def main() -> None:
    measurement: dict[str, dict[str, Any]] = json.loads(MEASUREMENT.read_text(encoding="utf-8"))

    before, after, unresolved_pitches, rows = _collect_rows(measurement)

    corpus_total = sum(before.values())
    hat_before, hat_after = _hat_mass(before, after, corpus_total)
    excluded = [row for row in rows if row[3] > GATE_THRESHOLD]

    lines: list[str] = []
    lines.append("# Gate G1 \N{EM DASH} articulation coverage")
    lines.append("")
    lines.append(
        f"Corpus: {len(measurement)} collections, {corpus_total} notes over the byte-unique files."
    )
    lines.append("")
    lines += _role_lines(before, after, corpus_total)
    lines += _hat_lines(before, after, corpus_total)
    lines += _unresolved_lines(unresolved_pitches, corpus_total)
    lines += _excluded_lines(rows, excluded)

    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"hi-hat mass {hat_before:.2%} -> {hat_after:.2%}")
    print(f"unresolved  {before[UNRESOLVED] / corpus_total:.2%} -> "
          f"{after[UNRESOLVED] / corpus_total:.2%}")
    print(f"gate G1 excludes {len(excluded)} of {len(rows)} collections")
    print(f"written to {OUTPUT}")


if __name__ == "__main__":
    main()
