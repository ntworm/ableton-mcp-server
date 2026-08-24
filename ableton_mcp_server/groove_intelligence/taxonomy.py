"""Versioned, bounded facet derivation for rhythm and source taxonomy."""

from __future__ import annotations

import re
import unicodedata
from contextlib import suppress
from os import PathLike, fspath
from pathlib import PurePosixPath

from .constants import (
    TAXONOMY_ALIASES,
    TAXONOMY_GENRE_VOCABULARY,
    TAXONOMY_SECTION_ALIASES,
    TAXONOMY_SECTION_VOCABULARY,
    TAXONOMY_STYLE_VOCABULARY,
    TAXONOMY_SUBGENRE_VOCABULARY,
    TAXONOMY_TOKENIZER_VERSION,
)
from .constants import (
    TAXONOMY_VERSION as _TAXONOMY_VERSION,
)
from .projections import ROLES
from .schema import FeaturesProjectionV1, FeatureValueV1, HvoProjectionV1, Redistribution

TAXONOMY_VERSION = _TAXONOMY_VERSION
MAX_TAXONOMY_COMPONENTS = 16
MAX_TAXONOMY_LABELS = 32
MAX_TAXONOMY_LABEL_LENGTH = 48

_SAFE_LABEL = re.compile(r"[^a-z0-9]+")
_TOKEN_RE = re.compile(r"[^a-z0-9]+")
_TAXONOMY_AXES = ("collection", "genre", "subgenre", "style", "section", "source_category")
_ALLOWED_AXES = _TAXONOMY_AXES + ("feel", "density", "microtiming", "kit", "license")

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


def _alias_key(value: str) -> str:
    return " ".join(value.casefold().replace("_", " ").split())


def normalize_label(value: str, *, axis: str | None = None) -> str:
    """Return one bounded, portable label; reject empty or unsafe components."""

    del axis
    if not isinstance(value, str):
        raise ValueError("taxonomy label must be text")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"\br\s*&\s*b\b", "rnb", value, flags=re.IGNORECASE)
    value = value.replace("#", " ")
    alias = _ALIASES.get(_alias_key(value))
    if alias is not None:
        return alias
    label = _SAFE_LABEL.sub("_", value.casefold()).strip("_")[:MAX_TAXONOMY_LABEL_LENGTH]
    if not label:
        raise ValueError("taxonomy label is empty")
    return label


def normalize_facet_value(axis: str, value: str) -> str:
    """Normalize a search filter value using build-time label rules."""

    del axis
    normalized = normalize_label(value)
    return _SECTION_ALIASES.get(normalized, normalized)


def _validate_relative_path(relative_path: str | PathLike[str]) -> tuple[str, ...]:
    try:
        raw_path = fspath(relative_path)
    except TypeError as error:
        raise ValueError("taxonomy path must be a non-empty relative path") from error
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("taxonomy path must be a non-empty relative path")
    portable = raw_path.replace("\\", "/")
    if portable.startswith("/") or re.match(r"^[a-zA-Z]:", portable):
        raise ValueError("taxonomy path must be relative")
    parts = tuple(PurePosixPath(portable).parts)
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("taxonomy path contains an invalid component")
    if len(parts) > MAX_TAXONOMY_COMPONENTS:
        raise ValueError("taxonomy path exceeds component limit")
    return parts


def _component_payload(component: str) -> str:
    stem = component
    for suffix in (".midi", ".mid"):
        if stem.casefold().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem.split("@", 1)[1] if "@" in stem else stem


def _component_label(component: str) -> str:
    return normalize_label(_component_payload(component))


def _canonical_token(token: str) -> str:
    if not token or token.isdigit():
        return ""
    token = re.sub(r"\d+$", "", token)
    if not token:
        return ""
    return _ALIASES.get(_alias_key(token), token)


def _component_tokens(component: str) -> tuple[str, ...]:
    label = _component_label(component)
    tokens = tuple(_canonical_token(token) for token in _TOKEN_RE.split(label))
    return tuple(token for token in tokens if token)


def _contains_phrase(tokens: tuple[str, ...], value: str) -> bool:
    """Match a vocabulary label only on complete canonical token boundaries."""

    wanted = tuple(token for token in value.split("_") if token)
    if not wanted or len(wanted) > len(tokens):
        return False
    width = len(wanted)
    return any(tokens[index : index + width] == wanted for index in range(len(tokens) - width + 1))


def _component_labels(component: str) -> tuple[set[str], set[str], set[str], set[str]]:
    tokens = _component_tokens(component)
    genres = {token for token in tokens if token in _KNOWN_GENRES}
    genres.update(value for value in _KNOWN_GENRES if _contains_phrase(tokens, value))
    subgenres = {value for value in _KNOWN_SUBGENRES if _contains_phrase(tokens, value)}
    styles = {token for token in tokens if token in _KNOWN_STYLES}
    styles.update(value for value in _KNOWN_STYLES if _contains_phrase(tokens, value))
    sections = set()
    section_vocab_tokens = {
        token
        for value in (*_KNOWN_SECTIONS, *_SECTION_ALIASES)
        for token in value.split("_")
    }
    if tokens and all(token in section_vocab_tokens for token in tokens):
        for value in tokens:
            canonical = _SECTION_ALIASES.get(value, value)
            if canonical in _KNOWN_SECTIONS:
                sections.add(canonical)
        for value, canonical in _SECTION_ALIASES.items():
            if _contains_phrase(tokens, value):
                sections.add(canonical)
    return genres, subgenres, styles, sections


def _add(values: dict[str, set[str]], axis: str, value: str) -> None:
    try:
        label = normalize_label(value, axis=axis)
    except ValueError:
        return
    if len(values[axis]) < MAX_TAXONOMY_LABELS:
        values[axis].add(label)


def _add_component_labels(values: dict[str, set[str]], component: str) -> None:
    genres, subgenres, styles, sections = _component_labels(component)
    for label in genres:
        _add(values, "genre", label)
    for label in subgenres:
        _add(values, "subgenre", label)
    for label in styles:
        _add(values, "style", label)
    for label in sections:
        _add(values, "section", label)


def _add_source_category(values: dict[str, set[str]], component: str, *, depth: int) -> None:
    if depth > 3:
        return
    label = _component_label(component)
    if label in _GENERIC_SOURCE or label in _HIERARCHY_MARKERS or any(
        char.isdigit() for char in label
    ):
        return
    genres, subgenres, styles, sections = _component_labels(component)
    if genres or subgenres or styles:
        return
    known_tokens = (
        set(_KNOWN_GENRES)
        | set(_KNOWN_SUBGENRES)
        | set(_KNOWN_STYLES)
        | set(_KNOWN_SECTIONS)
        | set(_SECTION_ALIASES)
    )
    label = _component_label(component)
    if label in _SECTION_ALIASES or (
        sections and all(token in known_tokens for token in _component_tokens(component))
    ):
        return
    _add(values, "source_category", label)


def _path_values(relative_path: str | PathLike[str]) -> dict[str, tuple[str, ...]]:
    parts = _validate_relative_path(relative_path)
    directories = list(parts[:-1])
    filename = parts[-1]
    values: dict[str, set[str]] = {axis: set() for axis in _TAXONOMY_AXES}
    if directories:
        root_label = _component_label(directories[0])
        collection_index = 0
        if (
            len(directories) > 1
            and root_label in _GENERIC_ROOTS | {"collections", "packs", "libraries"}
        ):
            collection_index = 1
        _add(values, "collection", _component_payload(directories[collection_index]))
        for index, component in enumerate(directories):
            if index == collection_index and index == 0:
                continue
            if index == 0 and root_label in _GENERIC_ROOTS:
                continue
            _add_component_labels(values, component)
            if index != collection_index and not (
                index == 0 and root_label in _GENERIC_ROOTS
            ):
                _add_source_category(values, component, depth=index)

    _add_component_labels(values, filename)
    return {axis: tuple(sorted(labels)) for axis, labels in values.items() if labels}


class FacetSetV1:
    def __init__(
        self,
        values: dict[str, tuple[str, ...]],
        *,
        version: str = TAXONOMY_VERSION,
    ) -> None:
        self.values = {
            str(axis): tuple(str(value) for value in labels)
            for axis, labels in values.items()
            if axis in _ALLOWED_AXES and labels
        }
        self.version = version

    def model_dump(self, *, mode: str = "python") -> dict[str, object]:
        del mode
        return {"version": self.version, "values": self.values}


def classify_path_facets(relative_path: str | PathLike[str]) -> FacetSetV1:
    """Derive portable taxonomy from an authorized, relative source path."""

    return FacetSetV1(_path_values(relative_path))


derive_taxonomy = classify_path_facets
taxonomy_from_relative_path = classify_path_facets


def search_aliases(value: str) -> tuple[str, ...]:
    """Return canonical aliases that should participate in free-text matching."""

    normalized = normalize_label(value)
    aliases = [normalized]
    for alias, canonical in _ALIASES.items():
        if normalize_label(alias) == normalized:
            aliases.append(canonical)
    return tuple(dict.fromkeys(aliases))


def search_tokens(value: object) -> set[str]:
    """Tokenize text and retain canonical compound labels for free-text search."""

    text = str(value).casefold()
    tokens = {token for token in re.split(r"[^a-z0-9_]+", text) if token}
    candidates = [text]
    with suppress(ValueError):
        candidates.extend(search_aliases(text))
    for candidate in candidates:
        normalized = candidate.strip("_")
        if normalized:
            tokens.add(normalized)
        tokens.update(token for token in re.split(r"[^a-z0-9_]+", candidate) if token)
    for token in tuple(tokens):
        try:
            aliases = search_aliases(token)
        except ValueError:
            continue
        for alias in aliases:
            tokens.add(alias)
            tokens.update(item for item in re.split(r"[^a-z0-9_]+", alias) if item)
    return tokens


def _value(features: FeaturesProjectionV1, name: str) -> float | None:
    item: FeatureValueV1 | None = features.values.get(name)
    if item is None or item.status != "available" or not isinstance(item.value, (float, int)):
        return None
    return float(item.value)


def classify_facets(
    features: FeaturesProjectionV1,
    hvo: HvoProjectionV1,
    *,
    relative_path: str | None = None,
    redistribution: Redistribution = "full",
) -> FacetSetV1:
    """Combine rhythmic facets with optional taxonomy from an authorized relative path."""

    hits_per_bar = _value(features, "hits_per_bar") or 0.0
    offset_mean = _value(features, "offset_mean") or 0.0
    offset_std = _value(features, "offset_std") or 0.0
    density = "sparse" if hits_per_bar < 8 else "dense" if hits_per_bar > 20 else "medium"
    feel = "laid_back" if offset_mean > 3 else "pushed" if offset_mean < -3 else "straight"
    microtiming = "tight" if offset_std <= 3 else "loose" if offset_std >= 12 else "human"
    roles = tuple(sorted({cell.role for cell in hvo.cells}))
    values: dict[str, tuple[str, ...]] = {
        "feel": (feel,),
        "density": (density,),
        "microtiming": (microtiming,),
        "kit": roles or (ROLES[-1],),
        "license": (redistribution,),
    }
    if relative_path is not None:
        values.update(classify_path_facets(relative_path).values)
    return FacetSetV1(values)


__all__ = [
    "FacetSetV1",
    "MAX_TAXONOMY_COMPONENTS",
    "MAX_TAXONOMY_LABEL_LENGTH",
    "MAX_TAXONOMY_LABELS",
    "TAXONOMY_TOKENIZER_VERSION",
    "TAXONOMY_VERSION",
    "classify_facets",
    "classify_path_facets",
    "derive_taxonomy",
    "normalize_facet_value",
    "normalize_label",
    "search_aliases",
    "search_tokens",
    "taxonomy_from_relative_path",
]
