"""Derive articulation roles and file labels from the vendor MIDI databases.

Superior Drummer 3 installs one SQLite database per library at
``%PROGRAMDATA%\\Toontrack\\Superior Drummer 3\\Database\\<collection>\\midiDB``.
Each one carries, for every groove file the library ships:

* ``KITPIECES`` and ``REL_ENT_KITS`` - which drum pieces the file plays;
* ``GENRE`` - the vendor genre, an axis the folder taxonomy does not have;
* ``TAGS`` - beat or fill, straight or swing, half or double time, hit strength;
* ``HEADER``, ``Tempo``, ``TIMESIGS``, ``RESOLUTION``, ``Intensity``.

``LIBRARY.Name`` equals the corpus collection, and the file path is the corpus
path with ``_EZD2MIDI_`` in place of ``Drums Groove MIDI/``, so the join is exact.

Roles come from the vendor, not from inference.  A pitch is assigned the kit
piece that every file containing that pitch declares; among the pieces that hold
for all of them the rarest one wins, because it is the most specific claim the
data supports.  Kit pieces that do not name a single canonical role - ``Toms``
spans three lanes, ``Special`` and ``Brushes`` name none - assign nothing and let
General MIDI decide.

This is what settles pitches 60-63: in Superior Drummer 3 they are hi-hats, in
EZX Latin Percussion 60 and 61 are the bongo pair.  One global answer was always
going to be wrong.

Outputs:

* ``ableton_mcp_server/groove_intelligence/articulation_map.json`` - the map,
  vendor entries first, keeping any rhythm-inferred entry for a collection the
  vendor databases do not cover;
* ``scripts/vendor_labels_report.md`` - coverage and disagreements with GM;
* per-file labels as JSONL in the workspace, outside the repository.
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

from ableton_mcp_server.groove_intelligence.drum_roles import (  # noqa: E402
    GM_DRUM_ROLE_BY_PITCH,
)
from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf  # noqa: E402

CORPUS_ROOT = Path(
    r"C:\Users\Usuario\Desktop\AUDIO_PRODUCTION\AUDIO\Superior Drummer 3\Toontrack\Midi"
)
VENDOR_ROOT = Path(r"C:\ProgramData\Toontrack\Superior Drummer 3\Database")
WORKSPACE = Path(r"C:\Users\Usuario\AppData\Local\AbletonMCPServer\groove-vendor-labels")
MAP_PATH = REPO_ROOT / "ableton_mcp_server" / "groove_intelligence" / "articulation_map.json"
REPORT_PATH = REPO_ROOT / "scripts" / "vendor_labels_report.md"
LABELS_PATH = WORKSPACE / "vendor_labels.jsonl"

PATH_PREFIX = "_EZD2MIDI_"
CORPUS_PREFIX = "Drums Groove MIDI/"
UNRESOLVED = "other_percussion"

# A kit piece names a canonical role only when it names exactly one.  Toms spans
# three lanes and General MIDI already splits them by pitch; Special, Brushes and
# the generic pads name no instrument at all.
KIT_PIECE_ROLE: dict[str, str] = {
    "Kick": "kick",
    "Snare": "snare",
    "Sidestick": "rim",
    "Hi-Hat Closed": "hat_closed",
    "Hi-Hat Open": "hat_open",
    "Hi-Hat Pedal": "hat_pedal",
    "Ride": "ride",
    "Ride Crash": "ride",
    "Crash": "crash",
    "Cowbell": "cowbell",
    "Tambourine": "tambourine",
    "Tambourine Pad": "tambourine",
    "Cajon": UNRESOLVED,
    "Bongo": UNRESOLVED,
    "Conga": UNRESOLVED,
    "Timbales": UNRESOLVED,
    "Udu": UNRESOLVED,
    "Shaker Pad": UNRESOLVED,
    "Small Shakers": UNRESOLVED,
}

MIN_PITCH_FILES = 20
MIN_COVERAGE = 0.99
WORKERS = 8


def _corpus_path(vendor_path: str, filename: str) -> str | None:
    if not vendor_path.startswith(PATH_PREFIX):
        return None
    return CORPUS_PREFIX + vendor_path[len(PATH_PREFIX) :] + filename


def _read_library(db_path: Path) -> dict[str, Any] | None:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in connection.execute("select name from sqlite_master")}
        if not {"LIBRARY", "MIDIENTITY", "REL_ENT_KITS", "KITPIECES"} <= tables:
            return None
        library = connection.execute("select Name from LIBRARY limit 1").fetchone()
        if library is None:
            return None
        kit_names = dict(connection.execute("select ID, Name from KITPIECES"))
        tag_names = dict(connection.execute("select ID, Name from TAGS"))
        entity_kits: dict[int, set[str]] = collections.defaultdict(set)
        for entity, kit in connection.execute("select EntID, KitID from REL_ENT_KITS"):
            entity_kits[entity].add(kit_names.get(kit, str(kit)))
        entity_tags: dict[int, set[str]] = collections.defaultdict(set)
        for entity, tag in connection.execute("select EntID, TagID from REL_ENT_TAGS"):
            entity_tags[entity].add(tag_names.get(tag, str(tag)))
        entities = connection.execute(
            "select e.ID, p.Path, f.Name, e.Tempo, e.Intensity, e.Length, "
            "h.Name, g.Name, t.Name, r.Name "
            "from MIDIENTITY e "
            "left join PATHS p on p.ID = e.PathID "
            "left join FILENAMES f on f.ID = e.FilenameID "
            "left join HEADER h on h.ID = e.HeaderID "
            "left join GENRE g on g.ID = e.GenreID "
            "left join TIMESIGS t on t.ID = e.TimeSigID "
            "left join RESOLUTION r on r.ID = e.ResolutionID"
        ).fetchall()
    except sqlite3.DatabaseError:
        return None
    finally:
        connection.close()

    files: dict[str, dict[str, Any]] = {}
    for row in entities:
        entity, path, name, tempo, intensity, length = row[:6]
        header, genre, timesig, resolution = row[6:]
        if path is None or name is None:
            continue
        relative = _corpus_path(path, name)
        if relative is None:
            continue
        files[relative] = {
            "collection": library[0],
            "kits": sorted(entity_kits.get(entity, ())),
            "tags": sorted(entity_tags.get(entity, ())),
            "genre": genre,
            "header": header,
            "tempo": tempo,
            "time_signature": timesig,
            "resolution": resolution,
            "intensity": intensity,
            "length": length,
        }
    return {"collection": library[0], "files": files}


def _pitch_sets(relatives: list[str]) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for relative in relatives:
        try:
            parsed = parse_smf((CORPUS_ROOT / relative).read_bytes())
        except Exception:  # noqa: BLE001 - a corrupt file must not stop the sweep
            continue
        result[relative] = sorted({note.pitch for note in parsed.note_events})
    return result


def _assign_roles(
    files: dict[str, dict[str, Any]], pitches: dict[str, list[int]]
) -> tuple[dict[str, str], list[str], list[tuple[int, str, str, str]]]:
    """Return vendor roles, their evidence, and the disagreements left unapplied.

    An override is applied only where General MIDI leaves the pitch in
    ``other_percussion``.  Where the two disagree on a pitch General MIDI already
    resolves, the vendor vocabulary is usually the coarser one - it has a single
    ``Ride`` piece covering the bell, and a single ``Crash`` covering splash and
    china - so applying it would lose information.  Those cases are collected and
    reported instead of being acted on.
    """

    pitch_files: dict[int, set[str]] = collections.defaultdict(set)
    kit_files: dict[str, set[str]] = collections.defaultdict(set)
    for relative, record in files.items():
        present = pitches.get(relative)
        if present is None:
            continue
        for pitch in present:
            pitch_files[pitch].add(relative)
        for kit in record["kits"]:
            kit_files[kit].add(relative)

    total = len({r for r in files if r in pitches})
    roles: dict[str, str] = {}
    evidence: list[str] = []
    conflicts: list[tuple[int, str, str, str]] = []
    for pitch in sorted(pitch_files):
        holders = pitch_files[pitch]
        if len(holders) < MIN_PITCH_FILES:
            continue
        certain = [
            (len(kit_files[kit]) / total, kit)
            for kit in kit_files
            if len(holders & kit_files[kit]) / len(holders) >= MIN_COVERAGE
        ]
        if not certain:
            continue
        prevalence, kit = min(certain)
        role = KIT_PIECE_ROLE.get(kit)
        if role is None:
            continue
        gm_role = GM_DRUM_ROLE_BY_PITCH.get(pitch, UNRESOLVED)
        if role == gm_role:
            continue
        if gm_role != UNRESOLVED:
            conflicts.append((pitch, gm_role, role, kit))
            continue
        roles[str(pitch)] = role
        evidence.append(
            f"{pitch} -> {role} [vendor kit piece '{kit}', declared by 100% of the "
            f"{len(holders)} files using this pitch, piece prevalence {prevalence:.0%}]"
        )
    return roles, evidence, conflicts


def main() -> None:
    databases = sorted(VENDOR_ROOT.glob("*/midiDB"))
    print(f"vendor databases found: {len(databases)}", flush=True)

    libraries = [library for library in map(_read_library, databases) if library]
    print(f"readable libraries:     {len(libraries)}", flush=True)

    all_files: dict[str, dict[str, Any]] = {}
    for library in libraries:
        all_files.update(library["files"])
    print(f"labelled files:         {len(all_files)}", flush=True)

    relatives = sorted(all_files)
    chunk = max(1, len(relatives) // (WORKERS * 8))
    chunks = [relatives[i : i + chunk] for i in range(0, len(relatives), chunk)]
    pitches: dict[str, list[int]] = {}
    done = 0
    with multiprocessing.Pool(WORKERS) as pool:
        for part in pool.imap_unordered(_pitch_sets, chunks):
            pitches.update(part)
            done += 1
            print(f"parsed chunk {done}/{len(chunks)}", flush=True)
    print(f"files parsed:           {len(pitches)}", flush=True)

    # The map is keyed by the catalog stratum, which is the first two components of
    # the corpus path.  Grouping by that rather than by LIBRARY.Name keeps the join
    # exact even when a library ships under a differently spelled folder.
    by_stratum: dict[str, dict[str, dict[str, Any]]] = collections.defaultdict(dict)
    for relative, record in all_files.items():
        parts = relative.split("/")
        if len(parts) < 3:
            continue
        by_stratum["/".join(parts[:2])][relative] = record

    existing: dict[str, Any] = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    vendor_entries = 0
    overrides = 0
    conflicts: collections.Counter[tuple[str, str, str]] = collections.Counter()
    for stratum in sorted(by_stratum):
        files = by_stratum[stratum]
        roles, evidence, disagreements = _assign_roles(files, pitches)
        for _pitch, gm_role, vendor_role, kit in disagreements:
            conflicts[(gm_role, vendor_role, kit)] += 1
        if not roles:
            continue
        vendor_entries += 1
        overrides += len(roles)
        existing[stratum] = {
            "pitches": roles,
            "confidence": "high",
            "evidence": (
                f"Vendor database midiDB for this collection, {len(files)} labelled files. "
                + "; ".join(evidence)
                + "."
            ),
        }
    MAP_PATH.write_text(
        json.dumps(existing, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    with LABELS_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        for relative in relatives:
            record = dict(all_files[relative])
            record["path"] = relative
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")

    genres: collections.Counter[str] = collections.Counter()
    tags: collections.Counter[str] = collections.Counter()
    tempos = 0
    for record in all_files.values():
        if record["genre"]:
            genres[record["genre"]] += 1
        for tag in record["tags"]:
            tags[tag] += 1
        if record["tempo"]:
            tempos += 1

    lines = [
        "# Vendor labels from the Superior Drummer 3 databases",
        "",
        f"Databases read: {len(libraries)} of {len(databases)} found.",
        f"Files labelled: {len(all_files)}; parsed for pitch content: {len(pitches)}.",
        f"Collections given a vendor articulation entry: {vendor_entries}, "
        f"covering {overrides} pitch overrides.",
        "",
        "## Genre, an axis the folder taxonomy does not have",
        "",
        "| Genre | Files |",
        "|---|---|",
    ]
    lines += [f"| {name} | {count} |" for name, count in genres.most_common()]
    lines += [
        "",
        f"Files carrying a vendor tempo: {tempos} ({tempos / max(1, len(all_files)):.1%}).",
        "",
        "## Play-style tags",
        "",
        "| Tag | Files |",
        "|---|---|",
    ]
    lines += [f"| {name} | {count} |" for name, count in tags.most_common(30)]
    lines += [
        "",
        "## Disagreements left unapplied",
        "",
        "An override is applied only where General MIDI leaves the pitch unresolved.",
        "Where the two disagree on a pitch General MIDI already names, the vendor",
        "vocabulary is usually coarser - one `Ride` piece covering the bell, one",
        "`Crash` covering splash and china - so applying it would lose detail. These",
        "cases are recorded rather than acted on.",
        "",
        "| General MIDI | Vendor kit piece | Would become | Collections |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| `{gm_role}` | {kit} | `{vendor_role}` | {count} |"
        for (gm_role, vendor_role, kit), count in conflicts.most_common()
    ]
    lines += [
        "",
        f"Per-file labels are written outside the repository, to `{LABELS_PATH}`.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"vendor articulation entries: {vendor_entries}")
    print(f"pitch overrides:             {overrides}")
    print(f"genres: {dict(genres.most_common(8))}")
    print(f"labels written to {LABELS_PATH}")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
