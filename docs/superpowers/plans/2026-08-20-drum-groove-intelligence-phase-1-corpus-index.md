# Drum Groove Intelligence Phase 1 — Corpus and Portable Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a bounded, deterministic, lossless MIDI compiler and portable read-only seed bundle from a small authorized pilot fixture, with no runtime dependency on the source-corpus path.

**Architecture:** `schema.py` owns versioned value objects; `canonical.py` owns all domain-separated hashes; `midi_lossless.py` parses and serializes SMF using stdlib only; `projections.py`, `taxonomy.py`, and `rights.py` derive bounded views without changing source events. `build.py` consumes explicitly declared `BuildInput` records and writes a manifest plus SQLite v1 index/payload files; `index.py` opens a configured bundle immutable/read-only and validates its manifest before any query.

**Tech Stack:** Python >=3.10, Pydantic v2 already present, stdlib MIDI parser, SQLite 3.40+, zlib raw streams, pytest. No MIDI package, corpus-wide scan, model, package install, or database is used before the pilot gate.

**Spec:** `docs/superpowers/specs/2026-08-20-drum-groove-intelligence-design.md` at `0ea5b3712b32650e861b6e0380860e8133c2e388`.

## Global Constraints

- `MidiArtifactV1` preserves exact source SMF bytes and all events; projections retain source event ids.
- Fixed limits: 8 MiB source file, 256 tracks, 1,000,000 events, compressed BLOB 8 MiB, raw BLOB 32 MiB, expansion ratio 100:1.
- Parser/serializer are `smf-parser-v1`/`smf-serializer-v1`; codecs are `zlib-raw-midi-v1`/`zlib-raw-json-v1`; SQLite `user_version=1`, minimum SQLite `3.40`.
- No absolute source path, username, access timestamp, log content, SQL, or private corpus name may enter a manifest, index row, card, or seed bundle.
- Rights use the meet lattice `blocked < derived_only < full`; missing/invalid provenance blocks publication and there is no override.
- Build input order is by source SHA-256, never filesystem enumeration order. A full 183k scan is scheduled only after two identical pilot builds pass.
- This plan creates implementation code only through its executing worker; this planning task creates no code or fixtures.
- Generated `index.sqlite`, compressed payloads, manifests, and pilot bundles stay under pytest `tmp_path` or an ignored build output directory; only the synthetic fixture builder and sanitized pilot procedure are committed. A worker must delete temporary bundles after verification and prove the committed tree contains no payload BLOB.

### Task 1: Versioned schema and canonical identity primitives

**Files:**
- Create: `ableton_mcp_server/groove_intelligence/__init__.py`
- Create: `ableton_mcp_server/groove_intelligence/constants.py`
- Create: `ableton_mcp_server/groove_intelligence/schema.py`
- Create: `ableton_mcp_server/groove_intelligence/canonical.py`
- Test: `tests/test_groove_canonical.py`

**Interfaces:**
- Produces `ArtifactId = NewType("ArtifactId", str)`, `canonical_json(value: object) -> bytes`, `sha256_hex(data: bytes) -> str`, `artifact_id_from_identity(identity: Mapping[str, object]) -> ArtifactId`, `request_hash(request_for_hash: Mapping[str, object]) -> str`, and `reproducibility_key(*, schema_versions: Mapping[str, str], seed_bundle_id: str, algorithm_versions: Mapping[str, str], canonical_request: Mapping[str, object], parent_artifact_ids: Sequence[str], provider_identity: Mapping[str, object]) -> str`.
- Produces Pydantic models `BuildInput`, `MidiEventV1`, `NoteEventV1`, `MidiArtifactV1`, `ProjectionRefV1`, `BuildManifestV1`, and `GrooveSeedBundleManifestV1` with `extra="forbid"`.

- [ ] **Step 1: Write the failing tests**

```python
from ableton_mcp_server.groove_intelligence.canonical import (
    artifact_id_from_identity, canonical_json, request_hash,
)

def test_canonical_json_normalizes_unicode_numbers_and_key_order() -> None:
    assert canonical_json({"b": "e\u0301", "a": -0.0, "n": 1.2345678912}) == (
        b'{"a":0,"b":"\xc3\xa9","n":1.234567891}'
    )

def test_artifact_id_uses_domain_and_excludes_self_id() -> None:
    identity = {"schema_version": "groove.midi-artifact.v1", "kind": "source", "payload_sha256": "a" * 64}
    first = artifact_id_from_identity(identity)
    assert first.startswith("ga1_") and len(first) == 68
    assert artifact_id_from_identity({**identity, "artifact_id": "ga1_" + "f" * 64}) == first

def test_request_hash_excludes_cursor_but_includes_effective_defaults() -> None:
    page_one = {"schema_version": "groove.search.request.v1", "query": "kick", "limit": 20}
    page_two = {**page_one, "cursor": "opaque-page-two"}
    assert request_hash(page_one) == request_hash(page_two)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_canonical.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'ableton_mcp_server.groove_intelligence'`.

- [ ] **Step 3: Write the minimal implementation**

```python
def canonical_json(value: object) -> bytes:
    normalized = _normalize(value)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

def artifact_id_from_identity(identity: Mapping[str, object]) -> ArtifactId:
    body = b"ABLETON-GROOVE-ARTIFACT-V1\x00" + canonical_json({k: v for k, v in identity.items() if k != "artifact_id"})
    return ArtifactId("ga1_" + hashlib.sha256(body).hexdigest())

def request_hash(request_for_hash: Mapping[str, object]) -> str:
    body = {k: v for k, v in request_for_hash.items() if k != "cursor"}
    return hashlib.sha256(b"ABLETON-GROOVE-REQUEST-V1\x00" + canonical_json(body)).hexdigest()
```

`_normalize` must NFC-normalize strings, reject NaN/infinity, turn `-0.0` into `0`, quantize feature decimals to nine places without exponent notation, sort object keys by normalized Unicode code point, and deduplicate/sort `facets` and `required_projection_ids`. Pydantic models must constrain `artifact_id` to `^ga1_[0-9a-f]{64}$` and reject unknown fields.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_canonical.py`
Expected: PASS with 3 tests.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/groove_intelligence/__init__.py ableton_mcp_server/groove_intelligence/constants.py ableton_mcp_server/groove_intelligence/schema.py ableton_mcp_server/groove_intelligence/canonical.py tests/test_groove_canonical.py
git commit -m "feat: add groove canonical schemas and identity hashes"
```

### Task 2: Bounded SMF parser, lossless event table, and serializer

**Files:**
- Create: `ableton_mcp_server/groove_intelligence/midi_lossless.py`
- Create: `tests/fixtures/groove_smf.py`
- Test: `tests/test_groove_midi_lossless.py`

**Interfaces:**
- Consumes `schema.MidiEventV1`, `schema.NoteEventV1`, and limits from `constants.py`.
- Produces `parse_smf(payload: bytes) -> ParsedSmfV1`, `serialize_generated_smf(parsed: ParsedSmfV1) -> bytes`, `compress_bounded(raw: bytes, codec: Literal["zlib-raw-midi-v1", "zlib-raw-json-v1"]) -> CompressedBlobV1`, and `decompress_bounded(blob: bytes, *, codec: str, raw_size: int, max_compressed: int = 8 * 1024 * 1024, max_raw: int = 32 * 1024 * 1024, max_ratio: int = 100) -> bytes`.

- [ ] **Step 1: Write the failing tests**

```python
import zlib

from tests.fixtures.groove_smf import (
    HIGH_EXPANSION_RAW,
    HIGH_EXPANSION_BLOB,
    WRAPPED_COMPRESSED_BLOB,
    MALFORMED_COMPRESSED_BLOB,
    MINIMAL_TYPE1_SMF,
    MALFORMED_RUNNING_STATUS,
)
from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf, decompress_bounded

def test_parser_preserves_source_bytes_and_pairs_notes() -> None:
    parsed = parse_smf(MINIMAL_TYPE1_SMF)
    assert parsed.raw_bytes == MINIMAL_TYPE1_SMF
    assert parsed.format.ppq == 480
    assert parsed.note_events[0].pitch == 36
    assert parsed.note_events[0].duration_ticks == 240
    assert parsed.events[0].absolute_ticks == 0

def test_event_ids_are_stable_track_local_allocations() -> None:
    first = parse_smf(MINIMAL_TYPE1_SMF)
    second = parse_smf(MINIMAL_TYPE1_SMF)
    assert [event.event_id for event in first.events] == [event.event_id for event in second.events]
    assert first.note_events[0].event_id == (1 << 32) | 0

def test_parser_rejects_malformed_running_status() -> None:
    with pytest.raises(GrooveMidiError, match="running status"):
        parse_smf(MALFORMED_RUNNING_STATUS)

def test_valid_high_expansion_stream_is_rejected_by_ratio() -> None:
    assert zlib.decompress(HIGH_EXPANSION_BLOB, wbits=-15) == HIGH_EXPANSION_RAW
    with pytest.raises(GrooveBlobRejected, match="^decompression ratio exceeded$"):
        decompress_bounded(HIGH_EXPANSION_BLOB, codec="zlib-raw-midi-v1", raw_size=len(HIGH_EXPANSION_RAW), max_ratio=2)

def test_raw_size_guard_is_distinct_from_ratio_and_malformed() -> None:
    with pytest.raises(GrooveBlobRejected, match="^raw size limit exceeded$"):
        decompress_bounded(HIGH_EXPANSION_BLOB, codec="zlib-raw-midi-v1", raw_size=len(HIGH_EXPANSION_RAW), max_raw=len(HIGH_EXPANSION_RAW) - 1, max_ratio=1000)

def test_distinct_malformed_compressed_stream_is_rejected() -> None:
    with pytest.raises(GrooveBlobRejected, match="^malformed compressed stream$"):
        decompress_bounded(MALFORMED_COMPRESSED_BLOB, codec="zlib-raw-midi-v1", raw_size=len(HIGH_EXPANSION_RAW))

def test_v1_rejects_wrapped_codec_even_when_payload_is_valid() -> None:
    with pytest.raises(GrooveBlobRejected, match="^unsupported compression codec$"):
        decompress_bounded(WRAPPED_COMPRESSED_BLOB, codec="zlib-wrapped-midi-v1", raw_size=len(HIGH_EXPANSION_RAW))
```

The fixture file must define the bytes used above rather than reading a machine file:

```python
def _chunk(tag: bytes, body: bytes) -> bytes:
    return tag + len(body).to_bytes(4, "big") + body

MINIMAL_TYPE1_SMF = (
    _chunk(b"MThd", b"\x00\x01\x00\x02\x01\xe0")
    + _chunk(b"MTrk", b"\x00\xff\x51\x03\x07\xa1\x20\x00\xff\x2f\x00")
    + _chunk(b"MTrk", b"\x00\x99\x24\x64\x81\x70\x89\x24\x00\x00\xff\x2f\x00")
)
MULTI_TRACK_SMF = MINIMAL_TYPE1_SMF.replace(b"\x99\x24\x64", b"\x99\x26\x70")
MALFORMED_RUNNING_STATUS = _chunk(b"MThd", b"\x00\x01\x00\x01\x01\xe0") + _chunk(b"MTrk", b"\x00\x24\x64\x00\xff\x2f\x00")
MULTI_HIT_SMF = _chunk(b"MThd", b"\x00\x01\x00\x01\x01\xe0") + _chunk(b"MTrk", b"\x00\x99\x26\x68\x00\x99\x26\x68\x81\x70\x89\x26\x00\x00\xff\x2f\x00")
NO_TEMPO_SMF = _chunk(b"MThd", b"\x00\x01\x00\x01\x01\xe0") + _chunk(b"MTrk", b"\x00\x99\x24\x64\x81\x70\x89\x24\x00\x00\xff\x2f\x00")

def _raw_deflate(value: bytes) -> bytes:
    compressor = zlib.compressobj(level=9, wbits=-15)
    return compressor.compress(value) + compressor.flush()

HIGH_EXPANSION_RAW = b"A" * 8192
HIGH_EXPANSION_BLOB = _raw_deflate(HIGH_EXPANSION_RAW)
WRAPPED_COMPRESSED_BLOB = zlib.compress(HIGH_EXPANSION_RAW)
MALFORMED_COMPRESSED_BLOB = b"\x01\x02\x03\x04\x05"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_midi_lossless.py`
Expected: FAIL with `ModuleNotFoundError` for `midi_lossless`.

- [ ] **Step 3: Write minimal implementation**

Implement a cursor over `memoryview(payload)` that validates `MThd`, track chunk lengths, VLQ termination within four bytes, running-status legality, meta/sysex lengths, note-on velocity zero as note-off, and event/track/file limits before allocating event payloads. Allocate `event_id = (track_index << 32) | event_index`, with `event_index` starting at zero for each track; the note-on's ID is retained on its paired `NoteEventV1`, and close order is recorded separately. This formula is stable across reparses of identical bytes and never uses Python `hash()`. Emit `event_index`, `event_id`, `delta_ticks`, `absolute_ticks`, MIDI/meta/sysex payload bytes encoded as hex, and paired `NoteEventV1` with original channel/pitch and close order. Preserve `raw_bytes` unchanged for source artifacts. `decompress_bounded` admits only the two v1 raw codecs and feeds `zlib.decompressobj(wbits=-15)` in 64 KiB chunks. It catches `zlib.error` as the exact `malformed compressed stream` error, completes valid decompress plus `flush`, then enforces the separate `raw size limit exceeded` and `decompression ratio exceeded` guards outside the exception handler. Wrapped payloads are explicitly unsupported in v1; there is no wrapped-codec branch or future behavior hidden in this implementation. The raw-deflate fixture above is a valid high-expansion stream; the wrapped fixture is valid zlib-wrapped data used only to prove codec rejection; the malformed fixture is a separate invalid raw stream.

```python
RAW_BLOB_CODECS = frozenset({"zlib-raw-midi-v1", "zlib-raw-json-v1"})

def _decoder_for_codec(codec: str):
    if codec in RAW_BLOB_CODECS:
        return zlib.decompressobj(wbits=-15)
    raise GrooveBlobRejected("unsupported compression codec")

def decompress_bounded(blob: bytes, *, codec: str, raw_size: int, max_compressed: int = MAX_COMPRESSED_BLOB, max_raw: int = MAX_RAW_BLOB, max_ratio: int = MAX_EXPANSION_RATIO) -> bytes:
    if len(blob) > max_compressed or raw_size < 0:
        raise GrooveBlobRejected("codec, compressed size, or raw size is invalid")
    decoder = _decoder_for_codec(codec)
    output = bytearray()
    try:
        for start in range(0, len(blob), 65536):
            if len(output) > max_raw:
                break
            output.extend(decoder.decompress(blob[start:start + 65536], max(1, max_raw - len(output) + 1)))
        output.extend(decoder.flush(max(1, max_raw - len(output) + 1)))
    except zlib.error as error:
        raise GrooveBlobRejected("malformed compressed stream") from error
    if raw_size > max_raw or len(output) > max_raw:
        raise GrooveBlobRejected("raw size limit exceeded")
    if len(output) > max_ratio * max(1, len(blob)):
        raise GrooveBlobRejected("decompression ratio exceeded")
    if not decoder.eof or decoder.unused_data or len(output) != raw_size:
        raise GrooveBlobRejected("truncated or size-mismatched compressed BLOB")
    return bytes(output)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_midi_lossless.py`
Expected: PASS with parser, running-status, VLQ, event-limit, compression, and decompression tests.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/groove_intelligence/midi_lossless.py tests/fixtures/groove_smf.py tests/test_groove_midi_lossless.py
git commit -m "feat: add bounded lossless SMF parser"
```

### Task 3: HVO/features/grammar projections, facets, and rights

**Files:**
- Create: `ableton_mcp_server/groove_intelligence/projections.py`
- Create: `ableton_mcp_server/groove_intelligence/taxonomy.py`
- Create: `ableton_mcp_server/groove_intelligence/rights.py`
- Test: `tests/test_groove_projections.py`
- Test: `tests/test_groove_rights.py`

**Interfaces:**
- Consumes `ParsedSmfV1` from Task 2.
- Produces `derive_hvo(parsed: ParsedSmfV1) -> HvoProjectionV1`, `derive_features(parsed, hvo) -> FeaturesProjectionV1`, `derive_grammar(parsed, hvo) -> GrammarProjectionV1`, `classify_facets(features, hvo) -> FacetSetV1`, and `meet_rights(parents: Sequence[RightsRecordV1], operation: OperationRights, mapping_level: RightsLevel) -> RightsDecisionV1`.

- [ ] **Step 1: Write the failing tests**

```python
def test_hvo_keeps_all_colliding_event_ids_and_normalizes_velocity() -> None:
    hvo = derive_hvo(parse_smf(MULTI_HIT_SMF))
    cell = next(cell for cell in hvo.cells if cell.role == "snare")
    assert cell.hit == 1 and cell.velocity == pytest.approx(round(104 / 127, 9), abs=5e-10)
    assert cell.event_ids == [0, 1]
    assert -120 <= cell.offset_ticks <= 120

def test_missing_feature_is_unavailable_not_zero() -> None:
    features = derive_features(parse_smf(NO_TEMPO_SMF), derive_hvo(parse_smf(NO_TEMPO_SMF)))
    assert features.values["tempo_min"].status == "unavailable"
    assert features.values["tempo_min"].value is None

def test_rights_meet_never_promotes_and_blocks_missing_parent() -> None:
    result = meet_rights([RightsRecordV1(level="full"), RightsRecordV1(level="derived_only")], operation="apply", mapping_level="full")
    assert result.level == "derived_only" and result.capability_apply is False
    missing = meet_rights([RightsRecordV1(level="full", provenance_valid=False)], operation="generate", mapping_level="full")
    assert missing.level == "blocked" and missing.reason == "license_missing"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_projections.py tests/test_groove_rights.py`
Expected: FAIL because projection and rights modules do not exist.

- [ ] **Step 3: Write minimal implementation**

Use fixed role thresholds, grid `120` ticks, velocity `/127` quantized to nine decimal places with Decimal `ROUND_HALF_EVEN`, signed nearest-grid offset, Laplace `alpha=1`, lexical token tie-break, and explicit `status="unavailable"`. Store `source_events_digest` on every projection. Reparse the same fixture twice and assert identical `event_id` and projection arrays; use `pytest.approx(round(raw_velocity / 127, 9), abs=5e-10)` for floating-point consumers. Make `RightsLevel` an ordered enum and compute `min(parent.levels + operation + mapping)`; any invalid provenance or blocked parent returns `blocked` with an enum reason.

```python
def meet_rights(parents: Sequence[RightsRecordV1], operation: OperationRights, mapping_level: RightsLevel) -> RightsDecisionV1:
    if not parents or any(not parent.provenance_valid or parent.level == RightsLevel.blocked for parent in parents):
        return RightsDecisionV1(level=RightsLevel.blocked, reason="license_missing", capability_apply=False)
    level = min([parent.level for parent in parents] + [operation.minimum_level, mapping_level])
    return RightsDecisionV1(level=level, reason=None, capability_apply=level is RightsLevel.full)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_projections.py tests/test_groove_rights.py`
Expected: PASS with projection digests, collision retention, unavailable features, grammar bounds, facets, and rights meet tests.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/groove_intelligence/projections.py ableton_mcp_server/groove_intelligence/taxonomy.py ableton_mcp_server/groove_intelligence/rights.py tests/test_groove_projections.py tests/test_groove_rights.py
git commit -m "feat: derive bounded groove projections and rights"
```

### Task 4: Pilot compiler, provenance, and deterministic build manifest

**Files:**
- Create: `ableton_mcp_server/groove_intelligence/build.py`
- Create: `tests/test_groove_build.py`
- Modify: `tests/fixtures/groove_smf.py`

**Interfaces:**
- Consumes Tasks 1–3 and `BuildInput(path: Path, source_kind: str, license_id: str, redistribution: Literal["full", "derived_only", "blocked"])` only after `authorize_input` has validated its authorized root.
- Produces `AuthorizedSource(root: Path, path: Path, source_digest: str)`, `authorize_input(input_root: Path, candidate: Path, *, source_kind: str, license_id: str, redistribution: Redistribution) -> tuple[BuildInput, AuthorizedSource]`, `build_seed_bundle(*, input_root: Path, inputs: Sequence[BuildInput], output_dir: Path, build_config: Mapping[str, object]) -> GrooveSeedBundleManifestV1`, `compile_one(build_input: BuildInput, *, build_id: str, authorized_source: AuthorizedSource) -> CompiledGrooveArtifactV1`, `compile_parsed_artifact(build_input: BuildInput, parsed: ParsedSmfV1, *, build_id: str) -> CompiledGrooveArtifactV1`, and `validate_input_path(input_root: Path, candidate: Path) -> Path`. `AuthorizedSource` is an opaque scanner-issued token; `compile_one` rejects a missing token, a token whose root/path differs from `build_input`, or a digest mismatch before checking license fields.

- [ ] **Step 1: Write the failing tests**

```python
def test_pilot_build_is_path_free_and_sorted_by_source_digest(tmp_path: Path) -> None:
    root = tmp_path / "corpus"; root.mkdir()
    (root / "z.mid").write_bytes(MINIMAL_TYPE1_SMF)
    (root / "a.mid").write_bytes(MULTI_TRACK_SMF)
    manifest = build_seed_bundle(
        input_root=root,
        inputs=[BuildInput(path=root / "z.mid", source_kind="author", license_id="private-full", redistribution="full"), BuildInput(path=root / "a.mid", source_kind="author", license_id="private-derived", redistribution="derived_only")],
        output_dir=tmp_path / "bundle",
        build_config={"pilot": "v1"},
    )
    text = (tmp_path / "bundle" / "manifest.json").read_text(encoding="utf-8")
    assert str(root) not in text and "z.mid" not in text and "a.mid" not in text
    assert [item.source_digest for item in manifest.inputs] == sorted(item.source_digest for item in manifest.inputs)

def test_build_rejects_symlink_escape_and_external_valid_midi_at_root_boundary(tmp_path: Path) -> None:
    root = tmp_path / "root"; root.mkdir(); outside = tmp_path / "outside.mid"; outside.write_bytes(MINIMAL_TYPE1_SMF)
    (root / "inside.mid").write_bytes(MINIMAL_TYPE1_SMF)
    (root / "escape.mid").symlink_to(outside)
    with pytest.raises(GrooveBuildError, match="escapes authorized root"):
        authorize_input(root, root / "escape.mid", source_kind="author", license_id="private-full", redistribution="full")
    with pytest.raises(GrooveBuildError, match="authorized root"):
        authorize_input(root, outside, source_kind="author", license_id="private-full", redistribution="full")
    valid_input, token = authorize_input(root, root / "inside.mid", source_kind="author", license_id="private-full", redistribution="full")
    with pytest.raises(GrooveBuildError, match="authorized root"):
        compile_one(BuildInput(path=outside, source_kind="author", license_id="private-full", redistribution="full"), build_id="b1", authorized_source=token)
    with pytest.raises(GrooveBuildError, match="license"):
        compile_one(valid_input.model_copy(update={"license_id": "", "redistribution": "blocked"}), build_id="b1", authorized_source=token)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_build.py`
Expected: FAIL because `build_seed_bundle`, `authorize_input`, and the scanner-issued `AuthorizedSource` contract do not exist.

- [ ] **Step 3: Write minimal implementation**

Resolve each path and require `resolved.is_relative_to(input_root.resolve())`; `authorize_input` is the only scanner/root-validator constructor for `AuthorizedSource`, accepts regular `.mid`/`.midi` files at most 8 MiB, hashes bytes, and returns a token containing the resolved root/path/digest. `build_seed_bundle` calls `authorize_input` for every declared input and passes the resulting token to `compile_one`; `compile_one` rechecks token root/path/digest before any license validation, so a valid MIDI outside the authorized root fails with an authorization error rather than a license error. Require non-empty license and valid redistribution; sort inputs by `source_digest` directly and assert that ordering in the manifest; derive `build_id` from a canonical manifest that excludes time; compile each item independently and record digest/reason failures; fail final publication if any manifest integrity check fails. Write JSON UTF-8 compact sorted keys and a report that may contain wall-clock observations only outside the seed identity.

```python
def validate_input_path(input_root: Path, candidate: Path) -> Path:
    root = input_root.resolve(strict=True)
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise GrooveBuildError("input escapes authorized root")
    if resolved.suffix.lower() not in {".mid", ".midi"} or not resolved.is_file():
        raise GrooveBuildError("unsupported or non-regular MIDI input")
    if resolved.stat().st_size > MAX_INPUT_BYTES:
        raise GrooveBuildError("MIDI input exceeds 8 MiB")
    return resolved

def authorize_input(input_root: Path, candidate: Path, *, source_kind: str, license_id: str, redistribution: Redistribution) -> tuple[BuildInput, AuthorizedSource]:
    resolved = validate_input_path(input_root, candidate)
    digest = sha256_hex(resolved.read_bytes())
    token = AuthorizedSource(root=input_root.resolve(strict=True), path=resolved, source_digest=digest)
    return BuildInput(path=resolved, source_kind=source_kind, license_id=license_id, redistribution=redistribution), token

def compile_one(build_input: BuildInput, *, build_id: str, authorized_source: AuthorizedSource) -> CompiledGrooveArtifactV1:
    if authorized_source.root not in build_input.path.parents or authorized_source.path != build_input.path:
        raise GrooveBuildError("input is outside authorized root")
    if sha256_hex(build_input.path.read_bytes()) != authorized_source.source_digest:
        raise GrooveBuildError("authorized source digest changed")
    if not build_input.license_id:
        raise GrooveBuildError("license is required")
    parsed = parse_smf(build_input.path.read_bytes())
    return compile_parsed_artifact(build_input, parsed, build_id=build_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_build.py`
Expected: PASS with deterministic manifest, path exclusion, sorting, symlink, size, and license tests.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/groove_intelligence/build.py tests/test_groove_build.py tests/fixtures/groove_smf.py
git commit -m "feat: add deterministic pilot corpus compiler"
```

### Task 5: SQLite v1 immutable seed bundle and logical digest

**Files:**
- Create: `ableton_mcp_server/groove_intelligence/index.py`
- Create: `tests/test_groove_index.py`
- Create: `tests/fixtures/groove_bundle.py`
- Modify: `ableton_mcp_server/groove_intelligence/build.py`
- Modify: `ableton_mcp_server/groove_intelligence/schema.py`

**Interfaces:**
- Consumes `CompiledGrooveArtifactV1` and manifest from Task 4.
- Produces `write_index(bundle_dir: Path, artifacts: Sequence[CompiledGrooveArtifactV1], manifest: GrooveSeedBundleManifestV1) -> None`, `open_readonly_index(bundle_dir: Path) -> ReadonlyGrooveIndex`, `ReadonlyGrooveIndex.card_row(artifact_id: str) -> Mapping[str, object] | None`, `ReadonlyGrooveIndex.projection(artifact_id: str, name: str, version: str) -> bytes`, and `logical_index_digest(connection: sqlite3.Connection) -> str`.
- `GrooveSeedBundleManifestV1.inputs` is a tuple of path-free records carrying `source_digest`, `artifact_id`, and rights/provenance metadata; its order is the source-digest order asserted by Task 4 and is never derived from artifact-id lexical order.

- [ ] **Step 1: Write the failing tests**

```python
def test_index_uses_immutable_query_only_connection_and_schema_v1(tmp_path: Path) -> None:
    bundle = build_pilot_bundle(tmp_path)
    index = open_readonly_index(bundle)
    assert index.user_version == 1
    assert index.meta["schema_version"] == "groove.index.v1"
    with pytest.raises(GrooveIndexReadOnlyError):
        index.connection.execute("CREATE TABLE forbidden(name TEXT)")

def test_seed_reopens_after_source_directory_is_removed(tmp_path: Path) -> None:
    bundle = build_pilot_bundle(tmp_path)
    shutil.rmtree(tmp_path / "corpus")
    index = open_readonly_index(bundle)
    assert index.card_row(index.manifest.artifact_ids[0])["artifact_id"].startswith("ga1_")

def test_logical_digest_is_stable_even_when_sqlite_file_bytes_differ(tmp_path: Path) -> None:
    first = build_pilot_bundle(tmp_path / "one")
    second = build_pilot_bundle(tmp_path / "two")
    assert json.loads((first / "manifest.json").read_text())["logical_index_digest"] == json.loads((second / "manifest.json").read_text())["logical_index_digest"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_index.py`
Expected: FAIL because the SQLite writer/reader and the shared `tests/fixtures/groove_bundle.py` helper do not exist.

- [ ] **Step 3: Write minimal implementation**

Create the exact DDL from spec sections 6.4 (`index_meta`, `artifacts`, `facets`, `features`, `feature_norms`, `projections`, `payloads`, `lineage`, `provenance` and the four indexes), set `PRAGMA user_version=1`, insert all rows with bound parameters, compress projection JSON with zlib raw, and calculate the logical digest from all non-meta rows ordered by primary keys while excluding self-referential digest keys. Open with URI `file:<resolved>?mode=ro&immutable=1`, set `PRAGMA query_only=ON` and `foreign_keys=ON`, validate required metadata and manifest digest before returning the adapter. Payload reads must call `decompress_bounded` only after exact artifact/capability checks.

Own the shared fixture before any consumer uses it. In `tests/fixtures/groove_bundle.py`, define exactly `build_pilot_bundle(tmp_path: Path, *, source_root_name: str = "corpus") -> Path` and `run_pilot_cli(tmp_path: Path) -> dict[str, object]`. The builder creates `tmp_path/source_root_name/pilot-a.mid` from `MINIMAL_TYPE1_SMF` and `pilot-b.mid` from `MULTI_TRACK_SMF`, writes a manifest containing only relative names and explicit author licenses, calls `build_seed_bundle(input_root=source_root, inputs=authorized_inputs, output_dir=tmp_path / "bundle", build_config={"pilot": "v1"})` after producing `authorized_inputs` through the scanner, and returns that bundle directory. The CLI helper invokes the repository's `scripts/build_groove_seed.py` with `REPO_ROOT / ".venv-win/Scripts/python.exe"`, `--input-root`, `--manifest`, and `--output`, parses stdout JSON, and returns it. Every test creates its own temporary bundle; no module-level runtime, index, request, or artifact singleton is allowed.

```python
def build_pilot_bundle(tmp_path: Path, *, source_root_name: str = "corpus") -> Path:
    source_root = tmp_path / source_root_name
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "pilot-a.mid").write_bytes(MINIMAL_TYPE1_SMF)
    (source_root / "pilot-b.mid").write_bytes(MULTI_TRACK_SMF)
    inputs = [
        BuildInput(path=source_root / "pilot-a.mid", source_kind="author", license_id="private-full", redistribution="full"),
        BuildInput(path=source_root / "pilot-b.mid", source_kind="author", license_id="private-derived", redistribution="derived_only"),
    ]
    build_seed_bundle(input_root=source_root, inputs=inputs, output_dir=tmp_path / "bundle", build_config={"pilot": "v1"})
    return tmp_path / "bundle"

def run_pilot_cli(tmp_path: Path) -> dict[str, object]:
    root = tmp_path / "corpus"
    root.mkdir(parents=True, exist_ok=True)
    (root / "pilot-a.mid").write_bytes(MINIMAL_TYPE1_SMF)
    (root / "pilot-b.mid").write_bytes(MULTI_TRACK_SMF)
    bundle = tmp_path / "cli-bundle"
    manifest = root / "pilot-manifest.json"
    manifest.write_text(json.dumps({"files": ["pilot-a.mid", "pilot-b.mid"]}), encoding="utf-8")
    completed = subprocess.run([str(REPO_ROOT / ".venv-win/Scripts/python.exe"), "scripts/build_groove_seed.py", "--input-root", str(root), "--manifest", str(manifest), "--output", str(bundle)], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    return json.loads(completed.stdout)
```

```python
def open_readonly_index(bundle_dir: Path) -> ReadonlyGrooveIndex:
    manifest = GrooveSeedBundleManifestV1.model_validate_json((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    db = (bundle_dir / "index.sqlite").resolve(strict=True)
    connection = sqlite3.connect(f"file:{db.as_posix()}?mode=ro&immutable=1", uri=True, timeout=0.25)
    connection.execute("PRAGMA query_only=ON")
    if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
        connection.close(); raise GrooveSchemaUnsupported("SQLite user_version is not 1")
    meta = dict(connection.execute("SELECT key,value FROM index_meta"))
    if meta.get("manifest_digest") != manifest.manifest_digest or meta.get("schema_version") != "groove.index.v1":
        connection.close(); raise GrooveIndexInvalid("manifest or schema digest mismatch")
    return ReadonlyGrooveIndex(connection=connection, manifest=manifest, meta=meta)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_index.py`
Expected: PASS with immutable open, source-path independence, digest stability, metadata validation, bounded projection/payload reads, and rejection of schema/user_version drift.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/groove_intelligence/index.py ableton_mcp_server/groove_intelligence/build.py ableton_mcp_server/groove_intelligence/schema.py tests/test_groove_index.py
git commit -m "feat: write immutable groove seed index"
```

### Task 6: Pilot gate, repeatability report, and full-scan hold point

**Files:**
- Create: `scripts/build_groove_seed.py`
- Create: `tests/test_groove_pilot_gate.py`
- Create: `docs/groove_intelligence/pilot-build.md`

**Interfaces:**
- Consumes `build_seed_bundle` and the fixture corpus only.
- Produces CLI `.\.venv-win\Scripts\python.exe scripts/build_groove_seed.py --input-root <pilot-root> --manifest <manifest.json> --output <bundle-dir>`; CLI must require an explicit input root and manifest, never discover a directory implicitly, and write no private path to bundle outputs.

- [ ] **Step 1: Write the failing tests**

```python
from tests.fixtures.groove_bundle import run_pilot_cli

def test_two_pilot_builds_have_equal_manifest_and_logical_digests(tmp_path: Path) -> None:
    first = run_pilot_cli(tmp_path / "one")
    second = run_pilot_cli(tmp_path / "two")
    assert first["bundle_manifest_digest"] == second["bundle_manifest_digest"]
    assert first["logical_index_digest"] == second["logical_index_digest"]
    assert first["artifact_ids"] == second["artifact_ids"]

def test_cli_does_not_accept_unbounded_scan_flag() -> None:
    result = subprocess.run([str(REPO_ROOT / ".venv-win/Scripts/python.exe"), "scripts/build_groove_seed.py", "--help"], text=True, capture_output=True, check=True)
    assert "--input-root" in result.stdout and "--max-files" not in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_pilot_gate.py`
Expected: FAIL because the CLI and pilot gate do not exist.

- [ ] **Step 3: Write minimal implementation**

The CLI loads only the explicitly listed pilot manifest, validates each entry against the authorized root, calls `build_seed_bundle`, prints compact JSON containing bundle/logical digests and artifact ids, and exits nonzero on any gate failure. The companion document records that full corpus enumeration is a later separately authorized operation and names the exact pilot fixture command. The test invokes the CLI twice with the same bytes in different temporary roots and deletes the first source before reopening the second bundle.

- [ ] **Step 4: Run the phase gate**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_canonical.py tests/test_groove_midi_lossless.py tests/test_groove_projections.py tests/test_groove_rights.py tests/test_groove_build.py tests/test_groove_index.py tests/test_groove_pilot_gate.py`; `.\.venv-win\Scripts\python.exe -m ruff check ableton_mcp_server/groove_intelligence scripts/build_groove_seed.py tests/test_groove_*.py`; `.\.venv-win\Scripts\python.exe -m mypy --strict ableton_mcp_server/groove_intelligence`
Expected: PASS; two pilot builds have identical manifest/logical/artifact/projection/lineage digests; private path scan is empty; source deletion does not prevent seed opening.

- [ ] **Step 5: Commit**

```powershell
git add scripts/build_groove_seed.py docs/groove_intelligence/pilot-build.md tests/test_groove_pilot_gate.py
git commit -m "test: gate deterministic groove pilot build"
```

### Task 7: Phase terminal evidence and handoff

**Files:**
- Modify: no target-repository files. The parent creates `C:/Users/Usuario/repos/workflow-main/Lunacy/runs/drum-groove-intelligence/phases/01-corpus-index/reports/terminal.md` and `C:/Users/Usuario/repos/workflow-main/Lunacy/runs/drum-groove-intelligence/phases/01-corpus-index/evidence/phase1-tests.txt` as uncommitted control-plane artifacts after the worker handoff; the phase worker does not create or stage them.

**Interfaces:**
- Consumes the focused commands and pilot outputs from Tasks 1–6.
- Returns exact command output and exit codes to the parent; the parent publishes an immutable `FINAL` report only if all gate assertions pass, otherwise records `BLOCKED` and does not activate phase 2.

- [ ] **Step 1: Write the failing evidence check**

```powershell
if (-not (Test-Path 'docs/groove_intelligence/pilot-build.md')) { throw 'phase-1 documentation missing' }
.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_pilot_gate.py
```

- [ ] **Step 2: Run it to verify the report is not yet publishable**

Run: `Test-Path C:/Users/Usuario/repos/workflow-main/Lunacy/runs/drum-groove-intelligence/phases/01-corpus-index/reports/terminal.md`
Expected: `False` before the parent publishes the terminal report.

- [ ] **Step 3: Write the report with fresh evidence**

Return target HEAD, phase commits, exact commands and exit codes, pilot input count, manifest/logical/artifact/projection/lineage digest equality, private-path scan result, source-deletion reopen result, dependency/license statement, worktree choice, preserved unrelated changes, and the next phase activation condition to the parent. The parent writes the two control-plane files; no full corpus count is recorded because no full scan is authorized.

- [ ] **Step 4: Verify the report and owned diff**

Run: `git diff --check -- docs/superpowers/plans`; `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_pilot_gate.py`; `Get-Content -Raw C:/Users/Usuario/repos/workflow-main/Lunacy/runs/drum-groove-intelligence/phases/01-corpus-index/reports/terminal.md`
Expected: target checks exit 0; parent-owned terminal artifacts are present only after publication and contain `FINAL`, exact hashes, and no unresolved decision.

- [ ] **Step 5: Commit only target-repository phase-1 implementation paths**

```powershell
git add ableton_mcp_server/groove_intelligence scripts/build_groove_seed.py tests/fixtures/groove_smf.py tests/fixtures/groove_bundle.py tests/test_groove_*.py docs/groove_intelligence/pilot-build.md
git commit -m "feat: complete portable groove corpus index phase"
```
