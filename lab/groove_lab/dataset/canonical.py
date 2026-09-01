"""One file to one CanonicalGroove, with the multiplicity the grid would drop.

``derive_hvo_v3`` collapses every event in a ``(role, bar, step)`` cell into one
cell with averaged velocity and offset, but it keeps ``event_ids``, so the count
is recoverable without reparsing.  Storing that count is what makes the training
target round-trip and what turns "notes silently fused" into a published number.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from ableton_mcp_server.groove_intelligence.midi_lossless import ParsedSmfV1
from ableton_mcp_server.groove_intelligence.projections import derive_hvo_v3

MICROSECONDS_PER_MINUTE = 60_000_000


@dataclass(frozen=True)
class CanonicalCell:
    role: str
    bar: int
    step: int
    subhits: int
    velocity: float
    offset_ticks: int


@dataclass(frozen=True)
class CanonicalGroove:
    cells: tuple[CanonicalCell, ...]
    bpm: float | None
    meter: str
    bars: int
    collection: str
    source_events_digest: str
    canonical_hash: str = field(default="")
    rhythm_hash: str = field(default="")
    expression_hash: str = field(default="")


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _bpm(parsed: ParsedSmfV1) -> float | None:
    if not parsed.tempos:
        return None
    microseconds = parsed.tempos[0].get("microseconds")
    if not microseconds:
        return None
    return round(MICROSECONDS_PER_MINUTE / float(microseconds), 4)


def _meter(parsed: ParsedSmfV1) -> str:
    if not parsed.meters:
        return "4/4"
    first = parsed.meters[0]
    return f"{first['numerator']}/{2 ** first['denominator_power']}"


def build_canonical(parsed: ParsedSmfV1, collection: str) -> CanonicalGroove:
    hvo = derive_hvo_v3(parsed, collection)
    cells = tuple(
        CanonicalCell(
            role=cell.role,
            bar=cell.bar,
            step=cell.step,
            subhits=len(cell.event_ids),
            velocity=cell.velocity,
            offset_ticks=cell.offset_ticks,
        )
        for cell in sorted(hvo.cells, key=lambda c: (c.bar, c.step, c.role))
    )
    bars = max((cell.bar for cell in cells), default=0) + 1

    rhythm = [[cell.role, cell.bar, cell.step, cell.subhits] for cell in cells]
    expression = [[cell.velocity, cell.offset_ticks] for cell in cells]
    return CanonicalGroove(
        cells=cells,
        bpm=_bpm(parsed),
        meter=_meter(parsed),
        bars=bars,
        collection=collection,
        source_events_digest=parsed.source_events_digest,
        canonical_hash=_digest([rhythm, expression]),
        rhythm_hash=_digest(rhythm),
        expression_hash=_digest(expression),
    )


def note_mass_lost(parsed: ParsedSmfV1, groove: CanonicalGroove) -> float:
    """Fraction of source notes the canonical form does not account for.

    With ``subhits`` this is zero by construction, and that is the point: no note
    disappears.  It is not the whole story, which is why
    :func:`expression_mass_averaged` exists.
    """

    source = len(parsed.note_events)
    if source == 0:
        return 0.0
    kept = sum(cell.subhits for cell in groove.cells)
    return (source - kept) / source


def notes_fused_share(parsed: ParsedSmfV1, groove: CanonicalGroove) -> float:
    """Fraction of notes a one-hit-per-cell grid would have dropped.

    This is ``notes - cells`` over notes, the same quantity the corpus audit
    measured at 3.51% on a sixteenth grid, and it is what the representation
    budget in :class:`~groove_lab.dataset.config.BuildConfig` was derived from.
    Keeping the identical definition is the only way the budget means anything.
    """

    source = len(parsed.note_events)
    if source == 0:
        return 0.0
    return (source - len(groove.cells)) / source


def expression_mass_averaged(parsed: ParsedSmfV1, groove: CanonicalGroove) -> float:
    """Fraction of notes whose own velocity and offset were averaged away.

    Broader than :func:`notes_fused_share`: a cell holding two events fuses one
    note but averages the expression of both.  ``subhits`` keeps the count so
    nothing vanishes, and this is the honest cost that a comfortable zero on
    ``note_mass_lost`` would otherwise hide.
    """

    source = len(parsed.note_events)
    if source == 0:
        return 0.0
    averaged = sum(cell.subhits for cell in groove.cells if cell.subhits > 1)
    return averaged / source
