"""v0.5.0 lifecycle_status read-only probe tests + save_set conditional save tests."""

from __future__ import annotations

import pytest

from AbletonMCPServer_RemoteScript import RemoteError, execute_command
from tests.remote_fakes import FakeApplication, FakeSong


def test_lifecycle_status_reports_save_availability() -> None:
    song = FakeSong(save=lambda: None)
    application = FakeApplication(quit=lambda: None)

    result = execute_command(song, application, "lifecycle_status", {})

    assert result["song_save_available"] is True
    assert result["app_quit_available"] is True
    assert "save" in result["gui_workflow"]
    assert "quit" in result["gui_workflow"]


def test_lifecycle_status_reports_missing_quit() -> None:
    song = FakeSong(save=lambda: None)
    application = FakeApplication()

    result = execute_command(song, application, "lifecycle_status", {})

    assert result["song_save_available"] is True
    assert result["app_quit_available"] is False


def test_lifecycle_status_returns_gui_workflow() -> None:
    result = execute_command(
        FakeSong(),
        FakeApplication(),
        "lifecycle_status",
        {},
    )

    gui_workflow = result["gui_workflow"]
    assert isinstance(gui_workflow["save"], list)
    assert all(isinstance(step, str) for step in gui_workflow["save"])
    assert isinstance(gui_workflow["quit"], list)
    assert all(isinstance(step, str) for step in gui_workflow["quit"])
    assert "notes" in gui_workflow


def test_save_set_uses_song_save_when_available() -> None:
    invoked = {"called": False}

    def fake_save() -> None:
        invoked["called"] = True
        return None

    song = FakeSong(save=fake_save)
    result = execute_command(song, FakeApplication(), "save_set", {})

    assert invoked["called"] is True
    assert result == {"saved": True, "api_available": True, "result": None}


def test_save_set_returns_gui_workflow_when_save_missing() -> None:
    # FakeSong(save=None) explicitly opts out of the v0.5.0 lifecycle seam,
    # so the handler should treat the song as if the live host hid ``save``.
    song = FakeSong(save=None)
    result = execute_command(song, FakeApplication(), "save_set", {})

    assert result["saved"] is False
    assert result["api_available"] is False
    assert "save" in result["gui_workflow"]


def test_save_set_raises_when_require_api_true_and_save_missing() -> None:
    song = FakeSong(save=None)

    with pytest.raises(RemoteError) as error:
        execute_command(
            song,
            FakeApplication(),
            "save_set",
            {"require_api": True},
        )

    assert error.value.code == "BAD_INPUT"
