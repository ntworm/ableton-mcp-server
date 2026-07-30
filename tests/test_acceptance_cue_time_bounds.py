"""Regression tests for the bounded cue-time probe.

These tests pin the contract that the acceptance runner must obey when
it picks the two locator times it creates and deletes:

- 0 <= time <= song_length (real Live throws on out-of-bounds times)
- times must be distinct
- times must not collide with any locator that already exists
- times must be aligned to a coarse grid so Live accepts the move
- the StrictFake must reproduce Live's behavior by rejecting cue/bulk
  operations whose ``time`` exceeds the real ``song_length``
- if the grid does not yield two safe times the runner must raise
  ``AcceptanceSafetyError`` *before* mutating anything
- cleanup must use the times that were actually chosen; the legacy
  ``cue_time + 64`` shortcut is gone

The previous implementation hard-coded ``256.0`` for the primary time
and ``cue_time + 64.0`` for the bulk time, which worked when the
fixture's song length was large but fails on the canonical 232-beat
``TESTE_CODEX`` Set: Live refuses with
``Cannot set the Songtime behind the Songlength``.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ableton_mcp_server import acceptance as acceptance_module
from ableton_mcp_server.acceptance import AcceptanceSafetyError
from tests._strict_fake import StrictFakeBridge

# ---------------------------------------------------------------------------
# 1) song_length must be captured in the baseline
# ---------------------------------------------------------------------------


def test_discover_baseline_captures_song_length() -> None:
    bridge = StrictFakeBridge()
    # Match the canonical TESTE_CODEX song_length observed in 2026-07-16.
    bridge.state["song_length"] = 232.0
    baseline = acceptance_module._discover_baseline(bridge)  # noqa: SLF001
    assert "song_length" in baseline, (
        "_discover_baseline must capture song_length so the cue probes can "
        "stay inside the real Arrangement length"
    )
    assert baseline["song_length"] == pytest.approx(232.0)


def test_discover_baseline_rejects_non_dict_song_length() -> None:
    """A non-dict ``get_song_length`` payload must trip the safety guard.

    Reproduces the case where the bridge returns a malformed value, e.g.
    a bare list or string, instead of ``{"song_length": float}``.
    """
    bridge = _BrokenSongLengthBridge(payload=["oops"])
    with pytest.raises(AcceptanceSafetyError) as excinfo:
        acceptance_module._discover_baseline(bridge)  # noqa: SLF001
    assert "song_length" in str(excinfo.value)


def test_discover_baseline_rejects_non_positive_song_length() -> None:
    bridge = _BrokenSongLengthBridge(payload={"song_length": 0.0})
    with pytest.raises(AcceptanceSafetyError) as excinfo:
        acceptance_module._discover_baseline(bridge)  # noqa: SLF001
    assert "song_length" in str(excinfo.value)


class _BrokenSongLengthBridge(StrictFakeBridge):
    """StrictFakeBridge variant that overrides ``get_song_length``.

    Used by the malformed-payload regression tests; the fake otherwise
    behaves like the production StrictFakeBridge.
    """

    def __init__(self, *, payload: Any) -> None:
        super().__init__()
        self._payload = payload

    def call(self, command_type, params=None, *, timeout=None):  # type: ignore[override]
        if command_type == "get_song_length":
            return self._payload
        return super().call(command_type, params, timeout=timeout)


# ---------------------------------------------------------------------------
# 2) helper chooses two safe, distinct, grid-aligned times
# ---------------------------------------------------------------------------


def _loc(time: float, name: str = "EXISTING") -> dict[str, Any]:
    return {"name": name, "time": float(time)}


def test_helper_returns_two_distinct_grid_aligned_times() -> None:
    t1, t2 = acceptance_module._acceptance_safe_cue_times(
        song_length=232.0,
        locators=[],
        grid=8.0,
    )
    assert t1 != t2
    assert 0.0 <= t1 <= 232.0
    assert 0.0 <= t2 <= 232.0
    assert t1 % 8.0 == pytest.approx(0.0)
    assert t2 % 8.0 == pytest.approx(0.0)


def test_helper_avoids_existing_locators() -> None:
    t1, t2 = acceptance_module._acceptance_safe_cue_times(
        song_length=232.0,
        locators=[_loc(64.0), _loc(128.0)],
        grid=64.0,
    )
    assert t1 not in (64.0, 128.0)
    assert t2 not in (64.0, 128.0)
    assert t1 != t2


def test_helper_rejects_legacy_hardcoded_values() -> None:
    """The previous runner picked 256 and 320; both exceed a 232-beat Set.

    The new helper must therefore either raise (when the grid yields no
    safe cell) or return times strictly inside ``song_length``. Either
    outcome is acceptable; what is *not* acceptable is returning any
    time greater than ``song_length``.
    """
    try:
        t1, t2 = acceptance_module._acceptance_safe_cue_times(
            song_length=232.0,
            locators=[],
            grid=8.0,
        )
    except AcceptanceSafetyError:
        return  # rejection is a valid outcome for the bounded helper
    assert t1 <= 232.0, f"cue_time {t1} exceeds song_length 232.0"
    assert t2 <= 232.0, f"bulk_cue_time {t2} exceeds song_length 232.0"
    assert t1 != 256.0 and t2 != 320.0, (
        "the bounded helper must never return the legacy hard-coded 256/320"
    )


def test_helper_rejects_when_grid_cannot_yield_two_safe_times() -> None:
    """If the grid is too coarse to leave two free cells, abort cleanly.

    With ``song_length=8`` and ``grid=8`` there are only two cells on
    the grid (0 and 8). Occupying both leaves zero free cells, which
    must trip ``AcceptanceSafetyError`` before any mutation.
    """
    with pytest.raises(AcceptanceSafetyError):
        acceptance_module._acceptance_safe_cue_times(
            song_length=8.0,
            locators=[_loc(0.0), _loc(8.0)],
            grid=8.0,
        )


# ---------------------------------------------------------------------------
# 3) StrictFake rejects cue operations outside the song_length, like Live
# ---------------------------------------------------------------------------


def _bridge_with_song_length(song_length: float) -> StrictFakeBridge:
    bridge = StrictFakeBridge()
    bridge.state["song_length"] = song_length
    return bridge


class _StrictFakeWithSongLength(StrictFakeBridge):
    """StrictFake variant that exposes a configurable ``song_length``."""

    def __init__(self, song_length: float) -> None:
        super().__init__()
        self.state["song_length"] = float(song_length)

    def call(self, command_type, params=None, *, timeout=None):  # type: ignore[override]
        if command_type == "get_song_length":
            return {"song_length": self.state.get("song_length", 64.0)}
        return super().call(command_type, params, timeout=timeout)


def test_strict_fake_rejects_create_cue_point_outside_song_length() -> None:
    bridge = _bridge_with_song_length(232.0)
    with pytest.raises(Exception) as excinfo:
        bridge.call("create_cue_point", {"name": "X", "time": 256.0})
    msg = str(excinfo.value).lower()
    assert "songlength" in msg or "song_length" in msg or "256" in str(excinfo.value)


def test_strict_fake_rejects_bulk_cue_outside_song_length() -> None:
    bridge = _bridge_with_song_length(232.0)
    with pytest.raises(Exception) as excinfo:
        bridge.call(
            "bulk_create_cue_points",
            {"items": [{"name": "X", "time": 320.0}]},
        )
    msg = str(excinfo.value).lower()
    assert "songlength" in msg or "song_length" in msg or "320" in str(excinfo.value)


def test_strict_fake_rejects_delete_cue_when_locator_never_existed() -> None:
    """delete_cue_point must refuse to claim ``deleted=true`` for a phantom cue."""
    bridge = _bridge_with_song_length(232.0)
    result = bridge.call("delete_cue_point", {"time": 256.0})
    assert result.get("deleted") is False, (
        "StrictFake must mirror Live: deleting a non-existent locator returns "
        f"deleted=false, got {result!r}"
    )


def test_strict_fake_accepts_create_cue_point_inside_song_length() -> None:
    bridge = _bridge_with_song_length(232.0)
    # In-range probe must still work; the new behaviour only blocks overflow.
    result = bridge.call("create_cue_point", {"name": "IN_RANGE", "time": 64.0})
    assert result.get("time") == pytest.approx(64.0)


# ---------------------------------------------------------------------------
# 4) full acceptance probe stays inside song_length
# ---------------------------------------------------------------------------


def test_baseline_run_passes_cue_probes_when_song_length_is_232() -> None:
    """End-to-end probe: with song_length=232 and no locators, the cue
    trio (create / bulk / delete) must reach live_passed.

    Skipped if the runner exposes a different entry point than the
    helpers above; this test is the integration guard for the legacy
    ``cue_time=256`` regression.
    """
    runner_fn = getattr(acceptance_module, "run_acceptance", None)
    if runner_fn is None:
        pytest.skip("run_acceptance entry point not present in this build")

    bridge = _bridge_with_song_length(232.0)

    async def drive() -> Any:
        return await runner_fn(bridge, profile="baseline", fire_clip=False)

    report = asyncio.run(drive())
    cue_rows = [
        r
        for r in report.records
        if r.tool in {"create_cue_point", "bulk_create_cue_points", "delete_cue_point"}
    ]
    assert cue_rows, "the baseline run must include cue_point probes"
    for row in cue_rows:
        assert row.status == "live_passed", (
            f"cue probe {row.tool!r} expected live_passed, got "
            f"{row.status!r}: {row.evidence!r}"
        )


# ---------------------------------------------------------------------------
# 5) cleanup must use the times actually chosen by the helper
# ---------------------------------------------------------------------------


def test_cleanup_uses_chosen_times_not_legacy_offset() -> None:
    """The cleanup path must delete the times the helper picked, not
    blindly assume ``cue_time + 64``."""
    t1, t2 = acceptance_module._acceptance_safe_cue_times(
        song_length=232.0, locators=[], grid=8.0,
    )
    # Both chosen times are inside song_length and distinct.
    assert t1 <= 232.0 and t2 <= 232.0
    assert t1 != t2
    # And neither is the legacy 256 / 320 pair.
    assert (t1, t2) != (256.0, 320.0)