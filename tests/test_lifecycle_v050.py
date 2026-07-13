"""v0.5.0 lifecycle_status read-only probe tests."""

from __future__ import annotations

from AbletonMCPServer_RemoteScript import execute_command
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
