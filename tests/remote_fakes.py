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


class FakeSpecialTrack:
    """Return/master track fake.

    Deliberately narrower than :class:`FakeTrack`: it exposes ``color`` and
    ``color_index`` but none of the grouping properties, so the reads exercise
    the ``_safe`` fallback path a Live host takes when a property is missing.
    """

    def __init__(self, name: str, *, color_index: int = 0) -> None:
        self.name = name
        self.color = 0
        self.color_index = color_index
        self.mixer_device = FakeMixerDevice()
        self.devices: list[FakeDevice] = []


class FakeScene:
    def __init__(self, name: str, clip_slots: list[FakeClipSlot]) -> None:
        self.name = name
        self.clip_slots = clip_slots
        self.fire_count = 0

    def fire(self) -> None:
        self.fire_count += 1


class FakeSongView:
    def __init__(self, track: FakeTrack, scene: FakeScene) -> None:
        self.selected_track = track
        self.selected_scene = scene


class FakeSong:
    def __init__(
        self,
        *,
        stuck_writes: int = 0,
        deferred_writes: bool = False,
        save: Callable[[], Any] | None = None,
    ) -> None:
        self._tempo = 120.0
        self._pending_tempo: float | None = None
        self.signature_numerator = 4
        self.signature_denominator = 4
        self.deferred_writes = deferred_writes
        self._is_playing = False
        self._pending_is_playing: bool | None = None
        self._current_song_time = 0.0
        self._pending_song_time: float | None = None
        self.stuck_writes = stuck_writes
        self.transport_write_attempts = 0
        self._loop = False
        self._pending_loop: bool | None = None
        self._loop_start = 0.0
        self._pending_loop_start: float | None = None
        self._loop_length = 4.0
        self._pending_loop_length: float | None = None
        self._start_time = 0.0
        self._pending_start_time: float | None = None
        self.start_time_write_attempts = 0
        self.start_marker = 0.0
        self.end_marker = 64.0
        self.song_length = 64.25
        self.clip_trigger_quantization: Any = "quarter"
        self.cue_points: list[FakeCuePoint] = []
        self.tracks = [FakeTrack("Bass")]
        self.return_tracks = [FakeSpecialTrack("Return A")]
        self.master_track = FakeSpecialTrack("Master")
        self.scenes = [FakeScene("Verse", [self.tracks[0].clip_slots[0]])]
        self.view = FakeSongView(self.tracks[0], self.scenes[0])
        self.name = "Debug Set"
        self.file_path = r"C:\Music\Debug Set.als"
        self.is_dirty = False
        self.toggle_count = 0
        if save is not None:
            # v0.5.0 — Lifecycle seam. ``Song.save`` only exists when the Live host
            # exposes it; Fakes opt in by passing a callable here.
            self.save = save  # type: ignore[attr-defined]

    @property
    def current_song_time(self) -> float:
        return self._current_song_time

    @current_song_time.setter
    def current_song_time(self, value: float) -> None:
        self.transport_write_attempts += 1
        if self.transport_write_attempts > self.stuck_writes:
            if self.deferred_writes:
                self._pending_song_time = float(value)
            else:
                self._current_song_time = float(value)

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def tempo(self) -> float:
        return self._tempo

    @tempo.setter
    def tempo(self, value: float) -> None:
        if self.deferred_writes:
            self._pending_tempo = float(value)
        else:
            self._tempo = float(value)

    @property
    def loop(self) -> bool:
        return self._loop

    @loop.setter
    def loop(self, value: bool) -> None:
        if self.deferred_writes:
            self._pending_loop = value
        else:
            self._loop = value

    @property
    def loop_start(self) -> float:
        return self._loop_start

    @loop_start.setter
    def loop_start(self, value: float) -> None:
        if self.deferred_writes:
            self._pending_loop_start = float(value)
        else:
            self._loop_start = float(value)

    @property
    def loop_length(self) -> float:
        return self._loop_length

    @loop_length.setter
    def loop_length(self, value: float) -> None:
        if self.deferred_writes:
            self._pending_loop_length = float(value)
        else:
            self._loop_length = float(value)

    @property
    def start_time(self) -> float:
        return self._start_time

    @start_time.setter
    def start_time(self, value: float) -> None:
        self.start_time_write_attempts += 1
        if self.deferred_writes:
            self._pending_start_time = float(value)
        else:
            self._start_time = float(value)

    def tick(self) -> None:
        if self._pending_song_time is not None:
            self._current_song_time = self._pending_song_time
            self._pending_song_time = None
        if self._pending_is_playing is not None:
            self._is_playing = self._pending_is_playing
            self._pending_is_playing = None
        if self._pending_loop is not None:
            self._loop = self._pending_loop
            self._pending_loop = None
        if self._pending_tempo is not None:
            self._tempo = self._pending_tempo
            self._pending_tempo = None
        if self._pending_loop_start is not None:
            self._loop_start = self._pending_loop_start
            self._pending_loop_start = None
        if self._pending_loop_length is not None:
            self._loop_length = self._pending_loop_length
            self._pending_loop_length = None
        if self._pending_start_time is not None:
            self._start_time = self._pending_start_time
            self._pending_start_time = None

    def set_or_delete_cue(self) -> None:
        self.toggle_count += 1
        existing = next(
            (
                cue
                for cue in self.cue_points
                if abs(float(cue.time) - self.current_song_time) < 0.01
            ),
            None,
        )
        if existing is None:
            self.cue_points.append(FakeCuePoint("", BeatTime(self.current_song_time)))
        else:
            self.cue_points.remove(existing)

    def start_playing(self) -> None:
        if self.deferred_writes:
            self._pending_is_playing = True
        else:
            self._is_playing = True

    def stop_playing(self) -> None:
        if self.deferred_writes:
            self._pending_is_playing = False
        else:
            self._is_playing = False

    def create_midi_track(self, index: int = -1) -> None:
        track = FakeTrack("MIDI Track", midi=True)
        if index == -1:
            self.tracks.append(track)
        else:
            self.tracks.insert(index, track)


def grouped_song() -> FakeSong:
    """A Set shaped like the reported failure case.

    Track 0 is a folded Group Track named ``"1 DRUMS"`` — the name Live
    renders for a track literally named ``"# DRUMS"``. Track 1 is its hidden
    child, track 2 is ungrouped. The Group Track has no MIDI input, so
    ``_track_type`` reports ``audio`` for it; only ``is_group_track``
    separates it from a plain audio track.
    """

    song = FakeSong()
    group = FakeTrack("1 DRUMS", midi=False, is_foldable=True, fold_state=1, color_index=5)
    child = FakeTrack("Kick", midi=True, group_track=group, is_visible=False, color_index=6)
    loose = FakeTrack("Bass", midi=True, color_index=7)
    song.tracks = [group, child, loose]
    song.scenes = [FakeScene("Verse", [group.clip_slots[0]])]
    song.view = FakeSongView(loose, song.scenes[0])
    return song


class FakeBrowser:
    def __init__(self) -> None:
        self.sounds = FakeBrowserItem("Sounds")
        self.drums = FakeBrowserItem("Drums")
        self.instruments = FakeBrowserItem("Instruments")
        self.audio_effects = FakeBrowserItem("Audio Effects")
        self.midi_effects = FakeBrowserItem("MIDI Effects")
        self.plugins = FakeBrowserItem("Plug-ins")
        self.samples = FakeBrowserItem("Samples")
        self.clips = FakeBrowserItem("Clips")
        self.packs = FakeBrowserItem("Packs")
        self.user_library = FakeBrowserItem("User Library")

    @classmethod
    def with_operator(cls) -> FakeBrowser:
        browser = cls()
        browser.instruments.append_child(
            FakeBrowserItem(
                "Operator",
                uri="query:Instruments#Operator",
                is_loadable=True,
            )
        )
        return browser


class FakeControlSurface:
    """Stand-in for ``ableton.v2.control_surface.ControlSurface``.

    The v0.5.0 lifecycle commands run ``schedule_message`` to defer the quit
    callback to a future Live UI tick. Tests record what was scheduled rather
    than actually invoking the callback, so the ``FakeControlSurface`` keeps an
    audit list. The default policy is to **invoke immediately** (matches the
    dispatch path where ``update_display`` is calling), but tests can opt into
    "record only" behaviour via ``invoke_immediately=False``.
    """

    def __init__(
        self,
        c_instance: Any = None,
        *,
        invoke_immediately: bool = True,
    ) -> None:
        self._c_instance = c_instance
        self.song = c_instance.song if c_instance is not None else None
        self.scheduled: list[tuple[int, Callable[[], Any]]] = []
        self._invoke_immediately = invoke_immediately

    def schedule_message(self, delay: int, callback: Callable[[], Any]) -> None:
        self.scheduled.append((int(delay), callback))
        if self._invoke_immediately:
            callback()


class FakeApplication:
    def __init__(
        self,
        browser: FakeBrowser | None = None,
        quit: Callable[[], Any] | None = None,
    ) -> None:
        self.browser = browser if browser is not None else FakeBrowser()
        self.control_surfaces = [object()]
        self.begin_count = 0
        self.end_count = 0
        if quit is not None:
            # v0.5.0 — Lifecycle seam. ``Application.quit`` only exists when the
            # Live host exposes it; Fakes opt in by passing a callable here.
            self.quit = quit  # type: ignore[attr-defined]

    def get_major_version(self) -> int:
        return 12

    def get_minor_version(self) -> int:
        return 4

    def get_bugfix_version(self) -> int:
        return 5

    def begin_undo_step(self) -> None:
        self.begin_count += 1

    def end_undo_step(self) -> None:
        self.end_count += 1
