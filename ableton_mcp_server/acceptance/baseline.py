"""Baseline snapshot — the disposable Set state we must restore after a run.

The runner mutates tempo, song time, loop, cue points, mixer levels,
device parameters, and more. Every mutated value is captured here once,
before the first mutation, and the cleanup phase restores the Set
back to this exact state.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .safety import AcceptanceClient, AcceptanceSafetyError


@dataclass(frozen=True, slots=True)
class BaselineSnapshot:
    """Frozen snapshot of every field the runner may mutate.

    Provides both attribute-style access (preferred new style) and
    dict-style access (transitional compat for the legacy monolith).
    """

    song_name: str
    song_length: float
    track_names: dict[int, str] = field(default_factory=dict)
    track_types: dict[int, str] = field(default_factory=dict)
    track_mutes: dict[int, bool] = field(default_factory=dict)
    track_solos: dict[int, bool] = field(default_factory=dict)
    track_arms: dict[int, bool] = field(default_factory=dict)
    track_volumes: dict[int, float] = field(default_factory=dict)
    # ``None`` means the connected Remote Script did not report the field.
    # The colour probe and its restore are skipped for those tracks rather
    # than restoring an invented default.
    track_colors: dict[int, int | None] = field(default_factory=dict)
    track_color_indexes: dict[int, int | None] = field(default_factory=dict)
    tempo: float = 120.0
    current_song_time: float = 0.0
    loop: bool = False
    loop_start: float = 0.0
    loop_length: float = 4.0
    locators: list[Mapping[str, Any]] = field(default_factory=list)
    track_count: int = 0

    def __getitem__(self, key: str) -> Any:
        """Dict-style compat for the transitional monolith code paths."""
        return getattr(self, key)

    def __contains__(self, key: object) -> bool:
        """``"song_length" in baseline`` returns True iff the attribute exists."""
        if not isinstance(key, str):
            return False
        return hasattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style ``.get`` compat for transitional monolith code paths."""
        return getattr(self, key, default)

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict copy (useful for serialization)."""
        return {
            "song_name": self.song_name,
            "song_length": self.song_length,
            "track_names": dict(self.track_names),
            "track_types": dict(self.track_types),
            "track_mutes": dict(self.track_mutes),
            "track_solos": dict(self.track_solos),
            "track_arms": dict(self.track_arms),
            "track_volumes": dict(self.track_volumes),
            "track_colors": dict(self.track_colors),
            "track_color_indexes": dict(self.track_color_indexes),
            "tempo": self.tempo,
            "current_song_time": self.current_song_time,
            "loop": self.loop,
            "loop_start": self.loop_start,
            "loop_length": self.loop_length,
            "locators": list(self.locators),
            "track_count": self.track_count,
        }


def _optional_int(value: Any) -> int | None:
    """Return ``value`` as ``int`` when the bridge reported a real integer."""

    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _read_track_state(
    client: AcceptanceClient, idx: int
) -> tuple[bool, bool, bool, float, int | None, int | None]:
    """Read the mutable state of one track and refuse an unusable payload.

    Returns ``(mute, solo, arm, volume, color, color_index)``.
    """
    state = client.call("get_track_state", {"track_index": idx})
    if not isinstance(state, dict):
        raise AcceptanceSafetyError(f"get_track_state({idx}) returned non-dict: {state!r}")
    if "mute" not in state or "solo" not in state or "arm" not in state:
        raise AcceptanceSafetyError(
            f"get_track_state({idx}) missing mute/solo/arm; "
            "the disposable Set must expose the full track state"
        )
    if "volume" not in state:
        raise AcceptanceSafetyError(
            f"get_track_state({idx}) missing volume; the disposable "
            "Set must expose the mixer volume"
        )
    # Colour is captured leniently: a Remote Script older than the
    # set_track_color change does not report it, and that must degrade to
    # "no colour restore for this track" rather than aborting the run or
    # writing a fabricated default back into the Set.
    return (
        bool(state["mute"]),
        bool(state["solo"]),
        bool(state["arm"]),
        float(state["volume"]),
        _optional_int(state.get("color")),
        _optional_int(state.get("color_index")),
    )


def _capture_track_fields(
    client: AcceptanceClient,
    tracks: Any,
) -> tuple[
    dict[int, str],
    dict[int, str],
    dict[int, bool],
    dict[int, bool],
    dict[int, bool],
    dict[int, float],
    dict[int, int | None],
    dict[int, int | None],
]:
    """Capture the per-track fields the restore step has to round-trip.

    Returns the track names, types, mutes, solos, arms, volumes, colours
    and colour indexes, in that order.
    """
    track_names: dict[int, str] = {}
    track_types: dict[int, str] = {}
    track_mutes: dict[int, bool] = {}
    track_solos: dict[int, bool] = {}
    track_arms: dict[int, bool] = {}
    track_volumes: dict[int, float] = {}
    track_colors: dict[int, int | None] = {}
    track_color_indexes: dict[int, int | None] = {}
    for track in tracks:
        idx = int(track.get("index", -1))
        track_names[idx] = str(track.get("name", ""))
        track_types[idx] = str(track.get("type", ""))
        (
            track_mutes[idx],
            track_solos[idx],
            track_arms[idx],
            track_volumes[idx],
            track_colors[idx],
            track_color_indexes[idx],
        ) = _read_track_state(client, idx)
    return (
        track_names,
        track_types,
        track_mutes,
        track_solos,
        track_arms,
        track_volumes,
        track_colors,
        track_color_indexes,
    )


def _read_song_length(client: AcceptanceClient) -> float:
    """Read the song length and refuse a payload the restore cannot use."""
    song_length_payload = client.call("get_song_length")
    if not isinstance(song_length_payload, dict):
        raise AcceptanceSafetyError(f"get_song_length returned non-dict: {song_length_payload!r}")
    song_length_value = song_length_payload.get("song_length")
    if not isinstance(song_length_value, (int, float)) or isinstance(song_length_value, bool):
        raise AcceptanceSafetyError(
            f"get_song_length.song_length must be a positive number, got {song_length_value!r}"
        )
    song_length_f = float(song_length_value)
    if song_length_f <= 0.0:
        raise AcceptanceSafetyError(
            f"get_song_length.song_length must be positive, got {song_length_f}"
        )
    return song_length_f


def discover_baseline(client: AcceptanceClient) -> BaselineSnapshot:
    """Capture the disposable Set baseline that the runner must restore.

    The restore step relies on every value the mutations touch being
    captured here. A live ``live_fade`` or ``set_track_property`` run
    must round-trip through the original value, not a default.

    The real ``get_track_list`` contract returns only ``id``/``index``/
    ``name``/``type`` — no ``mute``/``solo``/``arm``/``volume``. We
    therefore drive every per-track field from ``get_track_state``,
    which exposes the mixer and arm state. We never read the absent
    fields from ``get_track_list`` or invent defaults for them.
    """
    metadata = client.call("get_project_metadata")
    song_name = str(metadata.get("song_name", ""))
    tracks = client.call("get_track_list")
    (
        track_names,
        track_types,
        track_mutes,
        track_solos,
        track_arms,
        track_volumes,
        track_colors,
        track_color_indexes,
    ) = _capture_track_fields(client, tracks)
    session = client.call("get_session_info")
    loop = client.call("get_loop_settings")
    locators = client.call("get_locators")
    song_length_f = _read_song_length(client)
    return BaselineSnapshot(
        song_name=song_name,
        song_length=song_length_f,
        track_names=track_names,
        track_types=track_types,
        track_mutes=track_mutes,
        track_solos=track_solos,
        track_arms=track_arms,
        track_volumes=track_volumes,
        track_colors=track_colors,
        track_color_indexes=track_color_indexes,
        tempo=float(session["tempo"]),
        current_song_time=float(session["current_song_time"]),
        loop=bool(loop.get("loop", False)),
        loop_start=float(loop.get("loop_start", 0.0)),
        loop_length=float(loop.get("loop_length", 4.0)),
        locators=list(locators),
        track_count=len(tracks),
    )


# Back-compat alias for the legacy module surface.
_discover_baseline = discover_baseline
