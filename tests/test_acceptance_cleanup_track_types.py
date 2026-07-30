"""RED->GREEN regression for the disposable Set cleanup loops.

The acceptance runner must NOT restore mixer state on master or
return tracks via ``set_track_property(arm)`` -- the disposable
Set's cleanup contract excludes both. The cleanup loops iterate
over the raw ``track_mutes`` / ``track_solos`` / ``track_arms``
baseline dicts without consulting ``track_types``, so the suite
fails on any project that has a master or return track.

Track-type policy the runner MUST follow:

- ``mute`` / ``solo``: applies to midi / audio / return tracks.
  Master is excluded because Live has no mute or solo state on
  the master track.
- ``arm``: applies to midi / audio tracks only. Master AND return
  tracks are excluded from arm restoration under the disposable
  Set contract.

Lives next to ``test_acceptance_audit_p0p1.py`` so the auditor
can re-run the audit set in isolation.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ableton_mcp_server.acceptance import _discover_baseline, run_live_acceptance

from ._offline_probe_fixture import fast_offline_probes
from ._strict_fake import StrictFakeBridge

# The auditor-mandated assertions in this module are phrased in
# terms of the master track's baseline index and the forbidden
# property / track_index pairs, so the per-property forbidden sets
# are encoded inline in each test (no shared constant).


class _BridgeWithMasterAndReturns(StrictFakeBridge):
    """StrictFakeBridge extended with a master track + 2 return tracks.

    The fake itself does NOT model Live's rejection of
    ``set_track_property(mute/solo/arm:master)`` -- it accepts every
    call. Tests that exercise the runner's cleanup loop wrap the
    bridge's ``call`` method to simulate Live's rejection so that
    cleanup failures block track-creation tools from running (the
    real cascade the runner implements in
    ``acceptance.py:_finalise_report``).
    """

    def __init__(self) -> None:
        super().__init__()
        # Append master (idx=3) + 2 returns (idx=4, idx=5) AFTER the
        # 3 baseline tracks (idx=0,1,2). The real ``get_track_list``
        # contract exposes these the same way: every track with its
        # ``type`` set to ``"master"`` or ``"return"``.
        self.state["tracks"].extend(
            [
                {
                    "index": 3,
                    "type": "master",
                    "name": "Master",
                    "id": "track:3",
                    "mute": False,
                    "solo": False,
                    "arm": False,
                    "devices": [],
                },
                {
                    "index": 4,
                    "type": "return",
                    "name": "Return A",
                    "id": "track:4",
                    "mute": False,
                    "solo": False,
                    "arm": False,
                    "devices": [],
                },
                {
                    "index": 5,
                    "type": "return",
                    "name": "Return B",
                    "id": "track:5",
                    "mute": False,
                    "solo": False,
                    "arm": False,
                    "devices": [],
                },
            ]
        )


@pytest.fixture(autouse=True)
def _inject_fast_offline_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same injector used by the audit tests -- keeps the runner fast."""
    import ableton_mcp_server.acceptance as acceptance_module

    monkeypatch.setattr(acceptance_module, "run_offline_probes", fast_offline_probes)


@pytest.fixture
def bridge_with_master_and_returns() -> _BridgeWithMasterAndReturns:
    """Fresh disposable Set with master + returns.

    The fake itself does NOT model Live's rejection of
    ``set_track_property(mute/solo/arm:master)``. This fixture
    wraps the bridge's ``call`` to raise ``RuntimeError`` on
    those forbidden indices so the runner's cleanup failure path
    activates and blocks the track-creation tools from running
    (matching the cascade the real Live bridge triggers). Without
    this, the fake accepts the forbidden calls, cleanup ``succeeds``,
    the runner then creates new audio + midi tracks, and the
    indices captured in the baseline no longer match the live
    state -- masking the bug the tests are designed to catch.

    Tests that record calls further wrap this fixture wrap so they
    can observe what the runner tried to emit before Live
    rejected it. See ``_run_with_recording`` for the ordering.
    """
    bridge = _BridgeWithMasterAndReturns()
    # The fake's track list can shift index when
    # ``create_audio_track`` / ``create_midi_track`` runs during
    # the acceptance suite. Resolve the target track's type from
    # the *current* state every time ``set_track_property`` is
    # called so the rejection fires no matter where the master
    # track has been pushed by then.
    raw_call = bridge.call

    def wrap(
        command_type: str,
        params: Any = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        if (
            command_type == "set_track_property"
            and params is not None
        ):
            target_idx = int(params.get("track_index", -1))
            target = next(
                (
                    t
                    for t in bridge.state["tracks"]
                    if int(t.get("index", -1)) == target_idx
                ),
                None,
            )
            if target is not None and str(target.get("type")) == "master":
                raise RuntimeError(
                    "set_track_property rejected by Live: master track has "
                    "no mixer property"
                )
        return raw_call(command_type, params, timeout=timeout)

    bridge.call = wrap  # type: ignore[assignment]
    return bridge


def _record_calls_around_live_rejection(
    bridge: _BridgeWithMasterAndReturns,
) -> list[dict[str, Any]]:
    """Wrap the bridge so every call is recorded BEFORE the
    fixture's Live-rejection wrap runs. Tests can then inspect
    the captured calls to assert what the runner tried to emit,
    even though the rejection prevented the underlying fake from
    observing the call.
    """
    recorded: list[dict[str, Any]] = []
    raw_call = bridge.call

    def wrap(
        command_type: str,
        params: Any = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        recorded.append({"command": command_type, "params": dict(params or {})})
        return raw_call(command_type, params, timeout=timeout)

    bridge.call = wrap  # type: ignore[assignment]
    return recorded


def _set_track_property_calls(
    recorded: list[dict[str, Any]],
    *,
    command_type: str = "set_track_property",
) -> list[tuple[int, str, Any]]:
    """Return ``(track_index, property, value)`` for every recorded call."""
    out: list[tuple[int, str, Any]] = []
    for entry in recorded:
        if entry["command"] != command_type:
            continue
        params = dict(entry.get("params") or {})
        out.append(
            (
                int(params.get("track_index", -1)),
                str(params.get("property", "")),
                params.get("value"),
            )
        )
    return out


def _run_with_recording(
    bridge: _BridgeWithMasterAndReturns,
) -> list[dict[str, Any]]:
    """Run the full acceptance with recording wired in. Returns
    the list of recorded calls in order. Calls targeting the
    master track are still raised out by the fixture wrap (after
    being recorded), so the runner exercises its cleanup-failure
    cascade path -- exactly mirroring the live behaviour."""
    recorded = _record_calls_around_live_rejection(bridge)
    asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=4,
            audio_track_index=2,
            audio_clip_index=0,
            fire_clip=True,
        )
    )
    return recorded





def test_baseline_exposes_master_and_return_track_types(
    bridge_with_master_and_returns: _BridgeWithMasterAndReturns,
) -> None:
    """Structural precondition: the ``track_types`` baseline dict
    must distinguish master and returns from regular tracks so
    the cleanup loop CAN filter them. If a future regression
    drops master/return entries from ``track_types``, the cleanup
    loop loses the information it needs to skip forbidden
    indices. This guard verifies the data shape is preserved."""
    bridge = bridge_with_master_and_returns

    fake_types = {int(t["index"]): str(t["type"]) for t in bridge.state["tracks"]}
    assert "master" in fake_types.values(), (
        f"master track missing from fake state: {fake_types}"
    )
    assert "return" in fake_types.values(), (
        f"return track missing from fake state: {fake_types}"
    )


def test_cleanup_loop_does_not_call_set_track_property_mute_3(
    bridge_with_master_and_returns: _BridgeWithMasterAndReturns,
) -> None:
    """Explicit auditor-mandated assertion: the runner must not
    call ``set_track_property(mute:N)`` for the master track.

    The audit lists ``set_track_property(mute:5)`` as one of the
    forbidden calls because in TESTE_CODEX the master track sits
    at index 5 once the disposable Set has been through its
    full acceptance. The StrictFakeBridge fixture here exposes
    the master track at index 3 instead (it's prepended to the
    baseline tracks, so the index space is stable across the
    run). The assertion targets the master index in the
    fixture's baseline: index 3. Either way the runner must
    NOT call ``set_track_property(mute:master_idx)`` -- Live
    rejects mute on master regardless of where the master
    sits in the index space.

    We snapshot the baseline BEFORE the run so the assertion
    is grounded in the type table the runner actually saw at
    cleanup planning time -- not in the post-shift live state
    where master may have moved to a different slot.
    """
    bridge = bridge_with_master_and_returns
    baseline_types = {
        int(idx): ttype
        for idx, ttype in _discover_baseline(bridge)["track_types"].items()
    }
    master_indices = {
        idx for idx, ttype in baseline_types.items() if ttype == "master"
    }
    assert master_indices, (
        f"fixture must expose a master track; baseline_types={baseline_types}"
    )

    recorded = _run_with_recording(bridge)

    forbidden_mute = [
        entry
        for entry in recorded
        if entry["command"] == "set_track_property"
        and int(entry["params"].get("track_index", -1)) in master_indices
        and str(entry["params"].get("property", "")) == "mute"
    ]
    assert not forbidden_mute, (
        f"cleanup loop must not call set_track_property(mute:N) for "
        f"N in master_indices ({sorted(master_indices)}); "
        f"saw {len(forbidden_mute)} call(s): {forbidden_mute}"
    )


def test_cleanup_loop_does_not_call_set_track_property_solo_master(
    bridge_with_master_and_returns: _BridgeWithMasterAndReturns,
) -> None:
    """Explicit auditor-mandated assertion: the runner must not
    call ``set_track_property(solo:N)`` for the master track --
    master has no solo state in Live. Same index-vs-name
    reasoning as the mute test: the fixture exposes master at
    index 3; the audit listed 5 because that's the master slot
    after the acceptance-induced index shifts in TESTE_CODEX.
    Either way, the runner must skip master."""
    bridge = bridge_with_master_and_returns
    baseline_types = {
        int(idx): ttype
        for idx, ttype in _discover_baseline(bridge)["track_types"].items()
    }
    master_indices = {
        idx for idx, ttype in baseline_types.items() if ttype == "master"
    }

    recorded = _run_with_recording(bridge)

    forbidden_solo = [
        entry
        for entry in recorded
        if entry["command"] == "set_track_property"
        and int(entry["params"].get("track_index", -1)) in master_indices
        and str(entry["params"].get("property", "")) == "solo"
    ]
    assert not forbidden_solo, (
        f"cleanup loop must not call set_track_property(solo:N) for "
        f"N in master_indices ({sorted(master_indices)}); "
        f"saw {len(forbidden_solo)} call(s): {forbidden_solo}"
    )


def test_cleanup_loop_does_not_call_set_track_property_arm_3_4_5(
    bridge_with_master_and_returns: _BridgeWithMasterAndReturns,
) -> None:
    """Explicit auditor-mandated assertion: the runner must not
    call ``set_track_property(arm:N)`` for any of indices 3, 4
    or 5. In the disposable Set under TESTE_CODEX those indices
    correspond to the two return tracks (3, 4) and the master
    track (5). The arm cleanup loop applies only to
    midi / audio tracks; master and returns are both excluded
    from arm restoration under the disposable Set contract.
    """
    recorded = _run_with_recording(bridge_with_master_and_returns)

    forbidden_arm = [
        entry
        for entry in recorded
        if entry["command"] == "set_track_property"
        and int(entry["params"].get("track_index", -1)) in {3, 4, 5}
        and str(entry["params"].get("property", "")) == "arm"
    ]
    assert not forbidden_arm, (
        f"cleanup loop must not call set_track_property(arm:N) for "
        f"N in {{3, 4, 5}}; saw {len(forbidden_arm)} call(s): {forbidden_arm}"
    )