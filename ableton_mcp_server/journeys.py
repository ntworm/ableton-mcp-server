"""A fixed stage grid per guided journey.

There is no model behind this. Each journey has a known shape — discover, ask,
apply, verify — and the only thing that varies is which tool sits at the apply
and verify stages. Naming the tools without calling them is the point: the
caller sees what would happen before anything happens.
"""

from __future__ import annotations

from typing import Any

# The apply and verify tools per journey. Discovery and confirmation are the
# same for every journey, so they are not repeated here.
_JOURNEY_TOOLS: dict[str, tuple[str, str]] = {
    "sequence_drums": ("create_clip", "get_clip_summary"),
    "compose_melody": ("add_notes_to_clip", "get_clip_notes"),
    "compose_harmony": ("add_notes_to_clip", "get_clip_notes"),
    "design_sound": ("set_parameter_value", "get_track_state"),
}

# Asking for a named artist or an exact copy is a different request from
# describing a sound, and this tool answers only the second one.
_BLOCKED_TERMS = (
    "daft punk",
    "deadmau5",
    "skrillex",
    "beatles",
    "copy",
    "exact",
    "type beat",
)


def plan_user_journey(journey_type: str, traits: str) -> dict[str, Any]:
    """Return the stage plan for one journey, or a refusal explaining why not."""

    lowered = str(traits).casefold()
    blocked = sorted(term for term in _BLOCKED_TERMS if term in lowered)
    if blocked:
        return {
            "status": "intent-clarification-required",
            "reason": (
                "Traits contained restricted identity or copy language. "
                "Describe the audio features instead."
            ),
            "blocked_terms": blocked,
        }

    tools = _JOURNEY_TOOLS.get(journey_type)
    if tools is None:
        return {
            "status": "error",
            "reason": f"Unknown journey type: {journey_type}",
            "valid_journey_types": sorted(_JOURNEY_TOOLS),
        }

    apply_tool, verify_tool = tools
    return {
        "journey": journey_type,
        "traits": traits,
        "stages": [
            {"stage": "discovering", "status": "planned", "tool": "get_session_overview"},
            {"stage": "awaiting_confirmation", "status": "planned", "tool": None},
            {"stage": "applying", "status": "planned", "tool": apply_tool},
            {"stage": "verifying", "status": "planned", "tool": verify_tool},
        ],
    }


__all__ = ["plan_user_journey"]
