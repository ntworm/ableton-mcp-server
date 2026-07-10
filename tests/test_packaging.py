from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wheel_configuration_includes_contracts_and_remote_script() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'ableton-mcp = "ableton_mcp_server.cli:main"' in pyproject
    assert '"contracts.py" = "contracts.py"' in pyproject
    assert (
        '"AbletonMCPServer_RemoteScript" = "ableton_mcp_server/_remote_script"'
        in pyproject
    )


def test_windows_bootstrap_uses_a_distinct_native_virtualenv() -> None:
    script = (ROOT / "scripts" / "setup_windows.ps1").read_text(encoding="utf-8")
    assert ".venv-win" in script
    assert "py -3" in script
    assert 'pip install -e "$RepoRoot"' in script
    assert ".venv-win/" in (ROOT / ".gitignore").read_text(encoding="utf-8")
