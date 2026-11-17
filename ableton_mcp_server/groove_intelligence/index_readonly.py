"""Immutable, parameterized runtime adapter for the SQLite groove index."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from . import GrooveIndexInvalid, GrooveIndexReadOnlyError, GrooveSchemaUnsupported
from .canonical import sha256_hex
from .constants import (
    FEATURES_SCHEMA_VERSION,
    GRAMMAR_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION_V3,
    MAX_COMPRESSED_BLOB,
    MAX_RAW_BLOB,
    PROJECTION_CODEC,
    SQLITE_USER_VERSION,
)
from .index import (
    _ADAPTER_SQL,
    _MUTATING_PRAGMA,
    _MUTATING_SQL,
    GrooveQueryRejected,
    ProjectionModelV2,
    _validate_bundle_identity,
    _validate_bundle_versions,
    _validate_index_rows,
)
from .midi_lossless import decompress_bounded
from .schema import (
    ArtifactId,
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
            blob, codec=codec, raw_size=int(raw_size),
            max_compressed=MAX_COMPRESSED_BLOB, max_raw=MAX_RAW_BLOB,
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
        """Load one artifact card and validate every stored part of it."""

        row = self._execute_allowlisted("card", (artifact_id,)).fetchone()
        if row is None:
            raise GrooveIndexInvalid("artifact is not present")
        (
            stored_id, schema_version, kind, corpus_id, build_id, license_id,
            redistribution, rights_level, capabilities_json, summary_json,
            format_json, timing_json, tracks_json, _payload_size, payload_sha256,
            events_digest, provenance_digest, _lineage_digest,
        ) = row
        blob, codec, raw_size, compressed_size, payload_digest = self._load_payload(
            artifact_id, payload_sha256
        )
        references = self._load_projection_references(artifact_id)
        (
            stored_provenance_digest, source_digest, stored_license,
            stored_redistribution,
        ) = self._load_provenance(artifact_id, provenance_digest)
        lineage = self._load_lineage(artifact_id)
        facets = self._load_facets(artifact_id)
        features = self._load_features(artifact_id)
        capabilities, summary, format_value, timing_value, tracks = self._load_card_metadata(
            capabilities_json, summary_json, format_json, timing_json, tracks_json
        )
        metadata = {
            "corpus_id": str(corpus_id), "build_id": str(build_id),
            "license_id": stored_license, "redistribution": stored_redistribution,
            "rights_level": int(rights_level), "capabilities": capabilities,
            "summary": summary, "facets": facets, "features": features,
            "provenance_digest": stored_provenance_digest, "source_digest": source_digest,
        }
        return MidiArtifactV1(
            schema_version=str(schema_version),
            artifact_id=ArtifactId(str(stored_id)),
            kind=str(kind),  # type: ignore[arg-type]
            format=format_value,
            timing=timing_value,
            tracks=tracks,
            payload=CompressedBlobV1(
                codec=codec, raw_size=raw_size, compressed_size=compressed_size,
                sha256=payload_digest, blob=blob,
            ),
            events_digest=str(events_digest),
            provenance=metadata,
            lineage=lineage,
            projections=references,
        )

    def _load_payload(
        self, artifact_id: str, payload_sha256: object
    ) -> tuple[bytes, str, int, int, str]:
        """Read and validate the stored payload blob of one artifact."""

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
        return blob, str(codec), int(raw_size), int(compressed_size), str(payload_digest)

    def _load_projection_references(self, artifact_id: str) -> tuple[ProjectionRefV1, ...]:
        """Read the projection references of one artifact."""

        references_list: list[ProjectionRefV1] = []
        for name, version, digest in self._execute_allowlisted(
            "projection_refs", (artifact_id,)
        ).fetchall():
            projection_name = str(name)
            projection_version = str(version)
            expected_version = {
                "hvo": HVO_SCHEMA_VERSION, "hvo_v3": HVO_SCHEMA_VERSION_V3,
                "features": FEATURES_SCHEMA_VERSION, "grammar": GRAMMAR_SCHEMA_VERSION,
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
        return tuple(references_list)

    def _load_provenance(
        self, artifact_id: str, provenance_digest: object
    ) -> tuple[str, str, str, str]:
        """Read and check the provenance row of one artifact."""

        provenance_row = self._execute_allowlisted("provenance", (artifact_id,)).fetchone()
        if provenance_row is None:
            raise GrooveIndexInvalid("provenance row is missing")
        stored_provenance_digest, source_digest, stored_license, stored_redistribution = (
            provenance_row
        )
        if str(stored_provenance_digest) != str(provenance_digest):
            raise GrooveIndexInvalid("provenance digest mismatch")
        return (
            str(stored_provenance_digest), str(source_digest),
            str(stored_license), str(stored_redistribution),
        )

    def _load_lineage(self, artifact_id: str) -> dict[str, object]:
        """Read the lineage rows of one artifact."""

        lineage_rows = self._execute_allowlisted("lineage", (artifact_id,)).fetchall()
        return {
            "parent_artifact_ids": [str(parent) for parent, _relation, _ordinal in lineage_rows],
            "relations": [str(relation) for _parent, relation, _ordinal in lineage_rows],
            "ordinals": [int(ordinal) for _parent, _relation, ordinal in lineage_rows],
        }

    def _load_facets(self, artifact_id: str) -> dict[str, list[str]]:
        """Read the facet values of one artifact."""

        facets: dict[str, list[str]] = {}
        for axis, value, _source, _confidence in self._execute_allowlisted(
            "facets", (artifact_id,)
        ).fetchall():
            facets.setdefault(str(axis), []).append(str(value))
        return facets

    def _load_features(self, artifact_id: str) -> dict[str, object]:
        """Read the feature values of one artifact."""

        features: dict[str, object] = {}
        for name, _version, value, _unit, status in self._execute_allowlisted(
            "features", (artifact_id,)
        ).fetchall():
            features[str(name)] = value if status == "available" else None
        return features

    def _load_card_metadata(
        self, capabilities_json: object, summary_json: object, format_json: object,
        timing_json: object, tracks_json: object,
    ) -> tuple[Any, Any, SmfFormatV1, Any, tuple[TrackInfoV1, ...]]:
        """Parse the JSON metadata columns of one artifact card."""

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
        return capabilities, summary, format_value, timing_value, tracks

    def search_rows(self, criteria: Any) -> tuple[dict[str, object], ...]:
        """Return bounded card/features rows using only fixed statements."""

        del criteria
        rows = self._execute_allowlisted("all_cards").fetchall()
        return tuple(self._search_row(row) for row in rows)

    def _search_row(self, row: Any) -> dict[str, object]:
        """Build one bounded card row with its facets, features and projections."""

        (
            artifact_id, schema_version, kind, corpus_id, build_id, license_id,
            redistribution, rights_level, capabilities_json, summary_json,
            payload_size, payload_sha256, events_digest, provenance_digest,
            lineage_digest,
        ) = row
        facets = self._execute_allowlisted("facets", (artifact_id,)).fetchall()
        features = self._execute_allowlisted("features", (artifact_id,)).fetchall()
        projections = self._execute_allowlisted("projection_refs", (artifact_id,)).fetchall()
        return {
            "artifact_id": str(artifact_id), "schema_version": str(schema_version),
            "kind": str(kind), "corpus_id": str(corpus_id),
            "build_id": str(build_id), "license_id": str(license_id),
            "redistribution": str(redistribution), "rights_level": int(rights_level),
            "capabilities": json.loads(str(capabilities_json)),
            "summary": json.loads(str(summary_json)),
            "payload_size": int(payload_size), "payload_sha256": str(payload_sha256),
            "events_digest": str(events_digest), "provenance_digest": str(provenance_digest),
            "lineage_digest": str(lineage_digest),
            "facets": tuple(
                {
                    "axis": str(axis), "value": str(value),
                    "source": str(source), "confidence": float(confidence),
                }
                for axis, value, source, confidence in facets
            ),
            "features": tuple(
                {
                    "name": str(name), "version": str(version), "value": value,
                    "unit": str(unit), "status": str(status),
                }
                for name, version, value, unit, status in features
            ),
            "projections": tuple(
                {"name": str(name), "version": str(version), "digest": str(digest)}
                for name, version, digest in projections
            ),
        }


def _read_bundle_manifest(bundle_dir: Path) -> tuple[GrooveSeedBundleManifestV1, Path]:
    """Read the manifest and the checked database path of a seed bundle."""

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
    return manifest, db_path


def _read_index_meta(connection: sqlite3.Connection) -> dict[str, str]:
    """Read the index metadata rows and check that every required key is present."""

    user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if user_version != SQLITE_USER_VERSION:
        raise GrooveSchemaUnsupported(
            f"SQLite user_version is not {SQLITE_USER_VERSION}"
        )
    meta = dict(connection.execute("SELECT key, value FROM index_meta").fetchall())
    meta["user_version"] = str(user_version)
    required = {
        "schema_version", "seed_schema", "seed_bundle_id", "build_id",
        "parser_id", "manifest_digest", "logical_index_digest", "ranker_id",
        "ranker_manifest_digest", "normalizer_id", "projection_versions",
        "sqlite_min_version",
    }
    if not required.issubset(meta):
        raise GrooveIndexInvalid("index metadata is incomplete")
    return meta


def open_readonly_index(bundle_dir: Path) -> ReadonlyGrooveIndex:
    """Open a seed bundle and return its immutable, validated index."""

    manifest, db_path = _read_bundle_manifest(bundle_dir)
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
        meta = _read_index_meta(connection)
        _validate_bundle_versions(meta, manifest)
        _validate_bundle_identity(meta, manifest)
        _validate_index_rows(connection, meta, manifest)
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
