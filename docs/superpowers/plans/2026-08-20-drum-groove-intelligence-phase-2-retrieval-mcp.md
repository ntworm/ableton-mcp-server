# Drum Groove Intelligence Phase 2 — Retrieval, Generation, and Local MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the phase-1 immutable seed into bounded deterministic search, evidence, artifact generation, and comparison, then expose `groove_search`, `groove_evidence`, `groove_generate`, and `groove_compare` as explicit top-level FastMCP tools that work without Live or a neural provider.

**Architecture:** `ReadonlyGrooveIndex` is the only SQL owner and executes a closed set of parameterized statements. `cards.py` emits bounded card envelopes; `search.py` implements the versioned multi-axis ranker and signed cursor; `artifacts.py` stores content-addressed derived envelopes; `deterministic.py` transforms a parent artifact with a seeded, versioned algorithm. `server.py` wrappers validate explicit Pydantic models before resolving the host-configured `GrooveRuntime`; no wrapper receives a path, SQL, BLOB, or prompt.

**Tech Stack:** Existing Python/Pydantic v2/FastMCP/pytest plus phase-1 stdlib/SQLite interfaces. No package installation, model runtime, or Live bridge call.

**Spec:** `docs/superpowers/specs/2026-08-20-drum-groove-intelligence-design.md` at `0ea5b3712b32650e861b6e0380860e8133c2e388`.

## Global Constraints

- New cards never return note arrays, payload bytes, BLOBs, source paths, SQL, or private corpus identifiers.
- Search is deterministic: `groove-ranker-v1`, weights `text=20/100`, `facets=25/100`, `features=40/100`, `projection_coverage=15/100`; with no requested projections use `text=4/17`, `facets=5/17`, `features=8/17`.
- Filters are AND between axes and OR within an axis; missing required features/projections do not match; missing unconstrained features are unavailable, not zero.
- Cursor payload is `groove.search.cursor.v1`, max 4 KiB, checksum/domain exact, query hash excludes cursor, and mismatch fails closed.
- Search limit 1–50 (default 20), card 6 KiB, evidence 32 KiB, generation 16 KiB, compare 128 KiB, error 8 KiB, aggregate response 524,288 UTF-8 bytes.
- `groove_generate` accepts one artifact id or one inline search source, bars 1–64, transforms in `[-1,1]`, integer seed, deterministic default provider, and writes only to a content-addressed local store.
- Rights are recomputed from parents; derived-only artifacts may search/evidence/generate but cannot apply.
- Existing legacy `music_*` payloads, tests, and order of the four traits remain unchanged.
- At execution time the worker records disposable-worktree/current-branch choice and owns only paths listed in a task; parent verifies all concurrent edits before merge.

### Task 1: Runtime, bounded cards, and closed read-only adapter

**Files:**
- Create: `ableton_mcp_server/groove_intelligence/runtime.py`
- Create: `ableton_mcp_server/groove_intelligence/cards.py`
- Modify: `ableton_mcp_server/groove_intelligence/index.py`
- Create: `tests/fixtures/groove_runtime.py`
- Test: `tests/test_groove_cards.py`
- Test: `tests/test_groove_index_adapter.py`

**Interfaces:**
- Consumes phase-1 `open_readonly_index`, `MidiArtifactV1`, rights and decompression contracts plus `mcp.types.TextContent` and `fastmcp.tools.ToolResult` from the pinned FastMCP 3.4.x runtime.
- Produces the `ArtifactStore` protocol (`put`, `get`, `contains`), `GrooveRuntime(index: ReadonlyGrooveIndex, store: ArtifactStore, client: Client | None = None, provider: GrooveProvider | None = None)`, `GrooveRuntime.card(artifact_id: str) -> ArtifactCardV1`, `ConditionCardV1`, `ArtifactCardV1`, `EvidenceCardV1`, `GenerationCardV1`, `CompareCardV1`, `ResponseBudget`, `serialize_tool_result(result: ToolResult) -> bytes`, `ResponseBudget.measure_tool_result(result: ToolResult) -> int`, `assert_tool_result_budget(result: ToolResult, budget: ResponseBudget) -> None`, `build_budgeted_json(value: object, budget: ResponseBudget) -> str`, `ReadonlyGrooveIndex.search_rows(criteria: SearchCriteriaV1) -> tuple[Mapping[str, object], ...]`, `ReadonlyGrooveIndex.load_artifact(artifact_id: str) -> MidiArtifactV1`, and `ReadonlyGrooveIndex.load_projection(artifact_id: str, projection_id: str) -> ProjectionValueV1`. The fixture uses `load_artifact` only to populate `ArtifactStore`; all runtime and generated card paths call `GrooveRuntime.card`, which reads the store artifact and joins bounded projections, never `ReadonlyGrooveIndex.card`.

- [ ] **Step 1: Write the failing tests**

```python
from mcp.types import TextContent

from tests.fixtures.groove_runtime import make_pilot_runtime

def test_artifact_card_is_bounded_and_contains_capabilities_without_payload(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    card = runtime.card(runtime.index.manifest.artifact_ids[0])
    serialized = canonical_json(card.model_dump(exclude_none=True))
    assert len(serialized) <= 6 * 1024
    assert "payload" not in serialized and "source_path" not in serialized and "notes" not in serialized
    assert card.capabilities.apply.allowed is True

def test_index_adapter_uses_only_allowlisted_statements(tmp_path: Path) -> None:
    index = make_pilot_runtime(tmp_path).index
    with pytest.raises(GrooveQueryRejected, match="statement not allowlisted"):
        index.execute_for_test("SELECT * FROM artifacts")
    artifact_id = index.manifest.artifact_ids[0]
    assert index.load_projection(artifact_id, "groove.hvo.v1").schema_version == "groove.hvo.v1"

def test_budget_counts_actual_tool_result_wire_once() -> None:
    result = ToolResult(structured_content={"x": "é"}, content=[TextContent(type="text", text="x")], meta={"trace": "t"})
    expected = len(serialize_tool_result(result))
    assert ResponseBudget(max_bytes=expected).measure_tool_result(result) == expected
    with pytest.raises(GrooveResponseBudgetExceeded):
        assert_tool_result_budget(result, ResponseBudget(max_bytes=expected - 1))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_cards.py tests/test_groove_index_adapter.py`
Expected: FAIL because runtime/cards/allowlisted adapter methods do not exist.

- [ ] **Step 3: Write minimal implementation**

Define Pydantic cards with `extra="forbid"`, omit optional `None` fields, cap warning/limitation arrays, and construct cards from selected columns only. Register SQL strings in a private tuple keyed by operation (`card`, `features`, `projection`, `lineage`); bind every artifact id/name/version; reject arbitrary SQL. `serialize_tool_result` is the single wire serializer used by `_explicit_json_result`: it serializes the actual FastMCP `ToolResult` envelope, including `structured_content`, every emitted text/content block, `is_error`, and present `meta` fields, as compact canonical UTF-8 JSON. `ResponseBudget.measure_tool_result` returns the byte length of that exact serializer output; it does not estimate from the payload or omit envelope overhead. The wrapper constructs one `ToolResult`, measures it, then returns that same object.

`GrooveRuntime.card` obtains the source artifact only from `ArtifactStore.get`, then reads named bounded projections through the read-only adapter and constructs the card from that artifact plus projection values. It never calls `ReadonlyGrooveIndex.card`; the fixture's `populate_pilot_store` is the only place that materializes source artifacts from the pilot bundle. Generated artifacts are inserted into the same store before their card is built, so generation/evidence/compare tests cannot accidentally read an immutable seed row as a generated artifact.

```python
class ResponseBudget:
    def __init__(self, max_bytes: int = 524_288) -> None:
        self.max_bytes = max_bytes

    def measure_tool_result(self, result: ToolResult) -> int:
        return len(serialize_tool_result(result))

    def assert_tool_result(self, result: ToolResult) -> None:
        if self.measure_tool_result(result) > self.max_bytes:
            raise GrooveResponseBudgetExceeded("response budget exceeded")

def serialize_tool_result(result: ToolResult) -> bytes:
    wire = {"structured_content": result.structured_content, "content": [block.model_dump() for block in result.content], "is_error": result.is_error, "meta": result.meta}
    return canonical_json(wire)

def assert_tool_result_budget(result: ToolResult, budget: ResponseBudget) -> None:
    budget.assert_tool_result(result)
```

The fixture module must expose concrete builders used by every phase-2 test, so tests never open a private path:

```python
def make_pilot_runtime(tmp_path: Path) -> GrooveRuntime:
    from tests.fixtures.groove_bundle import build_pilot_bundle
    bundle_dir = build_pilot_bundle(tmp_path)
    index = open_readonly_index(bundle_dir)
    store = MemoryArtifactStore()
    populate_pilot_store(index, store, bundle_dir)
    return GrooveRuntime(index=index, store=store)

class MemoryArtifactStore:
    def __init__(self) -> None:
        self._items: dict[str, MidiArtifactV1] = {}
    def put(self, artifact: MidiArtifactV1) -> ArtifactId:
        self._items[artifact.artifact_id] = artifact
        return artifact.artifact_id
    def get(self, artifact_id: str) -> MidiArtifactV1:
        return self._items[artifact_id]
    def contains(self, artifact_id: str) -> bool:
        return artifact_id in self._items

def build_source_artifact_from_bundle(bundle_dir: Path, artifact_id: str) -> MidiArtifactV1:
    index = open_readonly_index(bundle_dir)
    return index.load_artifact(artifact_id)

def populate_pilot_store(index: ReadonlyGrooveIndex, store: MemoryArtifactStore, bundle_dir: Path) -> None:
    for artifact_id in index.manifest.artifact_ids:
        store.put(build_source_artifact_from_bundle(bundle_dir, artifact_id))

def make_pilot_card(runtime: GrooveRuntime) -> ArtifactCardV1:
    return runtime.card(runtime.index.manifest.artifact_ids[0])

def make_search_request(*, facets: dict[str, list[str]] | None = None, query: str | None = None, limit: int = 20, cursor: str | None = None) -> SearchRequestV1:
    return SearchRequestV1(schema_version="groove.search.request.v1", query=query, facets=facets, limit=limit, cursor=cursor)

def make_generate_request(runtime: GrooveRuntime, *, seed: int = 7, bars: int = 4, provider: str = "deterministic") -> GenerateRequestV1:
    return GenerateRequestV1(schema_version="groove.generate.request.v1", source={"artifact_id": runtime.index.manifest.artifact_ids[0]}, transforms={"density": 0.2}, bars=bars, seed=seed, provider=provider)

def make_evidence_request(runtime: GrooveRuntime) -> EvidenceRequestV1:
    return EvidenceRequestV1(schema_version="groove.evidence.request.v1", artifact_id=runtime.index.manifest.artifact_ids[0], include_projections=["hvo", "features", "grammar"])

def make_compare_request(runtime: GrooveRuntime) -> CompareRequestV1:
    return CompareRequestV1(schema_version="groove.compare.request.v1", artifact_ids=list(runtime.index.manifest.artifact_ids[:2]), metrics=["facets", "features", "hvo", "grammar"], normalize=True)

def make_pilot_acceptance_inputs(tmp_path: Path) -> tuple[GrooveRuntime, dict[str, object]]:
    runtime = make_pilot_runtime(tmp_path)
    return runtime, {"search": make_search_request(facets={"feel": ["laid_back"]}, limit=1), "evidence": make_evidence_request(runtime), "generate": make_generate_request(runtime), "compare": make_compare_request(runtime)}
```

Each test receives `tmp_path` and calls `runtime = make_pilot_runtime(tmp_path)`; `pilot_artifact_id = runtime.index.manifest.artifact_ids[0]`. The second compare id is `runtime.index.manifest.artifact_ids[1]` from the two-entry fixture bundle. No module-level mutable runtime or source path is permitted.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_cards.py tests/test_groove_index_adapter.py`
Expected: PASS with card limits, no-payload checks, allowlisted SQL, immutable connection, and exact budget accounting.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/groove_intelligence/runtime.py ableton_mcp_server/groove_intelligence/cards.py ableton_mcp_server/groove_intelligence/index.py tests/test_groove_cards.py tests/test_groove_index_adapter.py
git commit -m "feat: add bounded groove runtime cards and index adapter"
```

### Task 2: Deterministic ranker, filters, and cursor

**Files:**
- Create: `ableton_mcp_server/groove_intelligence/search.py`
- Create: `ableton_mcp_server/groove_intelligence/mcp_models.py`
- Test: `tests/test_groove_search.py`
- Test: `tests/test_groove_cursor.py`

**Interfaces:**
- Consumes `GrooveRuntime`, `ArtifactCardV1`, `canonical_json`, `request_hash`, and index rows.
- Produces `SearchRequestV1` (exported alias `GrooveSearchRequest`), `SearchResponseV1`, `SearchCriteriaV1`, `rank_candidate(card, request) -> RankedCandidateV1`, `encode_cursor(cursor: SearchCursorV1) -> str`, `decode_cursor(token: str) -> SearchCursorV1`, and `search(runtime, request) -> SearchResponseV1`.

- [ ] **Step 1: Write the failing tests**

```python
def test_search_uses_fixed_weights_and_artifact_id_tie_break(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    result = search(runtime, make_search_request(facets={"feel": ["laid_back"]}))
    assert [item.artifact_id for item in result.items] == sorted(item.artifact_id for item in result.items)
    assert result.ranking.ranker_id == "groove-ranker-v1"
    assert result.ranking.weights == {"text": 0.2, "facets": 0.25, "features": 0.4, "projection_coverage": 0.15}

def test_cursor_rejects_query_mismatch_and_noncanonical_padding(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    first_request = make_search_request(facets={"feel": ["laid_back"]}, limit=1)
    response = search(runtime, first_request)
    assert response.next_cursor is not None
    bad = make_search_request(query="different", facets={"feel": ["laid_back"]}, limit=1, cursor=response.next_cursor)
    with pytest.raises(GrooveCursorQueryMismatch):
        search(runtime, bad)
    with pytest.raises(GrooveCursorInvalid):
        decode_cursor(response.next_cursor + "=")

def test_missing_required_feature_excludes_candidate_without_zero_score(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    request = SearchRequestV1(schema_version="groove.search.request.v1", feature_constraints=[{"name": "swing", "op": "gte", "value": 0.2}], limit=20)
    assert all("swing" in item.features for item in search(runtime, request).items)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_search.py tests/test_groove_cursor.py`
Expected: FAIL because `SearchRequestV1`, `search`, and cursor functions are not defined.

- [ ] **Step 3: Write minimal implementation**

Validate at least one criterion (`query`, facets, feature constraints, bpm, meter, or required projections). Tokenize NFC/lowercase text deterministically; normalize feature constraints using `feature_norms`; quantize scores to nine decimals; apply projection eligibility before ranking; sort by `(-score, artifact_id)`. Search constructs each returned card through `runtime.card`, never `runtime.index.card`. Cursor stores the exact schema/bundle/logical digest/ranker ids/request hash/limit/last score/last id, appends raw SHA-256 checksum after canonical JSON, base64url-no-pad encodes, rejects padding/noncanonical JSON/oversize/constant-time checksum mismatch, and resumes strictly after the last pair. `tests/fixtures/groove_runtime.py` owns `make_search_request`, `make_pilot_runtime`, `make_generate_request`, `make_evidence_request`, and `make_compare_request`; each test calls one of these with its own `tmp_path`, and no module-level `PILOT_RUNTIME`, `SEARCH_WITH_TWO_PAGES`, or artifact-id constant is permitted.

```python
def _sort_key(candidate: RankedCandidateV1) -> tuple[float, str]:
    return (-quantize_nine(candidate.score), candidate.artifact_id)

def encode_cursor(cursor: SearchCursorV1) -> str:
    payload = canonical_json(cursor.model_dump(exclude_none=True))
    checksum = hashlib.sha256(b"ABLETON-GROOVE-CURSOR-V1\x00" + payload).digest()
    return base64.urlsafe_b64encode(payload + checksum).decode("ascii").rstrip("=")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_search.py tests/test_groove_cursor.py`
Expected: PASS with AND/OR filtering, fixed weights, missing-feature behavior, projection all/any, deterministic tie-break, pagination, and cursor tamper/query/bundle/ranker rejection.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/groove_intelligence/search.py tests/test_groove_search.py tests/test_groove_cursor.py
git commit -m "feat: add deterministic groove search and cursor"
```

### Task 3: Content-addressed artifacts, deterministic generation, evidence, and compare

**Files:**
- Create: `ableton_mcp_server/groove_intelligence/artifacts.py`
- Create: `ableton_mcp_server/groove_intelligence/deterministic.py`
- Create: `ableton_mcp_server/groove_intelligence/evidence.py`
- Modify: `ableton_mcp_server/groove_intelligence/mcp_models.py`
- Create: `tests/test_groove_generation.py`
- Create: `tests/test_groove_compare.py`
- Create: `tests/test_groove_budget.py`

**Interfaces:**
- Consumes `MidiArtifactV1`, projections, rights, `GrooveRuntime`, `SearchRequestV1`, and phase-1 canonical identity functions.
- Extends the `mcp_models.py` owned by Task 2 with `GrooveEvidenceRequest`, `GrooveGenerateRequest`, and `GrooveCompareRequest` models (plus aliases `EvidenceRequestV1`, `GenerateRequestV1`, and `CompareRequestV1`), and produces `FileArtifactStore` implementing `ArtifactStore`, `ArtifactStore.put(artifact: MidiArtifactV1) -> ArtifactId`, `ArtifactStore.get(artifact_id: str) -> MidiArtifactV1`, `deterministic_generate(runtime, request: GenerateRequestV1, fallback: FallbackV1 | None = None) -> GenerationResponseV1`, `evidence(runtime, request: EvidenceRequestV1) -> EvidenceResponseV1`, and `compare(runtime, request: CompareRequestV1) -> CompareResponseV1`.

- [ ] **Step 1: Write the failing tests**

```python
def test_same_generation_request_returns_same_artifact_and_lineage(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    request = make_generate_request(runtime)
    first = deterministic_generate(runtime, request)
    second = deterministic_generate(runtime, request)
    assert first.artifact.artifact_id == second.artifact.artifact_id
    assert first.card.parent_artifact_ids == (runtime.index.manifest.artifact_ids[0],)
    assert first.card.deterministic is True and first.card.fallback is False

def test_evidence_and_compare_are_cards_only_and_bound_details(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    evidence_result = evidence(runtime, make_evidence_request(runtime))
    compare_result = compare(runtime, make_compare_request(runtime))
    assert "events" not in canonical_json(evidence_result.model_dump())
    assert len(evidence_result.card.references) <= 32
    assert len(canonical_json(compare_result.model_dump())) <= 128 * 1024

def test_generated_artifact_respects_64_bar_and_2048_event_limits(tmp_path: Path) -> None:
    runtime = make_pilot_runtime(tmp_path)
    with pytest.raises(GrooveLimitExceeded):
        deterministic_generate(runtime, make_generate_request(runtime, bars=65, seed=1))

def test_actual_emitted_tool_result_budget_is_bounded_and_uses_text_content(tmp_path: Path) -> None:
    from ableton_mcp_server import server
    result = server._explicit_json_result({"value": "x" * (524288 - 4096)})
    assert all(block.type == "text" for block in result.content)
    assert len(serialize_tool_result(result)) <= 524288
    with pytest.raises(GrooveResponseBudgetExceeded):
        server._explicit_json_result({"value": "x" * 524288})

def test_actual_emitted_tool_result_truncates_bounded_lists_before_budget_check() -> None:
    result = server._explicit_json_result({"warnings": [f"w-{index}" for index in range(20000)]})
    assert len(result.structured_content["warnings"]) < 20000
    assert len(serialize_tool_result(result)) <= 524288
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_generation.py tests/test_groove_compare.py tests/test_groove_budget.py`
Expected: FAIL because artifact store, generation, evidence, and compare functions do not exist.

- [ ] **Step 3: Write minimal implementation**

Resolve inline search sources through `search(runtime, request_with_limit_one)` and pin the selected parent id. Apply transforms in a fixed versioned order, using `random.Random(seed)` only in the deterministic module; retain original pitch/channel and lossless event ids; reject bars/event count before writing. Build a new `MidiArtifactV1` identity preimage without self-id, calculate lineage and projection digests, write one atomic local store object keyed by artifact id, and return the existing object on repeat. Evidence aggregates at most 32 role/grid references; compare refuses incompatible PPQ/meter/projection versions instead of inventing distance. All response builders invoke the aggregate budget before returning.

```python
def generate(runtime: GrooveRuntime, request: GenerateRequestV1) -> GenerationResponseV1:
    parent = runtime.store.get(resolve_source_id(runtime, request.source))
    rights = require_rights(parent, operation="generate")
    generated = deterministic_transform(parent, request.transforms, request.bars, request.seed)
    artifact_id = runtime.store.put(generated.with_lineage((parent.artifact_id,), request))
    card = build_generation_card(generated, parent, request, reproducibility_key=generated.reproducibility_key)
    return GenerationResponseV1(schema_version="groove.generate.response.v1", card=card, artifact=runtime.card(artifact_id))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_generation.py tests/test_groove_compare.py tests/test_groove_budget.py`
Expected: PASS with repeatability, lineage, rights, bounds, no-payload cards, evidence truncation, compare compatibility, and aggregate budget behavior.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/groove_intelligence/artifacts.py ableton_mcp_server/groove_intelligence/deterministic.py ableton_mcp_server/groove_intelligence/evidence.py tests/test_groove_generation.py tests/test_groove_compare.py tests/test_groove_budget.py
git commit -m "feat: add deterministic groove artifacts and comparison"
```

### Task 4: Explicit Pydantic/FastMCP contracts for four local tools

**Files:**
- Modify: `ableton_mcp_server/groove_intelligence/mcp_models.py`
- Modify: `ableton_mcp_server/models.py`
- Modify: `ableton_mcp_server/catalog.py`
- Modify: `ableton_mcp_server/server.py`
- Modify: `tests/test_models.py`
- Modify: `tests/test_catalog.py`
- Modify: `tests/test_tool_registry.py`
- Modify: `tests/test_server_tools.py`
- Modify: `tests/test_cli.py`
- Create: `tests/fixtures/groove_mcp_wire.py`
- Create: `tests/test_groove_schema.py`
- Create: `tests/test_groove_mcp_local.py`

**Interfaces:**
- Consumes `GrooveRuntime`, `search`, `evidence`, `deterministic_generate`, and `compare` from Tasks 1–3.
- Produces four request models with exact literals: `GrooveSearchRequest(schema_version="groove.search.request.v1", query=None, facets=None, feature_constraints=None, bpm=None, meter=None, seed_bundle_id=None, required_projection_ids=None, projection_operator="all", limit=20, cursor=None)`, `GrooveEvidenceRequest`, `GrooveGenerateRequest`, and `GrooveCompareRequest`; four response envelopes; `truncate_response_value(value: Mapping[str, object], *, max_items: int = 32) -> dict[str, object]`; `server._explicit_json_result(value: Mapping[str, object], *, budget: ResponseBudget = DEFAULT_RESPONSE_BUDGET) -> ToolResult`; and `server.groove_search`, `server.groove_evidence`, `server.groove_generate`, `server.groove_compare` with explicit top-level function arguments.

The shared wire helper is owned by this task. It uses only FastMCP 3.4.4's public
client/server surfaces: `Client.list_tools()` is the client-visible protocol
discovery and each returned client tool's `inputSchema` is authoritative. The
server-side `FastMCP.list_tools()` result is a `FunctionTool`; when it exposes
`.parameters`, that generated schema is normalized as the server comparison
view. The helper never reads an invented `FunctionTool.inputSchema` attribute.
The comparison deliberately removes presentation-only titles but retains
`minimum`, `maximum`, `minLength`, `maxLength`, `minItems`, `maxItems`, `enum`,
`required`, and `additionalProperties`. FastMCP 3.4.4 emits a one-value
`Literal` as JSON Schema `const`; `normalize_wire_schema` maps that public wire
representation to the equivalent one-value `enum` so the contract test proves
the constrained enum without assuming a nonexistent server attribute.

```python
from fastmcp import Client as FastMCPClient, FastMCP
from pydantic import BaseModel
import json

async def discover_client_wire_schemas(mcp: FastMCP) -> dict[str, dict[str, object]]:
    async with FastMCPClient(mcp) as client:
        listed = await client.list_tools()
    result: dict[str, dict[str, object]] = {}
    for tool in listed:
        schema = getattr(tool, "inputSchema", None)
        if schema is None:
            schema = getattr(tool, "input_schema", None)
        if not isinstance(schema, dict):
            raise AssertionError(f"client wire tool {tool.name} has no input schema")
        result[tool.name] = schema
    return result

def generated_server_schema(tool: object) -> dict[str, object]:
    parameters = getattr(tool, "parameters", None)
    if isinstance(parameters, dict):
        return parameters
    schema_method = getattr(tool, "schema", None)
    if callable(schema_method):
        schema = schema_method()
        if isinstance(schema, dict):
            return schema
    raise AssertionError("FastMCP FunctionTool exposes neither parameters nor schema()")

def normalize_wire_schema(schema: Mapping[str, object]) -> dict[str, object]:
    presentation = {"title", "$schema", "$id", "description"}
    def clean(value: object) -> object:
        if isinstance(value, dict):
            result = {key: clean(item) for key, item in value.items() if key not in presentation and key != "const"}
            if "const" in value:
                result["enum"] = [clean(value["const"])]
            return result
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value
    normalized = clean(dict(schema))
    assert isinstance(normalized, dict)
    return normalized

def assert_client_schema_constraints(schema: Mapping[str, object], model: type[BaseModel]) -> None:
    actual = normalize_wire_schema(schema)
    declared = normalize_wire_schema(model.model_json_schema())
    assert actual["additionalProperties"] is False
    assert set(actual["required"]) == set(declared["required"])
    for field_name, declared_field in declared["properties"].items():
        actual_field = actual["properties"][field_name]
        for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength", "minItems", "maxItems", "enum", "pattern"):
            declared_value = declared_field.get(key)
            actual_value = actual_field.get(key)
            if declared_value is None:
                declared_value = next((branch.get(key) for branch in declared_field.get("anyOf", []) if isinstance(branch, dict) and key in branch), None)
            if actual_value is None:
                actual_value = next((branch.get(key) for branch in actual_field.get("anyOf", []) if isinstance(branch, dict) and key in branch), None)
            if declared_value is not None:
                assert actual_value == declared_value, (field_name, key)
    constraint_keys = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength", "minItems", "maxItems", "enum", "pattern", "additionalProperties"}
    def collect(value: object, found: set[tuple[str, str]]) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in constraint_keys:
                    found.add((key, json.dumps(item, sort_keys=True)))
                collect(item, found)
        elif isinstance(value, list):
            for item in value:
                collect(item, found)
    actual_all: set[tuple[str, str]] = set()
    declared_all: set[tuple[str, str]] = set()
    collect(actual, actual_all)
    collect(declared, declared_all)
    assert declared_all <= actual_all

def schema_constraint(schema: Mapping[str, object], field_name: str, key: str) -> object:
    field = schema["properties"][field_name]
    if key in field:
        return field[key]
    for branch in field.get("anyOf", []):
        if isinstance(branch, dict) and key in branch:
            return branch[key]
    raise AssertionError(f"{field_name} has no {key} constraint")
```

- [ ] **Step 1: Write the failing tests**

```python
from tests.fixtures.groove_mcp_wire import discover_client_wire_schemas, generated_server_schema, normalize_wire_schema

@pytest.mark.asyncio
async def test_four_fastmcp_schemas_match_actual_client_wire_and_pydantic_models() -> None:
    client_wire = await discover_client_wire_schemas(server.mcp)
    generated = {tool.name: generated_server_schema(tool) for tool in await server.mcp.list_tools()}
    for name, model in GROOVE_REQUEST_MODEL_BY_TOOL.items():
        assert normalize_wire_schema(client_wire[name]) == normalize_wire_schema(generated[name])
        assert_client_schema_constraints(client_wire[name], model)
        assert normalize_wire_schema(client_wire[name])["properties"]["schema_version"]["enum"] == [model.model_fields["schema_version"].default]
        assert client_wire[name]["additionalProperties"] is False

@pytest.mark.parametrize("name", ["groove_search", "groove_evidence", "groove_generate", "groove_compare"])
def test_invalid_version_or_extra_field_fails_before_runtime_io(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "get_groove_runtime", lambda: pytest.fail("runtime must not be resolved"))
    adapter = {"groove_search": server._groove_search_from_mapping, "groove_evidence": server._groove_evidence_from_mapping, "groove_generate": server._groove_generate_from_mapping, "groove_compare": server._groove_compare_from_mapping}[name]
    with pytest.raises(ValidationError):
        adapter({"schema_version": "wrong.v1", "unexpected": True})

def test_four_local_tools_do_not_call_bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_get_client: MagicMock) -> None:
    runtime = make_pilot_runtime(tmp_path)
    monkeypatch.setattr(server, "get_groove_runtime", lambda: runtime)
    artifact_id = runtime.index.manifest.artifact_ids[0]
    server.groove_search(schema_version="groove.search.request.v1", facets={"feel": ["laid_back"]}, limit=1)
    server.groove_evidence(schema_version="groove.evidence.request.v1", artifact_id=artifact_id, include_projections=[])
    mock_get_client.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_schema.py tests/test_groove_mcp_local.py tests/test_models.py tests/test_catalog.py tests/test_tool_registry.py`
Expected: FAIL because the four names/models/wrappers are absent, client-wire schema discovery is not wired, and existing count assertions still use the old hardcoded total.

- [ ] **Step 3: Write minimal implementation**

Use Pydantic `Literal` schema versions, `ConfigDict(extra="forbid")`, the
following shared constrained aliases, exact unions, cross-field validation, and
explicit wrapper signatures whose annotations are the same aliases used by the
declared models. This is important: FastMCP introspects these top-level
annotations, so a plain `str`/`int` wrapper is a schema regression even when the
Pydantic adapter later rejects the value.

```python
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

ArtifactId = Annotated[str, Field(pattern=r"^ga1_[0-9a-f]{64}$", min_length=68, max_length=68)]
QueryText = Annotated[str, Field(min_length=1, max_length=256)]
FacetValue = Annotated[str, Field(min_length=1, max_length=64)]
ProjectionId = Literal["groove.hvo.v1", "groove.features.v1", "groove.grammar.v1"]
ProjectionIds = Annotated[list[ProjectionId], Field(min_length=1, max_length=3)]
ProjectionSelection = Annotated[list[ProjectionId], Field(max_length=3)]
FacetKey = Annotated[str, Field(min_length=1, max_length=32)]
FacetMap = Annotated[dict[FacetKey, Annotated[list[FacetValue], Field(min_length=1, max_length=32)]], Field(max_length=16)]
FeatureConstraints = Annotated[list[dict[str, object]], Field(max_length=32)]
BpmRange = Annotated[tuple[float, float], Field(min_length=2, max_length=2)]
Cursor = Annotated[str, Field(min_length=1, max_length=4096)]
QueryHash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", min_length=64, max_length=64)]
TransformMap = Annotated[dict[str, Annotated[float, Field(ge=-1.0, le=1.0)]], Field(max_length=16)]
InlineSearch = Annotated[dict[str, object], Field(min_length=1, max_length=12)]
ArtifactIdList = Annotated[list[ArtifactId], Field(min_length=2, max_length=8)]
MetricList = Annotated[list[Literal["facets", "features", "hvo", "grammar"]], Field(min_length=1, max_length=4)]
GenerationSeed = Annotated[int, Field(ge=0, le=9_223_372_036_854_775_807)]
GenerationBars = Annotated[int, Field(ge=1, le=64)]
SearchLimit = Annotated[int, Field(ge=1, le=50)]

class GrooveSourceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: ArtifactId | None = None
    search: InlineSearch | None = None

    @model_validator(mode="after")
    def exactly_one_source(self) -> "GrooveSourceV1":
        if (self.artifact_id is None) == (self.search is None):
            raise ValueError("source must contain exactly one artifact_id or search")
        return self
```

`GrooveSearchRequest`, `GrooveEvidenceRequest`, `GrooveGenerateRequest`, and
`GrooveCompareRequest` must use these aliases field-for-field (`source` is the
same `GrooveSourceV1` model in the request and wrapper); no duplicate
looser annotation is allowed in `server.py`. Register the four `ToolSpec`
entries as `domain="groove"`, `route=Route.LOCAL`, risks `READ` except
`groove_generate=LOCAL_WRITE`, and `AcceptanceMode.OFFLINE`. Add each request
class to `TOOL_REQUEST_MODELS`, each callable to `PUBLIC_TOOL_FUNCTIONS`, and
update existing registry tests to assert derived lengths
(`len(TOOL_CATALOG) == len(TOOL_REQUEST_MODELS) == len(PUBLIC_TOOL_FUNCTIONS)`)
plus required name sets instead of hardcoding a future total.
`tests/fixtures/groove_mcp_wire.py` must provide the helper signatures shown
above and `assert_client_schema_constraints`; FastMCP 3.4.4's server
`FunctionTool` exposes generated input schema as `.parameters`, while the
actual client protocol exposes it as `.inputSchema`. The helper checks both
public views and strips only presentation keys (`title`, `$schema`, `$id`,
`description`) while preserving validation properties, required fields, enums,
and `additionalProperties`. Wrappers validate first, call the runtime service
second, and use `_explicit_json_result` with one response schema version in
both structured content and the sole text block. Update `tests/test_cli.py`,
`tests/test_models.py`, `tests/test_catalog.py`, `tests/test_tool_registry.py`,
and `tests/test_server_tools.py` to derive counts from `TOOL_CATALOG`/
`PUBLIC_TOOL_FUNCTIONS` and required-name sets; phase-3 Task 4 owns
packaging/docs/acceptance count consumers and the active-claim gate after
`groove_apply` is added.

`_explicit_json_result` must construct the actual FastMCP `ToolResult` first, with `structured_content` equal to the response mapping and exactly one `TextContent` whose text is the canonical response JSON, then call `ResponseBudget.assert_tool_result` on that object. It returns the same measured object; no preflight payload estimate or second envelope is accepted. The schema test calls each private top-level mapping adapter with an unknown key so `ConfigDict(extra="forbid")` raises Pydantic `ValidationError` after Python signature binding, proving extras reach Pydantic rather than being rejected by a `**kwargs`-free public signature.
Use `from mcp.types import TextContent`; FastMCP 3.4.x does not export this class from `fastmcp.types`. Every constructor supplies `type="text"` explicitly.

```python
def truncate_response_value(value: Mapping[str, object], *, max_items: int = 32) -> dict[str, object]:
    bounded = dict(value)
    for key in ("warnings", "limitations", "references"):
        items = bounded.get(key)
        if isinstance(items, list) and len(items) > max_items:
            bounded[key] = items[:max_items]
    return bounded

def _explicit_json_result(value: Mapping[str, object], *, budget: ResponseBudget = DEFAULT_RESPONSE_BUDGET) -> ToolResult:
    bounded = truncate_response_value(value)
    text = canonical_json(bounded).decode("utf-8")
    result = ToolResult(structured_content=bounded, content=[TextContent(type="text", text=text)], is_error=False, meta=None)
    budget.assert_tool_result(result)
    return result
```

```python
def test_registry_counts_derive_from_catalog_and_public_functions() -> None:
    from ableton_mcp_server import server
    from ableton_mcp_server.catalog import TOOL_CATALOG
    from ableton_mcp_server.server import PUBLIC_TOOL_FUNCTIONS

    assert len(TOOL_CATALOG) == len(TOOL_REQUEST_MODELS) == len(PUBLIC_TOOL_FUNCTIONS)
    assert {"groove_search", "groove_evidence", "groove_generate", "groove_compare"} <= {item.name for item in TOOL_CATALOG}
    assert len(PUBLIC_TOOL_FUNCTIONS) == len(server.mcp.list_tools())

from mcp.types import TextContent

def test_truncated_response_is_the_actual_tool_result_and_fits_aggregate_budget() -> None:
    value = {"schema_version": "groove.evidence.response.v1", "references": ["r" * 10_000] * 64}
    result = _explicit_json_result(value, budget=ResponseBudget(max_bytes=524_288))
    assert isinstance(result.content[0], TextContent) and result.content[0].type == "text"
    assert len(result.content) == 1
    assert ResponseBudget(max_bytes=524_288).measure_tool_result(result) <= 524_288
```

```python
def _groove_search_from_mapping(payload: Mapping[str, object]) -> ToolResult:
    request = GrooveSearchRequest.model_validate(payload)
    return _explicit_json_result(search(get_groove_runtime(), request).model_dump(exclude_none=True))

@mcp.tool()
def groove_search(schema_version: Literal["groove.search.request.v1"], query: QueryText | None = None, facets: FacetMap | None = None, feature_constraints: FeatureConstraints | None = None, bpm: BpmRange | None = None, meter: Annotated[str | None, Field(max_length=32)] = None, seed_bundle_id: ArtifactId | None = None, required_projection_ids: ProjectionIds | None = None, projection_operator: Literal["all", "any"] = "all", limit: SearchLimit = 20, cursor: Cursor | None = None) -> ToolResult:
    return _groove_search_from_mapping(locals())

def _groove_evidence_from_mapping(payload: Mapping[str, object]) -> ToolResult:
    request = GrooveEvidenceRequest.model_validate(payload)
    return _explicit_json_result(evidence(get_groove_runtime(), request).model_dump(exclude_none=True))

@mcp.tool()
def groove_evidence(schema_version: Literal["groove.evidence.request.v1"], artifact_id: ArtifactId, query_hash: QueryHash | None = None, include_projections: ProjectionSelection | None = None) -> ToolResult:
    return _groove_evidence_from_mapping(locals())

def _groove_generate_from_mapping(payload: Mapping[str, object]) -> ToolResult:
    request = GrooveGenerateRequest.model_validate(payload)
    return _explicit_json_result(deterministic_generate(get_groove_runtime(), request).model_dump(exclude_none=True))

@mcp.tool()
def groove_generate(schema_version: Literal["groove.generate.request.v1"], source: GrooveSourceV1, transforms: TransformMap, bars: GenerationBars, seed: GenerationSeed, provider: Literal["deterministic", "neural"] = "deterministic") -> ToolResult:
    return _groove_generate_from_mapping(locals())

def _groove_compare_from_mapping(payload: Mapping[str, object]) -> ToolResult:
    request = GrooveCompareRequest.model_validate(payload)
    return _explicit_json_result(compare(get_groove_runtime(), request).model_dump(exclude_none=True))

@mcp.tool()
def groove_compare(schema_version: Literal["groove.compare.request.v1"], artifact_ids: ArtifactIdList, metrics: MetricList, normalize: bool = True) -> ToolResult:
    return _groove_compare_from_mapping(locals())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_schema.py tests/test_groove_mcp_local.py tests/test_models.py tests/test_catalog.py tests/test_tool_registry.py tests/test_server_tools.py tests/test_cli.py`
Expected: PASS; all four tools appear in catalog/models/FastMCP, schemas match exactly, invalid input performs no I/O, CLI/registry counts derive from the catalog, and legacy tools still pass.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/groove_intelligence/mcp_models.py ableton_mcp_server/models.py ableton_mcp_server/catalog.py ableton_mcp_server/server.py tests/test_models.py tests/test_catalog.py tests/test_tool_registry.py tests/test_server_tools.py tests/test_groove_schema.py tests/test_groove_mcp_local.py
git commit -m "feat: expose local groove search and generation tools"
```

### Task 5: Offline acceptance probes and phase-2 compatibility gate

**Files:**
- Modify: `ableton_mcp_server/acceptance/probes/offline.py`
- Modify: `ableton_mcp_server/acceptance/probes/__init__.py`
- Modify: `ableton_mcp_server/acceptance/runner.py`
- Create: `tests/test_groove_acceptance_offline.py`
- Modify: `tests/test_music_brain.py`
- Modify: `tests/test_music_tools.py`
- Modify: `docs/TOOL_REFERENCE.md`
- Modify: `docs/ARCHITECTURE.md`

**Interfaces:**
- Consumes the four tools and pilot seed; produces acceptance rows for `groove_search`, `groove_evidence`, `groove_generate`, and `groove_compare` under the existing offline probe group without opening a bridge. The probe entry point is `run(report: CertificationReport, tmp_path: Path, *, runtime: GrooveRuntime, requests: Mapping[str, BaseModel]) -> None`; the test fixture supplies both runtime and request objects, so no production or test module singleton is consulted.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_offline_probe_records_four_groove_tools_without_bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, requests = make_pilot_acceptance_inputs(tmp_path)
    report = CertificationReport()
    bridge_calls: list[str] = []
    monkeypatch.setattr("ableton_mcp_server.acceptance.probes.offline.get_client", lambda: bridge_calls.append("bridge"))
    await run(report, tmp_path, runtime=runtime, requests=requests)
    rows = {row["tool"]: row for row in report.tools if row["tool"].startswith("groove_")}
    assert set(rows) == {"groove_search", "groove_evidence", "groove_generate", "groove_compare"}
    assert all(row["status"] == "offline_passed" for row in rows.values())
    assert bridge_calls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_acceptance_offline.py`
Expected: FAIL because the offline probe group has no groove rows.

- [ ] **Step 3: Write minimal implementation**

Add the four names to `BASELINE_PROBE_GROUPS["offline"]`, add real calls to the configured pilot bundle in `offline.run`, and ensure runner selection includes them without duplicating synthetic rows. Update the two canonical docs with the offline-only boundary, card/no-note response rule, seed configuration, and explicit statement that legacy `music_*` remains compatible. Do not add `groove_apply` to this phase's offline probe.

- [ ] **Step 4: Run the phase gate**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_*.py tests/test_music_brain.py tests/test_music_tools.py tests/test_acceptance_runner_integration.py`; `.\.venv-win\Scripts\python.exe -m ruff check ableton_mcp_server tests scripts`; `.\.venv-win\Scripts\python.exe -m mypy --strict ableton_mcp_server/groove_intelligence ableton_mcp_server/server.py ableton_mcp_server/models.py`
Expected: PASS; local tools are callable without Live/provider/corpus path, acceptance rows are real, and all legacy music tests stay green.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/acceptance/probes/offline.py ableton_mcp_server/acceptance/probes/__init__.py ableton_mcp_server/acceptance/runner.py tests/test_groove_acceptance_offline.py tests/test_music_brain.py tests/test_music_tools.py docs/TOOL_REFERENCE.md docs/ARCHITECTURE.md
git commit -m "test: certify offline groove MCP phase"
```

### Task 6: Phase terminal evidence and handoff

**Files:**
- Modify: no target-repository files. The parent creates `C:/Users/Usuario/repos/workflow-main/Lunacy/runs/drum-groove-intelligence/phases/02-search/reports/terminal.md` and `C:/Users/Usuario/repos/workflow-main/Lunacy/runs/drum-groove-intelligence/phases/02-search/evidence/phase2-tests.txt` as uncommitted control-plane artifacts after the worker handoff; the phase worker does not create or stage them.

**Interfaces:**
- Consumes Tasks 1–5 and fresh phase commands.
- Returns exact command output and exit codes to the parent. The parent publishes `FINAL` only when search ranking/cursor, card/budget, deterministic generation/compare, four FastMCP schemas, offline acceptance, and legacy compatibility are all evidenced; otherwise it records `BLOCKED` with exact command/output.

- [ ] **Step 1: Write the failing report check**

```powershell
.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_schema.py tests/test_groove_acceptance_offline.py
if ($LASTEXITCODE -ne 0) { throw 'phase-2 gate is red' }
```

- [ ] **Step 2: Run it before report publication**

Run: `Test-Path C:/Users/Usuario/repos/workflow-main/Lunacy/runs/drum-groove-intelligence/phases/02-search/reports/terminal.md`
Expected: `False` before the parent publishes the phase terminal report.

- [ ] **Step 3: Publish fresh evidence**

Return target HEAD, phase commits, worktree decision, exact test/lint/type commands, pilot bundle id, ranking/cursor and response-budget checks, offline probe rows, and legacy test totals to the parent. The parent writes both control-plane artifacts. Explicitly state that no Live call, neural process, package install, or private corpus scan occurred.

- [ ] **Step 4: Verify report and plan docs**

Run: `git diff --check -- docs/superpowers/plans`; `rg -n -e 'T(O)DO|T(B)D|FIX(M)E|PLACE(HOLDER)|similar[[:space:]]+to|implement[[:space:]]+later' docs/superpowers/plans/2026-08-20-drum-groove-intelligence-phase-2-retrieval-mcp.md`; `Get-Content -Raw C:/Users/Usuario/repos/workflow-main/Lunacy/runs/drum-groove-intelligence/phases/02-search/reports/terminal.md`
Expected: whitespace check passes, placeholder scan returns no lines, and report is immutable with `FINAL` or an honest `BLOCKED` state.

- [ ] **Step 5: Commit phase-2 target files**

```powershell
git add ableton_mcp_server/groove_intelligence ableton_mcp_server/acceptance tests docs/TOOL_REFERENCE.md docs/ARCHITECTURE.md
git commit -m "feat: complete deterministic groove retrieval phase"
```
