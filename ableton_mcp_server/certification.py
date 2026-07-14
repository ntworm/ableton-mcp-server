"""Baseline certification records.

Slice 1 Task 9 introduces a typed report that records an immutable
verification row per catalog tool. The report is the source of truth for
``release_ready`` decisions and for the JSON output of ``cli acceptance``.

Statuses
--------
- ``offline_passed`` — local-only probe (file or pure-Python) succeeded.
- ``live_passed`` — bridge mutation + readback succeeded.
- ``manual_passed`` — owner manually confirmed.
- ``manual_required`` — operation was not executed; out-of-band owner
  confirmation is required before this row can flip to ``manual_passed``.
- ``host_unavailable`` — host does not expose the seam; verified by probe.
- ``environment_unavailable`` — environment (Node, audio clip, etc.) missing.
- ``failed`` — probe reached but readback failed; release blocker.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

_ALLOWED_STATUSES = {
    "offline_passed",
    "live_passed",
    "manual_passed",
    "manual_required",
    "host_unavailable",
    "environment_unavailable",
    "failed",
}


@dataclass(frozen=True, slots=True)
class Verification:
    tool: str
    status: str
    evidence: str

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_STATUSES:
            raise ValueError(f"unknown verification status: {self.status}")
        if not self.evidence.strip():
            raise ValueError("verification evidence must be non-empty")


class CertificationReport:
    """Owns one mutable ``_rows`` dict for a single CLI run."""

    def __init__(self, tool_names: tuple[str, ...]) -> None:
        self._tool_names = tool_names
        self._rows: dict[str, Verification] = {}

    @property
    def tool_names(self) -> tuple[str, ...]:
        return self._tool_names

    @property
    def recorded(self) -> dict[str, Verification]:
        return dict(self._rows)

    def record(self, row: Verification) -> None:
        if row.tool not in self._tool_names:
            raise ValueError(f"tool is not cataloged: {row.tool}")
        self._rows[row.tool] = row

    def finish(self) -> dict[str, object]:
        missing = [name for name in self._tool_names if name not in self._rows]
        if missing:
            raise ValueError(
                f"{len(missing)} tools are unclassified: {', '.join(missing[:10])}"
            )
        rows = [asdict(self._rows[name]) for name in self._tool_names]
        return {
            "tool_count": len(rows),
            "release_ready": not any(row["status"] == "failed" for row in rows),
            "tools": rows,
        }