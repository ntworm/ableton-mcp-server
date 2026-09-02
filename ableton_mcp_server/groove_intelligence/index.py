"""SQLite v2 seed writer and immutable, parameterized runtime adapter."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from . import GrooveIndexInvalid, GrooveIndexReadOnlyError, GrooveSchemaUnsupported
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
    MAX_COMPRESSED_BLOB,
    MAX_RAW_BLOB,
    NORMALIZER_ID,
    PARSER_ID,
    PROJECTION_CODEC,
    RANKER_ID,
    RANKER_MANIFEST_DIGEST,
    SEED_SCHEMA_VERSION,
    SQLITE_MIN_VERSION,
    SQLITE_USER_VERSION,
)
from .midi_lossless import decompress_bounded
from .schema import (
    ArtifactId,
    CompiledGrooveArtifactV1,
    CompressedBlobV1,
    FeaturesProjectionV1,
    GrammarProjectionV1,
    GrooveSeedBundleManifestV1,
    HvoProjectionV1,
    MidiArtifactV1,
    ProjectionRefV1,
    SmfFormatV1,
    TrackInfoV1,
)
from .taxonomy import TAXONOMY_VERSION


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
    ordered_artifacts = tuple(artifacts_by_id[item] for item in manifest_artifact_ids)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    db_path = bundle_dir / "index.sqlite"
    if db_path.exists():
        db_path.unlink()
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(_DDL)
        for artifact in ordered_artifacts:
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
            connection.executemany(
                "INSERT INTO facets VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        str(item.artifact_id),
                        row["axis"],
                        row["value"],
                        row["source"],
                        row["confidence"],
                    )
                    for row in artifact.facets
                ],
            )
            connection.executemany(
                "INSERT INTO features VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        str(item.artifact_id),
                        row["name"],
                        row["version"],
                        row["value"],
                        row["unit"],
                        row["status"],
                    )
                    for row in artifact.features
                ],
            )
            connection.executemany(
                "INSERT INTO projections VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        str(item.artifact_id),
                        row["name"],
                        row["version"],
                        row["digest"],
                        row["codec"],
                        row["blob"],
                        row["raw_size"],
                        row["compressed_size"],
                    )
                    for row in artifact.projections
                ],
            )
            connection.execute(
                "INSERT INTO payloads VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(item.artifact_id),
                    item.payload.codec,
                    item.payload.blob if apply_allowed else None,
                    item.payload.raw_size if apply_allowed else 0,
                    item.payload.compressed_size if apply_allowed else 0,
                    item.payload.sha256,
                ),
            )
            connection.executemany(
                "INSERT INTO lineage VALUES (?, ?, ?, ?)",
                [
                    (
                        str(item.artifact_id),
                        row["parent_artifact_id"],
                        row["relation"],
                        row["ordinal"],
                    )
                    for row in artifact.lineage_rows
                ],
            )
            connection.execute(
                "INSERT INTO provenance VALUES (?, ?, ?, ?, ?)",
                (
                    str(item.artifact_id),
                    artifact.provenance_digest,
                    artifact.source_digest,
                    artifact.license_id,
                    artifact.redistribution,
                ),
            )
        logical_digest = logical_index_digest(connection)
        manifest.logical_index_digest = logical_digest
        manifest_data = manifest.model_dump(mode="json")
        manifest.manifest_digest = manifest_digest(manifest_data)
        manifest.bundle_manifest_digest = bundle_manifest_digest(
            manifest.model_dump(mode="json")
        )
        required_meta = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "seed_schema": manifest.seed_schema,
            "seed_bundle_id": manifest.seed_bundle_id,
            "build_id": manifest.build_id,
            "parser_id": manifest.parser_id,
            "normalizer_id": manifest.normalizer_id,
            "manifest_digest": manifest.manifest_digest,
            "logical_index_digest": logical_digest,
            "ranker_id": manifest.ranker_id,
            "ranker_manifest_digest": manifest.ranker_manifest_digest,
            "projection_versions": canonical_json(manifest.projection_versions).decode("utf-8"),
            "sqlite_min_version": SQLITE_MIN_VERSION,
        }
        connection.executemany(
            "INSERT INTO index_meta(key, value) VALUES (?, ?)",
            required_meta.items(),
        )
        connection.commit()
    finally:
        connection.close()
    manifest.file_checksums = {"index.sqlite": sha256_hex(db_path.read_bytes())}
    _write_manifest(bundle_dir, manifest)


class _ReadonlyConnection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def execute(self, sql: str, parameters: tuple[object, ...] = ()) -> sqlite3.Cursor:
        if _MUTATING_SQL.search(sql) or _MUTATING_PRAGMA.search(sql):
            raise GrooveIndexReadOnlyError("index connection is read-only")
        try:
            return self._connection.execute(sql, parameters)
        except sqlite3.OperationalError as error:
            if "readonly" in str(error).lower() or "read-only" in str(error).lower():
                raise GrooveIndexReadOnlyError("index connection is read-only") from error
            raise

    def executemany(
        self,
        sql: str,
        parameters: Any,
    ) -> sqlite3.Cursor:
        if _MUTATING_SQL.search(sql) or _MUTATING_PRAGMA.search(sql):
            raise GrooveIndexReadOnlyError("index connection is read-only")
        try:
            return self._connection.executemany(sql, parameters)
        except sqlite3.OperationalError as error:
            if "readonly" in str(error).lower() or "read-only" in str(error).lower():
                raise GrooveIndexReadOnlyError("index connection is read-only") from error
            raise

    def close(self) -> None:
        self._connection.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


class ReadonlyGrooveIndex:
    def __init__(
        self,
        *,
        connection: _ReadonlyConnection,
        manifest: GrooveSeedBundleManifestV1,
        meta: dict[str, str],
    ) -> None:
        self.connection = connection
        self.manifest = manifest
        self.meta = meta
        self.user_version = int(meta.get("user_version", SQLITE_USER_VERSION))

    def close(self) -> None:
        self.connection.close()

    def _execute_allowlisted(
        self, operation: str, parameters: tuple[object, ...] = ()
    ) -> sqlite3.Cursor:
        statement = _ADAPTER_SQL.get(operation)
        if statement is None:
            raise GrooveQueryRejected("statement not allowlisted")
        return self.connection.execute(statement, parameters)

    def execute_for_test(self, sql: str, parameters: tuple[object, ...] = ()) -> sqlite3.Cursor:
        """Deliberately expose a rejecting test hook, never an SQL escape hatch."""

        del sql, parameters
        raise GrooveQueryRejected("statement not allowlisted")

    def card_row(self, artifact_id: str) -> dict[str, object] | None:
        row = self._execute_allowlisted("card", (artifact_id,)).fetchone()
        if row is None:
            return None
        keys = [
            column[1]
            for column in self.connection.execute("PRAGMA table_info(artifacts)").fetchall()
        ]
        result = dict(zip(keys, row, strict=True))
        result["capabilities"] = json.loads(str(result.pop("capabilities_json")))
        result["summary"] = json.loads(str(result.pop("summary_json")))
        return result

    @staticmethod
    def _projection_identity(projection_id: str) -> tuple[str, str]:
        names = {
            HVO_SCHEMA_VERSION: ("hvo", HVO_SCHEMA_VERSION),
            HVO_SCHEMA_VERSION_V3: ("hvo_v3", HVO_SCHEMA_VERSION_V3),
            FEATURES_SCHEMA_VERSION: ("features", FEATURES_SCHEMA_VERSION),
            GRAMMAR_SCHEMA_VERSION: ("grammar", GRAMMAR_SCHEMA_VERSION),
            "hvo": ("hvo", HVO_SCHEMA_VERSION),
            "hvo_v3": ("hvo_v3", HVO_SCHEMA_VERSION_V3),
            "features": ("features", FEATURES_SCHEMA_VERSION),
            "grammar": ("grammar", GRAMMAR_SCHEMA_VERSION),
        }
        try:
            return names[projection_id]
        except KeyError as error:
            raise GrooveIndexInvalid("projection id is unsupported") from error

    def projection(self, artifact_id: str, name: str, version: str) -> bytes:
        row = self._execute_allowlisted("projection", (artifact_id, name, version)).fetchone()
        if row is None:
            raise GrooveIndexInvalid("projection is not present")
        digest, codec, blob, raw_size, compressed_size = row
        if codec != PROJECTION_CODEC or not isinstance(blob, bytes):
            raise GrooveIndexInvalid("projection codec is unsupported")
        if compressed_size != len(blob) or compressed_size > MAX_COMPRESSED_BLOB:
            raise GrooveIndexInvalid("projection size is invalid")
        payload = decompress_bounded(
            blob,
            codec=codec,
            raw_size=int(raw_size),
            max_compressed=MAX_COMPRESSED_BLOB,
            max_raw=MAX_RAW_BLOB,
        )
        if sha256_hex(payload) != digest:
            raise GrooveIndexInvalid("projection digest mismatch")
        return payload

    def _artifact_events_digest(self, artifact_id: str) -> str:
        row = self._execute_allowlisted("card", (artifact_id,)).fetchone()
        if row is None:
            raise GrooveIndexInvalid("artifact is not present")
        return str(row[15])

    def _validate_projection_payload(
        self,
        artifact_id: str,
        projection_id: str,
        payload: bytes,
    ) -> ProjectionModelV2:
        _name, version = self._projection_identity(projection_id)
        try:
            value = json.loads(payload.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("projection is not an object")
            projection: ProjectionModelV2
            if version in (HVO_SCHEMA_VERSION, HVO_SCHEMA_VERSION_V3):
                projection = HvoProjectionV1.model_validate(value)
            elif version == FEATURES_SCHEMA_VERSION:
                projection = FeaturesProjectionV1.model_validate(value)
            else:
                projection = GrammarProjectionV1.model_validate(value)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise GrooveIndexInvalid("projection JSON is invalid") from error
        if projection.schema_version != version:
            raise GrooveIndexInvalid("projection schema version mismatch")
        if projection.source_events_digest != self._artifact_events_digest(artifact_id):
            raise GrooveIndexInvalid("projection source_events_digest mismatch")
        return projection

    def load_projection(self, artifact_id: str, projection_id: str) -> ProjectionModelV2:
        name, version = self._projection_identity(projection_id)
        payload = self.projection(artifact_id, name, version)
        return self._validate_projection_payload(artifact_id, version, payload)

    def _validate_all_projections(self) -> None:
        rows = self.connection.execute(
            "SELECT artifact_id, name, version FROM projections "
            "ORDER BY artifact_id, name, version"
        ).fetchall()
        for artifact_id, name, version in rows:
            projection_name, normalized_version = self._projection_identity(str(version))
            if str(version) != normalized_version or str(name) != projection_name:
                raise GrooveIndexInvalid("projection reference is inconsistent")
            self.load_projection(str(artifact_id), normalized_version)

    def load_artifact(self, artifact_id: str) -> MidiArtifactV1:
        row = self._execute_allowlisted("card", (artifact_id,)).fetchone()
        if row is None:
            raise GrooveIndexInvalid("artifact is not present")
        (
            stored_id,
            schema_version,
            kind,
            corpus_id,
            build_id,
            license_id,
            redistribution,
            rights_level,
            capabilities_json,
            summary_json,
            format_json,
            timing_json,
            tracks_json,
            _payload_size,
            payload_sha256,
            events_digest,
            provenance_digest,
            _lineage_digest,
        ) = row
        payload_row = self._execute_allowlisted("payload", (artifact_id,)).fetchone()
        if payload_row is None:
            raise GrooveIndexInvalid("artifact payload row is missing")
        codec, blob, raw_size, compressed_size, payload_digest = payload_row
        if codec != "zlib-raw-midi-v1":
            raise GrooveIndexInvalid("payload codec is unsupported")
        if not isinstance(blob, bytes):
            if int(raw_size) != 0 or int(compressed_size) != 0:
                raise GrooveIndexInvalid("derived payload row is invalid")
            blob = b""
        elif int(compressed_size) != len(blob) or int(compressed_size) > MAX_COMPRESSED_BLOB:
            raise GrooveIndexInvalid("payload size is invalid")
        if str(payload_digest) != str(payload_sha256):
            raise GrooveIndexInvalid("payload digest mismatch")
        references_list: list[ProjectionRefV1] = []
        for name, version, digest in self._execute_allowlisted(
            "projection_refs", (artifact_id,)
        ).fetchall():
            projection_name = str(name)
            projection_version = str(version)
            expected_version = {
                "hvo": HVO_SCHEMA_VERSION,
                "hvo_v3": HVO_SCHEMA_VERSION_V3,
                "features": FEATURES_SCHEMA_VERSION,
                "grammar": GRAMMAR_SCHEMA_VERSION,
            }.get(projection_name)
            if expected_version != projection_version:
                raise GrooveSchemaUnsupported("artifact projection reference is unsupported")
            references_list.append(
                ProjectionRefV1(
                    name=projection_name,
                    version=projection_version,
                    digest=str(digest),
                )
            )
        references = tuple(references_list)
        provenance_row = self._execute_allowlisted("provenance", (artifact_id,)).fetchone()
        if provenance_row is None:
            raise GrooveIndexInvalid("provenance row is missing")
        stored_provenance_digest, source_digest, stored_license, stored_redistribution = (
            provenance_row
        )
        if str(stored_provenance_digest) != str(provenance_digest):
            raise GrooveIndexInvalid("provenance digest mismatch")
        lineage_rows = self._execute_allowlisted("lineage", (artifact_id,)).fetchall()
        lineage = {
            "parent_artifact_ids": [str(parent) for parent, _relation, _ordinal in lineage_rows],
            "relations": [str(relation) for _parent, relation, _ordinal in lineage_rows],
            "ordinals": [int(ordinal) for _parent, _relation, ordinal in lineage_rows],
        }
        facets: dict[str, list[str]] = {}
        for axis, value, _source, _confidence in self._execute_allowlisted(
            "facets", (artifact_id,)
        ).fetchall():
            facets.setdefault(str(axis), []).append(str(value))
        features: dict[str, object] = {}
        for name, _version, value, _unit, status in self._execute_allowlisted(
            "features", (artifact_id,)
        ).fetchall():
            features[str(name)] = value if status == "available" else None
        try:
            capabilities = json.loads(str(capabilities_json))
            summary = json.loads(str(summary_json))
            format_value = SmfFormatV1.model_validate(json.loads(str(format_json)))
            timing_value = json.loads(str(timing_json))
            tracks_value = json.loads(str(tracks_json))
            if not isinstance(timing_value, dict) or not isinstance(tracks_value, list):
                raise ValueError("artifact timing or tracks metadata is invalid")
            tracks = tuple(TrackInfoV1.model_validate(item) for item in tracks_value)
        except json.JSONDecodeError as error:
            raise GrooveIndexInvalid("card metadata is invalid") from error
        except (TypeError, ValueError) as error:
            raise GrooveIndexInvalid("artifact format or timing metadata is invalid") from error
        metadata = {
            "corpus_id": str(corpus_id),
            "build_id": str(build_id),
            "license_id": str(stored_license),
            "redistribution": str(stored_redistribution),
            "rights_level": int(rights_level),
            "capabilities": capabilities,
            "summary": summary,
            "facets": facets,
            "features": features,
            "provenance_digest": str(stored_provenance_digest),
            "source_digest": str(source_digest),
        }
        return MidiArtifactV1(
            schema_version=str(schema_version),
            artifact_id=ArtifactId(str(stored_id)),
            kind=str(kind),  # type: ignore[arg-type]
            format=format_value,
            timing=timing_value,
            tracks=tracks,
            payload=CompressedBlobV1(
                codec=str(codec),
                raw_size=int(raw_size),
                compressed_size=int(compressed_size),
                sha256=str(payload_digest),
                blob=blob,
            ),
            events_digest=str(events_digest),
            provenance=metadata,
            lineage=lineage,
            projections=references,
        )

    def search_rows(self, criteria: Any) -> tuple[dict[str, object], ...]:
        """Return bounded card/features rows using only fixed statements."""

        del criteria
        rows = self._execute_allowlisted("all_cards").fetchall()
        result: list[dict[str, object]] = []
        for row in rows:
            (
                artifact_id,
                schema_version,
                kind,
                corpus_id,
                build_id,
                license_id,
                redistribution,
                rights_level,
                capabilities_json,
                summary_json,
                payload_size,
                payload_sha256,
                events_digest,
                provenance_digest,
                lineage_digest,
            ) = row
            facets = self._execute_allowlisted("facets", (artifact_id,)).fetchall()
            features = self._execute_allowlisted("features", (artifact_id,)).fetchall()
            projections = self._execute_allowlisted("projection_refs", (artifact_id,)).fetchall()
            result.append(
                {
                    "artifact_id": str(artifact_id),
                    "schema_version": str(schema_version),
                    "kind": str(kind),
                    "corpus_id": str(corpus_id),
                    "build_id": str(build_id),
                    "license_id": str(license_id),
                    "redistribution": str(redistribution),
                    "rights_level": int(rights_level),
                    "capabilities": json.loads(str(capabilities_json)),
                    "summary": json.loads(str(summary_json)),
                    "payload_size": int(payload_size),
                    "payload_sha256": str(payload_sha256),
                    "events_digest": str(events_digest),
                    "provenance_digest": str(provenance_digest),
                    "lineage_digest": str(lineage_digest),
                    "facets": tuple(
                        {
                            "axis": str(axis),
                            "value": str(value),
                            "source": str(source),
                            "confidence": float(confidence),
                        }
                        for axis, value, source, confidence in facets
                    ),
                    "features": tuple(
                        {
                            "name": str(name),
                            "version": str(version),
                            "value": value,
                            "unit": str(unit),
                            "status": str(status),
                        }
                        for name, version, value, unit, status in features
                    ),
                    "projections": tuple(
                        {"name": str(name), "version": str(version), "digest": str(digest)}
                        for name, version, digest in projections
                    ),
                }
            )
        return tuple(result)


def open_readonly_index(bundle_dir: Path) -> ReadonlyGrooveIndex:
    try:
        manifest = GrooveSeedBundleManifestV1.model_validate_json(
            (bundle_dir / "manifest.json").read_text(encoding="utf-8")
        )
        db_path = (bundle_dir / "index.sqlite").resolve(strict=True)
    except (OSError, ValueError) as error:
        raise GrooveIndexInvalid("seed bundle manifest or database is unavailable") from error
    expected_checksum = manifest.file_checksums.get("index.sqlite")
    if not expected_checksum:
        raise GrooveIndexInvalid("index.sqlite checksum is missing")
    try:
        actual_checksum = sha256_hex(db_path.read_bytes())
    except OSError as error:
        raise GrooveIndexInvalid("index.sqlite checksum cannot be read") from error
    if actual_checksum != expected_checksum:
        raise GrooveIndexInvalid("index.sqlite checksum mismatch")
    if sqlite3.sqlite_version_info < (3, 40, 0):
        raise GrooveSchemaUnsupported("SQLite 3.40 or newer is required")
    connection = sqlite3.connect(
        f"file:{db_path.as_posix()}?mode=ro&immutable=1",
        uri=True,
        timeout=0.25,
    )
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA foreign_keys=ON")
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if user_version != SQLITE_USER_VERSION:
            raise GrooveSchemaUnsupported(
                f"SQLite user_version is not {SQLITE_USER_VERSION}"
            )
        meta = dict(connection.execute("SELECT key, value FROM index_meta").fetchall())
        meta["user_version"] = str(user_version)
        required = {
            "schema_version",
            "seed_schema",
            "seed_bundle_id",
            "build_id",
            "parser_id",
            "manifest_digest",
            "logical_index_digest",
            "ranker_id",
            "ranker_manifest_digest",
            "normalizer_id",
            "projection_versions",
            "sqlite_min_version",
        }
        if not required.issubset(meta):
            raise GrooveIndexInvalid("index metadata is incomplete")
        if (
            meta["schema_version"] != INDEX_SCHEMA_VERSION
            or meta["seed_schema"] != SEED_SCHEMA_VERSION
            or meta["parser_id"] != PARSER_ID
            or meta["normalizer_id"] != NORMALIZER_ID
            or manifest.seed_schema != SEED_SCHEMA_VERSION
            or manifest.schema_version != INDEX_SCHEMA_VERSION
            or manifest.parser_id != PARSER_ID
            or manifest.normalizer_id != NORMALIZER_ID
            or manifest.projection_versions
            != {
                "features": FEATURES_SCHEMA_VERSION,
                "grammar": GRAMMAR_SCHEMA_VERSION,
                "hvo": HVO_SCHEMA_VERSION,
                "hvo_v3": HVO_SCHEMA_VERSION_V3,
                "taxonomy": TAXONOMY_VERSION,
            }
            or meta["projection_versions"]
            != canonical_json(
                {
                    "features": FEATURES_SCHEMA_VERSION,
                    "grammar": GRAMMAR_SCHEMA_VERSION,
                    "hvo": HVO_SCHEMA_VERSION,
                    "hvo_v3": HVO_SCHEMA_VERSION_V3,
                    "taxonomy": TAXONOMY_VERSION,
                }
            ).decode("utf-8")
            or meta["ranker_id"] != RANKER_ID
            or meta["ranker_manifest_digest"] != RANKER_MANIFEST_DIGEST
            or meta["sqlite_min_version"] != SQLITE_MIN_VERSION
            or manifest.ranker_id != RANKER_ID
            or manifest.ranker_manifest_digest != RANKER_MANIFEST_DIGEST
        ):
            raise GrooveSchemaUnsupported(
                "seed bundle schema or derivation versions are unsupported"
            )
        if (
            meta["seed_bundle_id"] != manifest.seed_bundle_id
            or meta["build_id"] != manifest.build_id
        ):
            raise GrooveIndexInvalid("index metadata does not match manifest")
        if meta["manifest_digest"] != manifest.manifest_digest:
            raise GrooveIndexInvalid("manifest digest mismatch")
        if meta["logical_index_digest"] != manifest.logical_index_digest:
            raise GrooveIndexInvalid("logical index digest mismatch")
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
        index = ReadonlyGrooveIndex(
            connection=_ReadonlyConnection(connection),
            manifest=manifest,
            meta=meta,
        )
        index._validate_all_projections()
        return index
    except Exception:
        connection.close()
        raise
