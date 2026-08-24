from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from ableton_mcp_server import __version__
from ableton_mcp_server.catalog import TOOL_CATALOG

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_COUNT_PATHS = (
    ROOT / "README.md",
    ROOT / "docs" / "ARCHITECTURE.md",
    ROOT / "docs" / "TOOL_REFERENCE.md",
    ROOT / "docs" / "api_capability_matrix.md",
    ROOT / "docs" / "index.html",
)


class LandingContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.internal_targets: list[str] = []
        self.missing_translation_pairs: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(str(values["id"]))
        href = values.get("href")
        if href and href.startswith("#"):
            self.internal_targets.append(href[1:])
        has_en = "data-en" in values
        has_pt = "data-pt" in values
        if has_en != has_pt:
            self.missing_translation_pairs.append(
                f"{tag}:{values.get('id') or values.get('class') or 'anonymous'}"
            )


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_active_tool_count_markers_match_catalog() -> None:
    active_count = str(len(TOOL_CATALOG))
    for path in ACTIVE_COUNT_PATHS:
        marked_lines = [
            line for line in _text(path).splitlines() if "TOOL_COUNT: active_total" in line
        ]
        assert marked_lines, f"{path} has no active tool-count markers"
        assert all(
            re.search(rf"(?<!\d){active_count}(?!\d)", line) for line in marked_lines
        ), path


def test_landing_version_catalog_and_translations_are_current() -> None:
    html = _text(ROOT / "docs" / "index.html")
    catalog_names = {item.name for item in TOOL_CATALOG}
    card_names = re.findall(r"\{ name: '([^']+)'", html)

    assert f'<span class="brand-tag">v{__version__}</span>' in html
    assert f"<strong>ableton-mcp-server v{__version__}</strong>" in html
    assert len(card_names) == len(catalog_names)
    assert set(card_names) == catalog_names

    parser = LandingContractParser()
    parser.feed(html)
    assert len(parser.ids) == len(set(parser.ids))
    assert set(parser.internal_targets) <= set(parser.ids)
    assert parser.missing_translation_pairs == []


def test_release_identity_and_clean_install_are_catalog_driven() -> None:
    expected = re.escape(__version__)
    assert re.search(
        rf'^version\s*=\s*["\']{expected}["\']$',
        _text(ROOT / "pyproject.toml"),
        re.MULTILINE,
    )
    for path in (
        ROOT / "manifest.json",
        ROOT / "AbletonMCPServer_Extension" / "package.json",
        ROOT / "AbletonMCPServer_Extension" / "manifest.json",
    ):
        assert re.search(rf'"version"\s*:\s*"{expected}"', _text(path)), path

    verifier = _text(ROOT / "scripts" / "verify_clean_install.ps1")
    assert "Expected 65 tools" not in verifier
    assert "len(TOOL_CATALOG)" in verifier


def test_current_guidance_and_changelog_name_the_current_surface() -> None:
    agents = _text(ROOT / "AGENTS.md")
    readme = _text(ROOT / "README.md")
    changelog_head = _text(ROOT / "CHANGELOG.md").split("## [0.5.3]", maxsplit=1)[0]

    assert __version__ == "0.6.0"
    assert re.search(r"server\.py.*96 public MCP tools", agents)
    assert "Offline Music Generation" in readme
    assert "current v0.6.0 release ships 96 tools" in readme
    assert "## [Unreleased]" in changelog_head
    assert "## [0.6.0] - 2026-08-24" in changelog_head
    assert "## [0.5.6] - 2026-08-18" in changelog_head
    assert "three deterministic" in changelog_head
    assert "five Groove Intelligence tools" in changelog_head
    assert "## v0.6.0" in _text(ROOT / "releases" / "v0.6.0" / "RELEASE-NOTES.md")


def test_every_public_tool_is_present_in_canonical_user_docs() -> None:
    tool_reference = _text(ROOT / "docs" / "TOOL_REFERENCE.md")
    landing = _text(ROOT / "docs" / "index.html")
    for item in TOOL_CATALOG:
        assert f"`{item.name}" in tool_reference, item.name
        assert f"name: '{item.name}'" in landing, item.name
