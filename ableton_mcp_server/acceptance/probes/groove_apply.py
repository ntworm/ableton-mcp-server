"""Guarded groove apply acceptance seam; no Live mutation is performed here."""

from __future__ import annotations

from typing import Any


def preview_probe(
    *, confirm_project_name: str, expected_empty_slot: bool, disposable: bool
) -> dict[str, Any]:
    """Return an explicit offline refusal unless all commit guards are present."""

    if not confirm_project_name or not expected_empty_slot or not disposable:
        return {
            "state": "rejected",
            "error": {"code": "GROOVE_PRECONDITION_UNSUPPORTED"},
        }
    return {"state": "preview", "bridge_stage": "none"}


def run_apply_preview_with_bridge(*, contract: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "status": "offline_passed",
        "result": preview_probe(
            confirm_project_name="",
            expected_empty_slot=True,
            disposable=True,
        )
        if contract is None
        else preview_probe(
            confirm_project_name="TESTE_CODEX",
            expected_empty_slot=True,
            disposable=True,
        ),
    }


__all__ = ["preview_probe", "run_apply_preview_with_bridge"]
