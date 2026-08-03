"""Restore engine — declarative registration + ordered execution.

The legacy monolithic ``run_live_acceptance`` accumulated three near-
identical loops for mute/solo/arm plus independent loops for tempo,
loop, song time, cue, warp, volume, and parameter restoration. Each
new mutation tool added another inline ``_restore_call`` / ``_restore_ws``
block. This module collapses that pattern into a single registry.

Probe modules call ``engine.register(label=..., tool=..., restore=...,
verify=...)`` once for each field they mutate; ``run_all()`` executes
them in registration order, captures failures as ``(label, reason)``
tuples, and returns them to the caller (the runner) which is
responsible for downgrading affected ``live_passed`` rows on the
certification report.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .safety import AcceptanceClient


@dataclass(frozen=True)
class RestoreOp:
    """One restore operation.

    ``restore`` may be sync or async; ``verify`` matches that shape so
    the engine can run both interleaved. ``tool`` is the catalogued
    tool name whose certification row should be downgraded if this
    restore fails (see ``run_live_acceptance`` cleanup policy).
    """

    label: str
    tool: str
    restore: Callable[[], Any]
    verify: Callable[[Any], Any]


RestoreFn = Callable[[], Any | Awaitable[Any]]
VerifyFn = Callable[[Any], Any | Awaitable[None]]


class RestoreEngine:
    """Registry + runner for cleanup restores."""

    def __init__(self, client: AcceptanceClient, artifacts: dict[str, Any]) -> None:
        self._client = client
        self._artifacts = artifacts
        self._ops: list[RestoreOp] = []
        self.failures: list[tuple[str, str]] = []

    @property
    def ops(self) -> tuple[RestoreOp, ...]:
        """Read-only view of the registered operations in order."""
        return tuple(self._ops)

    @property
    def client(self) -> AcceptanceClient:
        """The bridge client the engine restores against.

        Probe modules need this to construct restore / verify lambdas
        that call ``client.call`` (or ``call_ws``); the alternative —
        threading ``client`` through every ``register_restores`` call —
        leaks the engine's internal contract.
        """
        return self._client

    @property
    def artifacts(self) -> dict[str, Any]:
        """Mutable artifacts dict shared with the runner.

        Restores can stash pre-mutation values here so a later restore
        step can read them back. The engine shares the same dict the
        runner owns; mutations never replace the binding, only mutate
        its contents.
        """
        return self._artifacts

    def register(
        self,
        *,
        label: str,
        tool: str,
        restore: RestoreFn,
        verify: VerifyFn,
    ) -> None:
        """Declare one restore op. Replaces inline ``_restore_call`` / ``_restore_ws``.

        ``label`` is the human-readable description used in failure
        messages (e.g. ``"set_track_property(mute:3)"``). ``tool`` is
        the catalogued tool name whose row should be downgraded if
        this restore fails.
        """
        self._ops.append(RestoreOp(label=label, tool=tool, restore=restore, verify=verify))

    async def run_all(self) -> list[tuple[str, str]]:
        """Execute all registered restores in order.

        Sync and async restores interleave correctly. Each verify runs
        after its corresponding restore returns. A failure appends
        ``(label, reason)`` to ``self.failures`` and continues — one
        failed restore never aborts the rest of the cleanup.

        Returns ``self.failures`` for convenience.
        """
        self.failures = []
        for op in self._ops:
            try:
                observed = op.restore()
                if inspect_awaitable(observed):
                    observed = await observed
                verify_result = op.verify(observed)
                if inspect_awaitable(verify_result):
                    await verify_result
            except Exception as error:  # noqa: BLE001 — cleanup layer swallows all
                self.failures.append((op.label, f"{type(error).__name__}: {error}"))
        return list(self.failures)


def inspect_awaitable(value: Any) -> bool:
    """Return True if ``value`` should be awaited."""
    return hasattr(value, "__await__") or isinstance(value, Awaitable)
