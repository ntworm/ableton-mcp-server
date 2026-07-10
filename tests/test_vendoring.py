from __future__ import annotations

from pathlib import Path

from scripts.vendor_contracts import GENERATED_HEADER, render_vendored_contracts

ROOT = Path(__file__).resolve().parents[1]


def test_rendered_contracts_are_deterministic_and_have_generated_header() -> None:
    source = (ROOT / "contracts.py").read_text(encoding="utf-8")
    first = render_vendored_contracts(source)
    second = render_vendored_contracts(source)
    assert first == second
    assert first.startswith(GENERATED_HEADER)
    assert first.removeprefix(GENERATED_HEADER) == source


def test_committed_vendor_copy_matches_canonical_contract() -> None:
    source = (ROOT / "contracts.py").read_text(encoding="utf-8")
    generated = (ROOT / "AbletonMCPServer_RemoteScript" / "_contracts.py").read_text(
        encoding="utf-8"
    )
    assert generated == render_vendored_contracts(source)
