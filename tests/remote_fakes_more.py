"""Live model fakes for the acceptance and remote-script tests.

This module holds the second half of the shared Live model: the song, its
tracks, the browser and the application. ``tests/remote_fakes.py`` keeps the
first half and re-exports the names below, so the existing imports keep
working.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


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
        self.can_undo = False
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
        if self.start_time_write_attempts > self.stuck_writes:
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


# The names above are built on the first half of the Live model; the import
# sits at the end so that both modules can be imported in any order.
from .remote_fakes import (  # noqa: E402
    BeatTime,
    FakeBrowserItem,
    FakeClipSlot,
    FakeCuePoint,
    FakeDevice,
    FakeMixerDevice,
    FakeTrack,
)
