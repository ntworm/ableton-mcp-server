"""Clip colouring, clip-target diagnostics, and content preservation.

``Clip.color`` and ``Clip.color_index`` are ``getsetobserve`` in the Live 12
LOM, and ``Track.arrangement_clips`` exists since Live 11 — so both the
Session and the Arrangement lane are genuinely writable, unlike track
reordering. These tests pin that difference down: what works must work, and
what cannot work must refuse without touching anything.
"""

from __future__ import annotations

from typing import Any

import pytest

from AbletonMCPServer_RemoteScript import RemoteError, execute_command
from tests.remote_fakes import (
    FakeApplication,
    FakeClip,
    FakeClipSlot,
    FakeSong,
    FakeTrack,
    grouped_song,
)


def call(song: FakeSong, command: str, params: dict[str, object] | None = None) -> Any:
    return execute_command(song, FakeApplication(), command, params or {})


def _song_with_arrangement() -> FakeSong:
    song = FakeSong()
    song.tracks[0].arrangement_clips = [
        FakeClip(name="Arr A", length=8.0),
        FakeClip(name="Arr B", length=16.0),
    ]
    return song


# ---------------------------------------------------------------------------
# set_clip_color — Session lane
# ---------------------------------------------------------------------------


def test_session_clip_color_index_is_written_and_read_back() -> None:
    song = FakeSong()
    result = call(song, "set_clip_color", {"track_index": 0, "clip_index": 0, "color_index": 14})

    clip = song.tracks[0].clip_slots[0].clip
    assert clip is not None
    assert clip.color_index == 14
    assert result["color_index"] == 14
    assert result["scope"] == "session"
    assert result["clip_id"] == "track:0/clipslot:0/clip"
    assert result["resolved"]["kind"] == "clip"
    assert result["resolved"]["clip_name"] == "Clip"


def test_session_clip_packed_rgb_is_written() -> None:
    song = FakeSong()
    result = call(song, "set_clip_color", {"track_index": 0, "clip_index": 0, "color": 0x00FF7F})

    assert song.tracks[0].clip_slots[0].clip.color == 0x00FF7F  # type: ignore[union-attr]
    assert result["property"] == "color"
    assert result["color"] == 0x00FF7F


def test_empty_session_slot_is_rejected() -> None:
    song = FakeSong()
    song.tracks[0].clip_slots = [FakeClipSlot(None)]

    with pytest.raises(RemoteError) as error:
        call(song, "set_clip_color", {"track_index": 0, "clip_index": 0, "color_index": 1})

    assert error.value.code == "BAD_INPUT"


@pytest.mark.parametrize(
    "params",
    [
        {"track_index": 0, "clip_index": 0},
        {"track_index": 0, "clip_index": 0, "color": 1, "color_index": 1},
    ],
)
def test_clip_color_requires_exactly_one_colour_source(params: dict[str, Any]) -> None:
    song = FakeSong()
    with pytest.raises(RemoteError) as error:
        call(song, "set_clip_color", params)
    assert error.value.code == "INVALID_PARAMS"


@pytest.mark.parametrize(
    "params",
    [
        {"track_index": 0, "clip_index": 0, "color_index": 70},
        {"track_index": 0, "clip_index": 0, "color_index": -1},
        {"track_index": 0, "clip_index": 0, "color": 0x1000000},
    ],
)
def test_clip_color_rejects_out_of_range_values(params: dict[str, Any]) -> None:
    song = FakeSong()
    with pytest.raises(RemoteError) as error:
        call(song, "set_clip_color", params)
    assert error.value.code == "BAD_INPUT"


def test_clip_color_rejects_an_unknown_scope() -> None:
    song = FakeSong()
    with pytest.raises(RemoteError) as error:
        call(
            song,
            "set_clip_color",
            {"track_index": 0, "clip_index": 0, "scope": "takelane", "color_index": 1},
        )
    assert error.value.code == "BAD_INPUT"


def test_clip_color_fails_verification_instead_of_retrying() -> None:
    class StubbornClip(FakeClip):
        write_attempts = 0

        @property  # type: ignore[misc]
        def color_index(self) -> int:
            return 0

        @color_index.setter
        def color_index(self, _value: int) -> None:
            self.write_attempts += 1

    song = FakeSong()
    clip = StubbornClip()
    clip.write_attempts = 0
    song.tracks[0].clip_slots = [FakeClipSlot(clip)]

    with pytest.raises(RemoteError) as error:
        call(song, "set_clip_color", {"track_index": 0, "clip_index": 0, "color_index": 6})

    assert error.value.code == "VERIFICATION_FAILED"
    assert clip.write_attempts == 1


def test_clip_color_is_a_single_undo_step() -> None:
    song = FakeSong()
    application = FakeApplication()
    execute_command(
        song, application, "set_clip_color", {"track_index": 0, "clip_index": 0, "color_index": 3}
    )
    assert application.begin_count == 1
    assert application.end_count == 1


# ---------------------------------------------------------------------------
# set_clip_color — Arrangement lane
# ---------------------------------------------------------------------------


def test_arrangement_clip_color_is_written_when_the_host_exposes_the_lane() -> None:
    song = _song_with_arrangement()
    result = call(
        song,
        "set_clip_color",
        {"track_index": 0, "clip_index": 1, "scope": "arrangement", "color_index": 21},
    )

    assert song.tracks[0].arrangement_clips[1].color_index == 21
    assert song.tracks[0].arrangement_clips[0].color_index != 21
    assert result["clip_id"] == "track:0/arrangementclip:1"
    assert result["scope"] == "arrangement"


def test_arrangement_scope_is_capability_unavailable_without_the_lom_property() -> None:
    song = FakeSong()  # FakeTrack has no arrangement_clips by default

    with pytest.raises(RemoteError) as error:
        call(
            song,
            "set_clip_color",
            {"track_index": 0, "clip_index": 0, "scope": "arrangement", "color_index": 1},
        )

    assert error.value.code == "CAPABILITY_UNAVAILABLE"
    assert "arrangement_clips" in str(error.value)


def test_out_of_range_arrangement_index_is_rejected() -> None:
    song = _song_with_arrangement()
    with pytest.raises(RemoteError) as error:
        call(
            song,
            "set_clip_color",
            {"track_index": 0, "clip_index": 9, "scope": "arrangement", "color_index": 1},
        )
    assert error.value.code == "INVALID_PARAMS"


# ---------------------------------------------------------------------------
# diagnose_clip_targets
# ---------------------------------------------------------------------------


def test_diagnostic_reports_session_and_arrangement_targets() -> None:
    song = _song_with_arrangement()
    report = call(song, "diagnose_clip_targets", {"track_index": 0})

    assert report["session_clip_count"] == 1
    assert report["arrangement_clip_count"] == 2
    track = report["tracks"][0]
    assert track["arrangement_supported"] is True
    assert [clip["scope"] for clip in track["arrangement_clips"]] == ["arrangement", "arrangement"]
    assert track["session_clips"][0]["id"] == "track:0/clipslot:0/clip"
    assert all(clip["colorable"] for clip in track["session_clips"])


def test_diagnostic_names_the_inaccessible_arrangement_lane() -> None:
    song = FakeSong()
    report = call(song, "diagnose_clip_targets", {"track_index": 0})

    assert report["arrangement_clip_count"] == 0
    assert report["tracks"][0]["arrangement_supported"] is False
    reasons = [entry["reason"] for entry in report["inaccessible"]]
    assert any("Track.arrangement_clips" in reason for reason in reasons)


def test_diagnostic_sweeps_every_track_when_no_index_is_given() -> None:
    song = grouped_song()
    report = call(song, "diagnose_clip_targets", {})

    # 3 regular tracks + 1 return + 1 master.
    assert len(report["tracks"]) == 5
    assert [track["track_index"] for track in report["tracks"]] == [0, 1, 2, 3, 4]


def test_diagnostic_never_writes() -> None:
    song = _song_with_arrangement()
    before = [
        (clip.name, clip.color, clip.color_index) for clip in song.tracks[0].arrangement_clips
    ]
    application = FakeApplication()

    execute_command(song, application, "diagnose_clip_targets", {})

    assert [
        (clip.name, clip.color, clip.color_index) for clip in song.tracks[0].arrangement_clips
    ] == before
    assert application.begin_count == 0


# ---------------------------------------------------------------------------
# Content preservation
# ---------------------------------------------------------------------------


def _content_fingerprint(song: FakeSong) -> list[tuple[Any, ...]]:
    """Everything a hierarchy edit is required to preserve."""

    fingerprint: list[tuple[Any, ...]] = []
    for track in song.tracks:
        mixer = track.mixer_device
        fingerprint.append(
            (
                track.name,
                tuple(device.name for device in track.devices),
                tuple(
                    (
                        slot.clip.name if slot.clip else None,
                        tuple(
                            (note.pitch, note.start_time, note.duration, note.velocity)
                            for note in (slot.clip.notes if slot.clip else [])
                        ),
                    )
                    for slot in track.clip_slots
                ),
                mixer.volume.value,
                mixer.panning.value,
                tuple(send.value for send in mixer.sends),
                track.mute,
                track.solo,
                track.arm,
                track.input_routing_type.display_name,
                track.output_routing_type.display_name,
                track.color,
                track.color_index,
                track.fold_state,
                track.is_grouped,
            )
        )
    return fingerprint


@pytest.mark.parametrize(
    ("command", "params"),
    [
        ("move_track", {"track_index": 2, "destination_index": 0}),
        ("reorder_tracks", {"order": [2, 1, 0]}),
        ("move_track_to_group", {"track_index": 2, "group_track_index": 0}),
        ("ungroup_track", {"track_index": 1}),
    ],
)
def test_refused_hierarchy_ops_preserve_every_piece_of_content(
    command: str, params: dict[str, Any]
) -> None:
    song = grouped_song()
    song.tracks[2].clip_slots = [FakeClipSlot(FakeClip(name="Bassline"))]
    before = _content_fingerprint(song)
    track_count = len(song.tracks)

    with pytest.raises(RemoteError) as error:
        call(song, command, params)

    assert error.value.code == "CAPABILITY_UNAVAILABLE"
    assert len(song.tracks) == track_count, "a refusal must never add or remove a track"
    assert _content_fingerprint(song) == before


def test_merge_groups_never_deletes_the_emptied_source() -> None:
    song = grouped_song()
    song.tracks.append(FakeTrack("2 KEYS", midi=False, is_foldable=True))
    names = [track.name for track in song.tracks]

    with pytest.raises(RemoteError) as error:
        call(song, "merge_groups", {"source_group_index": 0, "destination_group_index": 3})

    assert error.value.code == "CAPABILITY_UNAVAILABLE"
    assert [track.name for track in song.tracks] == names


# ---------------------------------------------------------------------------
# Public surface: models, catalog, registry, wrapper forwarding
# ---------------------------------------------------------------------------


def test_request_models_reject_malformed_hierarchy_requests() -> None:
    from pydantic import ValidationError

    from ableton_mcp_server import models

    with pytest.raises(ValidationError):
        models.MoveTrackRequest(track_index=-1, destination_index=0)
    with pytest.raises(ValidationError):
        models.ReorderTracksRequest(order=[])
    with pytest.raises(ValidationError):
        models.ReorderTracksRequest(order=[0, 0, 1])
    with pytest.raises(ValidationError):
        models.MoveTrackToGroupRequest(track_index=2, group_track_index=2)
    with pytest.raises(ValidationError):
        models.MergeGroupsRequest(source_group_index=1, destination_group_index=1)

    assert (
        models.MergeGroupsRequest(
            source_group_index=0, destination_group_index=1
        ).delete_empty_source
        is False
    )


def test_clip_colour_request_model_validates_scope_and_colour() -> None:
    from pydantic import ValidationError

    from ableton_mcp_server import models

    with pytest.raises(ValidationError):
        models.SetClipColorRequest(track_index=0, clip_index=0)
    with pytest.raises(ValidationError):
        models.SetClipColorRequest(track_index=0, clip_index=0, color_index=1, color=1)
    with pytest.raises(ValidationError):
        models.SetClipColorRequest(track_index=0, clip_index=0, scope="takelane", color_index=1)
    with pytest.raises(ValidationError):
        models.SetClipColorRequest(track_index=0, clip_index=0, color_index=70)

    assert models.SetClipColorRequest(track_index=0, clip_index=0, color_index=1).scope == "session"


def test_new_tools_are_registered_across_every_source_of_truth() -> None:
    from ableton_mcp_server.acceptance.probes import BASELINE_PROBE_GROUPS
    from ableton_mcp_server.catalog import TOOL_CATALOG, AcceptanceMode, Risk
    from ableton_mcp_server.models import TOOL_REQUEST_MODELS
    from ableton_mcp_server.server import PUBLIC_TOOL_NAMES
    from contracts import ALLOWED_MUTATIONS, READ_COMMANDS, UNSUPPORTED_CAPABILITIES

    by_name = {spec.name: spec for spec in TOOL_CATALOG}
    probe_home = {tool: group for group, tools in BASELINE_PROBE_GROUPS.items() for tool in tools}

    assert "set_clip_color" in ALLOWED_MUTATIONS
    assert "diagnose_clip_targets" in READ_COMMANDS
    for tool in ("set_clip_color", "diagnose_clip_targets", *UNSUPPORTED_CAPABILITIES):
        assert tool in by_name, tool
        assert tool in TOOL_REQUEST_MODELS, tool
        assert tool in PUBLIC_TOOL_NAMES, tool
        assert tool in probe_home, tool

    for tool in UNSUPPORTED_CAPABILITIES:
        assert by_name[tool].risk is Risk.UNAVAILABLE
        assert by_name[tool].acceptance is AcceptanceMode.CAPABILITY
        assert probe_home[tool] == "capability"


def test_server_wrappers_forward_the_exact_contract() -> None:
    from unittest.mock import MagicMock, patch

    from ableton_mcp_server import server

    with patch("ableton_mcp_server.server.get_client") as get_client:
        get_client.return_value = MagicMock()
        get_client.return_value.call.return_value = {"forwarded": True}

        server.set_clip_color(1, 2, color_index=7)
        server.set_clip_color(1, 2, scope="arrangement", color=0x112233)
        server.diagnose_clip_targets()
        server.diagnose_clip_targets(3)
        server.move_track(0, 4)
        server.reorder_tracks([1, 0])
        server.move_track_to_group(2, 1)
        server.ungroup_track(2)
        server.merge_groups(1, 3)

    assert [call.args for call in get_client.return_value.call.call_args_list] == [
        (
            "set_clip_color",
            {"track_index": 1, "clip_index": 2, "scope": "session", "color_index": 7},
        ),
        (
            "set_clip_color",
            {"track_index": 1, "clip_index": 2, "scope": "arrangement", "color": 0x112233},
        ),
        ("diagnose_clip_targets", {}),
        ("diagnose_clip_targets", {"track_index": 3}),
        ("move_track", {"track_index": 0, "destination_index": 4}),
        ("reorder_tracks", {"order": [1, 0]}),
        ("move_track_to_group", {"track_index": 2, "group_track_index": 1}),
        ("ungroup_track", {"track_index": 2}),
        (
            "merge_groups",
            {
                "source_group_index": 1,
                "destination_group_index": 3,
                "delete_empty_source": False,
            },
        ),
    ]


def test_capability_error_reaches_the_mcp_boundary_with_its_evidence() -> None:
    """A refusal must arrive as a structured MCP error, not a crash."""

    from unittest.mock import MagicMock, patch

    from ableton_mcp_server import server
    from ableton_mcp_server.errors import CapabilityUnavailableError
    from contracts import CAPABILITY_EVIDENCE

    with patch("ableton_mcp_server.server.get_client") as get_client:
        get_client.return_value = MagicMock()
        get_client.return_value.call.side_effect = CapabilityUnavailableError(
            "no public API",
            "nothing was changed",
            details={**CAPABILITY_EVIDENCE["move_track"], "applied": False},
        )
        result = server.move_track(0, 1)

    assert result.is_error is True
    envelope = result.structured_content
    assert envelope["code"] == "CAPABILITY_UNAVAILABLE"
    assert envelope["details"]["applied"] is False
    assert envelope["details"]["lom_song_functions_checked"]


def test_protocol_round_trips_the_details_payload() -> None:
    from ableton_mcp_server.protocol import decode_response, encode_response

    payload = {
        "status": "error",
        "code": "CAPABILITY_UNAVAILABLE",
        "message": "no public API",
        "hint": "nothing changed",
        "details": {"applied": False, "request": {"track_index": 0}},
    }
    decoded = decode_response(encode_response(payload))

    assert decoded.code == "CAPABILITY_UNAVAILABLE"
    assert decoded.details == {"applied": False, "request": {"track_index": 0}}


def test_colouring_a_clip_preserves_its_notes_and_devices() -> None:
    song = FakeSong()
    before = _content_fingerprint(song)
    clip = song.tracks[0].clip_slots[0].clip
    assert clip is not None
    notes_before = [(note.pitch, note.start_time) for note in clip.notes]

    call(song, "set_clip_color", {"track_index": 0, "clip_index": 0, "color_index": 5})

    assert [(note.pitch, note.start_time) for note in clip.notes] == notes_before
    after = _content_fingerprint(song)
    # Only the clip's colour changed; the track fingerprint above does not
    # include clip colour, so it must be byte-identical.
    assert after == before
    assert clip.color_index == 5
