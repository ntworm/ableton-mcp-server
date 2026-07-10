from __future__ import annotations

from pathlib import Path

GENERATED_HEADER = (
    "# GENERATED FILE - DO NOT EDIT.\n"
    "# Source: ../contracts.py\n"
    "# Regenerate with: python scripts/vendor_contracts.py\n\n"
)


def render_vendored_contracts(source: str) -> str:
    if not source.endswith("\n"):
        source += "\n"
    return GENERATED_HEADER + source


def vendor_contracts(root: Path | None = None) -> Path:
    project_root = root or Path(__file__).resolve().parents[1]
    source_path = project_root / "contracts.py"
    target_path = project_root / "AbletonMCPServer_RemoteScript" / "_contracts.py"
    rendered = render_vendored_contracts(source_path.read_text(encoding="utf-8"))
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8", newline="\n") as target:
        target.write(rendered)
    return target_path


def main() -> int:
    target = vendor_contracts()
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
