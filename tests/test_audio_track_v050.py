from __future__ import annotations

import pytest

from AbletonMCPServer_RemoteScript import RemoteError, execute_command
from tests.remote_fakes import FakeApplication, FakeSong, FakeTrack


def test_create_audio_track_appends_with_index_minus_one() -> None:
    song = FakeSong()
    app = FakeApplication()

    # Provide a real Live seam so cmd_create_audio_track doesn't short-circuit on LIVE_UNAVAILABLE.
    def _create_audio_track(index: int = -1) -> None:
        track = FakeTrack("Audio", midi=False)
        if index == -1:
            song.tracks.append(track)
        else:
            song.tracks.insert(index, track)

    song.create_audio_track = _create_audio_track  # type: ignore[attr-defined]

    res = execute_command(song, app, "create_audio_track", {"index": -1})

    assert res["created"] is True
    assert res["requested_index"] == -1
    # Brand-new track appended after the seeded "Bass" track
    assert res["track_index"] == len(song.tracks) - 1
    assert song.tracks[-1].name == "Audio"
    # No rename when name not provided: track_name echoes the LOM name
    assert res["track_name"] == "Audio"


def test_create_audio_track_inserts_at_index() -> None:
    song = FakeSong()
    app = FakeApplication()

    # Seed three more tracks so index=2 has a meaningful "before" set.
    seeded = [FakeTrack(f"Seed {i}") for i in range(3)]
    song.tracks.extend(seeded)

    def _create_audio_track(index: int = -1) -> None:
        track = FakeTrack("Audio", midi=False)
        if index == -1:
            song.tracks.append(track)
        else:
            song.tracks.insert(index, track)

    song.create_audio_track = _create_audio_track  # type: ignore[attr-defined]

    res = execute_command(song, app, "create_audio_track", {"index": 2})

    assert res["created"] is True
    assert res["requested_index"] == 2
    assert res["track_index"] == 2
    # The new track must be at index 2; "Seed 1" was previously at index 2 and
    # shifts to index 3, "Seed 2" stays at index 4.
    assert song.tracks[2].name == "Audio"
    assert song.tracks[3].name == "Seed 1"
    assert song.tracks[4].name == "Seed 2"


def test_create_audio_track_renames_when_name_provided() -> None:
    song = FakeSong()
    app = FakeApplication()

    def _create_audio_track(index: int = -1) -> None:
        track = FakeTrack("Audio", midi=False)
        if index == -1:
            song.tracks.append(track)
        else:
            song.tracks.insert(index, track)

    song.create_audio_track = _create_audio_track  # type: ignore[attr-defined]

    res = execute_command(song, app, "create_audio_track", {"name": "vocals"})

    assert res["created"] is True
    assert res["track_name"] == "vocals"
    assert song.tracks[-1].name == "vocals"


def test_create_audio_track_raises_when_live_unavailable() -> None:
    # Default FakeSong() has no create_audio_track attribute — this mirrors a Live host that
    # does not expose the seam (the documented LIVE_UNAVAILABLE failure mode).
    song = FakeSong()
    app = FakeApplication()

    with pytest.raises(RemoteError) as exc_info:
        execute_command(song, app, "create_audio_track", {})

    assert exc_info.value.code == "LIVE_UNAVAILABLE"


class TrackProxy:
    """Wraps a FakeTrack so every enumeration produces a fresh proxy object.

    Live's LOM exposes track collections as proxy iterators; each enumeration
    yields a new Python wrapper around the same underlying C++ object. Tracking
    identity via ``id()`` therefore collapses to the proxy, not the track.
    """

    def __init__(self, target: FakeTrack) -> None:
        object.__setattr__(self, "_target", target)

    def __getattr__(self, name: str) -> object:
        return getattr(self._target, name)

    def __setattr__(self, name: str, value: object) -> None:
        setattr(self._target, name, value)


class ReproxyingTracks:
    def __init__(self, targets: list[FakeTrack]) -> None:
        self.targets = targets

    def __iter__(self):
        return iter([TrackProxy(track) for track in self.targets])

    def __len__(self) -> int:
        return len(self.targets)

    def __getitem__(self, index: int) -> TrackProxy:
        return TrackProxy(self.targets[index])


def test_create_audio_track_resilient_to_proxy_identity_changes() -> None:
    song = FakeSong()  # seeded with one "Bass" track
    song.tracks = ReproxyingTracks(song.tracks)  # type: ignore[assignment]
    app = FakeApplication()

    def _create_audio_track(index: int = -1) -> None:
        track = FakeTrack("Audio", midi=False)
        if index == -1:
            song.tracks.targets.append(track)
        else:
            song.tracks.targets.insert(index, track)

    song.create_audio_track = _create_audio_track  # type: ignore[attr-defined]

    res = execute_command(
        song, app, "create_audio_track", {"index": -1, "name": "__MCP_ACCEPTANCE__Audio"}
    )

    assert res["created"] is True
    assert res["track_index"] == 1
    assert res["track_name"] == "__MCP_ACCEPTANCE__Audio"
    # The pre-existing track keeps its original name even though proxies refresh.
    assert song.tracks[0].name == "Bass"
