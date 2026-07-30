# Acceptance runner refactor — design

**Status:** proposed (autopilot mode, awaiting any owner interrupt)
**Date:** 2026-07-27
**Repo:** `ableton-mcp-server` (v0.5.1, main 97 commits ahead of origin)
**Scope:** `ableton_mcp_server/acceptance.py` only
**Goal:** split the 134 KB / ~3389-line monolithic runner into focused modules without changing external behavior.

## Background

`ableton_mcp_server/acceptance.py` grew to ~134 KB with a single `run_live_acceptance` async function. Recent commits (`6773830`, `fd21ce6`, `af406f4`, `415d3cb`, `ef91c46`) each add a defensive guard plus a regression test, but the file keeps growing and the bugs keep coming. The restore section alone contains three near-identical loops for mute/solo/arm plus loops for tempo, loop, song time, cue, warp, volume, and parameter restoration. Adding tool #66 (planned in `docs/superpowers/plans/2026-07-13-expand-to-125-tools.md`) without restructuring will continue the bug loop.

This refactor extracts focused modules and a `RestoreEngine` class that encapsulates the restore duplication. External behavior is preserved byte-for-byte.

## Architecture

```text
ableton_mcp_server/
├── acceptance.py                  # facade — re-exports (back-compat for tests + cli.py)
└── acceptance/
    ├── __init__.py                # public API
    ├── safety.py                  # AcceptanceClient Protocol, AcceptanceSafetyError, _resolve_track_id
    ├── baseline.py                # BaselineSnapshot frozen dataclass + discover_baseline()
    ├── helpers.py                 # _test_tempo, _acceptance_safe_cue_times,
    │                              # _parameter_tolerance, _write_sine_wav, _synthesize_offline_inputs,
    │                              # LIVE_FADE_UNITY_VALUE
    ├── report.py                  # _release_ready, build_baseline_report, _is_full_baseline
    │                              # (wraps certification.py)
    ├── restore.py                 # RestoreEngine class
    ├── probes/
    │   ├── __init__.py            # BASELINE_PROBE_GROUPS + registry helpers
    │   ├── offline.py             # run_offline_probes + synth inputs
    │   ├── composed.py            # bridge_status, session_overview
    │   ├── tcp_reads.py           # 25 reads
    │   ├── websocket_reads.py     # get_warp_state
    │   ├── mutations.py           # 29 mutations
    │   └── quit.py                # quit_ableton
    └── runner.py                  # run_live_acceptance — orchestrator
```

**Principles**

- `acceptance.py` facade of ~10 lines re-exports the public API → existing imports in `cli.py`, `_strict_fake.py`, and all 6 `tests/test_acceptance*.py` files keep working.
- Probes **do not** import other probes. Composition is via registry.
- `RestoreEngine` is the **only** owner of `_restore_call`/`_restore_ws`.
- `BaselineSnapshot` is a frozen dataclass with the complete snapshot.
- `_release_ready` policy is untouched.
- Errors preserved: `AcceptanceSafetyError`, `BridgeError`, status taxonomy.

## Components

### `safety.py` (foundational)

- `AcceptanceClient` Protocol (unchanged shape: `host`, `port`, `call`, `call_ws`).
- `AcceptanceSafetyError(RuntimeError)`.
- `_resolve_track_id(client, index)` (unchanged).

### `baseline.py` (foundational)

- `BaselineSnapshot` frozen dataclass with fields:
  - `song_name: str`
  - `song_length: float`
  - `track_names: dict[int, str]`
  - `track_types: dict[int, str]`
  - `track_mutes: dict[int, bool]`
  - `track_solos: dict[int, bool]`
  - `track_arms: dict[int, bool]`
  - `track_volumes: dict[int, float]`
  - `tempo: float`
  - `current_song_time: float`
  - `loop: bool`
  - `loop_start: float`
  - `loop_length: float`
  - `locators: list[Mapping[str, Any]]`
  - `track_count: int`
- `discover_baseline(client) -> BaselineSnapshot` — replaces `_discover_baseline`. Same safety guards, same shape, frozen dataclass return.

### `helpers.py` (pure functions)

- `_test_tempo`, `_acceptance_safe_cue_times`, `_parameter_tolerance`
- `_write_sine_wav`, `_synthesize_offline_inputs`
- `LIVE_FADE_UNITY_VALUE` constant

### `restore.py` (the key abstraction)

```python
@dataclass(frozen=True)
class RestoreOp:
    label: str
    tool: str
    restore: Callable[[], Any | Awaitable[Any]]
    verify: Callable[[Any], None | Awaitable[None]]


class RestoreEngine:
    def __init__(self, client: AcceptanceClient, artifacts: dict[str, Any]):
        self._client = client
        self._artifacts = artifacts
        self._ops: list[RestoreOp] = []
        self.failures: list[tuple[str, str]] = []

    def register(
        self,
        *,
        label: str,            # e.g. "set_track_property(mute:3)"
        tool: str,             # tool name on the certification row
        restore: Callable[[], Any] | Callable[[], Awaitable[Any]],
        verify: Callable[[Any], None] | Callable[[Any], Awaitable[None]],
    ) -> None:
        """Declare one restore op. Replaces inline `_restore_call`/`_restore_ws`."""

    async def run_all(self) -> list[tuple[str, str]]:
        """Execute registered ops in order. Sync and async restores interleave.
        Returns [(label, reason), ...] for failures. Order preserved."""
```

**The 3 mute/solo/arm loops collapse into one table-driven loop:**

```python
_MIXER_RESTORES = (
    ("mute", "midi/audio/return", "track_mutes"),
    ("solo", "midi/audio/return", "track_solos"),
    ("arm",  "midi/audio",        "track_arms"),
)
# In probes/mutations.py:
for prop, type_filter, snapshot_key in _MIXER_RESTORES:
    for idx in _cleanup_indices_for(snapshot, type_filter):
        original = bool(snapshot[snapshot_key].get(idx, False))
        engine.register(
            label=f"set_track_property({prop}:{idx})",
            tool="set_track_property",
            restore=lambda i=idx, o=original: client.call(
                "set_track_property",
                {"track_index": i, "property": prop, "value": o},
            ),
            verify=lambda _o, i=idx, o=original: _eq(
                bool(client.call("get_track_state", {"track_index": i}).get(prop)),
                o,
                f"track:{i}.{prop}",
            ),
        )
```

### `probes/*.py` (one per probe group)

Each probe module exports:

```python
TOOLS: tuple[str, ...] = (...)


def register_probes(
    runner: "ProbeRunner",
    client: AcceptanceClient,
    snapshot: BaselineSnapshot | None,
    artifacts: dict[str, Any],
) -> None:
    """Register probe actions on the runner. Called by runner.py per group."""


def register_restores(
    engine: RestoreEngine,
    snapshot: BaselineSnapshot,
    artifacts: dict[str, Any],
) -> None:
    """Register cleanup restores. Called only for mutations group."""
```

Where `ProbeRunner` is a small protocol with:

- `record_call(report, tool, action, passed="live_passed") -> Awaitable[Any]`
- `record_unavailable(report, tool, reason)`

### `runner.py` (orchestrator, ~150 lines)

```python
async def run_live_acceptance(
    client, *, confirm_project_name, track_index, clip_index,
    audio_track_index=None, audio_clip_index=None,
    profiles=("baseline",), fire_clip=False,
    offline_probes=None,
) -> dict[str, Any]:
    expanded = _expand_profiles(profiles)
    report = build_baseline_report(profiles=profiles)
    artifacts = {"tags": [], "files": [], "tracks_created": [], "manual_cleanup": []}
    engine = RestoreEngine(client, artifacts)

    with tempfile.TemporaryDirectory(prefix="ableton-mcp-acceptance-") as tmp:
        offline_dir = Path(tmp) / "offline"

        if "offline" in expanded:
            probe_callable = offline_probes or probes.offline.run
            await probe_callable(report, offline_dir)
            _collect_offline_artifacts(offline_dir, artifacts)

        if "composed" in expanded:
            probes.composed.register_probes(_probe_runner(client), client, None, artifacts)

        if {tcp_reads, mutations, websocket_reads} & set(expanded):
            metadata = client.call("get_project_metadata")
            _verify_disposable(metadata, confirm_project_name)
            snapshot = baseline.discover_baseline(client)

            try:
                if "tcp_reads" in expanded:
                    probes.tcp_reads.register_probes(_probe_runner(client), client, snapshot, artifacts)
                if "websocket_reads" in expanded:
                    probes.websocket_reads.register_probes(_probe_runner(client), client, snapshot, artifacts)
                if "mutations" in expanded:
                    probes.mutations.register_probes(_probe_runner(client), client, snapshot, artifacts)
                    probes.mutations.register_restores(engine, snapshot, artifacts)
            except AcceptanceSafetyError as safety_error:
                _mark_unexecuted_failed(report, expanded, safety_error)
                raise

        if "quit" in profiles and "mutations" not in expanded:
            _record_quit_manual_required(report)

    failures = await engine.run_all()
    if failures:
        _downgrade_failed_cleanup(report, failures)

    _preclassify_unselected(report, expanded)
    return _finalize(report, profiles, fire_clip, artifacts, ...)
```

## Data flow

```text
CLI / tests
  │
  ▼
run_live_acceptance(client, profiles, ...)
  │
  ├─ build_baseline_report → CertificationReport
  ├─ [offline]     probes.offline.run           → records on report
  ├─ [composed]    probes.composed.register     → records on report
  │
  ├─ [tcp_reads/mutations/ws_reads] safety guard
  │   ├─ get_project_metadata → confirm disposable Set
  │   └─ baseline.discover_baseline(client)   → BaselineSnapshot
  │
  ├─ [tcp_reads]      probes.tcp_reads.register_probes        → records on report
  ├─ [websocket_reads] probes.websocket_reads.register_probes → records on report
  ├─ [mutations]      probes.mutations.register_probes        → records on report
  │                    probes.mutations.register_restores(engine) → engine._ops
  │
  ├─ engine.run_all() → executes cleanup, captures failures
  │   ├─ on failure: downgrades affected live_passed → failed
  │   └─ on pre-track-creation failure: marks track-creation tools failed
  │
  ├─ _preclassify_unselected(report, expanded) → environment_unavailable
  │
  └─ _finalize:
      ├─ _release_ready(report, profiles, fire_clip) → bool
      ├─ report.finish() → dict
      └─ return {project, status, certification, artifacts, ...}
```

## Error handling

**Preserved unchanged:**

- `AcceptanceSafetyError` — raised before any mutation when disposable Set cannot be proven safe (project name mismatch, dirty baseline, missing track state, missing volume, non-positive song length).
- `BridgeError` with code `CAPABILITY_UNAVAILABLE` → row status `host_unavailable`.
- Any other `Exception` → row status `failed`.
- `environment_unavailable` allowed only for `build_extension`, `fire_clip` (without `--fire-clip` flag).
- `manual_required` allowed only for `quit_ableton` and the strict `save_set` fallback (when host bridge reports `api_available: false`).

**Refactor-internal:**

- `RestoreEngine.run_all` returns `list[tuple[label, reason]]` of failures. Caller (runner) is responsible for downgrading affected rows on the report.
- Probe modules raise — they never swallow exceptions.
- Probe modules never import other probe modules.

## Testing strategy

**Zero behavior change** is the gate. Existing tests must pass byte-for-byte.

**Existing tests preserved via facade:**

- `tests/test_acceptance.py`
- `tests/test_acceptance_audit_p0p1.py`
- `tests/test_acceptance_cleanup_track_types.py`
- `tests/test_acceptance_cue_time_bounds.py`
- `tests/test_acceptance_live_fade_percent.py`
- `tests/test_acceptance_runner_integration.py`
- `tests/_strict_fake.py`
- All continue importing from `ableton_mcp_server.acceptance`.

**New unit tests added per new module:**

- `tests/test_acceptance_baseline.py` — `BaselineSnapshot` dataclass invariants, `discover_baseline` happy-path + each `AcceptanceSafetyError` branch.
- `tests/test_acceptance_helpers.py` — `_acceptance_safe_cue_times` (consolidates coverage from `test_acceptance_cue_time_bounds.py`), `_test_tempo`, `_parameter_tolerance`.
- `tests/test_acceptance_restore.py` — `RestoreEngine.register/run_all`: happy path, sync vs async restores, failure capture, failure aggregation, registration order preserved.
- `tests/test_acceptance_probes.py` — per-group probe registration smoke test against `_strict_fake`, asserts every `BASELINE_PROBE_GROUPS[group]` tool ends up recorded.
- `tests/test_acceptance_runner.py` — orchestrator smoke test using `_strict_fake` + `offline_probes` injection point.

**Verification commands (must all pass):**

```powershell
python -m pytest -q --tb=line
python scripts\coverage_check.py
python -m ruff check ableton_mcp_server/acceptance ableton_mcp_server/acceptance.py AbletonMCPServer_RemoteScript scripts tests
python -m mypy --strict ableton_mcp_server/acceptance ableton_mcp_server/acceptance.py
python -c "from ableton_mcp_server.acceptance import run_live_acceptance, BASELINE_PROBE_GROUPS; assert len(BASELINE_PROBE_GROUPS) >= 6"
```

## Phasing + rollout

**Phase 1 — foundation (sequential, me):**

- Create `acceptance/` package skeleton (`__init__.py` + empty submodules).
- Move + verify: `safety.py`, `helpers.py`, `baseline.py`, `report.py`.
- Write `restore.py` (`RestoreEngine` class) + new unit test.
- Wire facade `acceptance.py` re-exporting everything.
- Verify: existing test suite passes.

**Phase 2 — probes in parallel (subagents, 4-5 concurrent):**

- `probes/offline.py` (1 subagent).
- `probes/composed.py` + `probes/quit.py` (1 subagent, both small).
- `probes/tcp_reads.py` (1 subagent, biggest by tool count).
- `probes/websocket_reads.py` (1 subagent, smallest, single tool).
- `probes/mutations.py` (1 subagent, most complex — also owns restore registrations).

Each subagent receives:

- Exact slice of current `acceptance.py` lines to extract.
- Target module path + `TOOLS` tuple to declare.
- Required signatures for `register_probes` / `register_restores`.
- Instruction: no behavior change, must pass existing tests against the facade.

**Phase 3 — runner + tests (sequential, me):**

- Write `runner.py` (thin orchestrator).
- Wire `probes/__init__.py` with `BASELINE_PROBE_GROUPS` + registry.
- Add new unit tests per module.
- Run full verification suite.

**Phase 4 — coupled updates (me):**

- `AGENTS.md`: update "Critical paths" table (add `acceptance/` package).
- `.agent-context/architecture.md`: regenerate via `repo_context.py`.
- `.agent-context/hot-files.md`: regenerate.
- `docs/ARCHITECTURE.md`: add section on acceptance package.
- Do NOT touch `docs/CERTIFICATION.md` (policy unchanged).
- Do NOT touch `CHANGELOG.md` (internal refactor, no version bump).

**Phase 5 — commits (atomic per phase):**

- Commit 1: `docs(acceptance): scaffold refactor design spec`
- Commit 2: `refactor(acceptance): scaffold package + facade + RestoreEngine`
- Commit 3-N: `refactor(acceptance): extract probes/<group>` (one per subagent).
- Commit N+1: `refactor(acceptance): thin runner + new unit tests`.
- Commit N+2: `docs(agents): update critical paths for acceptance package`.
- Push only with explicit owner authorization (per AGENTS.md safety).

## Risk mitigation

| Risk | Mitigation |
|---|---|
| Behavior change in facade | Existing tests must pass without modification after Phase 1 |
| Test fixtures break | `_strict_fake.py` keeps importing from `ableton_mcp_server.acceptance` via facade |
| Subagent diverges from spec | Each subagent gets exact line ranges + signatures; commit review per Phase 2 PR |
| Cleanup ordering changes | `RestoreEngine` preserves registration order (= current code order) |
| `RestoreEngine` abstraction leaks | Probe modules only see `register(...)`; internal queue opaque |
| `_release_ready` policy changes | Wrapped verbatim in `report.py`; no touch |
| Lost defensive guards | Each guard migration tracked in commit messages; grep after Phase 1 |

## Out of scope (explicit)

- Touching `ableton_mcp_server/certification.py` (already focused).
- Adding new tools beyond the existing 65.
- Changing `_release_ready` semantics.
- Modifying `cli.py` interface.
- Splitting `ableton_mcp_server/analysis/` (separate package, already focused).
- Touching the TypeScript extension.
- Touching the Remote Script.
- Modifying existing tests (only ADD new ones; existing must pass unchanged).

## Open questions

None — design is committed under autopilot. Will surface anything genuinely blocking during implementation and ask the single precise question at that point.