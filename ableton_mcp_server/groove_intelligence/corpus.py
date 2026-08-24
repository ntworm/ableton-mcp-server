"""Streaming, restartable private-corpus inventory and bounded curation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from . import GrooveMidiError
from .build import build_seed_bundle
from .canonical import canonical_json, sha256_hex
from .constants import (
    CORPUS_SCHEMA_VERSION,
    FEATURES_SCHEMA_VERSION,
    GRAMMAR_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION,
    MAX_INPUT_BYTES,
    NORMALIZER_ID,
    PARSER_ID,
)
from .midi_lossless import parse_smf
from .projections import derive_features, derive_grammar, derive_hvo
from .schema import BuildInput
from .taxonomy import TAXONOMY_VERSION, classify_facets

_DDL = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
  relative_path TEXT PRIMARY KEY,
  file_size INTEGER NOT NULL,
  mtime_ns INTEGER NOT NULL,
  source_digest TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('ok','error')),
  error_code TEXT,
  error_detail TEXT,
  event_count INTEGER NOT NULL DEFAULT 0,
  note_count INTEGER NOT NULL DEFAULT 0,
  bars INTEGER NOT NULL DEFAULT 0,
  stratum TEXT NOT NULL,
  fingerprint TEXT NOT NULL DEFAULT '',
  facets_json TEXT NOT NULL DEFAULT '{}',
  features_json TEXT NOT NULL DEFAULT '{}',
  hvo_digest TEXT NOT NULL DEFAULT '',
  grammar_digest TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS files_status_idx ON files(status);
CREATE INDEX IF NOT EXISTS files_digest_idx ON files(source_digest);
CREATE INDEX IF NOT EXISTS files_stratum_idx ON files(stratum);
"""


@dataclass(frozen=True)
class InventoryRow:
    relative_path: str
    file_size: int
    mtime_ns: int
    source_digest: str
    status: str
    error_code: str | None
    error_detail: str | None
    event_count: int
    note_count: int
    bars: int
    stratum: str
    fingerprint: str
    facets: dict[str, tuple[str, ...]]
    features: dict[str, object]
    hvo_digest: str
    grammar_digest: str


@dataclass(frozen=True)
class InventoryStats:
    discovered: int
    processed: int
    reused: int
    valid: int
    failed: int
    deduplicated: int
    elapsed_seconds: float


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


def _stratum(relative_path: str) -> str:
    parts = Path(relative_path).parts
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0] if parts else "(root)"


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


def _error_code(error: BaseException) -> str:
    if isinstance(error, GrooveMidiError):
        return "groove_midi_error"
    if isinstance(error, OSError):
        return "io_error"
    if isinstance(error, ValueError):
        return "validation_error"
    return "internal_error"


def _catalog_derivation_values() -> dict[str, str]:
    """Return the version contract that determines every derived catalog row."""

    projections = {
        "features": FEATURES_SCHEMA_VERSION,
        "grammar": GRAMMAR_SCHEMA_VERSION,
        "hvo": HVO_SCHEMA_VERSION,
        "taxonomy": TAXONOMY_VERSION,
    }
    identity = {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "parser_id": PARSER_ID,
        "normalizer_id": NORMALIZER_ID,
        "projection_versions": projections,
        "taxonomy_version": TAXONOMY_VERSION,
    }
    return {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "parser_id": PARSER_ID,
        "normalizer_id": NORMALIZER_ID,
        "projection_versions": canonical_json(projections).decode("utf-8"),
        "taxonomy_version": TAXONOMY_VERSION,
        "derivation_fingerprint": sha256_hex(canonical_json(identity)),
    }


class CorpusCatalog:
    """A private SQLite catalog containing no BLOBs, notes, or absolute paths."""

    def __init__(self, db_path: Path, input_root: Path) -> None:
        try:
            root = input_root.resolve(strict=True)
        except OSError as error:
            raise ValueError("authorized corpus root is unavailable") from error
        if not root.is_dir():
            raise ValueError("authorized corpus root is not a directory")
        self.db_path = db_path.resolve()
        self.input_root = root
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.db_path)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._connection.executescript(_DDL)
        fingerprint = sha256_hex(str(root).casefold().encode("utf-8"))
        stored = self._connection.execute(
            "SELECT value FROM meta WHERE key='root_fingerprint'"
        ).fetchone()
        if stored is not None and str(stored[0]) != fingerprint:
            self.close()
            raise ValueError("catalog root does not match authorized corpus root")
        self._connection.execute(
            "INSERT OR IGNORE INTO meta(key,value) VALUES('root_fingerprint',?)",
            (fingerprint,),
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO meta(key,value) VALUES('scan_state','stale')"
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO meta(key,value) VALUES('derivation_state','stale')"
        )
        self._expected_derivation = _catalog_derivation_values()
        self._refresh_derivation_state()
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> CorpusCatalog:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _iter_paths(self) -> Iterator[tuple[str, Path]]:
        for directory, dirnames, filenames in os.walk(self.input_root, topdown=True):
            dirnames.sort(key=lambda value: value.casefold())
            for filename in sorted(filenames, key=lambda value: value.casefold()):
                if Path(filename).suffix.lower() not in {".mid", ".midi"}:
                    continue
                path = Path(directory) / filename
                try:
                    relative = path.resolve(strict=True).relative_to(self.input_root)
                except (OSError, ValueError):
                    # Keep the relative enumeration label for an auditable,
                    # sanitized failure; never follow an escaping target.
                    relative = path.relative_to(self.input_root)
                    yield relative.as_posix(), path
                    continue
                yield relative.as_posix(), path

    def _existing(self, relative_path: str, size: int, mtime_ns: int) -> bool:
        # Stat-only reuse cannot detect a same-size, same-mtime replacement.
        # A complete scan and matching derivation contract are prerequisites;
        # callers needing content verification must force a fresh catalog.
        row = self._connection.execute(
            "SELECT file_size,mtime_ns FROM files WHERE relative_path=?",
            (relative_path,),
        ).fetchone()
        return row is not None and int(row[0]) == size and int(row[1]) == mtime_ns

    def _refresh_derivation_state(self) -> None:
        metadata = dict(self._connection.execute("SELECT key,value FROM meta").fetchall())
        self._scan_state = metadata.get("scan_state", "stale")
        self._derivation_stale = any(
            metadata.get(key) != value for key, value in self._expected_derivation.items()
        )
        self._derivation_stale = self._derivation_stale or self._scan_state != "current"

    def _prepare_scan(self) -> bool:
        """Mark a scan incomplete before touching rows; return whether stat reuse is safe."""

        self._refresh_derivation_state()
        reuse_allowed = not self._derivation_stale
        # Recover an abandoned writer transaction before starting a new scan;
        # the committed in_progress marker remains the source of truth.
        self._connection.rollback()
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._connection.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES('scan_state','in_progress')"
            )
            self._connection.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES('derivation_state','in_progress')"
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        self._scan_state = "in_progress"
        self._derivation_stale = True
        return reuse_allowed

    def _write_error(
        self,
        relative_path: str,
        *,
        file_size: int,
        mtime_ns: int,
        source_digest: str,
        error: BaseException,
    ) -> None:
        self._connection.execute(
            """INSERT OR REPLACE INTO files(
                relative_path,file_size,mtime_ns,source_digest,status,error_code,error_detail,
                event_count,note_count,bars,stratum,fingerprint,facets_json,features_json,
                hvo_digest,grammar_digest
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                relative_path,
                file_size,
                mtime_ns,
                source_digest,
                "error",
                _error_code(error),
                type(error).__name__,
                0,
                0,
                0,
                _stratum(relative_path),
                "",
                "{}",
                "{}",
                "",
                "",
            ),
        )

    def _write_success(
        self,
        relative_path: str,
        *,
        file_size: int,
        mtime_ns: int,
        source_digest: str,
        parsed: object,
    ) -> None:
        hvo = derive_hvo(parsed)  # type: ignore[arg-type]
        features = derive_features(parsed, hvo)  # type: ignore[arg-type]
        grammar = derive_grammar(parsed, hvo)  # type: ignore[arg-type]
        facets = classify_facets(features, hvo, relative_path=relative_path)
        feature_json = features.model_dump(mode="json")
        facets_json = facets.model_dump(mode="json")
        hvo_json = hvo.model_dump(mode="json")
        grammar_json = grammar.model_dump(mode="json")
        fingerprint = sha256_hex(
            canonical_json({"facets": facets_json, "hvo": hvo_json, "features": feature_json})
        )
        values = features.values
        bars_value = values.get("bars")
        bars = int(bars_value.value) if bars_value and isinstance(bars_value.value, int) else 0
        self._connection.execute(
            """INSERT OR REPLACE INTO files(
                relative_path,file_size,mtime_ns,source_digest,status,error_code,error_detail,
                event_count,note_count,bars,stratum,fingerprint,facets_json,features_json,
                hvo_digest,grammar_digest
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                relative_path,
                file_size,
                mtime_ns,
                source_digest,
                "ok",
                None,
                None,
                len(parsed.events),  # type: ignore[attr-defined]
                len(parsed.note_events),  # type: ignore[attr-defined]
                bars,
                _stratum(relative_path),
                fingerprint,
                json.dumps(facets_json, ensure_ascii=False, separators=(",", ":")),
                json.dumps(feature_json, ensure_ascii=False, separators=(",", ":")),
                sha256_hex(canonical_json(hvo_json)),
                sha256_hex(canonical_json(grammar_json)),
            ),
        )

    def scan(self, *, retry_errors: bool = False) -> InventoryStats:
        started = time.perf_counter()
        reuse_allowed = self._prepare_scan()
        discovered = processed = reused = 0
        discovered_paths: set[str] = set()

        def iter_paths_safely() -> Iterator[tuple[str, Path]]:
            try:
                yield from self._iter_paths()
            except BaseException:
                # The in_progress marker was committed before enumeration, so
                # rolling back only discards partial row writes and preserves
                # the crash-safe incomplete state for the next opener.
                self._connection.rollback()
                raise

        for relative_path, path in iter_paths_safely():
            discovered += 1
            discovered_paths.add(relative_path)
            try:
                resolved = path.resolve(strict=True)
                if not resolved.is_relative_to(self.input_root):
                    size = 0
                    mtime_ns = 0
                    source_digest = "0" * 64
                    self._write_error(
                        relative_path,
                        file_size=size,
                        mtime_ns=mtime_ns,
                        source_digest=source_digest,
                        error=ValueError("authorized root escape"),
                    )
                    processed += 1
                    continue
                stat = resolved.stat()
                size = int(stat.st_size)
                mtime_ns = int(stat.st_mtime_ns)
                existing = self._connection.execute(
                    "SELECT status FROM files WHERE relative_path=?", (relative_path,)
                ).fetchone()
                if reuse_allowed and self._existing(relative_path, size, mtime_ns) and not (
                    retry_errors and existing is not None and existing[0] == "error"
                ):
                    reused += 1
                    continue
                if size > MAX_INPUT_BYTES:
                    raise GrooveMidiError("input size limit exceeded")
                source_digest, raw = _digest_file(resolved)
                parsed = parse_smf(raw)
                self._write_success(
                    relative_path,
                    file_size=size,
                    mtime_ns=mtime_ns,
                    source_digest=source_digest,
                    parsed=parsed,
                )
            except (OSError, ValueError, GrooveMidiError) as error:
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
                self._write_error(
                    relative_path,
                    file_size=size,
                    mtime_ns=mtime_ns,
                    source_digest=source_digest,
                    error=error,
                )
            processed += 1
            if processed % 256 == 0:
                self._connection.commit()
        if not self._connection.in_transaction:
            self._connection.execute("BEGIN IMMEDIATE")
        try:
            existing_paths = {
                str(row[0]) for row in self._connection.execute("SELECT relative_path FROM files")
            }
            for removed_path in existing_paths - discovered_paths:
                self._connection.execute(
                    "DELETE FROM files WHERE relative_path=?", (removed_path,)
                )
            self._connection.executemany(
                "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
                self._expected_derivation.items(),
            )
            self._connection.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES('scan_state','current')"
            )
            self._connection.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES('derivation_state','current')"
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        self._scan_state = "current"
        self._derivation_stale = False
        valid, failed, distinct = self._connection.execute(
            "SELECT SUM(status='ok'), SUM(status='error'), "
            "COUNT(DISTINCT CASE WHEN status='ok' THEN source_digest END) "
            "FROM files"
        ).fetchone()
        valid_count = int(valid or 0)
        failed_count = int(failed or 0)
        total_valid = valid_count
        return InventoryStats(
            discovered=discovered,
            processed=processed,
            reused=reused,
            valid=valid_count,
            failed=failed_count,
            deduplicated=total_valid - int(distinct or 0),
            elapsed_seconds=round(time.perf_counter() - started, 3),
        )

    def rows(self, *, status: str | None = None) -> tuple[InventoryRow, ...]:
        self._refresh_derivation_state()
        if self._scan_state != "current":
            raise ValueError("catalog scan is incomplete; scan required")
        if self._derivation_stale:
            raise ValueError("catalog derivation metadata is stale; scan required")
        statement = """SELECT relative_path,file_size,mtime_ns,source_digest,status,error_code,
               error_detail,event_count,note_count,bars,stratum,fingerprint,facets_json,
               features_json,hvo_digest,grammar_digest FROM files"""
        parameters: tuple[object, ...] = ()
        if status is not None:
            statement += " WHERE status=?"
            parameters = (status,)
        statement += " ORDER BY relative_path"
        records = self._connection.execute(statement, parameters).fetchall()
        result: list[InventoryRow] = []
        for row in records:
            raw_facets = json.loads(str(row[12]))
            facets = {
                str(key): tuple(str(item) for item in values)
                for key, values in raw_facets.get("values", {}).items()
            }
            features = json.loads(str(row[13])).get("values", {})
            result.append(
                InventoryRow(
                    relative_path=str(row[0]),
                    file_size=int(row[1]),
                    mtime_ns=int(row[2]),
                    source_digest=str(row[3]),
                    status=str(row[4]),
                    error_code=None if row[5] is None else str(row[5]),
                    error_detail=None if row[6] is None else str(row[6]),
                    event_count=int(row[7]),
                    note_count=int(row[8]),
                    bars=int(row[9]),
                    stratum=str(row[10]),
                    fingerprint=str(row[11]),
                    facets=facets,
                    features=features,
                    hvo_digest=str(row[14]),
                    grammar_digest=str(row[15]),
                )
            )
        return tuple(result)


def curate_representatives(
    catalog: CorpusCatalog,
    *,
    max_files: int = 2048,
    max_source_bytes: int = 24 * 1024 * 1024,
) -> tuple[InventoryRow, ...]:
    """Round-robin deterministic strata while respecting a conservative byte cap."""

    if max_files <= 0 or max_source_bytes <= 0:
        return ()
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
    return tuple(selected)


def _directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def build_curated_bundle(
    catalog: CorpusCatalog,
    output_dir: Path,
    *,
    max_files: int = 2048,
    max_bundle_bytes: int = 32 * 1024 * 1024,
) -> CuratedBuildResult:
    """Build two identical portable bundles, shrinking selection if required."""

    if max_files < 1 or max_files > 2048:
        raise ValueError("curated selection cap must be between one and 2048")
    if max_bundle_bytes < 1024:
        raise ValueError("curated bundle cap is too small")
    try:
        output_resolved = output_dir.resolve()
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
        inputs = [
            BuildInput(
                path=catalog.input_root / row.relative_path,
                source_kind="author",
                license_id="user-owned",
                redistribution="full",
            )
            for row in selected
        ]
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
            if (
                first_size <= max_bundle_bytes
                and second_size <= max_bundle_bytes
                and first.bundle_manifest_digest == second.bundle_manifest_digest
                and first.logical_index_digest == second.logical_index_digest
                and first.artifact_ids == second.artifact_ids
            ):
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


__all__ = [
    "CorpusCatalog",
    "CuratedBuildResult",
    "InventoryRow",
    "InventoryStats",
    "build_curated_bundle",
    "curate_representatives",
]
