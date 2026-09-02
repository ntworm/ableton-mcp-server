from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from scripts.gate0.verify_groove_brain_ablx import verify_ablx

ROOT = Path(__file__).resolve().parents[1]
GATE0 = ROOT / "AbletonMCPServer_Extension" / "groove-brain-gate0"


def _artifact(
    path: Path, *, helper_bytes: bytes = b"helper", runtime_version: str = "0.1.0"
) -> Path:
    helper_hash = hashlib.sha256(helper_bytes).hexdigest()
    runtime = {
        "protocol": 1,
        "platform": "win32-x64",
        "version": runtime_version,
        "helper": "windows-x64/groove-brain-gate0-helper.exe",
        "sha256": helper_hash,
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json", '{"entry":"dist/extension.js","version":"0.1.0"}'
        )
        archive.writestr("dist/extension.js", "module.exports={};")
        archive.writestr("ui/index.html", "<html></html>")
        archive.writestr("ui/app.js", "")
        archive.writestr("ui/styles.css", "")
        archive.writestr("runtime/manifest.json", json.dumps(runtime))
        archive.writestr("runtime/windows-x64/groove-brain-gate0-helper.exe", helper_bytes)
    return path


def test_verifier_accepts_exact_hashed_inventory(tmp_path: Path) -> None:
    report = verify_ablx(_artifact(tmp_path / "gate0.ablx"))

    assert report["status"] == "pass"
    assert report["entry_count"] == 7
    assert report["helper_hash_match"] is True
    assert report["extension_version"] == "0.1.0"


def test_verifier_rejects_helper_hash_mismatch(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path / "gate0.ablx")
    with (
        pytest.warns(UserWarning, match="Duplicate name"),
        zipfile.ZipFile(artifact, "a") as archive,
    ):
        archive.writestr(
            "runtime/windows-x64/groove-brain-gate0-helper.exe", b"tampered"
        )

    with pytest.raises(ValueError, match="DUPLICATE_ENTRY|HELPER_HASH_MISMATCH"):
        verify_ablx(artifact)


def test_verifier_rejects_extra_or_unsafe_entries(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path / "gate0.ablx")
    with zipfile.ZipFile(artifact, "a") as archive:
        archive.writestr("../escape.txt", "bad")

    with pytest.raises(ValueError, match="UNSAFE_ENTRY|UNEXPECTED_ENTRIES"):
        verify_ablx(artifact)


def test_verifier_rejects_runtime_and_extension_version_mismatch(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path / "gate0.ablx", runtime_version="0.1.1")

    with pytest.raises(ValueError, match="VERSION_MISMATCH"):
        verify_ablx(artifact)


def test_gate0_source_is_isolated_and_reachable_only_from_a_private_network() -> None:
    """The listener is no longer loopback-only, and that is deliberate.

    A modal dialog blocks Live while it is open, so the panel moved to a browser
    on the user's phone and the helper has to be reachable from it. What replaces
    the loopback bind is not nothing: the accept loop refuses any peer that is
    not on a private network, so the change adds the LAN and not the internet.
    """

    package = json.loads(
        (ROOT / "AbletonMCPServer_Extension" / "package.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((GATE0 / "manifest.json").read_text(encoding="utf-8"))
    server = (GATE0 / "helper" / "src" / "server.rs").read_text(encoding="utf-8")
    net = (GATE0 / "helper" / "src" / "net.rs").read_text(encoding="utf-8")
    extension = (GATE0 / "src" / "extension.ts").read_text(encoding="utf-8")

    assert manifest["entry"] == "dist/extension.js"
    assert "gate0:package" in package["scripts"]
    assert "registerContextMenuAction('ClipSlot'" in extension
    assert "Arrangement" not in extension

    # Binding wide is only safe because the peer check is the real gate, so the
    # two are asserted together: neither may be removed without the other.
    assert 'TcpListener::bind("0.0.0.0:0")' in server
    assert "is_allowed_peer(address.ip())" in server
    assert "v4.is_loopback() || v4.is_private() || v4.is_link_local()" in net
