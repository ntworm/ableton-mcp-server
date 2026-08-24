from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import ableton_mcp_server.groove_intelligence.deterministic as deterministic_module
from ableton_mcp_server.groove_intelligence.build import (
    authorize_input,
    build_seed_bundle,
    compile_one,
)
from ableton_mcp_server.groove_intelligence.canonical import canonical_json, sha256_hex
from ableton_mcp_server.groove_intelligence.deterministic import (
    GrooveLimitExceeded,
    _MusicalNote,
    _projected_parent,
    _transform_notes,
    deterministic_generate,
)
from ableton_mcp_server.groove_intelligence.drum_roles import (
    GM_DRUM_ROLE_BY_PITCH,
    GM_DRUM_ROLES,
)
from ableton_mcp_server.groove_intelligence.index import open_readonly_index, write_index
from ableton_mcp_server.groove_intelligence.midi_lossless import decompress_bounded, parse_smf
from ableton_mcp_server.groove_intelligence.runtime import GrooveRuntime
from ableton_mcp_server.groove_intelligence.schema import (
    BuildInput,
    CompressedBlobV1,
    FeaturesProjectionV1,
    FeatureValueV1,
    HvoCellV1,
    HvoProjectionV1,
    MidiArtifactV1,
    SmfFormatV1,
    TrackInfoV1,
)
from tests.fixtures.groove_runtime import (
    MemoryArtifactStore,
    make_generate_request,
    make_pilot_runtime,
)
from tests.fixtures.groove_smf import MINIMAL_TYPE1_SMF


def test_same_generation_request_returns_same_artifact_and_lineage(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    request = make_generate_request(runtime)
    first = deterministic_generate(runtime, request)
    second = deterministic_generate(runtime, request)
    assert first.artifact.artifact_id == second.artifact.artifact_id
    first_payload = runtime.store.get(str(first.artifact.artifact_id)).payload
    second_payload = runtime.store.get(str(second.artifact.artifact_id)).payload
    assert first_payload.blob == second_payload.blob
    assert first_payload.sha256 == second_payload.sha256
    assert first.card.parent_artifact_ids == (runtime.index.manifest.artifact_ids[0],)
    assert first.card.deterministic is True and first.card.fallback is False


def test_generated_artifact_respects_64_bar_and_2048_event_limits(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    invalid_request = make_generate_request(runtime, bars=64, seed=1).model_copy(
        update={"bars": 65}
    )
    with pytest.raises(GrooveLimitExceeded):
        deterministic_generate(runtime, invalid_request)


def test_generated_artifact_rejects_parent_event_count_over_2048(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    parent_id = str(runtime.index.manifest.artifact_ids[0])
    parent = runtime.store.get(parent_id)
    runtime.store.put(
        parent.model_copy(
            update={
                "tracks": (
                    TrackInfoV1(track_index=0, event_count=2049),
                )
            }
        )
    )

    with pytest.raises(GrooveLimitExceeded):
        deterministic_generate(runtime, make_generate_request(runtime, bars=1, seed=1))


def test_generation_preflights_bars_by_parent_before_materializing_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = make_pilot_runtime(tmp_path)
    request = make_generate_request(runtime, bars=64, seed=1, transforms={})
    parsed = deterministic_module.parse_smf(MINIMAL_TYPE1_SMF)
    parsed.note_events = parsed.note_events * 2_000

    monkeypatch.setattr(
        deterministic_module,
        "_raw_parent",
        lambda _runtime, _parent, _parent_id: parsed,
    )

    def fail_if_materialized(*_args: object, **_kwargs: object) -> list[object]:
        raise AssertionError("_initial_notes must not run after preflight rejection")

    monkeypatch.setattr(deterministic_module, "_initial_notes", fail_if_materialized)

    with pytest.raises(GrooveLimitExceeded, match="limited to 2048 events"):
        deterministic_generate(runtime, request)


def test_nonzero_transform_changes_real_note_events_and_payload(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    baseline = deterministic_generate(
        runtime,
        make_generate_request(runtime, bars=2, seed=13, transforms={}),
    )
    baseline_raw = decompress_bounded(
        runtime.store.get(str(baseline.artifact.artifact_id)).payload.blob,
        codec="zlib-raw-midi-v1",
        raw_size=runtime.store.get(str(baseline.artifact.artifact_id)).payload.raw_size,
    )
    baseline_notes = parse_smf(baseline_raw).note_events

    for axis in ("density", "energy", "microtiming", "swing", "syncopation", "complexity"):
        result = deterministic_generate(
            runtime,
            make_generate_request(runtime, bars=2, seed=13, transforms={axis: 1.0}),
        )
        artifact = runtime.store.get(str(result.artifact.artifact_id))
        raw = decompress_bounded(
            artifact.payload.blob,
            codec=artifact.payload.codec,
            raw_size=artifact.payload.raw_size,
        )
        notes = parse_smf(raw).note_events
        assert notes != baseline_notes, axis
        assert raw != baseline_raw, axis
        assert artifact.events_digest == parse_smf(raw).source_events_digest


def test_multi_parent_recombination_uses_all_material_and_records_lineage(
    tmp_path: Path,
) -> None:
    runtime = make_pilot_runtime(tmp_path)
    first_id, second_id = (str(item) for item in runtime.index.manifest.artifact_ids[:2])
    request = make_generate_request(
        runtime,
        source={"artifact_id": first_id},
        reference_artifact_ids=[second_id],
        bars=1,
        seed=19,
        transforms={},
    )
    result = deterministic_generate(runtime, request)
    artifact = runtime.store.get(str(result.artifact.artifact_id))
    raw = decompress_bounded(
        artifact.payload.blob,
        codec=artifact.payload.codec,
        raw_size=artifact.payload.raw_size,
    )
    pitches = {note.pitch for note in parse_smf(raw).note_events}
    assert 36 in pitches  # projected, rights-safe first parent material
    assert 38 in pitches  # raw second parent material
    assert result.card.parent_artifact_ids == (first_id, second_id)
    assert artifact.lineage["parent_artifact_ids"] == [first_id, second_id]


def test_multi_parent_recombination_rejects_incompatible_ppq(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    first_id, second_id = (str(item) for item in runtime.index.manifest.artifact_ids[:2])
    second = runtime.store.get(second_id)
    runtime.store.put(
        second.model_copy(update={"format": second.format.model_copy(update={"ppq": 960})})
    )
    with pytest.raises(ValueError, match="PPQ"):
        deterministic_generate(
            runtime,
            make_generate_request(
                runtime,
                source={"artifact_id": first_id},
                reference_artifact_ids=[second_id],
            ),
        )


def test_derived_only_ppq960_index_roundtrip_reconstructs_native_offsets(tmp_path: Path) -> None:
    source_root = tmp_path / "ppq960-corpus"
    source_root.mkdir()
    native_smf = MINIMAL_TYPE1_SMF.replace(b"\x01\xe0", b"\x03\xc0").replace(
        b"\x00\x99\x24\x64", b"\x3c\x99\x24\x64"
    )
    source_path = source_root / "native960.mid"
    source_path.write_bytes(native_smf)
    declared = BuildInput(
        path=source_path,
        source_kind="author",
        license_id="private-derived",
        redistribution="derived_only",
    )
    manifest = build_seed_bundle(
        input_root=source_root,
        inputs=[declared],
        output_dir=tmp_path / "bundle",
        build_config={"test": "ppq960"},
    )
    authorized, token = authorize_input(
        source_root,
        source_path,
        source_kind=declared.source_kind,
        license_id=declared.license_id,
        redistribution=declared.redistribution,
    )
    compiled = compile_one(authorized, build_id=manifest.build_id, authorized_source=token)
    write_index(tmp_path / "bundle", [compiled], manifest)
    index = open_readonly_index(tmp_path / "bundle")
    store = MemoryArtifactStore()
    artifact_id = str(manifest.artifact_ids[0])
    store.put(index.load_artifact(artifact_id))
    runtime = GrooveRuntime(index=index, store=store)

    result = deterministic_generate(
        runtime,
        make_generate_request(
            runtime,
            source={"artifact_id": artifact_id},
            bars=1,
            seed=2,
            transforms={},
        ),
    )
    generated = store.get(str(result.artifact.artifact_id))
    raw = decompress_bounded(
        generated.payload.blob,
        codec=generated.payload.codec,
        raw_size=generated.payload.raw_size,
    )
    parsed = parse_smf(raw)
    assert parsed.format.ppq == 960
    assert parsed.note_events[0].start_ticks == 60


def test_derived_only_reconstruction_uses_every_canonical_drum_role_pitch() -> None:
    cells = [
        HvoCellV1(
            role=role,
            bar=0,
            step=index,
            hit=1,
            velocity=0.8,
            offset_ticks=0,
            event_ids=[index],
        )
        for index, role in enumerate(GM_DRUM_ROLES)
    ]
    hvo = HvoProjectionV1(
        grid_ticks=120,
        roles=GM_DRUM_ROLES,
        cells=cells,
        source_events_digest="0" * 64,
    )
    features = FeaturesProjectionV1(
        values={
            "ppq": FeatureValueV1(value=480),
            "meter": FeatureValueV1(value="4/4"),
            "bars": FeatureValueV1(value=1),
        },
        source_events_digest="0" * 64,
    )
    parent = MidiArtifactV1(
        artifact_id="ga1_" + "0" * 64,
        format=SmfFormatV1(smf_type=1, ppq=480, track_count=2),
        payload=CompressedBlobV1(
            codec="zlib-raw-midi-v1",
            raw_size=0,
            compressed_size=0,
            sha256="0" * 64,
            blob=b"",
        ),
        events_digest="0" * 64,
    )
    runtime = SimpleNamespace(
        index=SimpleNamespace(
            load_projection=lambda _artifact_id, projection_id: (
                hvo if projection_id == hvo.schema_version else features
            )
        )
    )

    projected = parse_smf(_projected_parent(runtime, parent, str(parent.artifact_id)))
    expected_pitches = {
        min(pitch for pitch, mapped_role in GM_DRUM_ROLE_BY_PITCH.items() if mapped_role == role)
        for role in GM_DRUM_ROLES
    }
    assert {note.pitch for note in projected.note_events} == expected_pitches
    assert 60 not in {note.pitch for note in projected.note_events}
    assert deterministic_module._pitch_for_drum_role("closed_hat") == 42
    assert deterministic_module._pitch_for_drum_role("open_hat") == 46
    assert deterministic_module._pitch_for_drum_role("other") == 58


def test_density_minus_one_changes_a_minimum_note() -> None:
    note = _MusicalNote(1, 9, 36, 1, 0, 1, 0)
    generated = _transform_notes(
        [note], {"density": -1.0}, seed=1, ppq=480, meter=(4, 2), length_ticks=1920
    )
    assert generated != [note]


def test_generation_bounds_union_facets_and_records_canonical_parent_provenance(
    tmp_path: Path,
) -> None:
    runtime = make_pilot_runtime(tmp_path)
    first_id, second_id = (str(item) for item in runtime.index.manifest.artifact_ids[:2])
    first = runtime.store.get(first_id)
    second = runtime.store.get(second_id)
    runtime.store.put(
        first.model_copy(
            update={
                "provenance": {
                    **first.provenance,
                    "license_id": "license-first",
                    "license_ids": ["license-first", "license-inherited"],
                    "facets": {"feel": [f"value-{index:02d}" for index in range(40)]},
                }
            }
        )
    )
    runtime.store.put(
        second.model_copy(
            update={
                "provenance": {
                    **second.provenance,
                    "license_id": "license-second",
                    "facets": {"feel": [f"value-{index:02d}" for index in range(20, 52)]},
                }
            }
        )
    )
    result = deterministic_generate(
        runtime,
        make_generate_request(
            runtime,
            source={"artifact_id": first_id},
            reference_artifact_ids=[second_id],
            bars=1,
            transforms={},
        ),
    )
    generated = runtime.store.get(str(result.artifact.artifact_id))
    provenance = generated.provenance
    assert provenance["license_ids"] == [
        "license-first",
        "license-inherited",
        "license-second",
    ]
    assert len(provenance["facets"]["feel"]) == 32
    assert len(result.artifact.facets["feel"]) == 32
    digest_input = {key: value for key, value in provenance.items() if key != "provenance_digest"}
    assert provenance["provenance_digest"] == sha256_hex(canonical_json(digest_input))


@pytest.mark.parametrize(
    ("axis", "start_ticks"),
    (("microtiming", 240), ("swing", 240), ("syncopation", 1920)),
)
def test_negative_timing_transforms_move_directionally_with_clamp(
    axis: str, start_ticks: int
) -> None:
    note = _MusicalNote(1, 9, 36, 80, start_ticks, 60, 0)
    generated = _transform_notes(
        [note], {axis: -1.0}, seed=1, ppq=480, meter=(4, 2), length_ticks=3840
    )
    assert generated[0].start_ticks <= start_ticks
