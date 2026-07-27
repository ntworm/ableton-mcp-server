"""RED->GREEN regression for the ``live_fade`` target_percent probes.

The acceptance runner's ``live_fade`` probe issues::

    live_fade(track_index=N, target_percent=50.0, duration=0.0, steps=1)

then reads ``get_track_state(track_index=N).volume`` and asserts
the value landed close to ``0.5``.

In the real Ableton bridge the mixer volume parameter sits at
``LIVE_FADE_UNITY_VALUE = 0.8500000238418579`` -- Live's user-facing
fader percentage ``100%`` maps to that raw value, not to ``1.0``.
The Remote Script's ``live_fade`` handler therefore computes
``target = (percent / 100.0) * LIVE_FADE_UNITY_VALUE``. So a
``target_percent=50`` request must land at ``0.425``, not ``0.5``.

The probe today asserts ``abs(volume - 0.5) <= 0.05``, which is
wrong by ``0.075``. The acceptance run against TESTE_CODEX
recorded ``status=failed`` for ``live_fade`` with evidence
``"live_fade immediate target mismatch"`` because the readback
returned ``0.425`` and the probe demanded ``0.5``.

The GREEN fix must compare against
``LIVE_FADE_UNITY_VALUE * (target_percent / 100.0)`` instead of
the raw ``0.5`` / ``0.8`` magic numbers. We must not introduce a
new magic number like ``0.425`` -- the assertion should reference
the canonical UNITY constant so future drift between the runner
and the Remote Script is detectable.

Lives next to ``test_acceptance_audit_p0p1.py`` so the auditor
can re-run the audit set in isolation.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from ableton_mcp_server import acceptance as acceptance_module
from ableton_mcp_server.acceptance import run_live_acceptance

from ._offline_probe_fixture import fast_offline_probes
from ._strict_fake import StrictFakeBridge

# The canonical UNITY factor lives in
# ``ableton_mcp_server.acceptance.LIVE_FADE_UNITY_VALUE`` (the
# runner side). The Remote Script keeps a matching constant at
# ``AbletonMCPServer_RemoteScript/__init__.py``. The drift
# guard below compares the runner's value directly to the
# Remote Script's value; we do NOT introduce a parallel local
# constant here. If the two sides ever drift, the guard fails
# before any probe runs.
REMOTE_SCRIPT_UNITY_HINT = 0.8500000238418579


def _read_remote_script_unity_value() -> float | None:
    """Return the ``LIVE_FADE_UNITY_VALUE`` constant declared in
    the Remote Script, or ``None`` if the file is unreadable.

    Used by ``test_acceptance_and_remote_script_share_unity_value``
    to assert the runner and the Remote Script agree on the
    canonical unity factor.
    """
    repo_root = Path(__file__).resolve().parents[1]
    remote_script = repo_root / "AbletonMCPServer_RemoteScript" / "__init__.py"
    if not remote_script.is_file():
        return None
    for line in remote_script.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("LIVE_FADE_UNITY_VALUE") and "=" in stripped:
            value_part = stripped.split("=", 1)[1].split("#", 1)[0].strip()
            try:
                return float(value_part)
            except ValueError:
                return None
    return None


@pytest.fixture(autouse=True)
def _inject_fast_offline_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same injector used by the audit tests -- keeps the runner fast."""
    monkeypatch.setattr(acceptance_module, "run_offline_probes", fast_offline_probes)


class _LiveFadeUnityBridge(StrictFakeBridge):
    """Backward-compatible alias kept for the Bug 2 regression
    tests. The shared ``StrictFakeBridge`` now applies the
    ``LIVE_FADE_UNITY_VALUE`` factor on ``live_fade`` (the same
    way the real Remote Script does), so any subclass or
    direct use of the fake models Live accurately. This alias
    remains in case future Bug 2 regressions need extra
    fake-side knobs (e.g. simulating
    ``allow_over_unity=True``); today it is identical to its
    base.
    """

    pass


def test_acceptance_and_remote_script_share_unity_value() -> None:
    """Drift guard: the runner's reference value and the
    Remote Script's constant must agree exactly. If either
    side bumps the constant, the other side must move in
    lock-step or every live_fade probe will start producing
    false-positive readback failures.

    The comparison anchors on ``acceptance_module.LIVE_FADE_UNITY_VALUE``
    (the runner side) -- not on a parallel local constant --
    so this guard fails immediately if anyone touches one
    side without the other.
    """
    remote_value = _read_remote_script_unity_value()
    assert remote_value is not None, (
        "could not locate LIVE_FADE_UNITY_VALUE in the Remote Script"
    )
    assert remote_value == acceptance_module.LIVE_FADE_UNITY_VALUE, (
        f"runner LIVE_FADE_UNITY_VALUE="
        f"{acceptance_module.LIVE_FADE_UNITY_VALUE!r} "
        f"differs from Remote Script LIVE_FADE_UNITY_VALUE="
        f"{remote_value!r}; update both sides together"
    )
    # Optional sanity check: the canonical numeric value
    # itself has not been quietly re-bumped. If the runner or
    # the Remote Script ever drift away from the expected
    # 0.85 contract, this assertion fails loud.
    assert acceptance_module.LIVE_FADE_UNITY_VALUE == REMOTE_SCRIPT_UNITY_HINT, (
        "canonical UNITY factor drifted from 0.85; verify the "
        "Remote Script constant AND the runner's "
        "LIVE_FADE_UNITY_VALUE before relaxing this guard"
    )


def _run_live_fade_bridge() -> Any:
    """Run ``run_live_acceptance`` on a unity-aware fake and
    return the per-tool ``certification["tools"]`` mapping so
    individual tests can assert on per-tool status.

    The runner's ``_record_call`` swallows AssertionError
    internally and records ``failed`` instead, so the only
    way to observe the bug is to read the returned
    ``certification["tools"]`` dict for ``live_fade``.
    """
    bridge = _LiveFadeUnityBridge()
    bridge.fail_tool = None

    async def drive() -> Any:
        return await run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=4,
            audio_track_index=2,
            audio_clip_index=0,
            fire_clip=True,
        )

    return asyncio.run(drive())


def _live_fade_row(result: dict[str, Any]) -> dict[str, Any] | None:
    """Pull the ``live_fade`` row out of the runner's returned
    certification. The runner formats ``tools`` as a list of
    ``{tool, status, evidence}`` dicts rather than a mapping,
    so iterate to find the right entry.
    """
    tools = result["certification"]["tools"]
    for entry in tools:
        if entry.get("tool") == "live_fade":
            return entry
    return None


def test_live_fade_probe_at_50_percent_lands_at_unity_times_half() -> None:
    """RED->GREEN for the immediate ``target_percent=50`` probe.

    With the fake applying the UNITY factor (the same way the
    real Remote Script does), the runner's
    ``abs(post_immediate.volume - 0.5) > 0.05`` assertion must
    trip and ``_record_call`` records ``live_fade`` as
    ``failed`` with evidence ``"live_fade immediate target
    mismatch"``. After the GREEN fix the assertion compares
    against ``UNITY * 0.5`` and the probe records
    ``live_passed``.
    """
    result = _run_live_fade_bridge()
    row = _live_fade_row(result)
    assert row is not None, "live_fade row missing from certification"
    assert row["status"] == "live_passed", (
        f"live_fade probe failed because the runner hardcodes "
        f"target=0.5 instead of LIVE_FADE_UNITY_VALUE * 0.5; "
        f"evidence: {row.get('evidence')!r}"
    )


def test_live_fade_probe_at_80_percent_lands_at_unity_times_eight_tenths() -> None:
    """RED->GREEN for the timed ``target_percent=80`` probe.

    Same shape as the 50% probe: ``target_percent=80`` should
    land at ``LIVE_FADE_UNITY_VALUE * 0.8 = 0.68``, which is
    ``0.12`` away from the runner's hardcoded ``0.8``. Before
    the GREEN fix the runner asserts
    ``abs(post_fade.volume - 0.8) > 0.05`` and ``_record_call``
    records ``live_fade`` as ``failed``; after the fix the
    assertion compares against ``UNITY * 0.8`` and the probe
    records ``live_passed``.
    """
    result = _run_live_fade_bridge()
    row = _live_fade_row(result)
    assert row is not None, "live_fade row missing from certification"
    assert row["status"] == "live_passed", (
        f"live_fade probe failed because the runner hardcodes "
        f"target=0.8 instead of LIVE_FADE_UNITY_VALUE * 0.8; "
        f"evidence: {row.get('evidence')!r}"
    )


def test_live_fade_probe_does_not_hardcode_unity_factor_value() -> None:
    """Drift guard for the GREEN fix itself: the runner must
    not embed ``0.425`` (or any equivalent literal) directly
    in the live_fade probe assertion. The only acceptable
    references to the unity factor are:

    1. The ``LIVE_FADE_UNITY_VALUE`` constant declared at
       module top (or imported from a shared module).
    2. Arithmetic derived from it (``UNITY * (percent/100.0)``).

    This test scans the runner source for forbidden literals:
    the exact ``0.425`` value, and ``0.68`` (the 80% product).
    If either appears outside of an explanatory comment, the
    GREEN fix has introduced a magic number instead of using
    the named constant.
    """
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    # Post-refactor (2026-07-27): ``acceptance.py`` is now a package at
    # ``ableton_mcp_server/acceptance/``. The runner orchestrator is
    # ``runner.py``; the ``LIVE_FADE_UNITY_VALUE`` constant lives in
    # ``helpers.py``. Concatenate both for the magic-number scan.
    acceptance_pkg = repo_root / "ableton_mcp_server" / "acceptance"
    sources = [
        acceptance_pkg / "runner.py",
        acceptance_pkg / "helpers.py",
    ]
    acceptance_source = "\n".join(
        p.read_text(encoding="utf-8") for p in sources if p.exists()
    )

    forbidden_magic_numbers = {
        "0.425": "UNITY_TIMES_HALF_HARDCODED",
        "0.68": "UNITY_TIMES_EIGHT_TENTHS_HARDCODED",
    }
    # Strip line-comments and docstrings so explanatory prose
    # is not flagged.
    code_lines: list[str] = []
    for line in acceptance_source.splitlines():
        stripped = line.split("#", 1)[0]
        if stripped.strip():
            code_lines.append(stripped)
    code_only = "\n".join(code_lines)

    hits = {
        label: literal
        for literal, label in forbidden_magic_numbers.items()
        if literal in code_only
    }
    assert not hits, (
        "runner hardcoded live_fade unity-derived literals instead "
        f"of using LIVE_FADE_UNITY_VALUE: {hits}"
    )