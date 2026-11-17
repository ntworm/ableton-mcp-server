"""SQLite v2 seed writer and immutable, parameterized runtime adapter."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path
from typing import Any

from . import GrooveIndexInvalid, GrooveSchemaUnsupported
from .canonical import (
    bundle_manifest_digest,
    canonical_json,
    manifest_digest,
    sha256_hex,
)
from .constants import (
    FEATURES_SCHEMA_VERSION,
    GRAMMAR_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION_V3,
    INDEX_SCHEMA_VERSION,
    NORMALIZER_ID,
    PARSER_ID,
    RANKER_ID,
    RANKER_MANIFEST_DIGEST,
    SEED_SCHEMA_VERSION,
    SQLITE_MIN_VERSION,
    SQLITE_USER_VERSION,
    TAXONOMY_VERSION,
)
from .schema import (
    CompiledGrooveArtifactV1,
    FeaturesProjectionV1,
    GrammarProjectionV1,
    GrooveSeedBundleManifestV1,
    HvoProjectionV1,
)


class GrooveQueryRejected(GrooveIndexInvalid):
    """A query not present in the adapter's closed statement set."""


ProjectionModelV2 = HvoProjectionV1 | FeaturesProjectionV1 | GrammarProjectionV1


_ADAPTER_SQL: dict[str, str] = {
    "card": """SELECT artifact_id, schema_version, kind, corpus_id, build_id,
        license_id, redistribution, rights_level, capabilities_json,
        summary_json, format_json, timing_json, tracks_json, payload_size,
        payload_sha256, events_digest,
        provenance_digest, lineage_digest FROM artifacts WHERE artifact_id = ?""",
    "payload": """SELECT codec, blob, raw_size, compressed_size, sha256
        FROM payloads WHERE artifact_id = ?""",
    "provenance": """SELECT provenance_digest, source_digest, license_id, redistribution
        FROM provenance WHERE artifact_id = ?""",
    "lineage": """SELECT parent_artifact_id, relation, ordinal FROM lineage
        WHERE artifact_id = ? ORDER BY ordinal, parent_artifact_id""",
    "projection": """SELECT digest, codec, blob, raw_size, compressed_size
        FROM projections WHERE artifact_id = ? AND name = ? AND version = ?""",
    "projection_refs": """SELECT name, version, digest FROM projections
        WHERE artifact_id = ? ORDER BY name, version""",
    "facets": """SELECT axis, value, source, confidence FROM facets
        WHERE artifact_id = ? ORDER BY axis, value""",
    "features": """SELECT name, version, value, unit, status FROM features
        WHERE artifact_id = ? ORDER BY name, version""",
    "feature_norms": """SELECT feature_name, feature_version, min_value, max_value
        FROM feature_norms WHERE ranker_id = ? ORDER BY feature_name""",
    "all_cards": """SELECT artifact_id, schema_version, kind, corpus_id, build_id,
        license_id, redistribution, rights_level, capabilities_json,
        summary_json, payload_size, payload_sha256, events_digest,
        provenance_digest, lineage_digest FROM artifacts ORDER BY artifact_id""",
}

# The user_version is interpolated from the constant rather than written as a
# literal.  A literal here is invisible to any search for the identifier, and
# a bundle stamped with a stale one is rejected by its own reader.
_DDL = f"""
PRAGMA foreign_keys = ON;
PRAGMA user_version = {SQLITE_USER_VERSION};
CREATE TABLE index_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE artifacts (
  artifact_id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('source', 'generated', 'mapped')),
  corpus_id TEXT NOT NULL,
  build_id TEXT NOT NULL,
  license_id TEXT NOT NULL,
  redistribution TEXT NOT NULL CHECK (redistribution IN ('full', 'derived_only', 'blocked')),
  rights_level INTEGER NOT NULL CHECK (rights_level BETWEEN 0 AND 2),
  capabilities_json TEXT NOT NULL,
  summary_json TEXT NOT NULL,
  format_json TEXT NOT NULL,
  timing_json TEXT NOT NULL,
  tracks_json TEXT NOT NULL,
  payload_size INTEGER NOT NULL CHECK (payload_size >= 0),
  payload_sha256 TEXT NOT NULL,
  events_digest TEXT NOT NULL,
  provenance_digest TEXT NOT NULL,
  lineage_digest TEXT NOT NULL
);
CREATE TABLE facets (
  artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
  axis TEXT NOT NULL,
  value TEXT NOT NULL,
  source TEXT NOT NULL,
  confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
  PRIMARY KEY (artifact_id, axis, value)
);
CREATE TABLE features (
  artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  value REAL,
  unit TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('available', 'unavailable')),
  PRIMARY KEY (artifact_id, name, version),
  CHECK (status = 'unavailable' OR value IS NOT NULL)
);
CREATE TABLE feature_norms (
  ranker_id TEXT NOT NULL,
  feature_name TEXT NOT NULL,
  feature_version TEXT NOT NULL,
  min_value REAL NOT NULL,
  max_value REAL NOT NULL,
  PRIMARY KEY (ranker_id, feature_name, feature_version),
  CHECK (max_value > min_value)
);
CREATE TABLE projections (
  artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  digest TEXT NOT NULL,
  codec TEXT NOT NULL CHECK (codec IN ('zlib-raw-json-v1')),
  blob BLOB NOT NULL,
  raw_size INTEGER NOT NULL CHECK (raw_size >= 0),
  compressed_size INTEGER NOT NULL CHECK (compressed_size >= 0),
  PRIMARY KEY (artifact_id, name, version)
);
CREATE TABLE payloads (
  artifact_id TEXT PRIMARY KEY REFERENCES artifacts(artifact_id),
  codec TEXT NOT NULL CHECK (codec IN ('zlib-raw-midi-v1')),
  blob BLOB,
  raw_size INTEGER NOT NULL CHECK (raw_size >= 0),
  compressed_size INTEGER NOT NULL CHECK (compressed_size >= 0),
  sha256 TEXT NOT NULL,
  CHECK (blob IS NOT NULL OR raw_size = 0)
);
CREATE TABLE lineage (
  artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
  parent_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
  relation TEXT NOT NULL,
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  PRIMARY KEY (artifact_id, parent_artifact_id, relation, ordinal)
);
CREATE TABLE provenance (
  artifact_id TEXT PRIMARY KEY REFERENCES artifacts(artifact_id),
  provenance_digest TEXT NOT NULL,
  source_digest TEXT NOT NULL,
  license_id TEXT NOT NULL,
  redistribution TEXT NOT NULL CHECK (redistribution IN ('full', 'derived_only', 'blocked'))
);
CREATE INDEX facets_lookup ON facets(axis, value, artifact_id);
CREATE INDEX features_lookup ON features(name, version, value, artifact_id);
CREATE INDEX lineage_parent_lookup ON lineage(parent_artifact_id, artifact_id);
CREATE INDEX projections_lookup ON projections(artifact_id, name, version);
"""

_DIGEST_TABLES = (
    "artifacts",
    "facets",
    "features",
    "feature_norms",
    "projections",
    "payloads",
    "lineage",
    "provenance",
)
_MUTATING_SQL = re.compile(
    r"^\s*(CREATE|DROP|ALTER|INSERT|UPDATE|DELETE|REPLACE|VACUUM|REINDEX)\b",
    re.I,
)
_MUTATING_PRAGMA = re.compile(r"^\s*PRAGMA\s+\w+\s*=", re.I)


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest(), "size": len(value)}
    return value


def logical_index_digest(connection: sqlite3.Connection) -> str:
    tables: list[dict[str, object]] = []
    for table in _DIGEST_TABLES:
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()]
        order = ", ".join(columns)
        rows = connection.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
        tables.append(
            {
                "table": table,
                "columns": columns,
                "rows": [[_json_value(value) for value in row] for row in rows],
            }
        )
    return sha256_hex(canonical_json(tables))


def _write_manifest(bundle_dir: Path, manifest: GrooveSeedBundleManifestV1) -> None:
    (bundle_dir / "manifest.json").write_bytes(canonical_json(manifest.model_dump(mode="json")))


def write_index(
    bundle_dir: Path,
    artifacts: tuple[CompiledGrooveArtifactV1, ...] | list[CompiledGrooveArtifactV1],
    manifest: GrooveSeedBundleManifestV1,
) -> None:
    """Write the seed bundle database and the manifest that describes it."""

    ordered_artifacts = _ordered_artifacts(artifacts, manifest)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    db_path = bundle_dir / "index.sqlite"
    if db_path.exists():
        db_path.unlink()
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(_DDL)
        for artifact in ordered_artifacts:
            _write_artifact_card(connection, artifact, manifest)
            _write_artifact_values(connection, artifact)
            _write_artifact_blobs(connection, artifact)
            _write_artifact_lineage(connection, artifact)
        logical_digest = logical_index_digest(connection)
        manifest.logical_index_digest = logical_digest
        manifest_data = manifest.model_dump(mode="json")
        manifest.manifest_digest = manifest_digest(manifest_data)
        manifest.bundle_manifest_digest = bundle_manifest_digest(manifest.model_dump(mode="json"))
        _write_index_meta(connection, manifest, logical_digest)
        connection.commit()
    finally:
        connection.close()
    manifest.file_checksums = {"index.sqlite": sha256_hex(db_path.read_bytes())}
    _write_manifest(bundle_dir, manifest)


def _ordered_artifacts(
    artifacts: tuple[CompiledGrooveArtifactV1, ...] | list[CompiledGrooveArtifactV1],
    manifest: GrooveSeedBundleManifestV1,
) -> tuple[CompiledGrooveArtifactV1, ...]:
    """Return the artifacts in manifest order and reject duplicate identifiers."""

    artifacts_by_id: dict[str, CompiledGrooveArtifactV1] = {}
    for artifact in artifacts:
        artifact_id = str(artifact.artifact.artifact_id)
        if artifact_id in artifacts_by_id:
            raise GrooveIndexInvalid("duplicate artifact ID supplied to index writer")
        artifacts_by_id[artifact_id] = artifact
    manifest_artifact_ids = tuple(str(item) for item in manifest.artifact_ids)
    if len(set(manifest_artifact_ids)) != len(manifest_artifact_ids):
        raise GrooveIndexInvalid("duplicate artifact ID in manifest")
    if set(artifacts_by_id) != set(manifest_artifact_ids):
        raise GrooveIndexInvalid("artifacts do not match manifest artifact IDs")
    return tuple(artifacts_by_id[item] for item in manifest_artifact_ids)


def _write_artifact_card(
    connection: sqlite3.Connection,
    artifact: CompiledGrooveArtifactV1,
    manifest: GrooveSeedBundleManifestV1,
) -> None:
    """Write the artifact card row of one compiled artifact."""

    item = artifact.artifact
    apply_allowed = artifact.capabilities.get("apply", False)
    connection.execute(
        """INSERT INTO artifacts VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )""",
        (
            str(item.artifact_id),
            item.schema_version,
            item.kind,
            manifest.corpus_id,
            manifest.build_id,
            artifact.license_id,
            artifact.redistribution,
            artifact.rights_level,
            canonical_json(artifact.capabilities).decode("utf-8"),
            canonical_json(artifact.summary).decode("utf-8"),
            canonical_json(item.format.model_dump(mode="json")).decode("utf-8"),
            canonical_json(item.timing).decode("utf-8"),
            canonical_json(
                [track.model_dump(mode="json") for track in item.tracks]
            ).decode("utf-8"),
            item.payload.raw_size if apply_allowed else 0,
            item.payload.sha256,
            item.events_digest,
            artifact.provenance_digest,
            sha256_hex(canonical_json(item.lineage)),
        ),
    )


def _write_artifact_values(
    connection: sqlite3.Connection,
    artifact: CompiledGrooveArtifactV1,
) -> None:
    """Write the facet and feature rows of one compiled artifact."""

    item = artifact.artifact
    connection.executemany(
        "INSERT INTO facets VALUES (?, ?, ?, ?, ?)",
        [
            (str(item.artifact_id), row["axis"], row["value"], row["source"], row["confidence"])
            for row in artifact.facets
        ],
    )
    connection.executemany(
        "INSERT INTO features VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                str(item.artifact_id), row["name"], row["version"],
                row["value"], row["unit"], row["status"],
            )
            for row in artifact.features
        ],
    )


def _write_artifact_blobs(
    connection: sqlite3.Connection,
    artifact: CompiledGrooveArtifactV1,
) -> None:
    """Write the projection and payload rows of one compiled artifact."""

    item = artifact.artifact
    apply_allowed = artifact.capabilities.get("apply", False)
    connection.executemany(
        "INSERT INTO projections VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                str(item.artifact_id), row["name"], row["version"], row["digest"],
                row["codec"], row["blob"], row["raw_size"], row["compressed_size"],
            )
            for row in artifact.projections
        ],
    )
    connection.execute(
        "INSERT INTO payloads VALUES (?, ?, ?, ?, ?, ?)",
        (
            str(item.artifact_id), item.payload.codec,
            item.payload.blob if apply_allowed else None,
            item.payload.raw_size if apply_allowed else 0,
            item.payload.compressed_size if apply_allowed else 0,
            item.payload.sha256,
        ),
    )


def _write_artifact_lineage(
    connection: sqlite3.Connection,
    artifact: CompiledGrooveArtifactV1,
) -> None:
    """Write the lineage and provenance rows of one compiled artifact."""

    item = artifact.artifact
    connection.executemany(
        "INSERT INTO lineage VALUES (?, ?, ?, ?)",
        [
            (
                str(item.artifact_id), row["parent_artifact_id"], row["relation"], row["ordinal"],
            )
            for row in artifact.lineage_rows
        ],
    )
    connection.execute(
        "INSERT INTO provenance VALUES (?, ?, ?, ?, ?)",
        (
            str(item.artifact_id), artifact.provenance_digest, artifact.source_digest,
            artifact.license_id, artifact.redistribution,
        ),
    )


def _write_index_meta(
    connection: sqlite3.Connection,
    manifest: GrooveSeedBundleManifestV1,
    logical_digest: str,
) -> None:
    """Write the required metadata rows of the index."""

    required_meta = {
        "schema_version": INDEX_SCHEMA_VERSION, "seed_schema": manifest.seed_schema,
        "seed_bundle_id": manifest.seed_bundle_id, "build_id": manifest.build_id,
        "parser_id": manifest.parser_id, "normalizer_id": manifest.normalizer_id,
        "manifest_digest": manifest.manifest_digest, "logical_index_digest": logical_digest,
        "ranker_id": manifest.ranker_id,
        "ranker_manifest_digest": manifest.ranker_manifest_digest,
        "projection_versions": canonical_json(manifest.projection_versions).decode("utf-8"),
        "sqlite_min_version": SQLITE_MIN_VERSION,
    }
    connection.executemany(
        "INSERT INTO index_meta(key, value) VALUES (?, ?)",
        required_meta.items(),
    )


def _expected_projection_versions() -> dict[str, str]:
    """Return the projection versions a current seed bundle must declare."""

    return {
        "features": FEATURES_SCHEMA_VERSION, "grammar": GRAMMAR_SCHEMA_VERSION,
        "hvo": HVO_SCHEMA_VERSION, "hvo_v3": HVO_SCHEMA_VERSION_V3,
        "taxonomy": TAXONOMY_VERSION,
    }


def _validate_bundle_versions(
    meta: dict[str, str],
    manifest: GrooveSeedBundleManifestV1,
) -> None:
    """Reject a bundle whose schema or derivation versions are not supported."""

    expected = {
        "schema_version": INDEX_SCHEMA_VERSION, "seed_schema": SEED_SCHEMA_VERSION,
        "parser_id": PARSER_ID, "normalizer_id": NORMALIZER_ID,
        "ranker_id": RANKER_ID, "ranker_manifest_digest": RANKER_MANIFEST_DIGEST,
    }
    projections = _expected_projection_versions()
    if (
        any(meta[key] != value for key, value in expected.items())
        or meta["sqlite_min_version"] != SQLITE_MIN_VERSION
        or any(getattr(manifest, key) != value for key, value in expected.items())
        or manifest.projection_versions != projections
        or meta["projection_versions"] != canonical_json(projections).decode("utf-8")
    ):
        raise GrooveSchemaUnsupported(
            "seed bundle schema or derivation versions are unsupported"
        )


def _validate_bundle_identity(
    meta: dict[str, str],
    manifest: GrooveSeedBundleManifestV1,
) -> None:
    """Reject a bundle whose stored identity does not match its manifest."""

    if (
        meta["seed_bundle_id"] != manifest.seed_bundle_id or meta["build_id"] != manifest.build_id
    ):
        raise GrooveIndexInvalid("index metadata does not match manifest")
    if meta["manifest_digest"] != manifest.manifest_digest:
        raise GrooveIndexInvalid("manifest digest mismatch")
    if meta["logical_index_digest"] != manifest.logical_index_digest:
        raise GrooveIndexInvalid("logical index digest mismatch")


def _validate_index_rows(
    connection: sqlite3.Connection,
    meta: dict[str, str],
    manifest: GrooveSeedBundleManifestV1,
) -> None:
    """Reject a bundle whose stored rows or digests do not match its manifest."""

    if logical_index_digest(connection) != meta["logical_index_digest"]:
        raise GrooveIndexInvalid("index rows changed")
    manifest_data = manifest.model_dump(mode="json")
    if manifest_digest(manifest_data) != manifest.manifest_digest:
        raise GrooveIndexInvalid("manifest integrity mismatch")
    if bundle_manifest_digest(manifest_data) != manifest.bundle_manifest_digest:
        raise GrooveIndexInvalid("bundle manifest digest mismatch")
    stored_artifact_ids = tuple(
        str(row[0])
        for row in connection.execute(
            "SELECT artifact_id FROM artifacts ORDER BY rowid"
        ).fetchall()
    )
    manifest_artifact_ids = tuple(str(item) for item in manifest.artifact_ids)
    if stored_artifact_ids != manifest_artifact_ids:
        raise GrooveIndexInvalid("SQLite artifact IDs do not match manifest")


# The reader names live in the split module.  The import is last so that the
# reader finds the constants and the helpers it shares with this module.
from . import index_readonly  # noqa: E402

ReadonlyGrooveIndex = index_readonly.ReadonlyGrooveIndex
_ReadonlyConnection = index_readonly._ReadonlyConnection
open_readonly_index = index_readonly.open_readonly_index
