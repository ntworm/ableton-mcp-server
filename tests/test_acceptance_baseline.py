"""Unit tests for ``ableton_mcp_server.acceptance.baseline``.

Covers the ``BaselineSnapshot`` dataclass invariants + dict-style
compat shims (``__getitem__``, ``get``), and the four
``AcceptanceSafetyError`` branches of ``discover_baseline``.
"""

from __future__ import annotations

from typing import Any

import pytest

from ableton_mcp_server.acceptance.baseline import (
    BaselineSnapshot,
    _discover_baseline,
    discover_baseline,
)
from ableton_mcp_server.acceptance.safety import AcceptanceSafetyError


def _make_snapshot(**overrides: Any) -> BaselineSnapshot:
    base: dict[str, Any] = {
        "song_name": "TESTE_CODEX",
        "song_length": 232.0,
        "track_names": {0: "Bass", 1: "Lead"},
        "track_types": {0: "midi", 1: "audio"},
        "track_mutes": {0: False, 1: False},
        "track_solos": {0: False, 1: False},
        "track_arms": {0: True, 1: False},
        "track_volumes": {0: 0.85, 1: 0.75},
        "tempo": 120.0,
        "current_song_time": 4.0,
        "loop": True,
        "loop_start": 0.0,
        "loop_length": 8.0,
        "locators": [],
        "track_count": 2,
    }
    base.update(overrides)
    return BaselineSnapshot(**base)


class TestBaselineSnapshot:
    def test_frozen_dataclass(self) -> None:
        snap = _make_snapshot()
        with pytest.raises((AttributeError, Exception)):
            snap.tempo = 999.0  # type: ignore[misc]

    def test_attribute_access(self) -> None:
        snap = _make_snapshot(tempo=128.0)
        assert snap.tempo == 128.0
        assert snap.song_name == "TESTE_CODEX"
        assert snap.loop is True
        assert snap.track_names[0] == "Bass"

    def test_getitem_compat(self) -> None:
        snap = _make_snapshot(tempo=128.0)
        assert snap["tempo"] == 128.0
        assert snap["song_name"] == "TESTE_CODEX"
        assert snap["track_names"][0] == "Bass"

    def test_get_compat_with_default(self) -> None:
        snap = _make_snapshot()
        assert snap.get("tempo") == 120.0
        assert snap.get("nope", "fallback") == "fallback"
        assert snap.get("nope") is None

    def test_to_dict_round_trip(self) -> None:
        snap = _make_snapshot(tempo=128.0)
        d = snap.to_dict()
        assert d["tempo"] == 128.0
        assert d["song_name"] == "TESTE_CODEX"
        assert isinstance(d["track_names"], dict)
        assert d["track_names"][0] == "Bass"
        # Mutating the dict copy does not affect the frozen snapshot.
        d["track_names"][0] = "MUTATED"
        assert snap.track_names[0] == "Bass"

    def test_default_factories(self) -> None:
        snap = BaselineSnapshot(song_name="X", song_length=10.0)
        assert snap.track_names == {}
        assert snap.locators == []
        assert snap.tempo == 120.0


class TestDiscoverBaseline:
    """Drive ``discover_baseline`` with a minimal fake client."""

    def _make_client(
        self,
        *,
        track_state: dict[int, dict[str, Any]] | None = None,
        song_length: Any = 232.0,
        get_track_list_return: Any = None,
    ) -> Any:
        """Return an object exposing the protocol's ``call`` method only."""

        class _FakeClient:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict[str, Any]]] = []

            def call(self, command: str, params: dict[str, Any] | None = None) -> Any:
                self.calls.append((command, dict(params or {})))
                if command == "get_project_metadata":
                    return {"song_name": "TESTE_CODEX"}
                if command == "get_track_list":
                    return (
                        get_track_list_return
                        if get_track_list_return is not None
                        else [
                            {"index": 0, "name": "Bass", "type": "midi"},
                            {"index": 1, "name": "Lead", "type": "audio"},
                        ]
                    )
                if command == "get_track_state":
                    idx = params["track_index"]
                    default = {
                        "mute": False,
                        "solo": False,
                        "arm": False,
                        "volume": 0.85,
                    }
                    return (track_state or {}).get(idx, default)
                if command == "get_session_info":
                    return {"tempo": 120.0, "current_song_time": 4.0}
                if command == "get_loop_settings":
                    return {"loop": True, "loop_start": 0.0, "loop_length": 8.0}
                if command == "get_locators":
                    return []
                if command == "get_song_length":
                    if isinstance(song_length, Exception):
                        raise song_length
                    return {"song_length": song_length}
                raise AssertionError(f"unexpected command: {command}")

        return _FakeClient()

    def test_happy_path(self) -> None:
        client = self._make_client()
        snap = discover_baseline(client)
        assert isinstance(snap, BaselineSnapshot)
        assert snap.song_name == "TESTE_CODEX"
        assert snap.tempo == 120.0
        assert snap.song_length == 232.0
        assert snap.track_names == {0: "Bass", 1: "Lead"}
        assert snap.track_types == {0: "midi", 1: "audio"}
        assert snap.track_mutes == {0: False, 1: False}
        assert snap.track_volumes == {0: 0.85, 1: 0.85}
        assert snap.track_count == 2
        # Dict-style compat works.
        assert snap["tempo"] == 120.0
        assert snap.get("nope", 42) == 42

    def test_rejects_non_dict_get_track_state(self) -> None:
        client = self._make_client()
        # Override get_track_state to return non-dict.
        original_call = client.call

        def bad_call(cmd: str, params: dict[str, Any] | None = None) -> Any:
            if cmd == "get_track_state":
                return "not-a-dict"
            return original_call(cmd, params)

        client.call = bad_call  # type: ignore[method-assign]
        with pytest.raises(AcceptanceSafetyError, match="returned non-dict"):
            discover_baseline(client)

    def test_rejects_missing_mute(self) -> None:
        # Provide track_state without ``mute``.
        client = self._make_client(
            track_state={0: {"solo": False, "arm": False, "volume": 0.85}},
        )
        with pytest.raises(AcceptanceSafetyError, match="missing mute/solo/arm"):
            discover_baseline(client)

    def test_rejects_missing_volume(self) -> None:
        client = self._make_client(
            track_state={0: {"mute": False, "solo": False, "arm": False}},
        )
        with pytest.raises(AcceptanceSafetyError, match="missing volume"):
            discover_baseline(client)

    def test_rejects_non_positive_song_length(self) -> None:
        client = self._make_client(song_length=0.0)
        with pytest.raises(AcceptanceSafetyError, match="must be positive"):
            discover_baseline(client)

    def test_rejects_none_song_length(self) -> None:
        client = self._make_client(song_length=None)
        with pytest.raises(AcceptanceSafetyError, match="positive number"):
            discover_baseline(client)

    def test_rejects_non_dict_song_length_payload(self) -> None:
        client = self._make_client()
        original_call = client.call

        def bad_call(cmd: str, params: dict[str, Any] | None = None) -> Any:
            if cmd == "get_song_length":
                return 232  # not a dict
            return original_call(cmd, params)

        client.call = bad_call  # type: ignore[method-assign]
        with pytest.raises(AcceptanceSafetyError, match="non-dict"):
            discover_baseline(client)

    def test_rejects_bool_song_length(self) -> None:
        client = self._make_client(song_length=True)
        with pytest.raises(AcceptanceSafetyError, match="positive number"):
            discover_baseline(client)

    def test_back_compat_alias(self) -> None:
        """``_discover_baseline`` is the legacy underscore alias."""
        assert _discover_baseline is discover_baseline


class TestDiscoverBaselineSongLengthTypes:
    """Cover the song_length type-validation branches."""

    def _make_client_with_song_length(self, song_length: Any) -> Any:
        class _Client:
            def call(self, cmd: str, params: dict[str, Any] | None = None) -> Any:
                if cmd == "get_project_metadata":
                    return {"song_name": "X"}
                if cmd == "get_track_list":
                    return [{"index": 0, "name": "T", "type": "midi"}]
                if cmd == "get_track_state":
                    return {"mute": False, "solo": False, "arm": False, "volume": 0.85}
                if cmd == "get_session_info":
                    return {"tempo": 120.0, "current_song_time": 0.0}
                if cmd == "get_loop_settings":
                    return {"loop": False, "loop_start": 0.0, "loop_length": 4.0}
                if cmd == "get_locators":
                    return []
                if cmd == "get_song_length":
                    return {"song_length": song_length}
                raise AssertionError(cmd)

        return _Client()

    def test_string_song_length_rejected(self) -> None:
        client = self._make_client_with_song_length("232.0")
        with pytest.raises(AcceptanceSafetyError):
            discover_baseline(client)

    def test_negative_song_length_rejected(self) -> None:
        client = self._make_client_with_song_length(-1.0)
        with pytest.raises(AcceptanceSafetyError):
            discover_baseline(client)
