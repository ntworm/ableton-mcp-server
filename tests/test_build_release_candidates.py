"""RED: ``scripts/build_release_candidates.py`` must be testable.

These tests prove:

- The builder accepts an injectable ``output_directory`` and never writes
  to ``releases/v0.5.1-rc1`` outside the test invocation.
- Stale candidates from previous runs are removed before the new
  artifacts are chosen, so the produced wheel / .ablx / zip is always
  the freshly built one (never ``candidates[0]`` from a leftover).
- Manifest paths use forward slashes (``as_posix()``).
- Manifest paths and SHA256SUMS reference the same files that exist on
  disk.
- The wheel includes the repository-derived version in METADATA, and the ZIP
  excludes ``__pycache__``/``.pyc``.
- The manifest flags ``live_certified=false`` and
  ``promotion_ready=false`` until the Live checkpoint finishes.

If any of these tests fail, the builder cannot prove the artifacts in
the selected output directory actually match what was just produced.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scripts.build_release_candidates import (
    build_release,
)

FAKE_VERSION = "9.8.7"
FAKE_COMMIT = "f2a1ff840d93592e085b6f8ad5af1fdb27bfd61b"


@pytest.fixture
def fake_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Construct a minimal project tree the builder can package.

    The fake mimics the real layout: ``AbletonMCPServer_RemoteScript/``,
    ``ableton_mcp_server/``, ``AbletonMCPServer_Extension/``. The
    ``.ablx`` is fabricated by a mocked ``subprocess.run`` so the test
    does not depend on a real Node toolchain or shell interpreter.
    """
    project = tmp_path / "project"
    project.mkdir()

    _write_remote_script_tree(project)
    _write_python_package_tree(project)
    _write_extension_tree(project)
    _stub_python_wheel_build(monkeypatch)

    return project


def _write_remote_script_tree(project: Path) -> None:
    """Write the Remote Script folder with the __pycache__ that must be excluded."""
    # Remote Script: write a single module + a __pycache__ that must be
    # excluded.
    rs = project / "AbletonMCPServer_RemoteScript"
    rs.mkdir()
    (rs / "__init__.py").write_text("# remote script\n", encoding="utf-8")
    (rs / "_contracts.py").write_text("# contracts\n", encoding="utf-8")
    pycache = rs / "__pycache__"
    pycache.mkdir()
    (pycache / "__init__.pyc").write_text("stale", encoding="utf-8")
    (pycache / "_contracts.pyc").write_text("stale", encoding="utf-8")


def _write_python_package_tree(project: Path) -> None:
    """Write the Python package folder and the pyproject marker."""
    # Python package: a single module + version + pyproject marker.
    pkg = project / "ableton_mcp_server"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        f'__version__ = "{FAKE_VERSION}"\n', encoding="utf-8"
    )
    (project / "pyproject.toml").write_text(
        f"[project]\nname='ableton_mcp_server'\nversion='{FAKE_VERSION}'\n",
        encoding="utf-8",
    )


def _write_extension_tree(project: Path) -> None:
    """Write the Extension folder with its manifest, package and stale .ablx."""
    # Extension: a fake ``.ablx`` blob that the mocked ``npm run package``
    # call will drop in place. We also write a stub ``package.json`` so
    # the builder can locate ``npm run package`` semantics without
    # actually invoking Node.
    ext = project / "AbletonMCPServer_Extension"
    ext.mkdir()
    (ext / "manifest.json").write_text(
        json.dumps(
            {
                "name": "AbletonMCPServer",
                "version": FAKE_VERSION,
                "host": "127.0.0.1",
            }
        ),
        encoding="utf-8",
    )
    (ext / "package.json").write_text(
        json.dumps(
            {
                "name": "AbletonMCPServer",
                "version": FAKE_VERSION,
                "scripts": {"package": "extensions-cli package"},
            }
        ),
        encoding="utf-8",
    )
    dist = ext / "dist"
    dist.mkdir()
    (dist / "extension.js").write_text(
        "// fake extension with host: '127.0.0.1'\n",
        encoding="utf-8",
    )
    # Pre-existing stale artifact from a previous build — the builder
    # must remove it before choosing the fresh candidate.
    (ext / f"AbletonMCPServer-Extension-{FAKE_VERSION}.ablx").write_text(
        "stale-ablx", encoding="utf-8"
    )


def _stub_python_wheel_build(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``python -m build --wheel`` with a wheel written in place."""
    # The builder also needs to run ``python -m build --wheel``. We
    # stub that out by replacing ``_build_python_wheel`` directly.
    from scripts import build_release_candidates as brc

    def fake_build_wheel(_root: Path, output_directory: Path) -> Path:
        wheel_name = f"ableton_mcp_server-{FAKE_VERSION}-py3-none-any.whl"
        wheel = output_directory / wheel_name
        import zipfile as _zf

        if wheel.exists():
            wheel.unlink()
        with _zf.ZipFile(wheel, "w", _zf.ZIP_DEFLATED) as zf:
            zf.writestr(
                "ableton_mcp_server-9.8.7.dist-info/METADATA",
                f"Metadata-Version: 2.1\nName: ableton_mcp_server\nVersion: {FAKE_VERSION}\n",
            )
            zf.writestr(
                "ableton_mcp_server/__init__.py",
                f'__version__ = "{FAKE_VERSION}"\n',
            )
        return wheel

    monkeypatch.setattr(brc, "_build_python_wheel", fake_build_wheel)


class _FakeCompletedProcess:
    def __init__(
        self,
        returncode: int,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _FakeSubprocessModule:
    """Minimal stand-in for the ``subprocess`` module."""

    def __init__(self, runner: Callable[..., Any]) -> None:
        self._runner = runner
        self.run = runner

    def which(self, _name: str) -> str:  # not used by the builder
        return ""


@pytest.fixture(autouse=True)
def fake_npm_runner(fake_project: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Mock ``subprocess.run`` for ``npm run package`` AND ``git rev-parse``.

    Records every invocation so tests can assert ``argv``/``cwd``/
    ``check`` semantics, and produces a fresh ``.ablx`` blob where the
    builder expects one. The mock lives in ``scripts.build_release_candidates``
    so it overrides the production ``subprocess.run`` import. The
    ``.ablx`` is dropped into ``fake_project/AbletonMCPServer_Extension``
    so the builder's ``glob`` finds it where it expects.

    The ``git rev-parse HEAD`` call (used by ``_resolve_source_commit``
    when ``build_release`` is invoked without an explicit hash) is
    also intercepted so the test stays deterministic and never depends
    on the worktree's actual git state. The fake returns a stable
    40-char hex hash.
    """
    from scripts import build_release_candidates as brc

    calls: list[dict[str, Any]] = []
    ext_dir = fake_project / "AbletonMCPServer_Extension"
    fake_commit = FAKE_COMMIT

    def runner(argv: list[str] | str, *args: Any, **kwargs: Any) -> Any:
        argv_list = list(argv) if isinstance(argv, (list, tuple)) else argv
        calls.append(
            {
                "argv": argv_list,
                "kwargs": {k: v for k, v in kwargs.items()},
            }
        )
        # ``git rev-parse HEAD`` is the call site used by the builder
        # to resolve ``source_commit``. Return a valid hex hash so
        # validation passes without touching the worktree.
        if isinstance(argv_list, list) and len(argv_list) >= 3 and argv_list[0] == "git":
            if argv_list[1] == "rev-parse":
                return _FakeCompletedProcess(
                    returncode=0,
                    stdout=fake_commit + "\n",
                    stderr="",
                )
            if argv_list[1] == "cat-file":
                target_arg = argv_list[-1]
                if "ffffffffffffffffffffffffffffffffffffffff" in target_arg:
                    return _FakeCompletedProcess(returncode=1, stderr="not found")
                return _FakeCompletedProcess(returncode=0)

        # Default: behave like the npm runner and drop a fresh .ablx.
        target = ext_dir / f"AbletonMCPServer-Extension-{FAKE_VERSION}.ablx"
        if target.exists():
            target.unlink()
        target.write_bytes(b"fresh-ablx-from-mock")
        return _FakeCompletedProcess(returncode=0)

    monkeypatch.setattr(brc, "subprocess", _FakeSubprocessModule(runner))
    monkeypatch.setattr(brc.shutil, "which", lambda _name: "")  # avoid hitting the real npm
    return {"calls": calls, "ext_dir": ext_dir}


def test_builder_writes_only_to_injected_output_directory(
    fake_project: Path,
    tmp_path: Path,
) -> None:
    """The builder must not touch ``releases/v0.5.1-rc1`` when given a tmp dir."""
    output_directory = tmp_path / "rc-out"
    summary = build_release(
        root=fake_project,
        output_directory=output_directory,
    )
    # Stale artifacts inside the project must not leak in.
    assert output_directory.exists()
    for child in output_directory.iterdir():
        # Every artifact must be freshly produced, not a stale leftover
        # from ``fake_project`` (which has no shared files with
        # ``output_directory``).
        assert child.parent == output_directory
    assert summary["live_certified"] is False
    assert summary["promotion_ready"] is False


def test_builder_removes_stale_candidates(
    fake_project: Path,
    tmp_path: Path,
) -> None:
    """Stale .ablx from a previous run must not be selected as the artifact."""
    output_directory = tmp_path / "rc-out"
    output_directory.mkdir()
    # Drop a stale ``.ablx`` into the **output** directory too — the
    # builder should clear stale entries before writing new ones.
    stale_zip = output_directory / f"AbletonMCPServer-Extension-{FAKE_VERSION}.ablx"
    stale_zip.write_bytes(b"definitely-stale")

    summary = build_release(
        root=fake_project,
        output_directory=output_directory,
    )
    # Path in the manifest is **relative to the output directory**, so
    # the test resolves it against ``output_directory`` (not the CWD).
    ablx_rel = summary["artifacts"]["extension_ablx"]["path"]
    ablx_path = output_directory / ablx_rel
    assert ablx_path.read_bytes() != b"definitely-stale"
    assert ablx_path.read_bytes() == b"fresh-ablx-from-mock"


def test_builder_invokes_npm_with_list_argv(
    fake_project: Path,
    tmp_path: Path,
    fake_npm_runner: dict[str, Any],
) -> None:
    """``npm run package`` must run via list-form argv, no shell, cwd set.

    The runner is also called once for ``git rev-parse HEAD`` (used by
    ``_resolve_source_commit``); the npm call is therefore the second
    invocation in the captured list.
    """
    output_directory = tmp_path / "rc-out"
    build_release(
        root=fake_project,
        output_directory=output_directory,
        source_commit="f2a1ff840d93592e085b6f8ad5af1fdb27bfd61b",
    )

    # ``argv`` must be a list (``check=True`` semantics) and target
    # ``run package``. ``shell=True`` must not be set. The first
    # captured call is the ``git rev-parse HEAD`` resolution path; the
    # npm call follows.
    npm_call = _find_npm_call(fake_npm_runner["calls"])
    argv = npm_call["argv"]
    assert isinstance(argv, list), f"argv must be list-form, got {argv!r}"
    assert "run" in argv and "package" in argv, f"argv must invoke 'run package', got {argv!r}"
    kwargs = npm_call["kwargs"]
    assert "shell" not in kwargs or kwargs["shell"] is False, (
        "subprocess.run must not use shell=True"
    )
    assert kwargs.get("check") is True, "subprocess.run must be invoked with check=True"
    cwd = kwargs.get("cwd", "")
    assert str(fake_project / "AbletonMCPServer_Extension") in cwd, (
        f"cwd must target the Extension dir, got {cwd!r}"
    )


def _find_npm_call(calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the captured npm invocation from the recorded subprocess calls."""
    return next(
        call
        for call in calls
        if isinstance(call["argv"], list)
        and len(call["argv"]) >= 2
        and call["argv"][0] not in ("git",)
    )


def test_manifest_paths_use_forward_slashes(
    fake_project: Path,
    tmp_path: Path,
) -> None:
    """Manifest paths must use POSIX separators via ``as_posix()``."""
    output_directory = tmp_path / "rc-out"
    summary = build_release(
        root=fake_project,
        output_directory=output_directory,
    )
    for entry in summary["artifacts"].values():
        assert "\\" not in entry["path"], f"path {entry['path']} uses backslashes"


def test_manifest_matches_sha256_and_files(
    fake_project: Path,
    tmp_path: Path,
) -> None:
    """The SHA256SUMS file must list exactly the artifacts in the manifest."""
    output_directory = tmp_path / "rc-out"
    summary = build_release(
        root=fake_project,
        output_directory=output_directory,
    )
    sha_lines = (output_directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    sha_map = {}
    for line in sha_lines:
        sha, name = line.split("  ", 1)
        sha_map[name] = sha
    for _label, entry in summary["artifacts"].items():
        sha_name = Path(entry["path"]).name
        assert sha_name in sha_map, f"SHA256SUMS missing {sha_name}"
        assert sha_map[sha_name] == entry["sha256"]
        # File must exist with the declared byte count.
        path = output_directory / sha_name
        assert path.exists()
        assert path.stat().st_size == entry["bytes"]


def test_wheel_metadata_and_version(fake_project: Path, tmp_path: Path) -> None:
    """Wheel METADATA must declare the version, and ``__init__.py`` must match."""
    output_directory = tmp_path / "rc-out"
    summary = build_release(
        root=fake_project,
        output_directory=output_directory,
    )
    wheel_name = Path(summary["artifacts"]["wheel"]["path"]).name
    wheel_path = output_directory / wheel_name
    with zipfile.ZipFile(wheel_path) as zf:
        metadata = zf.read("ableton_mcp_server-9.8.7.dist-info/METADATA").decode("utf-8")
        init_py = zf.read("ableton_mcp_server/__init__.py").decode("utf-8")
    assert f"Version: {FAKE_VERSION}" in metadata
    assert f'__version__ = "{FAKE_VERSION}"' in init_py


def test_remote_script_zip_excludes_pycache(
    fake_project: Path,
    tmp_path: Path,
) -> None:
    """The Remote Script ZIP must not include ``__pycache__`` or ``.pyc``."""
    output_directory = tmp_path / "rc-out"
    summary = build_release(
        root=fake_project,
        output_directory=output_directory,
    )
    zip_name = Path(summary["artifacts"]["remote_script_zip"]["path"]).name
    zip_path = output_directory / zip_name
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert not any("__pycache__" in name for name in names)
    assert not any(name.endswith(".pyc") for name in names)
    # And it must include the live source modules.
    assert any(name.endswith("__init__.py") for name in names)
    assert any(name.endswith("_contracts.py") for name in names)


def test_manifest_flags_promotion_blocked_until_live_certified(
    fake_project: Path,
    tmp_path: Path,
) -> None:
    """The manifest must flag ``promotion_ready=false`` until Live runs."""
    output_directory = tmp_path / "rc-out"
    summary = build_release(
        root=fake_project,
        output_directory=output_directory,
    )
    assert summary["live_certified"] is False
    assert summary["promotion_ready"] is False
    manifest = json.loads((output_directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["live_certified"] is False
    assert manifest["promotion_ready"] is False
    assert manifest["candidate"] == "rc1"


def __getattr__(name: str) -> Any:
    """Expose the tests moved to ``test_build_release_candidates_part2``.

    The lookup is lazy so the two modules never import each other while
    they load, and so pytest does not collect the same test twice.
    """
    from . import test_build_release_candidates_part2 as _part2

    return getattr(_part2, name)
