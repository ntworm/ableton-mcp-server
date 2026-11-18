"""Regression tests for the audit findings fixed on 2026-11-18.

Every test pins one contract of the bridge:

- FINDING-04: a refused ``run_batch`` admission reaches the wire as an
  error envelope, not as a success frame that hides it in its result.
- FINDING-02: ``scaffold_extension`` refuses a project name that would
  leave ``output_directory``.
- FINDING-07: ``create_midi_track`` refuses an index that cannot exist
  before it creates anything.
- FINDING-08: ``live_fade`` resolves its target through the shared track
  lookup, so return and master tracks are addressable and an unknown
  index is an ``INVALID_PARAMS`` error.
"""

from __future__ import annotations

import json
import queue
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ValidationError

import ableton_mcp_server.server as server
from ableton_mcp_server import models
from AbletonMCPServer_RemoteScript import (
    QueuedRequest,
    RemoteError,
    RequestProcessor,
    execute_command,
)
from tests.remote_fakes import FakeApplication, FakeSong


def _answer(
    processor: RequestProcessor, response_queue: queue.Queue[dict[str, Any]]
) -> dict[str, Any]:
    """Advance the processor until the queued request is answered."""
    for _tick in range(12):
        processor.process_pending(max_requests=1)
        if not response_queue.empty():
            return response_queue.get_nowait()
    raise AssertionError("the processor did not answer the request")


def _occupied_slot_precondition() -> list[dict[str, Any]]:
    """Return a precondition that the Set cannot satisfy (slot 0 is taken)."""
    return [
        {
            "type": "slot_empty",
            "version": "v1",
            "params": {"track_index": 0, "clip_index": 0},
        }
    ]


def test_failed_batch_admission_reaches_the_wire_as_an_error() -> None:
    # FINDING-04: the admission error used to travel as the *result* of a
    # successful frame, so the client read a refused batch as a success.
    app = FakeApplication()
    processor = RequestProcessor(FakeSong(), app)
    response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
    processor.enqueue(
        QueuedRequest(
            "run_batch",
            {
                "commands": [{"type": "set_tempo", "params": {"tempo": 120}}],
                "preconditions": _occupied_slot_precondition(),
            },
            response_queue,
        )
    )

    response = _answer(processor, response_queue)

    assert response["status"] == "error"
    assert response["code"] == "PRECONDITION_FAILED"
    # The envelope is the response itself, not a payload of a success frame.
    assert "result" not in response
    # The refusal happened before the batch touched the Set.
    assert app.begin_count == 0

    # The success path is unchanged: an admitted batch is still reported as
    # "ok" with its result.
    ok_processor = RequestProcessor(FakeSong(), FakeApplication())
    ok_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
    ok_processor.enqueue(
        QueuedRequest(
            "run_batch",
            {"commands": [{"type": "set_tempo", "params": {"tempo": 120}}]},
            ok_queue,
        )
    )

    ok_response = _answer(ok_processor, ok_queue)

    assert ok_response["status"] == "ok"
    assert ok_response["result"]["completed"] == 1
    assert ok_response["result"]["aborted_at"] is None


@pytest.mark.parametrize(
    "name",
    [
        "../../evil",
        "..",
        "nested/child",
        "nested\\child",
        "C:\\evil",
        "C:evil",
        "evil..name",
    ],
)
def test_scaffold_extension_request_refuses_a_name_that_escapes(
    name: str, tmp_path: Any
) -> None:
    # FINDING-02: the scaffold is written to ``output_directory / name``,
    # so a name with a separator, a ".." or a drive would place the project
    # outside the requested directory.
    with pytest.raises(ValidationError):
        models.ScaffoldExtensionRequest(name=name, output_directory=str(tmp_path))


def test_scaffold_extension_writes_nothing_for_a_traversing_name(tmp_path: Any) -> None:
    # FINDING-02: the tool refuses through the request model and leaves the
    # filesystem alone; a plain name is still scaffolded as before.
    tarballs = {}
    for package in ("@ableton-extensions/sdk", "@ableton-extensions/cli"):
        tarball = tmp_path / ("%s.tgz" % package.replace("/", "-"))
        tarball.write_bytes(b"stub")
        tarballs[package] = tarball

    with patch(
        "ableton_mcp_server.tools_extension._read_extension_vendor_tarballs",
        return_value=tarballs,
    ):
        with pytest.raises(ValidationError):
            server.scaffold_extension(
                name="nested/child", output_directory=str(tmp_path)
            )
        assert not (tmp_path / "nested").exists()

        document = json.loads(
            server.scaffold_extension(name="MyEffect", output_directory=str(tmp_path))
        )

    assert document["status"] == "scaffolded"
    assert (tmp_path / "MyEffect" / "package.json").exists()


def test_create_midi_track_refuses_an_index_outside_the_track_range() -> None:
    # FINDING-07: an index beyond the track count used to create a track
    # the handler could not address, and the client heard LIVE_UNAVAILABLE.
    song = FakeSong()
    app = FakeApplication()

    with pytest.raises(RemoteError) as error:
        execute_command(song, app, "create_midi_track", {"index": 100})

    assert error.value.code == "INVALID_PARAMS"
    # The refusal happens before the mutation: no stray track was created.
    assert len(song.tracks) == 1

    # The success path is unchanged: -1 appends and ``len(tracks)`` is the
    # last position a new track can take.
    appended = execute_command(song, app, "create_midi_track", {"index": 1})

    assert appended["track_index"] == 1
    assert len(song.tracks) == 2


def test_create_midi_track_refuses_an_index_below_minus_one() -> None:
    song = FakeSong()
    app = FakeApplication()

    with pytest.raises(RemoteError) as error:
        execute_command(song, app, "create_midi_track", {"index": -2})

    assert error.value.code == "INVALID_PARAMS"
    assert len(song.tracks) == 1


def test_live_fade_resolves_a_return_track_through_the_track_helper() -> None:
    # FINDING-08: ``live_fade`` indexed the regular track list directly, so
    # the return tracks and the master track were not addressable.
    song = FakeSong()

    result = execute_command(
        song,
        FakeApplication(),
        "live_fade",
        {"track_index": 1, "target_percent": 50, "duration": 0, "steps": 4},
    )

    # Index 1 is the return track of this Set in the shared track order.
    assert result["track"] == "Return A"


def test_live_fade_refuses_an_unknown_track_index() -> None:
    # FINDING-08: an index that does not exist is an INVALID_PARAMS error,
    # not an IndexError the client hears as LIVE_UNAVAILABLE.
    with pytest.raises(RemoteError) as error:
        execute_command(
            FakeSong(),
            FakeApplication(),
            "live_fade",
            {"track_index": 99, "target_percent": 50, "duration": 0},
        )

    assert error.value.code == "INVALID_PARAMS"
