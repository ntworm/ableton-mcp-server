"""Build the per-collection articulation map from measured rhythmic behaviour.

The canonical role map in ``drum_roles`` covers General MIDI percussion pitches
35-81 only.  The drum libraries in this corpus place hi-hat articulations in a
low band around pitches 19-27, so under General MIDI alone roughly a quarter of
the corpus note mass lands in ``other_percussion`` and the lane that carries the
rhythmic subdivision disappears.

Roles are assigned from measurement, never from intuition.  Every candidate is
compared against reference profiles aggregated from the General MIDI hi-hat
pitches present in the same corpus, on five scale-free shape features: the share
of adjacent onsets, the share of onsets within two steps, the share sitting on
eighth-note positions, the share clustered at the end of the bar, and the median
onset gap.

Three rules decide the outcome, and each entry records which one applied:

1. A band pitch is a hi-hat candidate only when its corpus-wide profile is within
   ``MAX_PROFILE_DISTANCE`` of a reference lane.
2. It takes that lane's role only when the classification is stable: an aggregate
   margin of at least ``MIN_MARGIN`` over the runner-up, and at least
   ``MIN_AGREEMENT`` of the collections that use the pitch reaching the same
   answer independently.
3. Otherwise it maps to ``hat_closed``, the lane that carries the subdivision,
   and the evidence says the articulation is undetermined.  That is a documented,
   reversible collapse; leaving the pitch in ``other_percussion`` would instead
   mix hi-hats with congas, tambourines and everything else.

Measured on this corpus only pitch 21 is stable: it sits 0.061 from General MIDI
44, the pedal hi-hat, against 0.213 for the runner-up, and 73.3% of the 120
collections that use it agree. Pitches 22, 24, 25 and 26 are unambiguously
hi-hat family — they are nearest a hat lane and almost never sound together, at
0.035% same-tick co-occurrence — but their articulation is not determined.

Pitches 60-63 never appear here. They carry 7.9% of corpus note mass, while
General MIDI crash 49 measures 3.0 notes per file with a median gap of 8 steps,
so they cannot be crashes; in a latin library 60 and 61 are the bongo pair.

Input: ``scripts/measurement_output.json`` from ``scripts/measurement.py``.
Output: ``ableton_mcp_server/groove_intelligence/articulation_map.json``.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT = REPO_ROOT / "scripts" / "measurement_output.json"
OUTPUT = REPO_ROOT / "ableton_mcp_server" / "groove_intelligence" / "articulation_map.json"

HAT_BAND = tuple(range(19, 28))
REFERENCE_PITCHES = {42: "hat_closed", 44: "hat_pedal", 46: "hat_open"}
FALLBACK_ROLE = "hat_closed"

SHAPE_KEYS = (
    "gap_one_share",
    "gap_two_or_less_share",
    "eighth_share",
    "bar_end_share",
    "median_gap_steps",
)
GAP_SCALE = 8.0

MIN_CORPUS_NOTES = 2000
MIN_COLLECTION_NOTES = 50
VOTE_MIN_NOTES = 200
MAX_PROFILE_DISTANCE = 0.35
MIN_MARGIN = 0.05
MIN_AGREEMENT = 0.60


def _shape(profile: dict[str, Any]) -> tuple[float, ...]:
    return (
        float(profile["gap_one_share"]),
        float(profile["gap_two_or_less_share"]),
        float(profile["eighth_share"]),
        float(profile["bar_end_share"]),
        min(float(profile["median_gap_steps"]) / GAP_SCALE, 1.0),
    )


def _distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _aggregate(measurement: dict[str, dict[str, Any]]) -> dict[int, dict[str, float]]:
    totals: dict[int, dict[str, float]] = {}
    for record in measurement.values():
        for raw_pitch, profile in record.get("pitch_profiles", {}).items():
            pitch = int(raw_pitch)
            weight = float(profile["notes"])
            slot = totals.setdefault(pitch, dict.fromkeys(("notes", *SHAPE_KEYS), 0.0))
            slot["notes"] += weight
            for key in SHAPE_KEYS:
                slot[key] += float(profile[key]) * weight
    return {
        pitch: {"notes": slot["notes"], **{k: slot[k] / slot["notes"] for k in SHAPE_KEYS}}
        for pitch, slot in totals.items()
        if slot["notes"]
    }


def _rank(
    vector: tuple[float, ...], references: dict[int, tuple[float, ...]]
) -> list[tuple[float, int]]:
    return sorted((_distance(vector, ref), pitch) for pitch, ref in references.items())


def _classify_band(
    measurement: dict[str, dict[str, Any]],
    aggregate: dict[int, dict[str, float]],
    references: dict[int, tuple[float, ...]],
) -> dict[int, tuple[str, str]]:
    """Return role and the rule that produced it, for every mappable band pitch."""

    decisions: dict[int, tuple[str, str]] = {}
    for pitch in HAT_BAND:
        summary = aggregate.get(pitch)
        if summary is None or summary["notes"] < MIN_CORPUS_NOTES:
            continue
        ranked = _rank(_shape(summary), references)
        distance, nearest = ranked[0]
        if distance > MAX_PROFILE_DISTANCE:
            continue
        margin = ranked[1][0] - distance

        votes: Counter[str] = Counter()
        for record in measurement.values():
            profile = record.get("pitch_profiles", {}).get(str(pitch))
            if profile is None or int(profile["notes"]) < VOTE_MIN_NOTES:
                continue
            votes[REFERENCE_PITCHES[_rank(_shape(profile), references)[0][1]]] += 1
        total_votes = sum(votes.values())
        role = REFERENCE_PITCHES[nearest]
        agreement = votes[role] / total_votes if total_votes else 0.0

        if margin >= MIN_MARGIN and agreement >= MIN_AGREEMENT:
            rule = (
                f"stable: nearest GM {nearest} at d={distance:.3f}, margin {margin:.3f}, "
                f"{agreement:.0%} of {total_votes} collections agree"
            )
        else:
            role = FALLBACK_ROLE
            rule = (
                f"hi-hat family but articulation undetermined: nearest GM {nearest} at "
                f"d={distance:.3f}, margin {margin:.3f}, only {agreement:.0%} of "
                f"{total_votes} collections agree, so it collapses to {FALLBACK_ROLE}"
            )
        decisions[pitch] = (role, rule)
    return decisions


def _entry(
    record: dict[str, Any], decisions: dict[int, tuple[str, str]]
) -> dict[str, Any] | None:
    profiles = record.get("pitch_profiles", {})
    total_notes = int(record["total_notes"])

    pitches: dict[str, str] = {}
    detail: list[str] = []
    mapped_notes = 0
    stable = 0
    for pitch, (role, rule) in sorted(decisions.items()):
        profile = profiles.get(str(pitch))
        if profile is None or int(profile["notes"]) < MIN_COLLECTION_NOTES:
            continue
        pitches[str(pitch)] = role
        mapped_notes += int(profile["notes"])
        if rule.startswith("stable"):
            stable += 1
        detail.append(
            f"{pitch} -> {role} [{rule}]; here {profile['notes']} notes, "
            f"{profile['notes_per_file']:.1f}/file, gap1={profile['gap_one_share']:.0%}, "
            f"eighths={profile['eighth_share']:.0%}, bar-end={profile['bar_end_share']:.0%}"
        )

    if not pitches:
        return None

    share = mapped_notes / total_notes if total_notes else 0.0
    confidence = "high" if stable and share >= 0.03 else "medium"
    return {
        "pitches": pitches,
        "confidence": confidence,
        "evidence": (
            f"{len(pitches)} band pitches recovered, covering {share:.1%} of this collection. "
            + "; ".join(detail)
            + "."
        ),
    }


def main() -> None:
    measurement: dict[str, dict[str, Any]] = json.loads(MEASUREMENT.read_text(encoding="utf-8"))
    aggregate = _aggregate(measurement)
    references = {pitch: _shape(aggregate[pitch]) for pitch in REFERENCE_PITCHES}
    decisions = _classify_band(measurement, aggregate, references)

    articulation_map: dict[str, dict[str, Any]] = {}
    for collection in sorted(measurement):
        entry = _entry(measurement[collection], decisions)
        if entry is not None:
            articulation_map[collection] = entry

    OUTPUT.write_text(
        json.dumps(articulation_map, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("reference shapes (gap1, gap<=2, eighths, bar-end, median gap / 8):")
    for pitch, vector in sorted(references.items()):
        rendered = ", ".join(f"{value:.3f}" for value in vector)
        print(f"  GM {pitch} -> {REFERENCE_PITCHES[pitch]:11s} [{rendered}]")
    print("band decisions:")
    for pitch, (role, rule) in sorted(decisions.items()):
        print(f"  {pitch} -> {role:11s} {rule}")
    high = sum(1 for e in articulation_map.values() if e["confidence"] == "high")
    distinct = len({json.dumps(e["pitches"], sort_keys=True) for e in articulation_map.values()})
    print(f"collections in measurement: {len(measurement)}")
    print(f"collections mapped:         {len(articulation_map)} ({high} high confidence)")
    print(f"collections left on GM:     {len(measurement) - len(articulation_map)}")
    print(f"distinct pitch tables:      {distinct}")


if __name__ == "__main__":
    main()
