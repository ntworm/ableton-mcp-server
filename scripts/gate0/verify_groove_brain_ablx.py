from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

REQUIRED_FILES = {
    "manifest.json",
    "dist/extension.js",
    "ui/index.html",
    "ui/app.js",
    "ui/styles.css",
    "runtime/manifest.json",
    "runtime/windows-x64/groove-brain-gate0-helper.exe",
}
ALLOWED_DIRECTORIES = {
    "dist/",
    "ui/",
    "runtime/",
    "runtime/windows-x64/",
}
EXPECTED_HELPER = "windows-x64/groove-brain-gate0-helper.exe"
MAX_COMPRESSED_BYTES = 50 * 1024 * 1024
MAX_INSTALLED_BYTES = 100 * 1024 * 1024


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_name(name: str) -> None:
    pure = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or pure.is_absolute()
        or any(part in {"", ".", ".."} or ":" in part for part in pure.parts)
    ):
        raise ValueError(f"UNSAFE_ENTRY:{name}")


def _read_json(archive: zipfile.ZipFile, name: str) -> dict[str, Any]:
    try:
        value = json.loads(archive.read(name))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"INVALID_JSON:{name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"INVALID_JSON_OBJECT:{name}")
    return value


def verify_ablx(path: Path) -> dict[str, Any]:
    artifact = path.resolve(strict=True)
    compressed_bytes = artifact.stat().st_size
    if compressed_bytes > MAX_COMPRESSED_BYTES:
        raise ValueError("PACKAGE_TOO_LARGE")

    try:
        with zipfile.ZipFile(artifact) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise ValueError("DUPLICATE_ENTRY")

            for info in infos:
                _validate_name(info.filename)
                if info.flag_bits & 0x1:
                    raise ValueError(f"ENCRYPTED_ENTRY:{info.filename}")
                unix_type = (info.external_attr >> 16) & 0o170000
                if unix_type == 0o120000:
                    raise ValueError(f"SYMLINK_ENTRY:{info.filename}")

            directories = {info.filename for info in infos if info.is_dir()}
            unexpected_directories = sorted(directories - ALLOWED_DIRECTORIES)
            if unexpected_directories:
                raise ValueError(f"UNEXPECTED_DIRECTORIES:{','.join(unexpected_directories)}")

            file_infos = [info for info in infos if not info.is_dir()]
            files = {info.filename for info in file_infos}
            missing = sorted(REQUIRED_FILES - files)
            if missing:
                raise ValueError(f"MISSING_ENTRIES:{','.join(missing)}")
            unexpected = sorted(files - REQUIRED_FILES)
            if unexpected:
                raise ValueError(f"UNEXPECTED_ENTRIES:{','.join(unexpected)}")

            installed_bytes = sum(info.file_size for info in file_infos)
            if installed_bytes > MAX_INSTALLED_BYTES:
                raise ValueError("INSTALLED_PACKAGE_TOO_LARGE")

            manifest = _read_json(archive, "manifest.json")
            if manifest.get("entry") != "dist/extension.js":
                raise ValueError("INVALID_EXTENSION_ENTRY")

            runtime = _read_json(archive, "runtime/manifest.json")
            if runtime.get("protocol") != 1 or runtime.get("platform") != "win32-x64":
                raise ValueError("INVALID_RUNTIME_CONTRACT")
            if runtime.get("helper") != EXPECTED_HELPER:
                raise ValueError("INVALID_RUNTIME_HELPER")
            helper_path = f"runtime/{EXPECTED_HELPER}"
            helper_hash = _sha256(archive.read(helper_path))
            if helper_hash != runtime.get("sha256"):
                raise ValueError("HELPER_HASH_MISMATCH")
    except zipfile.BadZipFile as error:
        raise ValueError("INVALID_ZIP") from error

    return {
        "status": "pass",
        "artifact": str(artifact),
        "artifact_sha256": _sha256(artifact.read_bytes()),
        "compressed_bytes": compressed_bytes,
        "installed_bytes": installed_bytes,
        "entry_count": len(file_infos),
        "entries": sorted(files),
        "helper_sha256": helper_hash,
        "helper_hash_match": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify_ablx(args.artifact)
    encoded = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
