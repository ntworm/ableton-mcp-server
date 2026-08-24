from __future__ import annotations

from pathlib import Path

from ableton_mcp_server import server


def test_seed_bundle_resolution_prefers_env_override(
    tmp_path: Path, monkeypatch: object
) -> None:
    value = tmp_path / "bundle"
    value.mkdir()
    monkeypatch.setenv("ABLETON_GROOVE_SEED_BUNDLE", str(value))  # type: ignore[attr-defined]
    assert server.resolve_groove_seed_bundle() == value.resolve()


def test_default_seed_path_is_package_owned_when_present(monkeypatch: object) -> None:
    monkeypatch.delenv("ABLETON_GROOVE_SEED_BUNDLE", raising=False)  # type: ignore[attr-defined]
    expected = server.DEFAULT_GROOVE_SEED_BUNDLE.resolve()
    assert server.resolve_groove_seed_bundle() == expected


def test_wheel_configuration_includes_packaged_seed() -> None:
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    assert 'packages = ["ableton_mcp_server"]' in text
    assert (
        Path(__file__).resolve().parents[1] / "ableton_mcp_server/resources/groove_seed"
    ).is_dir()
