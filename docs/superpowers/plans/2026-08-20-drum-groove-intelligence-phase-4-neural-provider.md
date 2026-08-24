# Drum Groove Intelligence Phase 4 — Optional Neural Provider and Laboratory Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, offline, allowlisted neural provider behind a strict subprocess protocol and laboratory promotion gates while preserving deterministic generation as a complete, installable, provider-free runtime.

**Architecture:** `provider.py` defines only the provider protocol, bounded condition card, candidate, identity, and stable failure enums. `neural_subprocess.py` launches a registry-selected executable without shell, with an allowlisted environment, temporary directory, length-prefixed JSON frames, strict method/schema/size/depth/time limits, stderr sanitization, and process-tree termination. `fallback.py` validates/canonicalizes candidates and calls the phase-2 deterministic generator with the same seed/parents on every provider failure. `lab.py` runs versioned contract/fallback/reproducibility/quality/privacy-license/cost gates and writes a report; no failed candidate is promoted.

**Tech Stack:** Python >=3.10 stdlib subprocess/temporary files/JSON/struct/hashlib/resource/process-group primitives already available on the host, existing Pydantic/pytest. No neural package, model download, GPU runtime, network, training, or package installation.

**Spec:** `docs/superpowers/specs/2026-08-20-drum-groove-intelligence-design.md` at `0ea5b3712b32650e861b6e0380860e8133c2e388`.

## Global Constraints

- Provider is selected only by `provider="neural"` and an existing local allowlisted registry entry; request never supplies executable, argv, shell, cwd, URL, token, or model path.
- Condition card contains bounded facets/features/HVO only; it never contains SQL, private corpus path, raw BLOB, source bytes, or kit mapping.
- IPC methods are exactly `hello`, `generate`, and `shutdown`; frames are UTF-8 length-prefixed JSON, max 256 KiB, JSON depth 8, max 2,048 candidate events.
- Time limits are startup 2 s, generation 5 s, shutdown 1 s; memory 512 MiB and CPU 2 s per generation. Timeout, protocol, output, and resource failures kill the process tree once and never retry.
- Environment is an allowlist with minimal `PATH`, `TEMP`, `TMP`, `PYTHONNOUSERSITE=1`, locale `C`; cloud tokens/proxies/keys are removed. stderr is captured at 16 KiB, sanitized, and never sent to MCP.
- Stable failure enums are `not_installed`, `launch_denied`, `offline_policy`, `protocol_violation`, `timeout`, `exit_nonzero`, `output_too_large`, `output_invalid`, `resource_limit`, and `internal`.
- Neural output must pass schema/parser/limits/hash/projections/provenance/rights before store insertion; partial output is never returned as neural success.
- Missing identity (model digest, runtime, sampling config, provider version, seed, parent ids) makes neural production invalid; lab may record the rejection.
- If any lab gate fails, provider remains disabled and deterministic runtime remains complete. No implementation task may add an optional dependency to `pyproject.toml`.
- Dependency/licensing policy is explicit: use only the repository's existing Python runtime and stdlib; do not add a neural package, model artifact, or license file. A future provider dependency needs a new approved decision with exact version, SPDX license, offline provenance, and uninstall/fallback test before any manifest edit.

### Task 1: Provider protocol, identities, bounded condition cards, and registry

**Files:**
- Create: `ableton_mcp_server/groove_intelligence/provider.py`
- Create: `ableton_mcp_server/groove_intelligence/provider_registry.py`
- Create: `tests/test_groove_provider_contract.py`
- Create: `tests/fixtures/groove_provider_payloads.py`

**Interfaces:**
- Consumes phase-2 `ConditionCardV1`, `MidiArtifactV1`, `ArtifactStore`, `ProviderLimitsV1` bounds, and deterministic identity functions.
- Produces `GrooveProvider` protocol, `ProviderArtifactCandidate`, `ProviderFailure`, `ProviderFailureCode`, `ProviderIdentityV1`, `ProviderLimitsV1`, `AllowlistedProviderV1`, `load_provider_registry(path: Path) -> ProviderRegistry`, and `sanitize_provider_diagnostic(text: str) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
def test_provider_request_contains_only_bounded_card_and_complete_identity(tmp_path: Path) -> None:
    card, artifact_id = make_pilot_card_and_id(tmp_path)
    request = build_condition_card(card, parent_artifact_ids=(artifact_id,), seed=7, limits=make_provider_limits())
    serialized = canonical_json(request.model_dump())
    assert len(serialized) < 32 * 1024
    assert all(forbidden not in serialized for forbidden in (b"source_path", b"payload", b"sqlite", b"notes"))
    assert request.identity.model_digest == "sha256:" + "a" * 64

def test_registry_rejects_request_supplied_executable_and_unknown_failure_code(tmp_path: Path) -> None:
    path = tmp_path / "providers.json"
    path.write_text(json.dumps({"providers": [{"provider_id": "p1", "executable": "user.exe", "argv": ["--bad"], "executable_digest": "sha256:" + "a" * 64, "version": "1"}]}), encoding="utf-8")
    registry = load_provider_registry(path)
    assert registry.get("p1").argv == ("--provider-host",)
    with pytest.raises(ValidationError):
        ProviderFailure(code="command_from_request", provider_id="p1", diagnostic_digest="a" * 16)

def test_diagnostic_sanitization_removes_paths_and_secrets() -> None:
    assert sanitize_provider_diagnostic("C:\\Users\\me\\token=secret123") == "<path> token=<redacted>"
```

`tests/fixtures/groove_provider_payloads.py` must define factories rather than module singletons: `make_pilot_card_and_id(tmp_path: Path) -> tuple[ConditionCardV1, str]`, `make_condition_card(tmp_path: Path, *, seed: int = 7) -> ConditionCardV1`, `make_provider_limits(**overrides: object) -> ProviderLimitsV1`, `make_provider_registry(tmp_path: Path) -> ProviderRegistry`, `make_provider_failure(code: ProviderFailureCode = ProviderFailureCode.internal) -> ProviderFailure`, `make_candidate(tmp_path: Path, *, valid: bool = True, complete_identity: bool = True) -> ProviderArtifactCandidate`, `model_identity_missing_digest() -> ProviderIdentityV1`, `make_provider_runtime(tmp_path: Path, *, failure: ProviderFailure | None = None, candidate: ProviderArtifactCandidate | None = None, identity: ProviderIdentityV1 | None = None) -> GrooveRuntime`, `make_deterministic_request(provider: Literal["deterministic", "neural"] = "neural", seed: int = 7) -> GenerateRequestV1`, `make_fixture_set(tmp_path: Path) -> ProviderFixtureSet`, and `make_promotion_signer() -> HmacPromotionSigner`. Each factory builds from the phase-1 pilot bundle and contains only synthetic bounded events; no provider executable or source path is read during import. Tests call factories with their own `tmp_path` and never use `PILOT_CARD`, `PILOT_ARTIFACT_ID`, `GOOD_PROVIDER_CANDIDATE`, or other module-level mutable objects.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_provider_contract.py`
Expected: FAIL because provider protocol, registry, and failure enums do not exist.

- [ ] **Step 3: Write minimal implementation**

Use Pydantic `extra="forbid"` models and a `Protocol` with exactly `generate(condition_card, parent_artifact_ids, seed, limits)`. Registry entries contain provider id, executable digest, version, and fixed argv from a checked-in allowlist; ignore/reject executable/argv fields from untrusted request data. Condition card caps arrays and strips all raw/source/path fields. Diagnostic sanitizer replaces Windows/POSIX paths, environment assignments for token/key/secret/proxy, and executable command lines before hashing a short diagnostic digest.

```python
class ProviderFailureCode(str, Enum):
    not_installed = "not_installed"
    launch_denied = "launch_denied"
    offline_policy = "offline_policy"
    protocol_violation = "protocol_violation"
    timeout = "timeout"
    exit_nonzero = "exit_nonzero"
    output_too_large = "output_too_large"
    output_invalid = "output_invalid"
    resource_limit = "resource_limit"
    internal = "internal"

class GrooveProvider(Protocol):
    def generate(self, condition_card: ConditionCardV1, parent_artifact_ids: tuple[str, ...], seed: int, limits: ProviderLimitsV1) -> ProviderArtifactCandidate | ProviderFailure:
        raise NotImplementedError
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_provider_contract.py`
Expected: PASS with bounded card, fixed registry argv, failure enum, identity completeness, and sanitized diagnostic tests.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/groove_intelligence/provider.py ableton_mcp_server/groove_intelligence/provider_registry.py tests/test_groove_provider_contract.py tests/fixtures/groove_provider_payloads.py
git commit -m "feat: define optional groove provider contract"
```

### Task 2: Hardened length-prefixed subprocess adapter

**Files:**
- Create: `ableton_mcp_server/groove_intelligence/neural_subprocess.py`
- Create: `ableton_mcp_server/groove_intelligence/resource_limits.py`
- Create: `tests/test_groove_provider_process.py`
- Create: `tests/test_groove_resource_limits.py`
- Create: `tests/fixtures/providers/echo_provider.py`
- Create: `tests/fixtures/providers/invalid_provider.py`
- Create: `tests/fixtures/providers/slow_provider.py`

**Interfaces:**
- Consumes `ProviderRegistry`, `ProviderIdentityV1`, condition cards, and `ProviderLimitsV1` from Task 1.
- Produces `NeuralSubprocessProvider.generate(condition_card: ConditionCardV1, parent_artifact_ids: tuple[str, ...], seed: int, limits: ProviderLimitsV1) -> ProviderArtifactCandidate | ProviderFailure`, `encode_frame(payload: Mapping[str, object]) -> bytes`, `decode_frame(stream: BinaryIO) -> Mapping[str, object]`, `terminate_process_tree(process: subprocess.Popen[bytes]) -> None`, and `build_allowlisted_environment(base: Mapping[str, str]) -> dict[str, str]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_provider_uses_fixed_argv_no_shell_and_strips_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(subprocess, "Popen", capture_popen(captured, provider_script="echo_provider.py"))
    provider = NeuralSubprocessProvider(registry=make_provider_registry(tmp_path), provider_id="echo")
    card, artifact_id = make_pilot_card_and_id(tmp_path)
    result = provider.generate(card, (artifact_id,), 7, make_provider_limits())
    assert result.artifact is not None
    assert captured["shell"] is False and captured["argv"] == ["echo_provider.py", "--provider-host"]
    assert "TOKEN" not in captured["env"] and captured["env"]["PYTHONNOUSERSITE"] == "1"

@pytest.mark.parametrize("script,code", [("invalid_provider.py", "protocol_violation"), ("slow_provider.py", "timeout")])
def test_invalid_or_slow_provider_is_killed_and_returns_sanitized_failure(tmp_path: Path, script: str, code: str) -> None:
    result = run_fixture_provider(tmp_path, script, timeout_limits=make_provider_limits(startup_seconds=0.05, generate_seconds=0.05))
    assert isinstance(result, ProviderFailure) and result.code.value == code
    assert "C:\\" not in result.diagnostic and "stdout" not in result.diagnostic

def test_frames_reject_unknown_method_depth_and_256k_limit() -> None:
    with pytest.raises(ProviderProtocolError):
        decode_frame(io.BytesIO(encode_frame({"method": "exec"})))
    with pytest.raises(ProviderProtocolError):
        encode_frame({"method": "generate", "nested": [[[[[[[[[1]]]]]]]]]})
    with pytest.raises(ProviderProtocolError):
        encode_frame({"method": "generate", "payload": "x" * (256 * 1024)})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_provider_process.py`
Expected: FAIL because subprocess adapter and provider fixtures do not exist.

- [ ] **Step 3: Write minimal implementation**

Define a concrete resource interface in `resource_limits.py`: `class ResourceEnforcer(Protocol): enforce(process: subprocess.Popen[bytes], limits: ProviderLimitsV1) -> ResourceHandle; terminate(handle: ResourceHandle) -> None`. `WindowsJobObjectEnforcer` uses `ctypes.windll.kernel32.CreateJobObjectW`, `SetInformationJobObject` with `JOBOBJECT_EXTENDED_LIMIT_INFORMATION` for 512 MiB process memory and 2 s job CPU time, and `AssignProcessToJobObject`; failure to create/assign is `ProviderFailureCode.launch_denied` and has no unsafe Windows fallback. `PosixProcessGroupEnforcer` uses `start_new_session=True`, `os.setpgid`/`resource.setrlimit` where available, and kills the process group. `UnavailableEnforcer` is an explicit portable fallback that returns `resource_limit` (never silently disables enforcement), and `select_resource_enforcer(platform: str | None = None) -> ResourceEnforcer` is deterministic. Tests monkeypatch the Windows kernel32 calls to verify Job Object creation/limits/assignment, verify portable fallback failure, and verify POSIX process-group selection without spawning a real provider.

Launch with `subprocess.Popen(argv, stdin=PIPE, stdout=PIPE, stderr=PIPE, shell=False, cwd=temp_dir, env=allowlist, start_new_session=True)`; on Windows assign the Job Object before writing a frame, and on other hosts use the process-group enforcer. Send `hello`, then one `generate`, then `shutdown` with fixed length-prefixed frames; validate exact methods/fields, UTF-8, JSON depth 8, frame 256 KiB, candidate 2,048 events, and stderr 16 KiB. Apply startup/generate/shutdown deadlines, kill once on timeout/limit/protocol error, delete temp dir in `finally`, and return only stable enum/provider id/diagnostic digest.

```python
def encode_frame(payload: Mapping[str, object]) -> bytes:
    raw = canonical_json(payload)
    if len(raw) > 256 * 1024 or json_depth(payload) > 8:
        raise ProviderProtocolError("frame limit exceeded")
    return struct.pack(">I", len(raw)) + raw
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_provider_process.py`
Expected: PASS with no-shell/fixed-argv, environment stripping, temp cleanup, frame/method/depth/size limits, timeout kill, stderr sanitization, and no retry.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/groove_intelligence/neural_subprocess.py tests/test_groove_provider_process.py tests/fixtures/providers/echo_provider.py tests/fixtures/providers/invalid_provider.py tests/fixtures/providers/slow_provider.py
git commit -m "feat: isolate neural provider subprocess"
```

### Task 3: Candidate validation, deterministic fallback, and generation integration

**Files:**
- Create: `ableton_mcp_server/groove_intelligence/fallback.py`
- Modify: `ableton_mcp_server/groove_intelligence/provider.py`
- Modify: `ableton_mcp_server/groove_intelligence/deterministic.py`
- Modify: `ableton_mcp_server/groove_intelligence/runtime.py`
- Modify: `ableton_mcp_server/groove_intelligence/mcp_models.py`
- Modify: `ableton_mcp_server/server.py`
- Create: `tests/test_groove_provider_fallback.py`

**Interfaces:**
- Consumes the provider adapter and phase-2 deterministic `generate`.
- Produces `generate_with_provider(runtime, request) -> GenerationResponseV1`, `validate_provider_candidate(candidate, limits) -> MidiArtifactV1`, `fallback_reason(failure) -> FallbackV1`, and `ProviderResolution(provider_requested, provider_resolved, fallback, deterministic)`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("failure", list(ProviderFailureCode))
def test_every_neural_failure_returns_same_deterministic_artifact(tmp_path: Path, failure: ProviderFailureCode) -> None:
    runtime = make_provider_runtime(tmp_path, failure=make_provider_failure(failure))
    request = make_deterministic_request(provider="neural", seed=7)
    result = generate_with_provider(runtime, request)
    expected = generate_with_provider(make_provider_runtime(tmp_path / "deterministic"), make_deterministic_request(provider="deterministic", seed=7))
    assert result.artifact.artifact_id == expected.artifact.artifact_id
    assert result.card.provider_resolved == "deterministic"
    assert result.card.fallback.reason == failure

def test_invalid_neural_candidate_is_not_stored_or_reported_as_success(tmp_path: Path) -> None:
    runtime = make_provider_runtime(tmp_path, candidate=make_candidate(tmp_path, valid=False))
    result = generate_with_provider(runtime, make_deterministic_request(provider="neural", seed=3))
    assert result.card.fallback.reason == "output_invalid"
    assert runtime.store.contains_provider_artifact is False

def test_missing_model_identity_is_rejected_for_neural_production(tmp_path: Path) -> None:
    with pytest.raises(ProviderIdentityInvalid):
        generate_with_provider(make_provider_runtime(tmp_path, identity=model_identity_missing_digest()), make_deterministic_request(provider="neural", seed=1))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_provider_fallback.py`
Expected: FAIL because provider resolution and fallback are not wired into generation.

- [ ] **Step 3: Write minimal implementation**

For `provider="deterministic"`, call phase-2 generation directly. For `neural`, validate complete identity and rights, pass only the condition card/parent ids/seed/limits to the provider, validate the untrusted candidate with the phase-1 parser, bounds, canonical hash, projections, provenance, and rights, then store only a valid candidate. Any `ProviderFailure` or validation error runs deterministic generation with the same request and emits a bounded warning containing only enum/provider id/diagnostic digest. If deterministic fallback fails, return structured `GROOVE_PROVIDER_UNAVAILABLE` without partial payload.

```python
def generate_with_provider(runtime: GrooveRuntime, request: GenerateRequestV1) -> GenerationResponseV1:
    if request.provider == "deterministic":
        return deterministic_generate(runtime, request)
    identity = runtime.provider.identity_for(request.provider)
    identity.require_production_complete()
    outcome = runtime.provider.generate(build_condition_card(runtime, request), resolve_parent_ids(runtime, request), request.seed, ProviderLimitsV1())
    if isinstance(outcome, ProviderFailure):
        return deterministic_generate(runtime, request, fallback=fallback_reason(outcome))
    try:
        artifact = validate_provider_candidate(outcome, ProviderLimitsV1())
    except ProviderOutputInvalid as error:
        return deterministic_generate(runtime, request, fallback=FallbackV1(reason="output_invalid", diagnostic_digest=error.digest))
    return store_neural_artifact(runtime, artifact, identity, request)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_provider_fallback.py tests/test_groove_generation.py tests/test_groove_schema.py`
Expected: PASS for every failure enum, invalid candidate, complete identity, same-seed deterministic fallback, no partial storage, and unchanged deterministic mode when provider code is absent.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/groove_intelligence/provider.py ableton_mcp_server/groove_intelligence/fallback.py ableton_mcp_server/groove_intelligence/deterministic.py ableton_mcp_server/groove_intelligence/runtime.py ableton_mcp_server/groove_intelligence/mcp_models.py ableton_mcp_server/server.py tests/test_groove_provider_fallback.py
git commit -m "feat: add deterministic fallback for neural generation"
```

### Task 4: Laboratory gates, reports, and promotion lock

**Files:**
- Create: `ableton_mcp_server/groove_intelligence/lab.py`
- Create: `ableton_mcp_server/groove_intelligence/gates.py`
- Create: `ableton_mcp_server/groove_intelligence/promotion.py`
- Create: `tests/test_groove_provider_lab.py`
- Create: `docs/groove_intelligence/provider-lab.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/TOOL_REFERENCE.md`
- Modify: `README.md`
- Create: `tests/test_groove_provider_packaging.py`

**Interfaces:**
- Consumes provider fixtures, deterministic fallback, cards, mapping, rights, and limits.
- Produces `GateResultV1(status: Literal["passed", "failed"], details: Mapping[str, object])`, `run_provider_gates(candidate, fixture_set, *, signer: HmacPromotionSigner | None = None) -> ProviderGateReportV1`, `measurements_for(gates: Mapping[str, GateResultV1]) -> Mapping[str, float]`, six named gate results (`contract`, `fallback`, `reproducibility`, `quality`, `privacy_license`, `cost_latency`), `promotion_allowed(report, signer: HmacPromotionSigner) -> bool`, and `write_lab_report(report, path) -> None`. `ProviderGateReportV1` stores canonical `promotion_allowed: bool` and `failed_gates: tuple[str, ...]` fields alongside `schema_version`, thresholds, measurements, gates, registry opt-in, payload digest, signature, and signing key id; `run_provider_gates` derives both fields from the six gate statuses before signing, and `promotion_allowed(report, signer)` verifies the stored values against the statuses rather than maintaining a second competing property/function definition.

- [ ] **Step 1: Write the failing tests**

```python
def test_failed_gate_keeps_provider_disabled_and_deterministic_runtime_green(tmp_path: Path) -> None:
    report = run_provider_gates(make_candidate(tmp_path, valid=False), make_fixture_set(tmp_path))
    assert report.promotion_allowed is False
    assert set(report.failed_gates) >= {"contract", "privacy_license"}
    assert promotion_allowed(report, make_promotion_signer()) is False
    runtime = make_provider_runtime(tmp_path)
    assert deterministic_generate(runtime, make_deterministic_request(provider="deterministic")).artifact.artifact_id.startswith("ga1_")

def test_reproducibility_gate_requires_model_runtime_sampling_provider_seed_and_parents(tmp_path: Path) -> None:
    report = run_provider_gates(make_candidate(tmp_path, complete_identity=False), make_fixture_set(tmp_path))
    assert report.gates["reproducibility"].status == "failed"
    assert report.promotion_allowed is False

def test_lab_report_contains_no_path_raw_payload_or_secret(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    write_lab_report(run_provider_gates(make_candidate(tmp_path), make_fixture_set(tmp_path)), path)
    text = path.read_text(encoding="utf-8")
    assert "source_path" not in text and "payload" not in text and "TOKEN" not in text

def test_promotion_requires_canonical_identity_signature_and_numeric_thresholds(tmp_path: Path) -> None:
    signer = make_promotion_signer()
    report = run_provider_gates(make_candidate(tmp_path), make_fixture_set(tmp_path), signer=signer)
    assert promotion_allowed(report, signer) is True
    tampered = report.model_copy(update={"thresholds": report.thresholds.model_copy(update={"quality_hvo_f1_min": 0.91})})
    assert promotion_allowed(tampered, signer) is False
    assert promotion_allowed(report.model_copy(update={"signature": "00" * 32}), signer) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_provider_lab.py tests/test_groove_provider_packaging.py`
Expected: FAIL because lab gate/report modules do not exist.

- [ ] **Step 3: Write minimal implementation**

Implement gates as pure functions over bounded fixture data. Contract checks schema/parser/limits/hash/mapping; fallback checks absent/timeout/process/invalid/incompatible outcomes produce a deterministic valid artifact; reproducibility checks complete identity and equal digest when provider declares deterministic; quality checks published metric thresholds in `provider-lab.md`; privacy/license checks no blocked inputs/path/raw content and complete lineage; cost/latency checks fixed timeout/CPU/memory/BLOB limits. Define `GateThresholdsV1` with numeric thresholds exactly `contract_invalid_max=0`, `fallback_pass_rate_min=1.0`, `reproducibility_match_rate_min=1.0`, `quality_hvo_f1_min=0.90`, `quality_feature_mae_max=0.05`, `privacy_path_leaks_max=0`, `blocked_lineage_max=0`, `p95_latency_seconds_max=5.0`, `peak_memory_mib_max=512`, `response_bytes_max=262144`, and `candidate_events_max=2048`; publish these values in `provider-lab.md`. Define `ProviderGateReportV1(schema_version="groove.provider-gate.v1", thresholds, measurements, gates, registry_opt_in, promotion_allowed, failed_gates, payload_digest, signature, signing_key_id)`. `canonical_promotion_payload(report)` serializes the report with sorted keys, fixed six-decimal numeric formatting, and excludes `payload_digest`/`signature`; `report_digest = sha256(b"ABLETON-GROOVE-PROMOTION-V1\\x00" + canonical_promotion_payload(report))`. `HmacPromotionSigner.sign/verify` signs that digest with a lab-only key; no secret is stored in the report. `promotion_allowed(report, signer)` verifies schema, canonical payload digest, signature/key id, exact published thresholds, registry opt-in, stored `failed_gates == tuple(sorted(name for name, gate in gates.items() if gate.status != "passed"))`, stored `promotion_allowed == (not failed_gates and registry_opt_in)`, and all six `passed` statuses before returning true. Any tampered measurement, threshold, digest, signature, identity, or gate status returns false. Packaging test imports the package with no provider executable/fixture installed and invokes deterministic generation successfully.

```python
def promotion_allowed(report: ProviderGateReportV1, signer: HmacPromotionSigner) -> bool:
    if report.schema_version != "groove.provider-gate.v1" or not report.registry_opt_in:
        return False
    if report.payload_digest != report_digest(report) or not signer.verify(report.payload_digest, report.signature, report.signing_key_id):
        return False
    if report.thresholds != GateThresholdsV1():
        return False
    failed = tuple(sorted(name for name, gate in report.gates.items() if gate.status != "passed"))
    return len(report.gates) == 6 and report.failed_gates == failed and report.promotion_allowed == (not failed) and not failed

def build_gate_report(gates: Mapping[str, GateResultV1], *, thresholds: GateThresholdsV1, registry_opt_in: bool, signer: HmacPromotionSigner) -> ProviderGateReportV1:
    failed = tuple(sorted(name for name, gate in gates.items() if gate.status != "passed"))
    report = ProviderGateReportV1(schema_version="groove.provider-gate.v1", thresholds=thresholds, measurements=measurements_for(gates), gates=gates, registry_opt_in=registry_opt_in, promotion_allowed=(not failed and registry_opt_in), failed_gates=failed, payload_digest="", signature="", signing_key_id=signer.key_id)
    digest = report_digest(report)
    return report.model_copy(update={"payload_digest": digest, "signature": signer.sign(digest)})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_provider_lab.py tests/test_groove_provider_packaging.py tests/test_groove_provider_fallback.py`; `.\.venv-win\Scripts\python.exe -m ruff check ableton_mcp_server/groove_intelligence`; `.\.venv-win\Scripts\python.exe -m mypy --strict ableton_mcp_server/groove_intelligence`
Expected: PASS; failed gates disable promotion, good fixture passes only with all identities/thresholds, reports are sanitized, and deterministic mode works with no provider install.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/groove_intelligence/lab.py ableton_mcp_server/groove_intelligence/gates.py tests/test_groove_provider_lab.py tests/test_groove_provider_packaging.py docs/groove_intelligence/provider-lab.md docs/ARCHITECTURE.md docs/TOOL_REFERENCE.md README.md
git commit -m "test: add neural provider laboratory gates"
```

### Task 5: Phase terminal evidence and handoff

**Files:**
- Modify: no target-repository files. The parent creates `C:/Users/Usuario/repos/workflow-main/Lunacy/runs/drum-groove-intelligence/phases/04-neural-provider/reports/terminal.md` and `C:/Users/Usuario/repos/workflow-main/Lunacy/runs/drum-groove-intelligence/phases/04-neural-provider/evidence/phase4-tests.txt` as uncommitted control-plane artifacts after the worker handoff; the phase worker does not create or stage them.

**Interfaces:**
- Consumes Tasks 1–4 and fresh deterministic/provider/lab commands.
- Returns exact command output and exit codes to the parent. The parent publishes `FINAL` only if provider absence, launch denial, offline violation, timeout/kill, IPC invalidity, oversized/invalid output, fallback, identity, privacy/license, reproducibility, quality, and cost gates are evidenced; otherwise it records `BLOCKED` and promotion remains off.

- [ ] **Step 1: Write the failing gate command**

```powershell
.\.venv-win\Scripts\python.exe -m pytest -q tests/test_groove_provider_contract.py tests/test_groove_provider_process.py tests/test_groove_provider_fallback.py tests/test_groove_provider_lab.py
if ($LASTEXITCODE -ne 0) { throw 'phase-4 gate is red' }
```

- [ ] **Step 2: Run it before report publication**

Run: `Test-Path C:/Users/Usuario/repos/workflow-main/Lunacy/runs/drum-groove-intelligence/phases/04-neural-provider/reports/terminal.md`
Expected: `False` before the parent publishes the terminal report.

- [ ] **Step 3: Publish fresh report and evidence**

Return target HEAD, phase commits, worktree choice, provider registry/opt-in state, exact subprocess limits, each failure enum fixture including `internal`, fallback artifact equality, canonical signed gate report digest/status, no-install packaging result, and any blocked promotion decision to the parent. The parent writes the two control-plane artifacts. Do not report a model name, path, stderr, command, or credential.

- [ ] **Step 4: Verify report, plans, and scope**

Run: `git diff --check -- docs/superpowers/plans`; `rg -n -e 'T(O)DO|T(B)D|FIX(M)E|PLACE(HOLDER)|similar[[:space:]]+to|implement[[:space:]]+later' docs/superpowers/plans/2026-08-20-drum-groove-intelligence-phase-4-neural-provider.md`; `git status --short --branch`
Expected: whitespace and placeholder scans are empty; only intentional phase-4 files are owned and promotion is disabled unless the report proves all gates.

- [ ] **Step 5: Commit phase-4 target files**

```powershell
git add ableton_mcp_server/groove_intelligence tests docs README.md
git commit -m "feat: complete optional neural provider phase"
```
