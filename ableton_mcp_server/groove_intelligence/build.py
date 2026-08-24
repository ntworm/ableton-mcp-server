"""Authorized pilot ingestion and deterministic, path-free build manifests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import GrooveBuildError
from .canonical import artifact_id_from_identity, canonical_json, sha256_hex
from .constants import (
    FEATURES_SCHEMA_VERSION,
    GRAMMAR_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION,
    MAX_INPUT_BYTES,
    NORMALIZER_ID,
    PARSER_ID,
    RANKER_ID,
    RANKER_MANIFEST_DIGEST,
)
from .midi_lossless import compress_bounded, parse_smf
from .projections import derive_features, derive_grammar, derive_hvo
from .schema import (
    BuildInput,
    BuildManifestInputV1,
    CompiledGrooveArtifactV1,
    GrooveSeedBundleManifestV1,
    MidiArtifactV1,
    ProjectionRefV1,
)
from .taxonomy import TAXONOMY_VERSION, classify_facets, classify_path_facets


@dataclass(frozen=True)
class AuthorizedSource:
    """Opaque scanner-issued root/path/digest token used by ``compile_one``."""

    root: Path
    path: Path
    source_digest: str


def validate_input_path(input_root: Path, candidate: Path) -> Path:
    try:
        root = input_root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise GrooveBuildError("authorized root or input does not exist") from error
    try:
        inside_root = resolved.is_relative_to(root)
    except AttributeError:
        inside_root = root == resolved or root in resolved.parents
    if not inside_root:
        raise GrooveBuildError("input escapes authorized root")
    if resolved.suffix.lower() not in {".mid", ".midi"} or not resolved.is_file():
        raise GrooveBuildError("unsupported or non-regular MIDI input")
    if resolved.stat().st_size > MAX_INPUT_BYTES:
        raise GrooveBuildError("MIDI input exceeds 8 MiB")
    return resolved


def authorize_input(
    input_root: Path,
    candidate: Path,
    *,
    source_kind: str,
    license_id: str,
    redistribution: str,
) -> tuple[BuildInput, AuthorizedSource]:
    resolved = validate_input_path(input_root, candidate)
    digest = sha256_hex(resolved.read_bytes())
    root = input_root.resolve(strict=True)
    token = AuthorizedSource(root=root, path=resolved, source_digest=digest)
    try:
        build_input = BuildInput(
            path=resolved,
            source_kind=source_kind,
            license_id=license_id,
            redistribution=redistribution,  # type: ignore[arg-type]
        )
    except ValueError as error:
        raise GrooveBuildError("invalid license or redistribution") from error
    return build_input, token


def _rights_level(redistribution: str) -> int:
    return {"blocked": 0, "derived_only": 1, "full": 2}.get(redistribution, 0)


def _projection_row(
    name: str,
    version: str,
    projection: Any,
) -> tuple[ProjectionRefV1, dict[str, Any]]:
    raw = canonical_json(projection.model_dump(mode="json"))
    compressed = compress_bounded(raw, "zlib-raw-json-v1")
    reference = ProjectionRefV1(name=name, version=version, digest=sha256_hex(raw))
    row = {
        "name": name,
        "version": version,
        "digest": reference.digest,
        "codec": compressed.codec,
        "blob": compressed.blob,
        "raw_size": compressed.raw_size,
        "compressed_size": compressed.compressed_size,
    }
    return reference, row


def compile_parsed_artifact(
    build_input: BuildInput,
    parsed: Any,
    *,
    build_id: str,
    relative_path: str | None = None,
) -> CompiledGrooveArtifactV1:
    if not build_input.license_id:
        raise GrooveBuildError("license is required")
    rights_level = _rights_level(build_input.redistribution)
    if rights_level == 0:
        raise GrooveBuildError("license does not permit publication")
    hvo = derive_hvo(parsed)
    features = derive_features(parsed, hvo)
    grammar = derive_grammar(parsed, hvo)
    facet_set = classify_facets(
        features,
        hvo,
        relative_path=relative_path,
        redistribution=build_input.redistribution,
    )
    payload = compress_bounded(parsed.raw_bytes, "zlib-raw-midi-v1")
    provenance = {
        "source_digest": sha256_hex(parsed.raw_bytes),
        "source_kind": build_input.source_kind,
        "license_id": build_input.license_id,
        "redistribution": build_input.redistribution,
        "importer_id": PARSER_ID,
        "importer_version": "1",
        "build_id": build_id,
    }
    provenance_digest = sha256_hex(canonical_json(provenance))
    lineage: dict[str, object] = {"parent_artifact_ids": [], "relations": [], "ordinals": []}
    lineage_digest = sha256_hex(canonical_json(lineage))
    hvo_ref, hvo_row = _projection_row("hvo", HVO_SCHEMA_VERSION, hvo)
    features_ref, features_row = _projection_row("features", FEATURES_SCHEMA_VERSION, features)
    grammar_ref, grammar_row = _projection_row("grammar", GRAMMAR_SCHEMA_VERSION, grammar)
    identity = {
        "schema_version": "groove.midi-artifact.v1",
        "kind": "source",
        "format": parsed.format.model_dump(mode="json"),
        "timing": {
            "length_ticks": parsed.length_ticks,
            "meters": parsed.meters,
            "tempos": parsed.tempos,
        },
        "tracks": [track.model_dump(mode="json") for track in parsed.tracks],
        "payload_sha256": payload.sha256,
        "events_digest": parsed.source_events_digest,
        "projection_digests": {
            "hvo": hvo_ref.digest,
            "features": features_ref.digest,
            "grammar": grammar_ref.digest,
        },
        "provenance_digest": provenance_digest,
        "lineage_digest": lineage_digest,
    }
    artifact_id = artifact_id_from_identity(identity)
    artifact = MidiArtifactV1(
        artifact_id=artifact_id,
        format=parsed.format,
        timing=identity["timing"],
        tracks=tuple(parsed.tracks),
        payload=payload,
        events_digest=parsed.source_events_digest,
        provenance=provenance,
        lineage=lineage,
        projections=(hvo_ref, features_ref, grammar_ref),
    )
    feature_rows = tuple(
        {
            "name": name,
            "version": FEATURES_SCHEMA_VERSION,
            "value": item.value,
            "unit": item.unit,
            "status": item.status,
        }
        for name, item in sorted(features.values.items())
    )
    facet_rows = tuple(
        {
            "axis": axis,
            "value": value,
            "source": facet_set.version,
            "confidence": 1.0,
        }
        for axis, values in sorted(facet_set.values.items())
        for value in values
    )
    summary = {
        "bars": features.values["bars"].value,
        "meter": features.values["meter"].value,
        "roles": sorted({cell.role for cell in hvo.cells}),
        "taxonomy_version": facet_set.version,
    }
    return CompiledGrooveArtifactV1(
        artifact=artifact,
        source_digest=payload.sha256,
        source_kind=build_input.source_kind,
        license_id=build_input.license_id,
        redistribution=build_input.redistribution,
        rights_level=rights_level,
        capabilities={
            "search": True,
            "evidence": True,
            "generate": rights_level >= 1,
            "apply": rights_level == 2,
        },
        summary=summary,
        facets=facet_rows,
        features=feature_rows,
        projections=(hvo_row, features_row, grammar_row),
        lineage_rows=(),
        provenance_digest=provenance_digest,
    )


def compile_one(
    build_input: BuildInput,
    *,
    build_id: str,
    authorized_source: AuthorizedSource,
) -> CompiledGrooveArtifactV1:
    if not isinstance(authorized_source, AuthorizedSource):
        raise GrooveBuildError("authorized root token is required")
    try:
        inside_root = build_input.path.resolve(strict=True).is_relative_to(authorized_source.root)
    except AttributeError:
        resolved_path = build_input.path.resolve(strict=True)
        inside_root = (
            authorized_source.root == resolved_path
            or authorized_source.root in resolved_path.parents
        )
    if not inside_root or build_input.path.resolve(strict=True) != authorized_source.path:
        raise GrooveBuildError("input is outside authorized root")
    current_digest = sha256_hex(authorized_source.path.read_bytes())
    if current_digest != authorized_source.source_digest:
        raise GrooveBuildError("authorized source digest changed")
    if not build_input.license_id:
        raise GrooveBuildError("license is required")
    parsed = parse_smf(authorized_source.path.read_bytes())
    relative_path = authorized_source.path.relative_to(authorized_source.root).as_posix()
    return compile_parsed_artifact(
        build_input,
        parsed,
        build_id=build_id,
        relative_path=relative_path,
    )


def merge_taxonomy_facets(
    artifact: CompiledGrooveArtifactV1,
    relative_paths: list[str] | tuple[str, ...],
) -> CompiledGrooveArtifactV1:
    """Union bounded path taxonomy for duplicate payloads without retaining paths."""

    merged: dict[str, set[str]] = {}
    for row in artifact.facets:
        axis = str(row.get("axis", ""))
        value = row.get("value")
        if axis and isinstance(value, str):
            merged.setdefault(axis, set()).add(value)
    for relative_path in sorted(set(relative_paths)):
        for axis, labels in classify_path_facets(relative_path).values.items():
            merged.setdefault(axis, set()).update(labels)
    rows = tuple(
        {
            "axis": axis,
            "value": value,
            "source": TAXONOMY_VERSION,
            "confidence": 1.0,
        }
        for axis in sorted(merged)
        for value in sorted(merged[axis])[:32]
    )
    return artifact.model_copy(update={"facets": rows})


def _manifest_digest(manifest: GrooveSeedBundleManifestV1) -> str:
    body = manifest.model_dump(mode="json")
    for key in (
        "manifest_digest",
        "bundle_manifest_digest",
        "logical_index_digest",
        "file_checksums",
    ):
        body.pop(key, None)
    return sha256_hex(canonical_json(body))


def build_seed_bundle(
    *,
    input_root: Path,
    inputs: list[BuildInput] | tuple[BuildInput, ...],
    output_dir: Path,
    build_config: dict[str, object],
) -> GrooveSeedBundleManifestV1:
    root = input_root.resolve(strict=True)
    authorized: list[tuple[BuildInput, AuthorizedSource]] = []
    for declared in inputs:
        authorized.append(
            authorize_input(
                root,
                declared.path,
                source_kind=declared.source_kind,
                license_id=declared.license_id,
                redistribution=declared.redistribution,
            )
        )
    groups: dict[str, list[tuple[BuildInput, AuthorizedSource]]] = {}
    for item in authorized:
        groups.setdefault(item[1].source_digest, []).append(item)
    deduped: list[tuple[BuildInput, AuthorizedSource]] = []
    duplicate_paths: dict[str, tuple[str, ...]] = {}
    for source_digest in sorted(groups):
        group = sorted(
            groups[source_digest],
            key=lambda item: item[1].path.relative_to(root).as_posix(),
        )
        deduped.append(group[0])
        duplicate_paths[source_digest] = tuple(
            item[1].path.relative_to(root).as_posix() for item in group
        )
    config_identity = {"schema_version": "groove.build.v1", "config": build_config, "inputs": [
        {
            "source_digest": token.source_digest,
            "source_kind": build_input.source_kind,
            "license_id": build_input.license_id,
            "redistribution": build_input.redistribution,
        }
        for build_input, token in deduped
    ]}
    build_id = "gb1_" + sha256_hex(canonical_json(config_identity))
    corpus_id = "gc1_" + sha256_hex(
        canonical_json({"source_digests": [token.source_digest for _input, token in deduped]})
    )
    artifacts = [
        merge_taxonomy_facets(
            compile_one(build_input, build_id=build_id, authorized_source=token),
            duplicate_paths[token.source_digest],
        )
        for build_input, token in deduped
    ]
    manifest_inputs = tuple(
        BuildManifestInputV1(
            source_digest=item.source_digest,
            artifact_id=artifact.artifact_id,
            source_kind=build_input.source_kind,
            license_id=build_input.license_id,
            redistribution=build_input.redistribution,
            provenance_digest=artifact.provenance_digest,
        )
        for (build_input, item), artifact in zip(deduped, artifacts, strict=True)
    )
    artifact_ids = tuple(artifact.artifact_id for artifact in artifacts)
    seed_bundle_id = "gsb1_" + sha256_hex(
        canonical_json({"corpus_id": corpus_id, "build_id": build_id, "artifact_ids": artifact_ids})
    )
    manifest = GrooveSeedBundleManifestV1(
        seed_bundle_id=seed_bundle_id,
        corpus_id=corpus_id,
        build_id=build_id,
        parser_id=PARSER_ID,
        normalizer_id=NORMALIZER_ID,
        projection_versions={
            "hvo": HVO_SCHEMA_VERSION,
            "features": FEATURES_SCHEMA_VERSION,
            "grammar": GRAMMAR_SCHEMA_VERSION,
            "taxonomy": TAXONOMY_VERSION,
        },
        inputs=manifest_inputs,
        artifact_ids=artifact_ids,
        ranker_id=RANKER_ID,
        ranker_manifest_digest=RANKER_MANIFEST_DIGEST,
    )
    manifest.manifest_digest = _manifest_digest(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_bytes(canonical_json(manifest.model_dump(mode="json")))
    # Imported lazily to keep the compiler usable while the index module is
    # imported by tests and to avoid a module-level cycle.
    from .index import write_index

    write_index(output_dir, artifacts, manifest)
    return manifest
