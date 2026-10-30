"""The acceptance preflight proves a fresh Set through its undo history.

Live 12.4.25b1 has no ``Song.is_dirty`` in its Python API, so
``get_project_metadata`` answers ``is_dirty: None`` and only ``can_undo``
can tell that nothing was edited since the Set was opened.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ableton_mcp_server.acceptance import AcceptanceSafetyError, run_live_acceptance
from ableton_mcp_server.acceptance.safety import require_fresh_set

from ._offline_probe_fixture import fast_offline_probes
from ._strict_fake import _READ_ONLY_TCP_COMMANDS, StrictFakeBridge

_LIVE_12_4_METADATA = {
    "song_name": "TESTE_CODEX",
    "file_path": None,
    "is_dirty": None,
    "can_undo": False,
}
_MANUAL_SAVE = {
    "saved": False,
    "api_available": False,
    "gui_workflow": {"save": ["Open the File menu in the Live window."]},
}


def _run(bridge: StrictFakeBridge) -> dict[str, Any]:
    return asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=2,
            audio_clip_index=0,
            fire_clip=True,
            offline_probes=fast_offline_probes,
        )
    )


@pytest.mark.parametrize(
    "metadata",
    [_LIVE_12_4_METADATA, {"song_name": "TESTE_CODEX", "is_dirty": False, "can_undo": False}],
)
def test_empty_undo_history_is_a_fresh_set(metadata: dict[str, Any]) -> None:
    require_fresh_set(metadata)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"can_undo": True}, r"undo history \(can_undo=True\)"),
        ({"can_undo": None}, r"undo history \(can_undo=None\)"),
        ({"can_undo": "false"}, r"undo history \(can_undo='false'\)"),
        ({"is_dirty": True}, r"unsaved changes \(is_dirty=True\)"),
    ],
)
def test_preflight_refuses_an_unproven_fresh_set(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(AcceptanceSafetyError, match=message):
        require_fresh_set({**_LIVE_12_4_METADATA, **changes})


def test_edited_set_is_refused_before_any_mutation() -> None:
    bridge = StrictFakeBridge()
    bridge.state["is_dirty"] = None
    bridge.state["can_undo"] = True
    with pytest.raises(AcceptanceSafetyError, match="Reopen the saved Set"):
        _run(bridge)
    sent = [command for command, _ in bridge.tcp_calls]
    assert "get_project_metadata" in sent
    assert set(sent) <= _READ_ONLY_TCP_COMMANDS
    assert [method for method, _ in bridge.ws_calls if method != "get_warp_state"] == []


def test_fresh_set_without_dirty_flag_still_certifies() -> None:
    bridge = StrictFakeBridge()
    bridge.state["is_dirty"] = None
    bridge.save_set_response = dict(_MANUAL_SAVE)
    cert = _run(bridge)["certification"]
    rows = {row["tool"]: row for row in cert["tools"]}
    assert rows["get_project_metadata"]["status"] == "live_passed"
    assert rows["save_set"]["status"] == "manual_required"
    assert [row for row in cert["tools"] if row["status"] == "failed"] == []
    assert cert["release_ready"] is True
