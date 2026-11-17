"""Constant tables of the versioned, bounded facet derivation."""

from __future__ import annotations

import re

from .constants import (
    TAXONOMY_ALIASES,
    TAXONOMY_GENRE_VOCABULARY,
    TAXONOMY_SECTION_ALIASES,
    TAXONOMY_SECTION_VOCABULARY,
    TAXONOMY_STYLE_VOCABULARY,
    TAXONOMY_SUBGENRE_VOCABULARY,
)

_SAFE_LABEL = re.compile(r"[^a-z0-9]+")
_TOKEN_RE = re.compile(r"[^a-z0-9]+")
_TAXONOMY_AXES = ("collection", "genre", "subgenre", "style", "section", "source_category")
_ALLOWED_AXES = _TAXONOMY_AXES + (
    "feel",
    "density",
    "microtiming",
    "kit",
    "license",
    "bpm",
)

# Explicit aliases observed in the authorized catalogue, plus common music
# abbreviations used by the same naming conventions.
_ALIASES = {
    "afro beat": "afrobeat",
    "afro-beat": "afrobeat",
    "afoxe": "afoxe",
    "back beats": "backbeat",
    "back-beat": "backbeat",
    "boom-bap": "boom_bap",
    "boom bap": "boom_bap",
    "break beat": "breakbeat",
    "break-beat": "breakbeat",
    "d and b": "drum_and_bass",
    "dnb": "drum_and_bass",
    "drum and bass": "drum_and_bass",
    "drum & bass": "drum_and_bass",
    "four on the floor": "four_on_the_floor",
    "4 on the floor": "four_on_the_floor",
    "half time": "half_time",
    "half-time": "half_time",
    "hip hop": "hip_hop",
    "hip-hop": "hip_hop",
    "ht": "half_time",
    "laid back": "laid_back",
    "laid-back": "laid_back",
    "lo fi": "lofi",
    "lo-fi": "lofi",
    "new jack": "new_jack",
    "new jack swing": "new_jack_swing",
    "old school": "old_school",
    "old skool": "old_school",
    "old-school": "old_school",
    "r and b": "rnb",
    "r&b": "rnb",
    "rb": "rnb",
    "prog": "progressive",
    "straight feel": "straight",
    "swing straight": "swing_straight",
}

_KNOWN_GENRES = frozenset(
    {
        "afrobeat",
        "alternative",
        "ambient",
        "americana",
        "blues",
        "boogie",
        "breakbeat",
        "country",
        "dance",
        "disco",
        "downtempo",
        "drum_and_bass",
        "dub",
        "dubstep",
        "edm",
        "electronic",
        "electronica",
        "folk",
        "funk",
        "garage",
        "gospel",
        "grindcore",
        "hardcore",
        "hip_hop",
        "house",
        "industrial",
        "indie",
        "jazz",
        "jungle",
        "latin",
        "metal",
        "motown",
        "neo_disco",
        "pop",
        "punk",
        "reggae",
        "rnb",
        "rock",
        "salsa",
        "ska",
        "soul",
        "techno",
        "trance",
        "trap",
        "fusion",
        "world",
    }
)

# Compound and descriptor labels are subgenres only when their musical tokens
# are present. A bare unknown component never becomes a genre by position.
_KNOWN_SUBGENRES = frozenset(
    {
        "alternative_rock",
        "arena_rock",
        "black_metal",
        "blues_rock",
        "boogie_woogie",
        "boom_bap",
        "british_invasion",
        "classic_breaks",
        "classic_rock",
        "contemporary_rnb",
        "country_breakbeat",
        "death_metal",
        "deathcore",
        "delta_blues",
        "doom_core",
        "doom_metal",
        "east_coast",
        "folk_metal",
        "funk_hip_hop",
        "funk_rock",
        "grind_blast",
        "hard_rock",
        "hardcore_punk",
        "heavy_metal",
        "indie_folk",
        "indie_rock",
        "industrial_metal",
        "jazz_fusion",
        "jump_blues",
        "latin_jazz",
        "melodic_metal",
        "metalcore",
        "modern_funk",
        "modern_pop",
        "new_jack_swing",
        "neo_soul",
        "nu_metal",
        "pop_punk",
        "pop_rock",
        "post_metal",
        "post_rock",
        "power_metal",
        "progressive",
        "progressive_metal",
        "progressive_rock",
        "punk_rock",
        "rnb_grooves",
        "singer_songwriter",
        "skate_punk",
        "soul_blues",
        "soul_funk",
        "southern_soul",
        "street_punk",
        "swamp_blues",
        "texas_blues",
        "thrash_metal",
        "urban_jazz",
        "west_coast",
        "west_coast_rock",
    }
)

_KNOWN_STYLES = frozenset(
    {
        "backbeat",
        "ballad",
        "broken",
        "double_kick",
        "double_time",
        "driving",
        "four_on_the_floor",
        "funky",
        "half_time",
        "laid_back",
        "linear",
        "lofi",
        "loose_feel",
        "moderate",
        "odd_meter",
        "push",
        "shuffled",
        "shuffle",
        "smooth",
        "straight",
        "swing",
        "swing_straight",
        "swung",
        "syncopated",
        "triplet",
    }
)

_SECTION_ALIASES = {
    "breaks": "break",
    "ending": "ending",
    "endings": "ending",
    "fill": "fill",
    "fill_ins": "fill",
    "fill_variations": "fill",
    "fills": "fill",
    "groove": "groove",
    "grooves": "groove",
    "intro": "intro",
    "intro_fills": "intro",
    "intros": "intro",
    "outro": "outro",
    "outros": "outro",
    "patterns": "pattern",
    "pre_chorus": "pre_chorus",
    "pickups": "pickup",
    "solo": "solo",
    "specials": "special",
    "themes": "theme",
    "variations": "variation",
    "verses": "verse",
}
_KNOWN_SECTIONS = frozenset(
    {
        "a",
        "b",
        "break",
        "bridge",
        "chorus",
        "drop",
        "ending",
        "fill",
        "groove",
        "intro",
        "main",
        "outro",
        "pattern",
        "pickup",
        "pre_chorus",
        "solo",
        "special",
        "theme",
        "variation",
        "verse",
    }
)

_GENERIC_ROOTS = frozenset({"drums_groove_midi", "midi", "midi_files", "drums_midi"})
_HIERARCHY_MARKERS = frozenset(
    {"collections", "genres", "subgenres", "styles", "sections", "parts"}
)
_GENERIC_SOURCE = frozenset(
    {
        "beats",
        "drum_set",
        "fills",
        "groove",
        "grooves",
        "midi",
        "patterns",
        "preview_files",
        "songs",
        "variations",
    }
)

# The data-only constants are authoritative for both taxonomy derivation and
# the ranker manifest digest.  Keep the local names private for compatibility
# with the bounded parser helpers below.
_ALIASES = dict(TAXONOMY_ALIASES)
_KNOWN_GENRES = frozenset(TAXONOMY_GENRE_VOCABULARY)
_KNOWN_SUBGENRES = frozenset(TAXONOMY_SUBGENRE_VOCABULARY)
_KNOWN_STYLES = frozenset(TAXONOMY_STYLE_VOCABULARY)
_SECTION_ALIASES = dict(TAXONOMY_SECTION_ALIASES)
_KNOWN_SECTIONS = frozenset(TAXONOMY_SECTION_VOCABULARY)
