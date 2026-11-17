"""Bounded curation of the private corpus: scanning, selection and bundles."""

from __future__ import annotations

import hashlib
import shutil
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from . import GrooveMidiError
from .build import build_seed_bundle
from .constants import MAX_CURATED_REPRESENTATIVES, MAX_INPUT_BYTES
from .midi_lossless import parse_smf
from .schema import BuildInput

if TYPE_CHECKING:
    from .corpus import CorpusCatalog, InventoryRow


@dataclass(frozen=True)
class CuratedBuildResult:
    selected_count: int
    selected_source_bytes: int
    bundle_bytes: int
    first_digest: str
    second_digest: str
    logical_index_digest: str
    artifact_ids: tuple[str, ...]
    reduction_attempts: int


def _digest_file(path: Path) -> tuple[str, bytes]:
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            chunks.append(chunk)
    return digest.hexdigest(), b"".join(chunks)


def _stratified_rows(catalog: CorpusCatalog) -> dict[str, list[InventoryRow]]:
    """Group the deduplicated catalog rows by stratum in a stable order."""

    deduped: dict[str, InventoryRow] = {}
    for row in catalog.rows(status="ok"):
        previous = deduped.get(row.source_digest)
        if previous is None or row.relative_path < previous.relative_path:
            deduped[row.source_digest] = row
    strata: dict[str, list[InventoryRow]] = defaultdict(list)
    for row in deduped.values():
        strata[row.stratum].append(row)
    for values in strata.values():
        values.sort(key=lambda item: (item.fingerprint, item.source_digest, item.relative_path))
    return strata


def _round_robin_selection(
    strata: dict[str, list[InventoryRow]],
    *,
    max_files: int,
    max_source_bytes: int,
) -> list[InventoryRow]:
    """Take one row per stratum in turn until the file or byte cap is reached."""

    selected: list[InventoryRow] = []
    total_bytes = 0
    ordered_strata = sorted(strata)
    cursors = {stratum: 0 for stratum in ordered_strata}
    while len(selected) < max_files and ordered_strata:
        made_progress = False
        for stratum in ordered_strata:
            values = strata[stratum]
            cursor = cursors[stratum]
            while cursor < len(values):
                candidate = values[cursor]
                cursor += 1
                if total_bytes + candidate.file_size > max_source_bytes:
                    continue
                selected.append(candidate)
                total_bytes += candidate.file_size
                cursors[stratum] = cursor
                made_progress = True
                break
            else:
                cursors[stratum] = cursor
            if len(selected) >= max_files:
                break
        if not made_progress:
            break
    return selected


def curate_representatives(
    catalog: CorpusCatalog,
    *,
    max_files: int = MAX_CURATED_REPRESENTATIVES,
    max_source_bytes: int = 24 * 1024 * 1024,
) -> tuple[InventoryRow, ...]:
    """Round-robin deterministic strata while respecting a conservative byte cap."""

    if max_files <= 0 or max_source_bytes <= 0:
        return ()
    strata = _stratified_rows(catalog)
    selected = _round_robin_selection(
        strata,
        max_files=max_files,
        max_source_bytes=max_source_bytes,
    )
    return tuple(selected)


def _directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _validate_caps(max_files: int, max_bundle_bytes: int) -> None:
    """Reject a curated selection or bundle cap outside the bounded contract."""

    if max_files < 1 or max_files > MAX_CURATED_REPRESENTATIVES:
        raise ValueError(
            "curated selection cap must be between one and "
            f"{MAX_CURATED_REPRESENTATIVES}"
        )
    if max_bundle_bytes < 1024:
        raise ValueError("curated bundle cap is too small")


def _build_inputs(
    catalog: CorpusCatalog,
    selected: tuple[InventoryRow, ...],
) -> list[BuildInput]:
    """Return the build inputs of the selected corpus files."""

    return [
        BuildInput(
            path=catalog.input_root / row.relative_path,
            source_kind="author",
            license_id="user-owned",
            redistribution="full",
        )
        for row in selected
    ]


def _publish_curated_bundle(
    catalog: CorpusCatalog,
    output_dir: Path,
    selected: tuple[InventoryRow, ...],
    parent: Path,
    *,
    max_files: int,
    max_bundle_bytes: int,
    attempts: int,
) -> CuratedBuildResult | None:
    """Build two identical bundles and publish the first one when it fits the cap."""

    inputs = _build_inputs(catalog, selected)
    with _temporary_build_dirs(parent) as directories:
        first_dir, second_dir = directories
        build_config = {
            "curation": "groove-curated-v1",
            "license_id": "user-owned",
            "source_kind": "author",
            "redistribution": "full",
            "selection_cap": max_files,
        }
        first = build_seed_bundle(
            input_root=catalog.input_root,
            inputs=inputs,
            output_dir=first_dir,
            build_config=build_config,
        )
        second = build_seed_bundle(
            input_root=catalog.input_root,
            inputs=inputs,
            output_dir=second_dir,
            build_config=build_config,
        )
        first_size = _directory_bytes(first_dir)
        second_size = _directory_bytes(second_dir)
        if not (
            first_size <= max_bundle_bytes
            and second_size <= max_bundle_bytes
            and first.bundle_manifest_digest == second.bundle_manifest_digest
            and first.logical_index_digest == second.logical_index_digest
            and first.artifact_ids == second.artifact_ids
        ):
            return None
        output_dir.mkdir(parents=True, exist_ok=True)
        for item in first_dir.iterdir():
            target = output_dir / item.name
            if item.is_file():
                shutil.copy2(item, target)
        return CuratedBuildResult(
            selected_count=len(selected),
            selected_source_bytes=sum(item.file_size for item in selected),
            bundle_bytes=first_size,
            first_digest=first.bundle_manifest_digest,
            second_digest=second.bundle_manifest_digest,
            logical_index_digest=first.logical_index_digest,
            artifact_ids=tuple(str(item) for item in first.artifact_ids),
            reduction_attempts=attempts,
        )


def build_curated_bundle(
    catalog: CorpusCatalog,
    output_dir: Path,
    *,
    max_files: int = MAX_CURATED_REPRESENTATIVES,
    max_bundle_bytes: int = 32 * 1024 * 1024,
) -> CuratedBuildResult:
    """Build two identical portable bundles, shrinking selection if required."""

    _validate_caps(max_files, max_bundle_bytes)
    output_resolved = output_dir.resolve()
    try:
        if output_resolved.is_relative_to(catalog.input_root):
            raise ValueError("curated bundle output must be outside source root")
    except AttributeError:
        pass
    source_cap = max_bundle_bytes // 2
    attempts = 0
    parent = output_resolved.parent
    parent.mkdir(parents=True, exist_ok=True)
    while True:
        selected = curate_representatives(
            catalog,
            max_files=max_files,
            max_source_bytes=max(1, source_cap),
        )
        if not selected:
            raise ValueError("curated selection has no valid representatives")
        result = _publish_curated_bundle(
            catalog,
            output_dir,
            selected,
            parent,
            max_files=max_files,
            max_bundle_bytes=max_bundle_bytes,
            attempts=attempts,
        )
        if result is not None:
            return result
        attempts += 1
        next_cap = max(1, int(source_cap * 0.75))
        if next_cap >= source_cap:
            raise ValueError("curated bundle exceeds byte cap at minimum selection")
        source_cap = next_cap


class _temporary_build_dirs:
    def __init__(self, parent: Path) -> None:
        import tempfile

        self._context = tempfile.TemporaryDirectory(prefix="groove-curation-", dir=parent)
        self._root: Path | None = None

    def __enter__(self) -> tuple[Path, Path]:
        self._root = Path(self._context.name)
        first = self._root / "one"
        second = self._root / "two"
        first.mkdir()
        second.mkdir()
        return first, second

    def __exit__(self, *_args: object) -> None:
        self._context.cleanup()


def _write_failed_row(
    catalog: CorpusCatalog,
    relative_path: str,
    path: Path,
    error: BaseException,
) -> None:
    """Write the catalog row of a corpus file that could not be scanned."""

    try:
        stat = path.stat()
        size = int(stat.st_size)
        mtime_ns = int(stat.st_mtime_ns)
    except OSError:
        size = 0
        mtime_ns = 0
    source_digest = "0" * 64
    with suppress(OSError):
        source_digest, _raw = _digest_file(path.resolve(strict=True))
    catalog._write_error(
        relative_path,
        file_size=size,
        mtime_ns=mtime_ns,
        source_digest=source_digest,
        error=error,
    )


def _scan_file(
    catalog: CorpusCatalog,
    relative_path: str,
    path: Path,
    *,
    reuse_allowed: bool,
    retry_errors: bool,
) -> str:
    """Scan one corpus file into the catalog and report how it was handled."""

    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(catalog.input_root):
            catalog._write_error(
                relative_path,
                file_size=0,
                mtime_ns=0,
                source_digest="0" * 64,
                error=ValueError("authorized root escape"),
            )
            return "escaped"
        stat = resolved.stat()
        size = int(stat.st_size)
        mtime_ns = int(stat.st_mtime_ns)
        existing = catalog._connection.execute(
            "SELECT status FROM files WHERE relative_path=?", (relative_path,)
        ).fetchone()
        if (
            reuse_allowed
            and catalog._existing(relative_path, size, mtime_ns)
            and not (retry_errors and existing is not None and existing[0] == "error")
        ):
            return "reused"
        if size > MAX_INPUT_BYTES:
            raise GrooveMidiError("input size limit exceeded")
        source_digest, raw = _digest_file(resolved)
        parsed = parse_smf(raw)
        catalog._write_success(
            relative_path,
            file_size=size,
            mtime_ns=mtime_ns,
            source_digest=source_digest,
            parsed=parsed,
        )
        return "scanned"
    except (OSError, ValueError, GrooveMidiError) as error:
        _write_failed_row(catalog, relative_path, path, error)
        return "scanned"


def _finalize_scan(catalog: CorpusCatalog, discovered_paths: set[str]) -> None:
    """Drop the rows of removed files and mark the catalog as current."""

    if not catalog._connection.in_transaction:
        catalog._connection.execute("BEGIN IMMEDIATE")
    try:
        existing_paths = {
            str(row[0]) for row in catalog._connection.execute("SELECT relative_path FROM files")
        }
        for removed_path in existing_paths - discovered_paths:
            catalog._connection.execute(
                "DELETE FROM files WHERE relative_path=?", (removed_path,)
            )
        catalog._connection.executemany(
            "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
            catalog._expected_derivation.items(),
        )
        catalog._connection.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES('scan_state','current')"
        )
        catalog._connection.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES('derivation_state','current')"
        )
        catalog._connection.commit()
    except Exception:
        catalog._connection.rollback()
        raise
    catalog._scan_state = "current"
    catalog._derivation_stale = False


def _scan_totals(catalog: CorpusCatalog) -> tuple[int, int, int]:
    """Return the valid, failed and distinct row counts of the catalog."""

    valid, failed, distinct = catalog._connection.execute(
        "SELECT SUM(status='ok'), SUM(status='error'), "
        "COUNT(DISTINCT CASE WHEN status='ok' THEN source_digest END) "
        "FROM files"
    ).fetchone()
    return int(valid or 0), int(failed or 0), int(distinct or 0)
