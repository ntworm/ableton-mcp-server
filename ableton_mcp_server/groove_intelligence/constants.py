"""Version identifiers and hard safety limits for groove corpus artifacts."""

from __future__ import annotations

import hashlib
import json

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_TRACKS = 256
MAX_EVENTS = 1_000_000
MAX_COMPRESSED_BLOB = 8 * 1024 * 1024
MAX_RAW_BLOB = 32 * 1024 * 1024
MAX_EXPANSION_RATIO = 100
MAX_PILOT_FILES = 5_000

PARSER_ID = "smf-parser-v1"
SERIALIZER_ID = "smf-serializer-v1"
RAW_BLOB_CODECS = frozenset({"zlib-raw-midi-v1", "zlib-raw-json-v1"})
PROJECTION_CODEC = "zlib-raw-json-v1"
SEED_SCHEMA_VERSION = "groove.seed.v2"
INDEX_SCHEMA_VERSION = "groove.index.v2"
SQLITE_USER_VERSION = 2
SQLITE_MIN_VERSION = "3.40"
HVO_SCHEMA_VERSION = "groove.hvo.v2"
FEATURES_SCHEMA_VERSION = "groove.features.v2"
GRAMMAR_SCHEMA_VERSION = "groove.grammar.v2"
NORMALIZER_ID = "groove-normalizer-v2"
CORPUS_SCHEMA_VERSION = "groove.corpus.v2"
TAXONOMY_VERSION = "groove-taxonomy-v2"
TAXONOMY_TOKENIZER_VERSION = "groove-taxonomy-tokenizer-v2"
RANKER_ID = "groove-ranker-v2"
RANKER_SCHEMA = "groove.search.ranker.v2"
CURSOR_SCHEMA_VERSION = "groove.search.cursor.v2"
CURSOR_DOMAIN = b"ABLETON-GROOVE-CURSOR-V2\x00"
RANKER_WEIGHTS = {
    "text": 0.2,
    "facets": 0.25,
    "features": 0.4,
    "projection_coverage": 0.15,
}
RANKER_NO_PROJECTION_WEIGHTS = {"text": 4 / 17, "facets": 5 / 17, "features": 8 / 17}

# This is deliberately data-only.  ``taxonomy.py`` consumes the same public
# contract, while the ranker digest can cover it without importing taxonomy
# (which would create a constants -> schema -> taxonomy cycle).
TAXONOMY_ALIASES = {
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
TAXONOMY_GENRE_VOCABULARY = (
    "afrobeat", "alternative", "ambient", "americana", "blues", "boogie", "breakbeat",
    "country", "dance", "disco", "downtempo", "drum_and_bass", "dub", "dubstep", "edm",
    "electronic", "electronica", "folk", "funk", "garage", "gospel", "grindcore", "hardcore",
    "hip_hop", "house", "industrial", "indie", "jazz", "jungle", "latin", "metal", "motown",
    "neo_disco", "pop", "punk", "reggae", "rnb", "rock", "salsa", "ska", "soul", "techno",
    "trance", "trap", "fusion", "world",
)
TAXONOMY_SUBGENRE_VOCABULARY = (
    "alternative_rock", "arena_rock", "black_metal", "blues_rock", "boogie_woogie", "boom_bap",
    "british_invasion", "classic_breaks", "classic_rock", "contemporary_rnb", "country_breakbeat",
    "death_metal", "deathcore", "delta_blues", "doom_core", "doom_metal", "east_coast",
    "folk_metal",
    "funk_hip_hop", "funk_rock", "grind_blast", "hard_rock", "hardcore_punk", "heavy_metal",
    "indie_folk", "indie_rock", "industrial_metal", "jazz_fusion", "jump_blues", "latin_jazz",
    "melodic_metal", "metalcore", "modern_funk", "modern_pop", "new_jack_swing", "neo_soul",
    "nu_metal",
    "pop_punk", "pop_rock", "post_metal", "post_rock", "power_metal", "progressive",
    "progressive_metal",
    "progressive_rock", "punk_rock", "rnb_grooves", "singer_songwriter", "skate_punk", "soul_blues",
    "soul_funk", "southern_soul", "street_punk", "swamp_blues", "texas_blues", "thrash_metal",
    "urban_jazz",
    "west_coast", "west_coast_rock",
)
TAXONOMY_STYLE_VOCABULARY = (
    "backbeat", "ballad", "broken", "double_kick", "double_time", "driving", "four_on_the_floor",
    "funky", "half_time", "laid_back", "linear", "lofi", "loose_feel", "moderate", "odd_meter",
    "push",
    "shuffled", "shuffle", "smooth", "straight", "swing", "swing_straight", "swung", "syncopated",
    "triplet",
)
TAXONOMY_SECTION_ALIASES = {
    "breaks": "break", "ending": "ending", "endings": "ending", "fill": "fill", "fill_ins": "fill",
    "fill_variations": "fill", "fills": "fill", "groove": "groove", "grooves": "groove",
    "intro": "intro",
    "intro_fills": "intro", "intros": "intro", "outro": "outro", "outros": "outro",
    "patterns": "pattern",
    "pre_chorus": "pre_chorus", "pickups": "pickup", "solo": "solo", "specials": "special",
    "themes": "theme",
    "variations": "variation", "verses": "verse",
}
TAXONOMY_SECTION_VOCABULARY = (
    "a", "b", "break", "bridge", "chorus", "drop", "ending", "fill", "groove", "intro", "main",
    "outro",
    "pattern", "pickup", "pre_chorus", "solo", "special", "theme", "variation", "verse",
)
TAXONOMY_TOKENIZER_CONTRACT = {
    "version": TAXONOMY_TOKENIZER_VERSION,
    "normalization": "casefold-and-ascii-labels",
    "separator": "non-ascii-alphanumeric-underscore",
    "compound_labels": True,
}
TAXONOMY_CONTRACT = {
    "version": TAXONOMY_VERSION,
    "tokenizer": TAXONOMY_TOKENIZER_CONTRACT,
    "aliases": tuple(sorted(TAXONOMY_ALIASES.items())),
    "genres": TAXONOMY_GENRE_VOCABULARY,
    "subgenres": TAXONOMY_SUBGENRE_VOCABULARY,
    "styles": TAXONOMY_STYLE_VOCABULARY,
    "sections": TAXONOMY_SECTION_VOCABULARY,
    "section_aliases": tuple(sorted(TAXONOMY_SECTION_ALIASES.items())),
}
RANKER_MANIFEST = {
    "ranker_id": RANKER_ID,
    "ranker_schema": RANKER_SCHEMA,
    "weights": RANKER_WEIGHTS,
    "no_projection_weights": RANKER_NO_PROJECTION_WEIGHTS,
    "projection_versions": {
        "hvo": HVO_SCHEMA_VERSION,
        "features": FEATURES_SCHEMA_VERSION,
        "grammar": GRAMMAR_SCHEMA_VERSION,
    },
    "taxonomy": TAXONOMY_CONTRACT,
}
RANKER_MANIFEST_DIGEST = hashlib.sha256(
    json.dumps(RANKER_MANIFEST, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
