from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any


class BeatTime:
    def __init__(self, value: float) -> None:
        self.value = value

    def __float__(self) -> float:
        return self.value


@dataclass
class FakeCuePoint:
    name: str
    time: BeatTime


@dataclass
class FakeNote:
    pitch: int
    start_time: float
    duration: float
    velocity: int
    mute: bool = False


class FakeParameter:
    def __init__(self, name: str, value: float, minimum: float = 0.0, maximum: float = 1.0) -> None:
        self.name = name
        self.value = value
        self.min = minimum
        self.max = maximum
        self.is_enabled = True
        self.is_quantized = False


class FakeAutomationEnvelope:
    def __init__(self, on_insert: Callable[[], None] | None = None) -> None:
        self.steps: list[tuple[float, float, float]] = []
        self._on_insert = on_insert

    def insert_step(self, time: float, duration: float, value: float) -> None:
        self.steps.append((time, duration, value))
        if self._on_insert is not None:
            self._on_insert()


class _BrowserItemProxy:
    """Wraps a FakeBrowserItem so every enumeration yields a fresh proxy.

    Mirrors Live's LOM: the C++ engine keeps one object per item, but each
    access through Python returns a new wrapper. ``id()`` therefore never
    compares equal across calls.
    """

    __slots__ = ("_target",)

    def __init__(self, target: FakeBrowserItem) -> None:
        object.__setattr__(self, "_target", target)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._target, name, value)

    @property
    def children(self) -> list[_BrowserItemProxy]:
        return [_BrowserItemProxy(child) for child in self._target.children]


class FakeBrowserItem:
    def __init__(
        self,
        name: str,
        *,
        uri: str = "",
        is_loadable: bool = False,
        children: list[FakeBrowserItem] | None = None,
        reproxy_children: bool = False,
    ) -> None:
        self.name = name
        self.uri = uri
        self.is_loadable = is_loadable
        self._static_children = children if children is not None else []
        self._reproxy_children = reproxy_children

    @property
    def children(self) -> list[Any]:
        if self._reproxy_children:
            return [_BrowserItemProxy(child) for child in self._static_children]
        return list(self._static_children)

    @children.setter
    def children(self, value: list[FakeBrowserItem]) -> None:
        self._static_children = value
        self._reproxy_children = False

    def append_child(self, child: FakeBrowserItem) -> None:
        self._static_children.append(child)


class FakeDevice:
    def __init__(self, name: str = "Operator") -> None:
        self.name = name
        self.class_name = name
        self.is_active = True
        self.parameters = [FakeParameter("Device On", 1.0), FakeParameter("Filter Freq", 0.5)]


class FakePluginDevice:
    """Live's VST/VST3/AU wrapper device.

    Mirrors the split that motivates the plugin tools: ``parameters`` holds
    only ``Device On`` plus whatever the user added through Live's Configure
    button, while ``presets`` / ``selected_preset_index`` are exposed with no
    Configure step at all.
    """

    def __init__(
        self,
        name: str = "Superior Drummer 3",
        *,
        configured: bool = False,
        presets: list[str] | None = None,
        selected_preset_index: int = 0,
        stuck_writes: int = 0,
    ) -> None:
        self.name = name
        self.class_name = "PluginDevice"
        self.is_active = True
        self.parameters = [FakeParameter("Device On", 1.0)]
        if configured:
            self.parameters.append(FakeParameter("Master Volume", 0.5))
        self.presets = ["Default", "Rock Kit", "Jazz Kit"] if presets is None else list(presets)
        self._selected_preset_index = selected_preset_index
        # Live can lag one UI tick behind a write; ``stuck_writes`` reproduces a
        # host that never lands it so the verification path can be tested.
        self.stuck_writes = stuck_writes
        self.write_attempts = 0

    @property
    def selected_preset_index(self) -> int:
        return self._selected_preset_index

    @selected_preset_index.setter
    def selected_preset_index(self, value: int) -> None:
        self.write_attempts += 1
        if self.write_attempts <= self.stuck_writes:
            return
        self._selected_preset_index = value


class FakeClip:
    def __init__(self, name: str = "Clip", length: float = 4.0, midi: bool = True) -> None:
        self.name = name
        self.color = 0x1A2B3C
        self.color_index = 0
        self.length = length
        self.loop_start = 0.0
        self.loop_end = length
        self.is_session_clip = True
        self.has_envelopes = False
        self._automation_envelopes: dict[FakeParameter, FakeAutomationEnvelope] = {}
        self.is_midi_clip = midi
        self.is_playing = False
        self.notes = [FakeNote(60, 0.0, 1.0, 100)] if midi else []
        self.add_payloads: list[tuple[Any, ...]] = []
        self.fire_count = 0

    def get_notes_extended(
        self, _from_pitch: int, _pitch_span: int, _from_time: float, _time_span: float
    ) -> list[FakeNote]:
        return list(self.notes)

    def add_new_notes(self, payload: Iterable[Any]) -> list[int]:
        specifications = tuple(payload)
        self.add_payloads.append(specifications)
        ids = []
        for index, note in enumerate(specifications, start=len(self.notes) + 1):
            self.notes.append(
                FakeNote(
                    int(note.pitch),
                    float(note.start_time),
                    float(note.duration),
                    int(note.velocity),
                    bool(note.mute),
                )
            )
            ids.append(index)
        return ids

    def fire(self) -> None:
        self.fire_count += 1
        self.is_playing = True

    def remove_notes_extended(
        self,
        _from_pitch: int,
        _pitch_span: int,
        _from_time: float,
        _time_span: float,
    ) -> None:
        self.notes.clear()

    def automation_envelope(self, parameter: FakeParameter) -> FakeAutomationEnvelope | None:
        return self._automation_envelopes.get(parameter)

    def create_automation_envelope(self, parameter: FakeParameter) -> FakeAutomationEnvelope:
        if parameter not in self._automation_envelopes:
            self._automation_envelopes[parameter] = FakeAutomationEnvelope(
                lambda: setattr(self, "has_envelopes", True)
            )
        self.has_envelopes = True
        return self._automation_envelopes[parameter]

    def clear_envelope(self, parameter: FakeParameter) -> None:
        if parameter in self._automation_envelopes:
            self._automation_envelopes[parameter].steps.clear()
            del self._automation_envelopes[parameter]
        self.has_envelopes = False


class FakeClipSlot:
    def __init__(self, clip: FakeClip | None = None) -> None:
        self.clip = clip
        self.fire_count = 0
        self.created_lengths: list[float] = []

    @property
    def has_clip(self) -> bool:
        return self.clip is not None

    def create_clip(self, length: float) -> None:
        if self.clip is not None:
            raise RuntimeError("slot is not empty")
        self.created_lengths.append(length)
        self.clip = FakeClip(length=length)

    def fire(self) -> None:
        if self.clip is None:
            raise RuntimeError("slot is empty")
        self.fire_count += 1
        self.clip.fire()

    def delete_clip(self) -> None:
        if self.clip is None:
            raise RuntimeError("slot is empty")
        self.clip = None


class FakeMixerDevice:
    def __init__(self) -> None:
        self.volume = FakeParameter("Volume", 0.85)
        self.panning = FakeParameter("Pan", 0.0, -1.0, 1.0)
        self.sends = [FakeParameter("Send A", 0.1)]


class RoutingValue:
    def __init__(self, display_name: str) -> None:
        self.display_name = display_name


class FakeTrackView:
    def __init__(self, selected_device: FakeDevice | None = None) -> None:
        self.selected_device = selected_device


class FakeTrack:
    """Regular (midi/audio) track fake.

    ``is_foldable`` mirrors Live: it is ``True`` only for Group Tracks, which
    also report ``has_midi_input == False`` — that combination is exactly why
    a Group Track cannot be recognised from ``type`` alone. ``group_track``
    holds the parent Group Track object (Live returns a falsy ``id 0`` object
    for ungrouped tracks; ``None`` is the fake's equivalent).
    """

    def __init__(
        self,
        name: str,
        *,
        midi: bool = True,
        clip_slots: list[FakeClipSlot] | None = None,
        is_foldable: bool = False,
        group_track: FakeTrack | None = None,
        fold_state: int = 0,
        is_visible: bool = True,
        color_index: int = 0,
    ) -> None:
        self.name = name
        self.has_midi_input = midi
        self.has_audio_input = not midi
        self.color = 0x336699
        self.color_index = color_index
        self.is_foldable = is_foldable
        self.group_track = group_track
        self.is_grouped = group_track is not None
        self.fold_state = fold_state
        self.is_visible = is_visible
        self.mute = False
        self.solo = False
        self.arm = False
        self.mixer_device = FakeMixerDevice()
        self.devices = [FakeDevice()]
        self.clip_slots = clip_slots if clip_slots is not None else [FakeClipSlot(FakeClip())]
        self.view = FakeTrackView(self.devices[0])
        self.input_routing_type = RoutingValue("Ext. In")
        self.input_routing_channel = RoutingValue("1/2")
        self.output_routing_type = RoutingValue("Master")
        self.output_routing_channel = RoutingValue("1/2")


# The second half of the Live model lives in the sibling module; the import
# sits at the end so that both modules can be imported in any order.
from .remote_fakes_more import (  # noqa: E402,F401  (kept importable from this module)
    FakeApplication,
    FakeBrowser,
    FakeControlSurface,
    FakeScene,
    FakeSong,
    FakeSongView,
    FakeSpecialTrack,
    grouped_song,
)
