from __future__ import annotations

from collections.abc import Iterable
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


class FakeDevice:
    def __init__(self, name: str = "Operator") -> None:
        self.name = name
        self.class_name = name
        self.is_active = True
        self.parameters = [FakeParameter("Device On", 1.0), FakeParameter("Filter Freq", 0.5)]


class FakeClip:
    def __init__(self, name: str = "Clip", length: float = 4.0, midi: bool = True) -> None:
        self.name = name
        self.length = length
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
    def __init__(
        self,
        name: str,
        *,
        midi: bool = True,
        clip_slots: list[FakeClipSlot] | None = None,
    ) -> None:
        self.name = name
        self.has_midi_input = midi
        self.has_audio_input = not midi
        self.color = 0x336699
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
    def __init__(self, name: str) -> None:
        self.name = name
        self.color = 0
        self.mixer_device = FakeMixerDevice()
        self.devices: list[FakeDevice] = []


class FakeScene:
    def __init__(self, name: str, clip_slots: list[FakeClipSlot]) -> None:
        self.name = name
        self.clip_slots = clip_slots


class FakeSongView:
    def __init__(self, track: FakeTrack, scene: FakeScene) -> None:
        self.selected_track = track
        self.selected_scene = scene


class FakeSong:
    def __init__(self, *, stuck_writes: int = 0, deferred_writes: bool = False) -> None:
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


class FakeBrowser:
    sounds = object()
    drums = object()
    instruments = object()
    audio_effects = object()
    midi_effects = object()
    plugins = object()
    samples = object()


class FakeApplication:
    def __init__(self) -> None:
        self.browser = FakeBrowser()
        self.control_surfaces = [object()]
        self.begin_count = 0
        self.end_count = 0

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
