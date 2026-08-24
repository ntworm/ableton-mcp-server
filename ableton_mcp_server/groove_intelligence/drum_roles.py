"""Canonical General MIDI percussion roles used by projections and apply mapping."""

from __future__ import annotations

# Keep role identifiers stable and descriptive: this tuple is part of the HVO
# projection contract and is also the kit facet vocabulary.
GM_DRUM_ROLES = (
    "kick",
    "snare",
    "rim",
    "clap",
    "hat_closed",
    "hat_open",
    "hat_pedal",
    "tom_low",
    "tom_mid",
    "tom_high",
    "crash",
    "splash",
    "china",
    "ride",
    "ride_bell",
    "tambourine",
    "cowbell",
    "other_percussion",
)


# GM percussion pitches 35–81.  Articulations that do not have a dedicated
# groove role remain searchable as ``other_percussion`` instead of being
# silently dropped from the HVO or late kit mapping.
GM_DRUM_ROLE_BY_PITCH: dict[int, str] = {
    35: "kick",
    36: "kick",
    37: "rim",
    38: "snare",
    39: "clap",
    40: "snare",
    41: "tom_low",
    42: "hat_closed",
    43: "tom_low",
    44: "hat_pedal",
    45: "tom_mid",
    46: "hat_open",
    47: "tom_mid",
    48: "tom_high",
    49: "crash",
    50: "tom_high",
    51: "ride",
    52: "china",
    53: "ride_bell",
    54: "tambourine",
    55: "splash",
    56: "cowbell",
    57: "crash",
    58: "other_percussion",  # vibraslap
    59: "ride",
    60: "other_percussion",  # hi bongo
    61: "other_percussion",  # low bongo
    62: "other_percussion",  # mute hi conga
    63: "other_percussion",  # open hi conga
    64: "other_percussion",  # low conga
    65: "other_percussion",  # high timbale
    66: "other_percussion",  # low timbale
    67: "other_percussion",  # high agogo
    68: "other_percussion",  # low agogo
    69: "other_percussion",  # cabasa
    70: "other_percussion",  # maracas
    71: "other_percussion",  # short whistle
    72: "other_percussion",  # long whistle
    73: "other_percussion",  # short guiro
    74: "other_percussion",  # long guiro
    75: "other_percussion",  # claves
    76: "other_percussion",  # hi wood block
    77: "other_percussion",  # low wood block
    78: "other_percussion",  # mute cuica
    79: "other_percussion",  # open cuica
    80: "other_percussion",  # mute triangle
    81: "other_percussion",  # open triangle
}


# Concise compatibility aliases for callers that do not need to distinguish
# the General MIDI vocabulary from future kit vocabularies.
ROLE_BY_PITCH = GM_DRUM_ROLE_BY_PITCH
ROLES = GM_DRUM_ROLES


__all__ = ["GM_DRUM_ROLE_BY_PITCH", "GM_DRUM_ROLES", "ROLE_BY_PITCH", "ROLES"]
