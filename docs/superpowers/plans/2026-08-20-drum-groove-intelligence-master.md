# Drum Groove Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved Drum Groove Intelligence design as four dependency-safe, independently testable phases: a portable deterministic corpus seed, bounded retrieval/generation/MCP tools, guarded Live application, and an optional neural provider with deterministic fallback.

**Architecture:** The build-only corpus compiler produces a content-addressed `GrooveSeedBundle` containing a lossless MIDI envelope, versioned projections, rights/provenance, and an immutable SQLite index. Runtime opens one configured bundle read-only; search, evidence, deterministic generation, and comparison are pure/offline, while only `groove_apply` crosses the existing TCP bridge through an epoch-bound, capability-negotiated `run_batch`. Neural generation is a separate allowlisted subprocess adapter and never a prerequisite for deterministic mode.

**Tech Stack:** Python >=3.10 stdlib (`hashlib`, `json`, `struct`, `zlib`, `sqlite3`, `unicodedata`, `decimal`, `subprocess`, `socket`, `threading`), existing Pydantic v2/FastMCP/pytest/Ruff/Mypy, existing TCP Remote Script bridge, SQLite 3.40+ seed bundles. No new package is installed by these plans.

**Spec:** `docs/superpowers/specs/2026-08-20-drum-groove-intelligence-design.md` at approved target HEAD `0ea5b3712b32650e861b6e0380860e8133c2e388` (SHA-256 `484218941243A980878D46F09A92DF4A3185F83DA8F4D787018A4842ACFAA09E`).

## Global Constraints

- Runtime opens only a host-configured seed bundle; it never receives or depends on the private corpus path.
- The private corpus is an explicitly authorized build input; implementation starts with a pilot fixture and must not schedule a full 183k-file scan before pilot gates pass.
- The parser/serializer identifiers are `smf-parser-v1` and `smf-serializer-v1`; payload codecs are `zlib-raw-midi-v1` and `zlib-raw-json-v1`; SQLite `user_version` is `1` and minimum SQLite is `3.40`.
- Fixed limits are copied from the spec: MIDI input 8 MiB, 256 tracks, 1,000,000 events, 1–64 generation bars, 2,048 Live notes, 8 MiB compressed BLOB, 32 MiB decompressed BLOB, 100:1 ratio, search limit 1–50 (default 20), 32 feature constraints, compare 2–8 ids, 32 facet values per axis, 16 axes, 64 KiB card, 524,288-byte aggregate response, and 250 ms index query.
- All identity, request, cursor, lineage, projection, manifest, and logical-index hashes use the spec's canonical JSON and domain-separated SHA-256 contracts.
- Cards and MCP responses never contain note arrays, raw MIDI, BLOBs, private paths, SQL, secrets, executable commands, or local corpus names.
- Rights are a conservative meet; `blocked` is omitted, `derived_only` cannot apply, and there is no MCP override.
- `groove_apply` requires an explicit session-local target, one selected drum track/channel, `expected_empty_slot=true`, at most one `run_batch`, and no retry after possible transmission; multi-track/multi-channel artifacts require paired `source_track_index`/`source_channel` selectors.
- The bridge precondition contract is optional for legacy `run_batch` batches but mandatory for `groove_apply`; a bridge without exact `bridge.contract.v1` capability is closed with `GROOVE_PRECONDITION_UNSUPPORTED`.
- Neural mode is opt-in, offline, allowlisted, no-shell, bounded, and disposable; no model training, model download, package installation, network access, or promotion is part of these phases.
- Dependency strategy is stdlib-only for MIDI/index/provider code; do not change `pyproject.toml` or install a package. If a future parser/provider dependency is proposed, record its pinned version, license compatibility with this MIT repository, offline artifact source, and removal/fallback behavior in a new decision before editing dependencies.
- Generated seed SQLite/BLOB bundles, provider stderr, temporary subprocess directories, lab fixtures, and acceptance outputs are build/test artifacts: write them under `tmp_path` or an ignored phase evidence directory, never commit private payloads, absolute paths, credentials, or model binaries. Commit only synthetic fixtures, schemas, code, docs, and sanitized reports.
- Existing `music_generate_drum_groove`, `music_generate_bass`, and `music_plan_production` remain backward-compatible and retain their note-bearing legacy payloads.
- At execution time, the worker must choose a disposable worktree or the current branch only after checking concurrent ownership; it must record the choice in the phase execution report. No worker may edit files outside its phase ownership.
- Every task uses red-green TDD, a focused test command, and one coherent local Conventional Commit. Workers must inspect status/diff before staging exact paths and must not push.

## Plan Index and Dependency Order

| Order | Plan | Deliverable | Depends on | Terminal gate |
|---|---|---|---|---|
| 1 | `2026-08-20-drum-groove-intelligence-phase-1-corpus-index.md` | `MidiArtifactV1`, canonical hashes, bounded SMF parser, projections, rights, pilot compiler, immutable seed/index | approved spec only | two identical pilot builds; seed opens without source corpus |
| 2 | `2026-08-20-drum-groove-intelligence-phase-2-retrieval-mcp.md` | read-only adapter, cards, ranker/cursor, deterministic artifact store/generator/compare, `groove_search`, `groove_evidence`, `groove_generate`, `groove_compare` | phase 1 interfaces and fixture bundle | offline search/evidence/generate/compare plus schema/limit gates |
| 3 | `2026-08-20-drum-groove-intelligence-phase-3-apply-bridge.md` | mapping, `groove_apply`, epoch/capability/precondition bridge, thin skill, acceptance/docs | phases 1–2; existing bridge | preview has zero Live calls; guarded apply covers committed/partial/rejected/unknown |
| 4 | `2026-08-20-drum-groove-intelligence-phase-4-neural-provider.md` | provider protocol, allowlisted subprocess, lab/gates, deterministic fallback | phase 2 generator and phase 3 cards/mapping contracts | every neural failure returns valid deterministic output; failed gate never promotes |

Each phase plan ends with a parent-owned terminal-evidence task. The worker returns target-repository evidence; the parent coordinator publishes `Lunacy/runs/drum-groove-intelligence/phases/<phase>/reports/terminal.md` and matching `evidence/` files only after verifying the commands. Those control-plane files are not staged in target-repository implementation commits. The implementation-plan author reports are separate, immutable Workflow Main artifacts.

## Ownership Matrix

| Owner lane | Exact target ownership while active | Exclusions |
|---|---|---|
| `phase-1-corpus-index` | `ableton_mcp_server/groove_intelligence/{__init__,constants,schema,canonical,midi_lossless,projections,taxonomy,rights,build,index}.py`, `scripts/build_groove_seed.py`, `tests/fixtures/groove_smf.py`, `tests/fixtures/groove_bundle.py`, phase-1 `tests/test_groove_*.py`, `docs/groove_intelligence/pilot-build.md` | MCP catalog/server, bridge, Live, neural provider, private corpus |
| `phase-2-retrieval-mcp` | `ableton_mcp_server/groove_intelligence/{runtime,cards,search,artifacts,deterministic,evidence,mcp_models}.py`, `tests/fixtures/{groove_runtime,groove_mcp_wire}.py`, phase-2 tests, `ableton_mcp_server/models.py`, `catalog.py`, `server.py`, `tests/test_models.py`, `tests/test_catalog.py`, `tests/test_tool_registry.py`, `tests/test_server_tools.py`, `tests/test_cli.py` | bridge/client/Remote Script, acceptance/docs count consumers, neural subprocess, private corpus |
| `phase-3-apply-bridge` | `client.py`, `errors.py`, `diagnostics.py`, `contracts.py`, Remote Script source/vendor, mapping/apply modules, `tests/test_diagnostics.py`, `tests/test_capability_matrix.py`, phase-3 tests/probes, all acceptance/count documentation and fixtures explicitly listed in phase 3 | neural provider, corpus compiler, UI automation |
| `phase-4-neural-provider` | provider/registry/subprocess/resource-limits/fallback/lab/gates/promotion modules, provider fixtures/tests/docs explicitly listed in phase 4 | bridge protocol changes, Live UI, model training/download, package installation |

### Current tool-count consumer inventory

The attempt-5 preflight inventory was run against current `feature/music-brain` with `rg -n -i '\b(?:91|88|65|56|75|37)\b|tool.?count|TOOL_CATALOG|public_tools|headless|live_required|certif|route'` across the target runtime/tests/docs. It assigns owners as follows: phase-2 Task 4 owns `ableton_mcp_server/models.py`, `catalog.py`, `server.py`, `tests/test_models.py`, `tests/test_catalog.py`, `tests/test_tool_registry.py`, `tests/test_server_tools.py`, and `tests/test_cli.py`; phase-3 Task 2 owns `diagnostics.py`, `tests/test_diagnostics.py`, and `tests/test_capability_matrix.py`; phase-3 Task 4 owns the new `ableton_mcp_server/tool_counts.py`, `ableton_mcp_server/certification.py`, `cli.py`, `scripts/generate_capability_matrix.py`, acceptance maps/probes/runner, `tests/test_acceptance_helpers.py`, `tests/test_acceptance_runner_integration.py`, `tests/test_acceptance_audit_p0p1.py`, `tests/test_certification.py`, `tests/test_packaging.py`, plus `README.md`, `docs/index.html`, `docs/ARCHITECTURE.md`, `docs/api_capability_matrix.md`, `docs/CERTIFICATION.md`, and `docs/TOOL_REFERENCE.md`. This inventory explicitly includes the current TOOL_REFERENCE release claim 88, CERTIFICATION baseline 65, and ARCHITECTURE baselines 65/56; only same-line historical markers may preserve those values.

Phase-2 Task 4 changes code consumers to derive `len(TOOL_CATALOG)`, required-name sets, and `len(PUBLIC_TOOL_FUNCTIONS)` rather than fixed totals. Phase-3 Task 2 derives `public_tools`, `live_required_tools`, `routed_commands`, `websocket_targets`, `read_only_blocked`, and feature counts from the shared `build_tool_count_snapshot()`/canonical contract sets; it preserves only contract-set invariants. Phase-3 Task 4 owns `ToolCountSnapshotV1` (`active_total`, `headless_total`, `live_required_total`, `certified_total`, `acceptance_total`, `route_counts`) built from `TOOL_CATALOG` plus `ACCEPTANCE_REGISTRY`, updates route/domain tables and generated matrix/docs, adds the five groove names to acceptance maps, and runs a marker-aware active-claim gate:

```powershell
$countFiles = @(
  "README.md", "docs/index.html", "docs/ARCHITECTURE.md", "docs/api_capability_matrix.md", "docs/CERTIFICATION.md", "docs/TOOL_REFERENCE.md",
  "ableton_mcp_server/tool_counts.py", "ableton_mcp_server/catalog.py", "ableton_mcp_server/server.py", "ableton_mcp_server/diagnostics.py", "ableton_mcp_server/cli.py", "ableton_mcp_server/certification.py", "scripts/generate_capability_matrix.py",
  "ableton_mcp_server/acceptance/probes/composed.py", "ableton_mcp_server/acceptance/probes/offline.py", "ableton_mcp_server/acceptance/probes/__init__.py", "ableton_mcp_server/acceptance/runner.py",
  "tests/test_cli.py", "tests/test_packaging.py", "tests/test_acceptance_helpers.py", "tests/test_acceptance_runner_integration.py", "tests/test_acceptance_audit_p0p1.py", "tests/test_certification.py", "tests/test_catalog.py", "tests/test_models.py", "tests/test_capability_matrix.py", "tests/test_diagnostics.py", "tests/test_server_tools.py", "tests/test_tool_registry.py"
)
$unmarked = rg --pcre2 -n '(?<![0-9])[0-9]+[ -](?:MCP )?tools?\b' $countFiles | ? { $_ -notmatch '<!-- (?:TOOL_COUNT: (?:active_total|headless_total|live_required_total|certified_total|acceptance_total|route=[a-z_]+)|HISTORICAL_TOOL_COUNT: [0-9]+; baseline=[^ ]+) -->' }
if ($unmarked) { throw "unmarked active tool-count claim: $($unmarked -join "`n")" }
```

The gate is intentionally limited to current runtime/tests/docs consumers; it does not reject historical release numbers in `prompts/`, approved specs, or prior plan archives. Historical values in the listed docs must carry their machine-detectable baseline marker. A separate assertion requires every count-bearing code path to import/derive `build_tool_count_snapshot`, `TOOL_CATALOG`, or the canonical contract set.

The parent coordinator owns cross-phase contract decisions, activation records, report acceptance, and final integration. A worker must stop and return `DECISION_REQUIRED` if a change crosses this matrix or alters a frozen schema.

## Cross-Phase Interfaces

Phase 1 publishes these importable interfaces; later plans must consume them without renaming:

```python
from pathlib import Path
from typing import Mapping, Sequence
from ableton_mcp_server.groove_intelligence.schema import (
    ArtifactId, BuildInput, BuildManifestV1, GrooveSeedBundleManifestV1,
    MidiArtifactV1, ProjectionRefV1,
)
from ableton_mcp_server.groove_intelligence.canonical import (
    artifact_id_from_identity, canonical_json, request_hash,
    reproducibility_key, sha256_hex,
)
from ableton_mcp_server.groove_intelligence.build import build_seed_bundle
from ableton_mcp_server.groove_intelligence.index import ReadonlyGrooveIndex

def build_seed_bundle(
    *, input_root: Path, inputs: Sequence[BuildInput], output_dir: Path,
    build_config: Mapping[str, object],
) -> GrooveSeedBundleManifestV1:
    """Compile the explicitly listed inputs into one portable seed bundle."""

def open_readonly_index(bundle_dir: Path) -> ReadonlyGrooveIndex:
    """Open the configured SQLite file immutable and validate its manifest."""
```

Phase 2 publishes:

```python
from ableton_mcp_server.groove_intelligence.cards import (
    ArtifactCardV1, EvidenceCardV1, GenerationCardV1, CompareCardV1,
)
from ableton_mcp_server.groove_intelligence.runtime import GrooveRuntime
from ableton_mcp_server.groove_intelligence.search import SearchRequestV1, search
from ableton_mcp_server.groove_intelligence.deterministic import deterministic_generate

def search(runtime: GrooveRuntime, request: SearchRequestV1) -> SearchResponseV1:
    """Return deterministic bounded cards ordered by the pinned ranker."""
def deterministic_generate(runtime: GrooveRuntime, request: GenerateRequestV1, fallback: FallbackV1 | None = None) -> GenerationResponseV1:
    """Create or retrieve one content-addressed deterministic artifact."""
```

Phase 3 adds:

```python
from ableton_mcp_server.groove_intelligence.mapping import map_artifact
from ableton_mcp_server.groove_intelligence.apply import apply_artifact
from ableton_mcp_server.client import AtEpochCallResultV1, ConnectionSnapshot

def map_artifact(artifact: MidiArtifactV1, profile_id: str, *, on_unmapped: str = "reject", source_track_index: int | None = None, source_channel: int | None = None) -> MappingPlanV1:
    """Resolve a late kit mapping without mutating the source artifact."""
def apply_artifact(runtime: GrooveRuntime, request: ApplyRequestV1) -> ApplyReceiptV1:
    """Materialize one guarded Live batch and return its bounded receipt."""
def call_at_epoch(expected_epoch: int, action: str, params: Mapping[str, object] | None = None, *, timeout: float | None = None) -> AtEpochCallResultV1[object]:
    """Send one TCP action while holding the epoch lock."""
```

Phase 4 consumes the stable provider boundary:

```python
class GrooveProvider(Protocol):
    def generate(
        self, condition_card: ConditionCardV1,
        parent_artifact_ids: tuple[ArtifactId, ...],
        seed: int,
        limits: ProviderLimitsV1,
    ) -> ProviderArtifactCandidate | ProviderFailure:
        """Return one candidate or one stable failure enum."""
```

The phase plans provide concrete body snippets and tests for each interface.

## Execution and Verification Rules

1. Parent records the phase activation, selected worker, worktree decision, exact source/spec HEAD, and route before code edits.
2. Before phase 1 Task 1, parent runs the narrow preflight from the target root: `.\.venv-win\Scripts\python.exe C:\Users\Usuario\.agents\skills\repo-context-loader\scripts\repo_context.py check C:\Users\Usuario\repos\ableton-mcp-server --json`, `git rev-parse HEAD`, `Get-FileHash -Algorithm SHA256 -LiteralPath docs/superpowers/specs/2026-08-20-drum-groove-intelligence-design.md`, and `git status --short --branch`. If status is `stale`, parent inspects only reported changed paths plus direct consumers of the phase and records `stale`; it does not refresh/finalize the broad map automatically.
3. Worker reads the phase plan and current source paths, writes only its owned paths, and runs the exact red-green commands in task order.
4. Worker runs `git diff --check`, the phase focused suite, `.\.venv-win\Scripts\python.exe -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests`, and strict Mypy for changed package modules where applicable.
5. Parent verifies the complete diff, ownership scope, fresh commands, acceptance gate, and publishes the parent-owned terminal evidence. A phase gate does not authorize the next phase automatically.
6. Final integration runs the phase-specific focused suites plus `.\.venv-win\Scripts\python.exe -m pytest -q --tb=line`, `.\.venv-win\Scripts\python.exe -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests`, `.\.venv-win\Scripts\python.exe -m mypy --strict ableton_mcp_server`, and `.\.venv-win\Scripts\python.exe scripts/coverage_check.py` in the repository's configured Windows venv. If the venv is unavailable, record the exact environment failure rather than changing dependencies.

## Spec Coverage Map

| Spec requirement | Plan task |
|---|---|
| offline-first boundary, source-path exclusion, pilot-before-full-scan | phase 1 tasks 1, 4, 6; master constraints |
| canonical identity, request hash, reproducibility key | phase 1 task 1 |
| lossless SMF, parser/serializer, bounded limits and post-flush decompression guards | phase 1 task 2 |
| HVO/features/grammar and multi-axis facets | phase 1 task 3 |
| provenance, license lattice, authorized-root seed manifest and source-digest ordering | phase 1 tasks 3–5 |
| SQLite v1, immutable read-only adapter, logical digest and store-populated runtime artifacts | phase 1 task 5; phase 2 task 1 |
| bounded decompression and aggregate MCP budget | phase 1 task 5; phase 2 task 1/4 |
| ranker, filters, AND/OR, projection operator, cursor | phase 2 task 2 |
| Artifact/Evidence/Generation/Compare cards and artifact store | phase 2 tasks 1 and 3 |
| deterministic generation and legacy compatibility | phase 2 task 3/5 |
| five MCP tools including `groove_apply`, explicit top-level/client-visible schemas discovered through FastMCP client wire | phase 2 task 4; phase 3 task 3 |
| late pitch mapping, optional source-track/source-channel selection, and mapping receipts | phase 3 task 3 |
| bridge contract and precondition admission | phase 3 task 1 |
| capability cache, epoch and call_at_epoch | phase 3 task 2 |
| preconditions, malformed bridge contract, invalid/duplicate admission, TOCTOU, one batch, partial/unknown receipts, no retry | phase 3 tasks 1–3 |
| thin skill, acceptance probes, docs/capability catalog | phase 3 task 4 |
| neural subprocess, privacy/offline policy, failure enums | phase 4 tasks 1–2 |
| fallback, identity/reproducibility, lab gates, signed promotion identity and numeric thresholds | phase 4 tasks 3–4 |
| exact phase-2 factories, ToolResult wire budget, visible FastMCP Literal schemas, derived five-tool count consumers | phase 2 tasks 1–5; phase 3 task 3 |
| every current tool-count consumer, one catalog/acceptance-derived snapshot, active/historical doc markers, route/domain-derived counts, acceptance-map coverage, generated capability matrix, and marker-aware relevant-file gate | phase 2 task 4; phase 3 tasks 2 and 4 |
| capability snapshot epoch, cache invalidation, TOCTOU, pre-send vs ambiguous transport, legacy/all-precondition/close-receipt/direct-client tests | phase 3 tasks 1–3 |
| concrete Windows Job Object/resource fallback and internal failure enum | phase 4 tasks 1–2 |
