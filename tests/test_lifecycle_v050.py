"""v0.5.0 lifecycle_status read-only probe tests + save_set conditional save tests."""

from __future__ import annotations

import pytest

from AbletonMCPServer_RemoteScript import (
    GUI_LIFECYCLE_WORKFLOW,
    RemoteError,
    execute_command,
    quit_ableton_steps,
)
from tests.remote_fakes import FakeApplication, FakeControlSurface, FakeSong


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


def test_quit_ableton_saves_first_then_schedules_quit() -> None:
    called: list[int] = []
    song = FakeSong(save=lambda: (called.append(1), None)[1])
    application = FakeApplication(quit=lambda: (called.append(2), None)[1])
    control_surface = FakeControlSurface()

    result = quit_ableton_steps(
        song,
        application,
        control_surface,
        {"save": True, "quit_delay_ticks": 1},
    )

    assert result == {
        "quit_requested": True,
        "saved_first": True,
        "api_available": True,
        "scheduled": True,
    }
    assert called == [1, 2]
    assert len(control_surface.scheduled) == 1
    assert control_surface.scheduled[0][0] == 1


def test_quit_ableton_refuses_when_save_unavailable_and_force_false() -> None:
    result = quit_ableton_steps(
        FakeSong(save=None),
        FakeApplication(quit=lambda: None),
        FakeControlSurface(),
        {},
    )

    assert result["quit_requested"] is False
    assert result["saved_first"] is False
    assert result["gui_workflow"] is GUI_LIFECYCLE_WORKFLOW


def test_quit_ableton_quits_when_save_unavailable_and_force_true() -> None:
    called: list[int] = []
    control_surface = FakeControlSurface()

    result = quit_ableton_steps(
        FakeSong(save=None),
        FakeApplication(quit=lambda: (called.append(2), None)[1]),
        control_surface,
        {"force_without_save": True},
    )

    assert result["quit_requested"] is True
    assert result["saved_first"] is False
    assert called == [2]
    assert len(control_surface.scheduled) == 1


def test_quit_ableton_refuses_when_quit_unavailable() -> None:
    result = quit_ableton_steps(
        FakeSong(save=lambda: None),
        FakeApplication(),
        FakeControlSurface(),
        {},
    )

    assert result["api_available"] is False
    assert result["quit_requested"] is False
    assert isinstance(result["gui_workflow"], list)
    assert all(isinstance(step, str) for step in result["gui_workflow"])
