"""Release candidate builder tests moved from the original module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ableton_mcp_server.catalog import TOOL_CATALOG
from scripts.build_release_candidates import (
    _validate_source_commit,
    build_release,
    main,
)

from . import test_build_release_candidates as _shared
from .test_build_release_candidates import FAKE_COMMIT, FAKE_VERSION

# Capture the real ``build_release`` before any test fixture
# replaces it; the CLI tests need to bypass their own monkeypatch
# so the recursion does not loop.
_real_build_release = build_release

# The shared fixtures of the original module, bound here so pytest finds
# them in this module's namespace.
fake_npm_runner = _shared.fake_npm_runner
fake_project = _shared.fake_project
_FakeCompletedProcess = _shared._FakeCompletedProcess


# Read from the catalog rather than pinned. The builder's whole job here is to
# reject evidence whose count disagrees with the catalog, so a literal turns
# every new tool into a false failure of a test that is working correctly.
CATALOG_TOOL_COUNT = len(TOOL_CATALOG)


def _write_acceptance_report(
    path: Path,
    *,
    source_commit: str = FAKE_COMMIT,
    release_ready: bool = True,
    tool_count: int = CATALOG_TOOL_COUNT,
) -> Path:
    payload = {
        "source_commit": source_commit,
        "tool_count": tool_count,
        "certification": {"release_ready": release_ready},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_stable_builder_uses_project_version_and_certification(
    fake_project: Path,
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "stable-out"
    report = _write_acceptance_report(tmp_path / "acceptance.json")

    summary = build_release(
        root=fake_project,
        output_directory=output_directory,
        source_commit=FAKE_COMMIT,
        stable=True,
        acceptance_report=report,
    )

    assert summary["version"] == FAKE_VERSION
    assert summary["candidate"] is None
    assert summary["live_certified"] is True
    assert summary["promotion_ready"] is True
    assert summary["artifacts"]["wheel"]["path"].startswith(
        f"ableton_mcp_server-{FAKE_VERSION}"
    )
    assert summary["certification"]["report"] == report.name
    assert len(summary["certification"]["sha256"]) == 64


def test_stable_builder_requires_acceptance_report(
    fake_project: Path,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="acceptance report"):
        build_release(
            root=fake_project,
            output_directory=tmp_path / "stable-out",
            source_commit=FAKE_COMMIT,
            stable=True,
        )


@pytest.mark.parametrize(
    ("release_ready", "tool_count", "source_commit", "message"),
    [
        (False, CATALOG_TOOL_COUNT, FAKE_COMMIT, "release_ready"),
        (True, CATALOG_TOOL_COUNT - 1, FAKE_COMMIT, "tool count"),
        (True, CATALOG_TOOL_COUNT, "1" * 40, "source commit"),
    ],
)
def test_stable_builder_rejects_invalid_acceptance_evidence(
    fake_project: Path,
    tmp_path: Path,
    release_ready: bool,
    tool_count: int,
    source_commit: str,
    message: str,
) -> None:
    report = _write_acceptance_report(
        tmp_path / "acceptance.json",
        source_commit=source_commit,
        release_ready=release_ready,
        tool_count=tool_count,
    )
    with pytest.raises(ValueError, match=message):
        build_release(
            root=fake_project,
            output_directory=tmp_path / "stable-out",
            source_commit=FAKE_COMMIT,
            stable=True,
            acceptance_report=report,
        )


def test_summary_does_not_modify_real_release_dir(
    fake_project: Path,
    tmp_path: Path,
) -> None:
    """Calling the builder with an injected ``output_directory`` must not write
    to ``releases/v0.5.1-rc1/`` inside the project tree."""
    real_release_dir = fake_project / "releases" / f"v{FAKE_VERSION}-rc1"
    output_directory = tmp_path / "rc-out"
    build_release(
        root=fake_project,
        output_directory=output_directory,
    )
    assert not real_release_dir.exists(), (
        "the builder wrote into the project's releases/ directory even "
        "though an injected output_directory was supplied"
    )


def test_manifest_paths_are_relative_to_output_directory(
    fake_project: Path,
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "rc-out"
    summary = build_release(
        root=fake_project,
        output_directory=output_directory,
    )
    for entry in summary["artifacts"].values():
        # Paths must be relative to the output directory, not absolute.
        assert not Path(entry["path"]).is_absolute()
        # And the file must live under that path.
        assert (output_directory / Path(entry["path"]).name).exists()


# -----------------------------------------------------------------------
# P1-7: source_commit must be a real git hash; never "unknown"
# -----------------------------------------------------------------------


class _CapturedProcess:
    def __init__(self, stdout: str) -> None:
        self.returncode = 0
        self.stdout = stdout
        self.stderr = ""


def test_validate_source_commit_accepts_hex_hash() -> None:
    def fake_git(*_args: Any, **_kwargs: Any) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(returncode=0)

    full_hash = "f2a1ff840d93592e085b6f8ad5af1fdb27bfd61b"
    assert _validate_source_commit(full_hash, git_runner=fake_git) == full_hash

    # Short 7-char hashes must be rejected.
    with pytest.raises(ValueError, match="40-character"):
        _validate_source_commit("f2a1ff8", git_runner=fake_git)


def test_validate_source_commit_rejects_non_existent_commit() -> None:
    def fake_failing_git(*_args: Any, **_kwargs: Any) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(returncode=1, stderr="Not found")

    non_existent_hash = "ffffffffffffffffffffffffffffffffffffffff"
    with pytest.raises(ValueError, match="does not correspond to an existing git commit object"):
        _validate_source_commit(non_existent_hash, git_runner=fake_failing_git)


def test_validate_source_commit_rejects_unknown_placeholder() -> None:
    with pytest.raises(ValueError, match="unknown"):
        _validate_source_commit("unknown")


def test_validate_source_commit_rejects_non_hex() -> None:
    with pytest.raises(ValueError, match="hexadecimal"):
        _validate_source_commit("not-a-hash")
    # Hex digits but with non-hex characters interleaved - must reject.
    with pytest.raises(ValueError, match="hexadecimal"):
        _validate_source_commit("zzzzzzz")
    with pytest.raises(ValueError):
        _validate_source_commit("")
    with pytest.raises(ValueError):
        _validate_source_commit(None)  # type: ignore[arg-type]


def test_build_release_manifest_records_real_commit_when_invoked_directly(
    fake_project: Path,
    tmp_path: Path,
) -> None:
    """Direct ``build_release`` call without ``source_commit`` must
    resolve the worktree HEAD via ``git rev-parse HEAD`` and record it
    in the manifest — never the literal ``"unknown"`` placeholder.
    """
    fake_hash = "f2a1ff840d93592e085b6f8ad5af1fdb27bfd61b"

    def fake_git(*_args: Any, **_kwargs: Any) -> _CapturedProcess:
        return _CapturedProcess(fake_hash + "\n")

    output_directory = tmp_path / "rc-out"
    summary = build_release(
        root=fake_project,
        output_directory=output_directory,
        git_runner=fake_git,
    )
    assert summary["source_commit"] == fake_hash, (
        f"manifest must record the real git hash, not 'unknown': {summary['source_commit']!r}"
    )
    manifest = json.loads((output_directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_commit"] == fake_hash


def test_build_release_rejects_source_commit_mismatching_head(
    fake_project: Path,
    tmp_path: Path,
) -> None:
    """Proves that supplying a valid commit that does not match active HEAD aborts build."""
    head_commit = "f2a1ff840d93592e085b6f8ad5af1fdb27bfd61b"
    other_commit = "1111111111111111111111111111111111111111"

    def fake_git(cmd: list[str], *_args: Any, **_kwargs: Any) -> _FakeCompletedProcess:
        if "rev-parse" in cmd:
            return _FakeCompletedProcess(returncode=0, stdout=head_commit + "\n")
        if "cat-file" in cmd:
            return _FakeCompletedProcess(returncode=0)
        return _FakeCompletedProcess(returncode=0)

    output_directory = tmp_path / "rc-out"
    with pytest.raises(ValueError, match="does not match worktree HEAD"):
        build_release(
            root=fake_project,
            output_directory=output_directory,
            source_commit=other_commit,
            git_runner=fake_git,
        )
    assert not (output_directory / "manifest.json").exists(), (
        "manifest must not be created when source_commit does not match HEAD"
    )


def test_build_release_manifest_rejects_unknown_source_commit(
    fake_project: Path,
    tmp_path: Path,
) -> None:
    """Passing ``source_commit='unknown'`` explicitly must abort the
    build — the manifest is never written with the placeholder."""
    output_directory = tmp_path / "rc-out"
    with pytest.raises(ValueError, match="unknown"):
        build_release(
            root=fake_project,
            output_directory=output_directory,
            source_commit="unknown",
        )
    assert not (output_directory / "manifest.json").exists(), (
        "manifest must not be written when source_commit is invalid"
    )


def test_main_cli_passes_explicit_source_commit_to_builder(
    fake_project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``main(['--source-commit', '<hash>'])` must forward the hash to
    ``build_release`` and surface it on the manifest.

    The CLI is the production entrypoint; the test exercises the full
    ``main()`` path so a regression that bypasses ``--source-commit``
    (e.g. ``main()`` ignoring ``argv``) is caught here.
    """
    from scripts import build_release_candidates as brc

    fake_hash = "f2a1ff840d93592e085b6f8ad5af1fdb27bfd61b"
    output_directory = tmp_path / "rc-out"

    captured: dict[str, Any] = {}

    def fake_build_release(**kwargs: Any) -> dict[str, Any]:
        captured["kwargs"] = dict(kwargs)
        # Drop the git_runner since we are forwarding the explicit hash.
        kwargs.pop("git_runner", None)
        # Forward ``root`` so the builder operates on the fake project
        # tree (whose ``AbletonMCPServer_Extension/`` is the only
        # directory the fixture populated with a mock .ablx).
        kwargs["root"] = fake_project
        return _real_build_release(**kwargs)

    monkeypatch.setattr(brc, "build_release", fake_build_release)
    rc = main(
        [
            "--source-commit",
            fake_hash,
            "--output-directory",
            str(output_directory),
        ]
    )
    assert rc == 0
    assert captured["kwargs"].get("source_commit") == fake_hash, (
        f"main() must forward --source-commit to build_release: {captured['kwargs']!r}"
    )


def test_main_cli_resolves_source_commit_when_not_provided(
    fake_project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``--source-commit`` is omitted, ``main()`` must let
    ``build_release`` resolve it from the worktree git. The resolved
    value (never ``"unknown"``) must reach the manifest.
    """
    from scripts import build_release_candidates as brc

    fake_hash = "0123456789abcdef0123456789abcdef01234567"
    output_directory = tmp_path / "rc-out"

    def fake_build_release(**kwargs: Any) -> dict[str, Any]:
        # Resolve via the injected git_runner so the test never depends
        # on the worktree's actual git state.
        kwargs["git_runner"] = lambda *a, **k: _CapturedProcess(fake_hash + "\n")
        kwargs["root"] = fake_project
        return _real_build_release(**kwargs)

    monkeypatch.setattr(brc, "build_release", fake_build_release)
    rc = main(["--output-directory", str(output_directory)])
    assert rc == 0
    manifest = json.loads((output_directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_commit"] == fake_hash, (
        f"resolved source_commit must reach the manifest, got {manifest['source_commit']!r}"
    )


def test_main_cli_rejects_unknown_source_commit(
    tmp_path: Path,
) -> None:
    """``main(['--source-commit', 'unknown'])`` must exit non-zero and
    never write a manifest with the placeholder.
    """
    output_directory = tmp_path / "rc-out"
    rc = main(
        [
            "--source-commit",
            "unknown",
            "--output-directory",
            str(output_directory),
        ]
    )
    assert rc != 0, "main() must exit non-zero when --source-commit is 'unknown'"
    assert not (output_directory / "manifest.json").exists(), (
        "manifest must not be written when --source-commit is invalid"
    )
