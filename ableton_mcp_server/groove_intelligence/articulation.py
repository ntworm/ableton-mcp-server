from __future__ import annotations
import json
import os
from .drum_roles import GM_DRUM_ROLE_BY_PITCH

_MAP_PATH = os.path.join(os.path.dirname(__file__), "articulation_map.json")
with open(_MAP_PATH, "r", encoding="utf-8") as f:
    _ARTICULATION_MAP = json.load(f)

def resolve_role(stratum: str, pitch: int) -> str:
    # Get collection specific map
    collection_map = _ARTICULATION_MAP.get(stratum, {})
    pitches = collection_map.get("pitches", {})
    
    # Check if we have a mapping for this pitch
    str_pitch = str(pitch)
    if str_pitch in pitches:
        return pitches[str_pitch]
        
    # Fallback to GM
    return GM_DRUM_ROLE_BY_PITCH.get(pitch, "other_percussion")
