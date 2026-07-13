# Stabilize and Certify 65 Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct every confirmed defect in the current 65-tool surface and produce machine-readable evidence that each existing tool is either working, intentionally manual, or truthfully unavailable on the installed host.

**Architecture:** Introduce an immutable capability catalog without changing public names, fix defects at their originating runtime boundary, and extend the guarded acceptance runner into a per-tool certification system. TCP operations remain on the Remote Script UI thread; warp/device operations remain on the existing Extension WebSocket bridge.

**Tech Stack:** Python 3.10+, FastMCP 3.4, Pydantic 2.12, NumPy 2.2, soundfile, Ableton Python LOM, Ableton Extensions SDK, TypeScript, pytest, Ruff, mypy strict.

**Lint configuration:** Ruff uses `pyproject.toml` with line length 100 and Python 3.10 syntax. Mypy remains strict for project-owned Python; only `soundfile` receives a targeted missing-stub override. TypeScript uses the existing strict `tsconfig.json` and `npm run build:prod`.

---

## File map

- Create `ableton_mcp_server/catalog.py`: immutable metadata for the 65 current tools.
- Create `ableton_mcp_server/certification.py`: verification result types and report aggregation.
- Create `tests/test_catalog.py`: registry/catalog/contract invariants.
- Create `tests/test_certification.py`: complete-row and status rules.
- Create `scripts/verify_clean_install.ps1`: isolated wheel/install/import probe.
- Modify `ableton_mcp_server/server.py`: derive names from catalog and correct WS/tool annotations.
- Modify `ableton_mcp_server/models.py`: correct warp/device contracts.
- Modify `ableton_mcp_server/errors.py`: new stable public error types.
- Modify `ableton_mcp_server/ws_client.py`: preserve structured Extension errors.
- Modify `ableton_mcp_server/analysis/audio.py`: narrow-band masking algorithm and typing.
- Modify `ableton_mcp_server/diagnostics.py`: source identity and certification data.
- Modify `ableton_mcp_server/acceptance.py`: profile-aware per-tool evidence.
- Modify `AbletonMCPServer_RemoteScript/__init__.py`: identity-safe track/browser logic.
- Modify `contracts.py` and regenerate `AbletonMCPServer_RemoteScript/_contracts.py`.
- Modify `AbletonMCPServer_Extension/src/index.ts`: device-name contract and typed JSON-RPC errors.
- Modify package/version/docs files named in Tasks 3 and 11.

### Task 1: Freeze the 65-tool catalog

**Files:**
- Create: `ableton_mcp_server/catalog.py`
- Create: `tests/test_catalog.py`
- Modify: `ableton_mcp_server/server.py:38-108`
- Modify: `tests/test_models.py:20-95`
- Modify: `tests/test_tool_registry.py:1-30`

- [ ] **Step 1: Write the failing catalog invariant**

```python
# tests/test_catalog.py
from contracts import ALLOWED_MUTATIONS, READ_COMMANDS, WEBSOCKET_TARGET_COMMANDS

from ableton_mcp_server import models, server
from ableton_mcp_server.catalog import AcceptanceMode, Risk, Route, TOOL_CATALOG


def test_baseline_catalog_is_complete_and_unique() -> None:
    names = tuple(item.name for item in TOOL_CATALOG)
    assert len(names) == len(set(names)) == 65
    assert names == server.PUBLIC_TOOL_NAMES
    assert set(names) == set(models.TOOL_REQUEST_MODELS)


def test_wire_routes_and_risks_match_contracts() -> None:
    by_name = {item.name: item for item in TOOL_CATALOG}
    for name in READ_COMMANDS:
        assert by_name[name].route in {Route.TCP, Route.WEBSOCKET}
        assert by_name[name].risk is Risk.READ
    for name in ALLOWED_MUTATIONS:
        assert by_name[name].risk is not Risk.READ
    assert set(WEBSOCKET_TARGET_COMMANDS) == {
        item.name for item in TOOL_CATALOG if item.route is Route.WEBSOCKET
    }
    assert by_name["quit_ableton"].acceptance is AcceptanceMode.MANUAL
    assert by_name["build_extension"].acceptance is AcceptanceMode.ENVIRONMENT
```

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_catalog.py -q`

Expected: collection fails because `ableton_mcp_server.catalog` does not exist.

- [ ] **Step 3: Add the immutable catalog types and the complete baseline groups**

```python
# ableton_mcp_server/catalog.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Route(str, Enum):
    LOCAL = "local"
    TCP = "tcp"
    WEBSOCKET = "websocket"
    COMPOSED = "composed"


class Risk(str, Enum):
    READ = "read"
    REVERSIBLE = "reversible"
    DESTRUCTIVE = "destructive"
    LIFECYCLE = "lifecycle"
    LOCAL_WRITE = "local_write"


class AcceptanceMode(str, Enum):
    OFFLINE = "offline"
    GUARDED = "guarded"
    MANUAL = "manual"
    ENVIRONMENT = "environment"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    domain: str
    route: Route
    risk: Risk
    acceptance: AcceptanceMode
    reversible: bool


def _group(
    names: tuple[str, ...],
    *,
    domain: str,
    route: Route,
    risk: Risk,
    acceptance: AcceptanceMode,
    reversible: bool,
) -> tuple[ToolSpec, ...]:
    return tuple(
        ToolSpec(name, domain, route, risk, acceptance, reversible) for name in names
    )


_LOCAL_READS = (
    "get_ableton_logs", "diff_snapshots_tool", "analyze_audio",
    "find_frequency_masking", "analyze_mix", "extract_single_cycle",
)
_LOCAL_WRITES = ("scaffold_extension", "build_extension")
_COMPOSED_READS = ("get_session_overview", "get_bridge_status")
_WS_READS = ("get_warp_state",)
_WS_WRITES = ("set_warp_state", "load_device_to_track")
_TCP_READS = (
    "get_session_info", "get_track_list", "get_track_state", "get_locators",
    "take_snapshot", "get_control_surfaces", "get_scenes", "get_scene_state",
    "get_project_metadata", "get_loop_settings", "get_selected_context",
    "get_clip_summary", "get_clip_notes", "get_clip_info", "get_device_list",
    "get_parameter_value", "get_routing", "get_browser_categories", "search_browser",
    "get_song_length", "live_find_track", "list_device_params",
    "get_composition_structure", "diagnose_midi_clip", "lifecycle_status",
)
_TCP_MUTATIONS = (
    "create_cue_point", "bulk_create_cue_points", "delete_cue_point",
    "set_current_song_time", "set_tempo", "start_playback", "stop_playback",
    "set_loop", "set_loop_start", "set_loop_length", "run_batch",
    "add_notes_to_clip", "fire_clip", "create_clip", "delete_clip",
    "clear_clip_notes", "fire_scene", "set_track_property", "set_clip_properties",
    "create_clip_automation", "create_midi_track", "create_audio_track",
    "rename_track", "set_parameter_value", "save_set", "quit_ableton", "live_fade",
)


TOOL_CATALOG = (
    *_group(_TCP_READS, domain="live", route=Route.TCP, risk=Risk.READ,
            acceptance=AcceptanceMode.GUARDED, reversible=True),
    *_group(_TCP_MUTATIONS[:-3], domain="live", route=Route.TCP,
            risk=Risk.REVERSIBLE, acceptance=AcceptanceMode.GUARDED, reversible=True),
    ToolSpec("save_set", "lifecycle", Route.TCP, Risk.LIFECYCLE,
             AcceptanceMode.GUARDED, False),
    ToolSpec("quit_ableton", "lifecycle", Route.TCP, Risk.LIFECYCLE,
             AcceptanceMode.MANUAL, False),
    ToolSpec("live_fade", "mixer", Route.TCP, Risk.REVERSIBLE,
             AcceptanceMode.GUARDED, True),
    *_group(_WS_READS, domain="extension", route=Route.WEBSOCKET, risk=Risk.READ,
            acceptance=AcceptanceMode.GUARDED, reversible=True),
    *_group(_WS_WRITES, domain="extension", route=Route.WEBSOCKET,
            risk=Risk.REVERSIBLE, acceptance=AcceptanceMode.GUARDED, reversible=True),
    *_group(_COMPOSED_READS, domain="diagnostics", route=Route.COMPOSED,
            risk=Risk.READ, acceptance=AcceptanceMode.GUARDED, reversible=True),
    *_group(_LOCAL_READS, domain="local", route=Route.LOCAL, risk=Risk.READ,
            acceptance=AcceptanceMode.OFFLINE, reversible=True),
    ToolSpec("scaffold_extension", "developer", Route.LOCAL, Risk.LOCAL_WRITE,
             AcceptanceMode.OFFLINE, True),
    ToolSpec("build_extension", "developer", Route.LOCAL, Risk.LOCAL_WRITE,
             AcceptanceMode.ENVIRONMENT, True),
)
```

The test must show exactly 65. If it reports a different count, compare the
tuple to the existing `PUBLIC_TOOL_NAMES`; do not weaken the assertion.

- [ ] **Step 4: Derive the server name tuple and simplify the model test**

```python
# ableton_mcp_server/server.py
from .catalog import TOOL_CATALOG

PUBLIC_TOOL_NAMES = tuple(spec.name for spec in TOOL_CATALOG)
```

Replace the hand-maintained sets in `test_every_public_tool_has_an_explicit_request_model`
with:

```python
from ableton_mcp_server.catalog import TOOL_CATALOG

assert set(TOOL_REQUEST_MODELS) == {item.name for item in TOOL_CATALOG}
assert len(TOOL_REQUEST_MODELS) == 65
```

- [ ] **Step 5: Run GREEN and registry regression**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_catalog.py tests\test_models.py tests\test_tool_registry.py -q`

Expected: all selected tests pass and all three sources report 65 names.

- [ ] **Step 6: Commit**

```powershell
git add ableton_mcp_server/catalog.py ableton_mcp_server/server.py tests/test_catalog.py tests/test_models.py tests/test_tool_registry.py
git commit -m "refactor: add canonical 65-tool capability catalog"
```

### Task 2: Add stable cross-bridge error codes

**Files:**
- Modify: `contracts.py:1-70`
- Modify: `AbletonMCPServer_RemoteScript/__init__.py:15-50`
- Modify: `ableton_mcp_server/errors.py:1-145`
- Modify: `ableton_mcp_server/ws_client.py:55-90`
- Modify: `AbletonMCPServer_Extension/src/index.ts:130-190`
- Test: `tests/test_errors.py`
- Test: `tests/test_ws_client.py`

- [ ] **Step 1: Write failing Python error tests**

```python
from ableton_mcp_server.errors import error_from_envelope


@pytest.mark.parametrize(
    ("code", "class_name"),
    [
        ("CAPABILITY_UNAVAILABLE", "CapabilityUnavailableError"),
        ("AMBIGUOUS_MATCH", "AmbiguousMatchError"),
        ("VERIFICATION_FAILED", "VerificationFailedError"),
        ("ACCEPTANCE_GUARD_FAILED", "AcceptanceGuardFailedError"),
    ],
)
def test_new_public_error_codes_are_typed(code: str, class_name: str) -> None:
    assert type(error_from_envelope(code, "message", "hint")).__name__ == class_name
```

Add a WS test whose response is:

```python
{
    "jsonrpc": "2.0",
    "id": 1,
    "error": {
        "code": -32000,
        "message": "Audio clip warp markers are read-only",
        "data": {"code": "CAPABILITY_UNAVAILABLE", "hint": "Use get_warp_state"},
    },
}
```

and assert `CapabilityUnavailableError` is raised.

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_errors.py tests\test_ws_client.py -q`

Expected: failures for missing classes and generic WS `Exception`.

- [ ] **Step 3: Define and map the four errors**

Add constants to `contracts.py` and matching `BridgeError` subclasses to
`ableton_mcp_server/errors.py`:

```python
ERROR_CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
ERROR_AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
ERROR_VERIFICATION_FAILED = "VERIFICATION_FAILED"
ERROR_ACCEPTANCE_GUARD_FAILED = "ACCEPTANCE_GUARD_FAILED"


class CapabilityUnavailableError(BridgeError):
    default_code = "CAPABILITY_UNAVAILABLE"


class AmbiguousMatchError(BridgeError):
    default_code = "AMBIGUOUS_MATCH"


class VerificationFailedError(BridgeError):
    default_code = "VERIFICATION_FAILED"


class AcceptanceGuardFailedError(BridgeError):
    default_code = "ACCEPTANCE_GUARD_FAILED"
```

Include all four in `_ERROR_TYPES`. Import the vendored constants where a
Remote Script handler uses them.

- [ ] **Step 4: Preserve structured Extension error data**

Replace the generic response branch in `WSClient.call` with:

```python
if "error" in response:
    error_data = response["error"]
    details = error_data.get("data") or {}
    if isinstance(details, dict) and isinstance(details.get("code"), str):
        raise error_from_envelope(
            details["code"],
            str(error_data.get("message", details["code"])),
            details.get("hint") if isinstance(details.get("hint"), str) else None,
        )
    raise BridgeError(
        str(error_data.get("message", error_data)),
        code=f"EXTENSION_RPC_{error_data.get('code', -1)}",
    )
```

In the Extension, add and use:

```typescript
class RpcDomainError extends Error {
  constructor(
    public readonly domainCode: string,
    message: string,
    public readonly hint?: string,
  ) {
    super(message);
  }
}

function rpcError(error: unknown) {
  if (error instanceof RpcDomainError) {
    return {
      code: -32000,
      message: error.message,
      data: { code: error.domainCode, hint: error.hint },
    };
  }
  const message = error instanceof Error ? error.message : String(error);
  return { code: -32603, message };
}
```

- [ ] **Step 5: Regenerate contracts and run GREEN**

Run:

```powershell
.\.venv-win\Scripts\python.exe scripts\vendor_contracts.py
.\.venv-win\Scripts\python.exe -m pytest tests\test_errors.py tests\test_ws_client.py tests\test_vendoring.py -q
Push-Location AbletonMCPServer_Extension
npm run build
Pop-Location
```

Expected: Python tests and TypeScript build pass.

- [ ] **Step 6: Commit**

```powershell
git add contracts.py AbletonMCPServer_RemoteScript/_contracts.py AbletonMCPServer_RemoteScript/__init__.py ableton_mcp_server/errors.py ableton_mcp_server/ws_client.py AbletonMCPServer_Extension/src/index.ts tests/test_errors.py tests/test_ws_client.py
git commit -m "feat: preserve structured errors across both bridges"
```

### Task 3: Make clean installation and versions coherent

**Files:**
- Modify: `pyproject.toml`
- Modify: `AbletonMCPServer_Extension/manifest.json`
- Modify: `tests/test_packaging.py`
- Create: `scripts/verify_clean_install.ps1`

- [ ] **Step 1: Write failing packaging assertions**

Extend `test_release_version_is_aligned_across_package_metadata` to read both
Extension JSON files and assert all values equal `ableton_mcp_server.__version__`.
Add:

```python
def test_runtime_dependencies_cover_imported_analysis_and_fastmcp_websockets() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"websockets>=15.0.1,<17"' in pyproject
    assert '"numpy>=2.2,<3"' in pyproject
    assert '"soundfile>=0.13,<1"' in pyproject
```

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_packaging.py -q`

Expected: Extension manifest and dependency assertions fail.

- [ ] **Step 3: Correct package constraints and targeted typing configuration**

Use this dependency/configuration shape:

```toml
dependencies = [
    "mcp>=1.28,<2",
    "fastmcp>=3.4,<4",
    "pydantic>=2.12,<3",
    "websockets>=15.0.1,<17",
    "numpy>=2.2,<3",
    "soundfile>=0.13,<1",
]

[tool.mypy]
python_version = "3.10"
strict = true
warn_unused_configs = true
follow_imports_for_stubs = true

[[tool.mypy.overrides]]
module = ["numpy", "numpy.*", "soundfile"]
follow_imports = "skip"
ignore_missing_imports = true
```

Set `AbletonMCPServer_Extension/manifest.json` version to `0.5.0`. Do not bump
the product version during stabilization.

- [ ] **Step 4: Add an isolated clean-install script**

```powershell
# scripts/verify_clean_install.ps1
[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$temp = [IO.Path]::GetFullPath(
    (Join-Path $tempRoot ("ableton-mcp-clean-" + [guid]::NewGuid()))
)
if (-not $temp.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to create/delete a clean-install directory outside the OS temp root"
}
try {
    & py -3 -m venv $temp
    $python = Join-Path $temp "Scripts\python.exe"
    & $python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip bootstrap failed" }
    & $python -m pip install $root
    if ($LASTEXITCODE -ne 0) { throw "clean package install failed" }
    & $python -c "import ableton_mcp_server.server as s; assert len(s.PUBLIC_TOOL_NAMES) == 65"
    if ($LASTEXITCODE -ne 0) { throw "installed package import failed" }
} finally {
    if (Test-Path -LiteralPath $temp) { Remove-Item -Recurse -Force -LiteralPath $temp }
}
```

- [ ] **Step 5: Reinstall the development environment and run GREEN**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv-win\Scripts\python.exe -m pytest tests\test_packaging.py -q
powershell -ExecutionPolicy Bypass -File .\scripts\verify_clean_install.ps1
```

Expected: dependency resolution, import, and packaging tests pass.

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml AbletonMCPServer_Extension/manifest.json tests/test_packaging.py scripts/verify_clean_install.ps1
git commit -m "fix: make clean Python install resolvable"
```

### Task 4: Fix `create_audio_track` proxy identity

**Files:**
- Modify: `AbletonMCPServer_RemoteScript/__init__.py:1780-1830`
- Modify: `tests/test_audio_track_v050.py`

- [ ] **Step 1: Add a fake that recreates proxies on every enumeration**

```python
class TrackProxy:
    def __init__(self, target: FakeTrack) -> None:
        object.__setattr__(self, "_target", target)

    def __getattr__(self, name: str) -> object:
        return getattr(self._target, name)

    def __setattr__(self, name: str, value: object) -> None:
        setattr(self._target, name, value)


class ReproxyingTracks:
    def __init__(self, targets: list[FakeTrack]) -> None:
        self.targets = targets

    def __iter__(self):
        return iter([TrackProxy(track) for track in self.targets])

    def __len__(self) -> int:
        return len(self.targets)

    def __getitem__(self, index: int) -> TrackProxy:
        return TrackProxy(self.targets[index])
```

Use it in a regression that creates at index `1`, names the result
`"__MCP_ACCEPTANCE__Audio"`, and asserts the pre-existing track at index `0`
keeps its name.

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_audio_track_v050.py -q`

Expected: the reproxying test fails because `id(track)` identifies an old proxy
as new.

- [ ] **Step 3: Select the created track by verified collection delta and index**

```python
before_count = len(list(song.tracks))
fn(index)
tracks = list(song.tracks)
if len(tracks) != before_count + 1:
    raise RemoteError(
        ERROR_VERIFICATION_FAILED,
        "create_audio_track did not increase the regular track count by one",
    )
created_index = len(tracks) - 1 if index == -1 else index
if created_index < 0 or created_index >= len(tracks):
    raise RemoteError(ERROR_VERIFICATION_FAILED, "created track index is out of range")
created = tracks[created_index]
if name:
    created.name = str(name)
return {
    "created": True,
    "track_id": "track:%s" % created_index,
    "track_index": created_index,
    "requested_index": index,
    "track_name": str(getattr(created, "name", "")),
}
```

- [ ] **Step 4: Run GREEN and transaction regression**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_audio_track_v050.py tests\test_transaction.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```powershell
git add AbletonMCPServer_RemoteScript/__init__.py tests/test_audio_track_v050.py
git commit -m "fix: identify newly created audio track by position"
```

### Task 5: Fix bounded Browser traversal without proxy identity

**Files:**
- Modify: `AbletonMCPServer_RemoteScript/__init__.py:647-713`
- Modify: `tests/remote_fakes.py:45-70`
- Modify: `tests/test_session_reads_v040.py:40-61`

- [ ] **Step 1: Add reproxying Browser coverage**

Make `FakeBrowserItem.children` optionally return fresh wrappers and assert both
`Operator` and `Utility` are found under separate categories with `limit=10`.
Also add a cycle-shaped fake whose child path points back to a wrapper of the
root; assert traversal stops within the 5,000-node budget.

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_session_reads_v040.py -q -k browser`

Expected: the fresh-wrapper cycle exhausts work or the known built-ins are
skipped by unstable `id()` tracking.

- [ ] **Step 3: Track stable traversal keys rather than object identity**

Change stack entries to `(item, path, depth, ordinal_path)` and use:

```python
visited: set[str] = set()
stack = [(root, [root_name], 0, ())]
while stack and len(results) < limit and len(visited) < budget:
    item, path, depth, ordinal_path = stack.pop()
    uri = str(_safe(lambda item=item: item.uri, ""))
    key = "uri:" + uri if uri else "%s:%s" % (
        category,
        "/".join(str(part) for part in ordinal_path),
    )
    if key in visited:
        continue
    visited.add(key)
    # existing result capture remains here
    children = list(_safe(lambda item=item: item.children, []))[:500]
    for child_index in range(len(children) - 1, -1, -1):
        child = children[child_index]
        child_name = str(_safe(lambda child=child: child.name, ""))
        stack.append(
            (child, [*path, child_name], depth + 1, (*ordinal_path, child_index))
        )
```

For a URI cycle, the URI key terminates it. For URI-less trees, the depth cap
and ordinal path bound total work without relying on proxy identity.

- [ ] **Step 4: Run GREEN**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_session_reads_v040.py tests\test_remote_reads.py -q`

Expected: all Browser/read tests pass.

- [ ] **Step 5: Commit**

```powershell
git add AbletonMCPServer_RemoteScript/__init__.py tests/remote_fakes.py tests/test_session_reads_v040.py
git commit -m "fix: make Browser search stable across Live proxies"
```

### Task 6: Correct warp and device-loading contracts

**Files:**
- Modify: `ableton_mcp_server/models.py:443-488`
- Modify: `ableton_mcp_server/server.py:932-993`
- Modify: `AbletonMCPServer_Extension/src/index.ts:70-130`
- Modify: `tests/test_models.py`
- Modify: `tests/test_server_tools.py`

- [ ] **Step 1: Write failing public-contract tests**

```python
def test_warp_marker_write_is_rejected_before_ws_call() -> None:
    with pytest.raises(ValidationError):
        SetWarpStateRequest(
            track_index=0,
            clip_index=0,
            warp_markers=[{"sample_time": 0, "beat_time": 0}],
        )


def test_device_name_is_primary_and_uri_alias_is_compatible() -> None:
    assert LoadDeviceToTrackRequest(track_index=0, device_name=" Operator ").resolved_name == "Operator"
    assert LoadDeviceToTrackRequest(track_index=0, device_uri="Utility").resolved_name == "Utility"
    with pytest.raises(ValidationError):
        LoadDeviceToTrackRequest(track_index=0)
```

Add an async server test asserting both public arguments send only
`{"track_index": 0, "device_name": "Operator"}` over WS.

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_models.py tests\test_server_tools.py -q -k "warp or device"`

Expected: the request accepts marker writes and lacks `device_name`.

- [ ] **Step 3: Replace the request models**

```python
class SetWarpStateRequest(RequestModel):
    track_index: NonNegativeInt
    clip_index: NonNegativeInt
    warping: bool | None = None
    warp_mode: Annotated[str, Field(max_length=32)] | None = None

    @model_validator(mode="after")
    def require_change(self) -> SetWarpStateRequest:
        if self.warping is None and self.warp_mode is None:
            raise ValueError("provide warping or warp_mode")
        return self


class LoadDeviceToTrackRequest(RequestModel):
    track_index: NonNegativeInt
    device_name: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    device_uri: Annotated[str, Field(min_length=1, max_length=512)] | None = None

    @model_validator(mode="after")
    def exactly_one_name(self) -> LoadDeviceToTrackRequest:
        values = [value for value in (self.device_name, self.device_uri) if value is not None]
        if len(values) != 1:
            raise ValueError("provide exactly one of device_name or deprecated device_uri")
        resolved = values[0].strip()
        if not resolved:
            raise ValueError("device name must be non-empty after trimming")
        self.device_name = resolved
        return self

    @property
    def resolved_name(self) -> str:
        assert self.device_name is not None
        return self.device_name
```

Retain the existing `warp_mode` normalization/allowlist validator on the reduced
`SetWarpStateRequest`.

- [ ] **Step 4: Update the MCP wrapper and Extension handler**

Expose:

```python
async def load_device_to_track(
    track_index: int,
    device_name: str | None = None,
    device_uri: str | None = None,
) -> str:
    request = models.LoadDeviceToTrackRequest(
        track_index=track_index,
        device_name=device_name,
        device_uri=device_uri,
    )
    result = await _remote_ws(
        "load_device_to_track",
        {"track_index": request.track_index, "device_name": request.resolved_name},
    )
    return json.dumps(result, indent=2)
```

In TypeScript, call `track.insertDevice(params.device_name, index)` and return
`track_index`, `device_name`, and `device_index`. Reject a non-string/empty name
with `RpcDomainError("INVALID_PARAMS", ...)`.

- [ ] **Step 5: Run GREEN and build**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_models.py tests\test_server_tools.py tests\test_ws_client.py -q
Push-Location AbletonMCPServer_Extension
npm run build
Pop-Location
```

Expected: Python tests and TypeScript build pass.

- [ ] **Step 6: Commit**

```powershell
git add ableton_mcp_server/models.py ableton_mcp_server/server.py AbletonMCPServer_Extension/src/index.ts tests/test_models.py tests/test_server_tools.py
git commit -m "fix: align warp and device tools with Extension SDK"
```

### Task 7: Detect narrow-band masking and type the analysis module

**Files:**
- Modify: `ableton_mcp_server/analysis/audio.py:20-125`
- Modify: `ableton_mcp_server/server.py:1284-1348`
- Modify: `tests/test_audio_analysis_v050.py`

- [ ] **Step 1: Add deterministic tone-overlap and duration tests**

```python
def test_masking_detects_two_overlapping_1khz_tones(tmp_path: Path) -> None:
    target = write_sine(tmp_path / "target.wav", hz=1000, amplitude=0.8, seconds=1.0)
    reference = write_sine(tmp_path / "reference.wav", hz=1000, amplitude=0.2, seconds=1.0)
    result = find_frequency_masking(str(target), str(reference), threshold_db=6.0)
    assert result["score"] == pytest.approx(12.04, abs=1.5)
    assert any(item["overlap_ratio"] > 0.8 for item in result["bands"])


def test_masking_trims_to_shared_duration(tmp_path: Path) -> None:
    short = write_sine(tmp_path / "short.wav", hz=440, amplitude=0.5, seconds=0.5)
    long = write_sine(tmp_path / "long.wav", hz=440, amplitude=0.25, seconds=1.0)
    assert find_frequency_masking(str(short), str(long))["score"] > 0
```

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_audio_analysis_v050.py -q -k masking`

Expected: the 1 kHz test returns score `0` or the unequal-duration test raises a
shape error.

- [ ] **Step 3: Replace mean-of-log bins with overlapping STFT power**

Add typed aliases and helpers:

```python
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def _stft_power(samples: FloatArray, window_size: int = 4096, hop: int = 1024) -> FloatArray:
    if samples.size < window_size:
        samples = np.pad(samples, (0, window_size - samples.size))
    starts = range(0, samples.size - window_size + 1, hop)
    window = np.hanning(window_size)
    frames = np.stack([samples[start : start + window_size] * window for start in starts])
    return np.median(np.abs(np.fft.rfft(frames, axis=1)) ** 2, axis=0)


def _band_mask(
    freqs: FloatArray,
    target_power: FloatArray,
    reference_power: FloatArray,
    low_hz: float,
    high_hz: float,
    threshold_db: float,
) -> dict[str, float | None]:
    band = (freqs >= low_hz) & (freqs < high_hz)
    target = target_power[band]
    reference = reference_power[band]
    if not target.size:
        return {"start_hz": low_hz, "end_hz": high_hz, "target_db": -120.0,
                "reference_db": -120.0, "overlap_ratio": 0.0, "excess_db": None}
    active = (target >= target.max(initial=0.0) * 1e-6) & (
        reference >= reference.max(initial=0.0) * 1e-6
    )
    if not np.any(active):
        return {"start_hz": low_hz, "end_hz": high_hz, "target_db": -120.0,
                "reference_db": -120.0, "overlap_ratio": 0.0, "excess_db": None}
    target_sum = float(np.sum(target[active]))
    reference_sum = float(np.sum(reference[active]))
    target_db = 10.0 * math.log10(target_sum + 1e-12)
    reference_db = 10.0 * math.log10(reference_sum + 1e-12)
    excess = target_db - reference_db
    overlap = float(np.sum(np.minimum(target[active], reference[active]))) / max(
        reference_sum, 1e-12
    )
    return {"start_hz": low_hz, "end_hz": high_hz, "target_db": target_db,
            "reference_db": reference_db, "overlap_ratio": min(overlap, 1.0),
            "excess_db": excess if excess >= threshold_db else None}
```

In `find_frequency_masking`, trim both signals to the shared sample count, use
the two STFT powers, and create frequencies with `np.fft.rfftfreq(4096, ...)`.

- [ ] **Step 4: Correct analysis wrapper return annotations**

Change the four MCP analysis wrapper annotations from `dict[str, Any]` to
`ToolResult`, matching `_explicit_json_result`.

- [ ] **Step 5: Run GREEN, Ruff, and mypy**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_audio_analysis_v050.py tests\test_server_tools.py -q
.\.venv-win\Scripts\python.exe -m ruff check ableton_mcp_server\analysis ableton_mcp_server\server.py tests\test_audio_analysis_v050.py
.\.venv-win\Scripts\python.exe -m mypy --strict ableton_mcp_server
```

Expected: focused tests, Ruff, and mypy pass. If mypy still enters a NumPy stub
using Python 3.12-only syntax, confirm Task 3 set
`follow_imports_for_stubs = true` and limited `follow_imports = "skip"` to the
three listed third-party module patterns; do not change the project's Python
target or add a global ignore.

- [ ] **Step 6: Commit**

```powershell
git add ableton_mcp_server/analysis/audio.py ableton_mcp_server/server.py tests/test_audio_analysis_v050.py
git commit -m "fix: detect narrow-band frequency masking"
```

### Task 8: Report checkout versus installed source identity

**Files:**
- Modify: `ableton_mcp_server/diagnostics.py:25-155`
- Modify: `ableton_mcp_server/cli.py:31-95`
- Modify: `tests/test_diagnostics.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write a failing source-identity test**

Create one checkout tree and one simulated wheel tree with different Remote
Script hashes. Assert status returns:

```python
{
    "source_kind": "checkout",
    "source": str(checkout / "AbletonMCPServer_RemoteScript"),
    "python_executable": str(Path(sys.executable).resolve()),
}
```

and that an explicit `--source` wins over auto-detection.

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_diagnostics.py tests\test_cli.py -q -k "source or install_status"`

Expected: output has no `source_kind` or executable identity.

- [ ] **Step 3: Return a typed source selection**

Add:

```python
@dataclass(frozen=True)
class BundledSource:
    path: Path
    kind: str


def bundled_remote_script_source(package_dir: Path | None = None) -> BundledSource:
    package = Path(__file__).resolve().parent if package_dir is None else package_dir
    checkout = package.parent / REMOTE_SCRIPT_NAME
    if checkout.is_dir():
        return BundledSource(checkout, "checkout")
    wheel = package / "_remote_script"
    if wheel.is_dir():
        return BundledSource(wheel, "wheel")
    raise FileNotFoundError("Bundled Remote Script was not found")
```

Keep `bundled_remote_script_path()` as a compatibility wrapper returning
`.path`. Add `source_kind` and resolved `python_executable` to install/status
results and JSON CLI output.

- [ ] **Step 4: Run GREEN**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_diagnostics.py tests\test_cli.py -q`

Expected: all diagnostics/CLI tests pass.

- [ ] **Step 5: Commit**

```powershell
git add ableton_mcp_server/diagnostics.py ableton_mcp_server/cli.py tests/test_diagnostics.py tests/test_cli.py
git commit -m "fix: expose installation source identity"
```

### Task 9: Add complete baseline certification records

**Files:**
- Create: `ableton_mcp_server/certification.py`
- Create: `tests/test_certification.py`
- Modify: `ableton_mcp_server/acceptance.py`
- Modify: `ableton_mcp_server/cli.py`
- Modify: `tests/test_acceptance.py`

- [ ] **Step 1: Write failing report-completeness tests**

```python
from ableton_mcp_server.catalog import TOOL_CATALOG
from ableton_mcp_server.certification import CertificationReport, Verification


def test_report_rejects_missing_catalog_rows() -> None:
    report = CertificationReport(tool_names=tuple(item.name for item in TOOL_CATALOG))
    report.record(Verification("get_session_info", "live_passed", "ok"))
    with pytest.raises(ValueError, match="64 tools are unclassified"):
        report.finish()


def test_release_ready_rejects_failed_but_allows_explicit_unavailable() -> None:
    names = ("a", "b")
    report = CertificationReport(tool_names=names)
    report.record(Verification("a", "offline_passed", "pytest"))
    report.record(Verification("b", "host_unavailable", "Song.save missing"))
    assert report.finish()["release_ready"] is True
```

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_certification.py -q`

Expected: module import fails.

- [ ] **Step 3: Implement immutable verification rows and aggregation**

```python
_ALLOWED_STATUSES = {
    "offline_passed", "live_passed", "manual_passed",
    "host_unavailable", "environment_unavailable", "failed",
}


@dataclass(frozen=True, slots=True)
class Verification:
    tool: str
    status: str
    evidence: str

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_STATUSES:
            raise ValueError(f"unknown verification status: {self.status}")
        if not self.evidence.strip():
            raise ValueError("verification evidence must be non-empty")


class CertificationReport:
    def __init__(self, tool_names: tuple[str, ...]) -> None:
        self._tool_names = tool_names
        self._rows: dict[str, Verification] = {}

    def record(self, row: Verification) -> None:
        if row.tool not in self._tool_names:
            raise ValueError(f"tool is not cataloged: {row.tool}")
        self._rows[row.tool] = row

    def finish(self) -> dict[str, object]:
        missing = [name for name in self._tool_names if name not in self._rows]
        if missing:
            raise ValueError(f"{len(missing)} tools are unclassified: {missing}")
        rows = [asdict(self._rows[name]) for name in self._tool_names]
        return {
            "tool_count": len(rows),
            "release_ready": not any(row["status"] == "failed" for row in rows),
            "tools": rows,
        }
```

The mutable `_rows` dictionary is owned by one report instance for one CLI run;
it is never process-global.

- [ ] **Step 4: Extend acceptance with a baseline profile**

Convert `run_live_acceptance` to `async def`, add
`profiles: tuple[str, ...] = ("baseline",)`, and make the synchronous CLI invoke
it through `asyncio.run`. The acceptance client protocol keeps synchronous
`call()` for TCP and adds async `call_ws()` for Extension probes. Record
an evidence row immediately after every existing operation and cleanup readback.
Use this explicit coverage map and add a test asserting its flattened names equal
the 65 catalog names:

```python
BASELINE_PROBE_GROUPS = {
    "offline": (
        "get_ableton_logs", "diff_snapshots_tool", "scaffold_extension",
        "build_extension", "analyze_audio", "find_frequency_masking",
        "analyze_mix", "extract_single_cycle",
    ),
    "composed": ("get_bridge_status", "get_session_overview"),
    "tcp_reads": (
        "get_session_info", "get_track_list", "get_track_state", "get_locators",
        "take_snapshot", "get_control_surfaces", "get_scenes", "get_scene_state",
        "get_project_metadata", "get_loop_settings", "get_selected_context",
        "get_clip_summary", "get_clip_notes", "get_clip_info", "get_device_list",
        "get_parameter_value", "get_routing", "get_browser_categories",
        "search_browser", "get_song_length", "live_find_track", "list_device_params",
        "get_composition_structure", "diagnose_midi_clip", "lifecycle_status",
    ),
    "websocket_reads": ("get_warp_state",),
    "mutations": (
        "create_cue_point", "bulk_create_cue_points", "delete_cue_point",
        "set_current_song_time", "set_tempo", "start_playback", "stop_playback",
        "set_loop", "set_loop_start", "set_loop_length", "run_batch",
        "add_notes_to_clip", "fire_clip", "create_clip", "delete_clip",
        "clear_clip_notes", "fire_scene", "set_track_property", "set_clip_properties",
        "create_clip_automation", "create_midi_track", "create_audio_track",
        "rename_track", "set_parameter_value", "save_set", "quit_ableton",
        "live_fade", "set_warp_state", "load_device_to_track",
    ),
}
```

Offline probes use a temporary directory and deterministic synthesized WAVs.
They call the local Python implementations directly; they are never sent to the
TCP dispatcher. The two composed probes call `bridge_status(client)` and the
three reads that form session overview. TCP probes use `client.call`, and
WebSocket probes await `client.call_ws`.
Live probes build one scratch MIDI clip in the confirmed empty slot, load
`Operator` by name, and use the explicitly supplied audio clip selector for warp
reads/writes. Add `--audio-track-index` and `--audio-clip-index` to the baseline
profile and refuse warp certification if that slot is not an audio clip.
`build_extension` is `environment_unavailable` when Node is absent.
`quit_ableton` is `environment_unavailable` until the dedicated manual profile
is requested. Track-creation probes run last; because the baseline surface has
no delete-track tool, their reserved `__MCP_ACCEPTANCE__` tracks are reported as
manual cleanup and the runner instructs the owner to undo once or close the
disposable Set without saving. Return `report.finish()` under
`result["certification"]`.

Use exact status mapping:

```python
async def _record_call(
    report: CertificationReport,
    tool: str,
    action: Callable[[], Any | Awaitable[Any]],
    *,
    passed: str = "live_passed",
) -> Any:
    try:
        value = action()
        if inspect.isawaitable(value):
            value = await value
    except BridgeError as error:
        status = "host_unavailable" if error.code == "CAPABILITY_UNAVAILABLE" else "failed"
        report.record(Verification(tool, status, f"{error.code}: {error}"))
        return error.to_envelope()
    report.record(Verification(tool, passed, "call and readback completed"))
    return value
```

Do not mark a mutation passed at send time; record it only after the existing
readback assertion.

- [ ] **Step 5: Run GREEN**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_certification.py tests\test_acceptance.py tests\test_cli.py -q`

Expected: report tests pass and the fake acceptance result contains exactly 65
rows. Acceptance tests use `pytest.mark.asyncio`; CLI tests assert `asyncio.run`
is reached only from the synchronous CLI entry point.

- [ ] **Step 6: Commit**

```powershell
git add ableton_mcp_server/certification.py ableton_mcp_server/acceptance.py ableton_mcp_server/cli.py tests/test_certification.py tests/test_acceptance.py tests/test_cli.py
git commit -m "feat: certify every baseline MCP tool"
```

### Task 10: Regenerate current-state docs and run the baseline gates

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/KNOWN_BUGS.md`
- Modify: `docs/TOOL_REFERENCE.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_packaging.py`

- [ ] **Step 1: Write failing documentation assertions**

Assert current docs contain `65 tools`, `device_name`, read-only warp markers,
the new error codes, clean-install command, and certification statuses. Assert
they do not contain the stale phrase `37 registered tools`.

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_packaging.py -q`

Expected: stale/current-contract assertions fail.

- [ ] **Step 3: Update only current-state prose**

Document:

```text
- 65 cataloged public tools
- TCP 9888 and WebSocket 9889, loopback only
- device_name primary; device_uri deprecated for one cycle
- warp_markers readable, not writable
- per-tool certification statuses and guarded TESTE_CODEX command
- Node required only for Extension development
```

Retain historical release entries in `CHANGELOG.md`; add a new Unreleased
stabilization section instead of rewriting history.

- [ ] **Step 4: Run the complete automated gate**

Run:

```powershell
$py = ".\.venv-win\Scripts\python.exe"
& $py scripts\vendor_contracts.py
& $py -m pytest -q --tb=line
& $py scripts\coverage_check.py
& $py -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests
& $py -m mypy --strict ableton_mcp_server
powershell -ExecutionPolicy Bypass -File .\scripts\verify_clean_install.ps1
Push-Location AbletonMCPServer_Extension
npm run build:prod
npm audit --audit-level=high
Pop-Location
git diff --check
```

Expected: every command exits `0` with no test failure, lint error, type error,
high-severity audit issue, or diff whitespace error.

- [ ] **Step 5: Reinstall both current runtime artifacts**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
.\.venv-win\Scripts\ableton-mcp.exe install-status --json
$extension = Join-Path $env:LOCALAPPDATA "Ableton\Extensions\ntworm.abletonmcpserver-extension"
New-Item -ItemType Directory -Force -Path (Join-Path $extension "dist") | Out-Null
Copy-Item -Force AbletonMCPServer_Extension\manifest.json (Join-Path $extension "manifest.json")
Copy-Item -Force AbletonMCPServer_Extension\dist\extension.js (Join-Path $extension "dist\extension.js")
```

Expected: Remote Script status is `current`/`installed`, and the two Extension
payload files match the just-built source hashes. Restart Live once so it loads
the regenerated Remote Script and rebuilt Extension.

- [ ] **Step 6: Run guarded baseline Live certification**

Run:

```powershell
.\.venv-win\Scripts\ableton-mcp.exe acceptance `
  --confirm-project-name TESTE_CODEX `
  --track-index 0 --clip-index 3 `
  --audio-track-index 2 --audio-clip-index 0 `
  --fire-clip --profile baseline --json
```

Expected: 65 certification rows, zero `failed`, and no unexpected artifact
outside the reserved acceptance clip/cue documented by the runner. If Live does
not expose save/quit, their rows must be explicit unavailable statuses, not
successful mutations.

- [ ] **Step 7: Commit**

```powershell
git add README.md docs/ARCHITECTURE.md docs/KNOWN_BUGS.md docs/TOOL_REFERENCE.md CHANGELOG.md tests/test_packaging.py AbletonMCPServer_RemoteScript/_contracts.py
git commit -m "docs: publish certified 65-tool baseline"
```

## Self-Review

Spec coverage: Tasks 1–10 cover all ten confirmed baseline corrections,
catalog/evidence requirements, clean install, error taxonomy, current docs, and
the guarded Live report from Slice 1 of the approved design.

Execution Consistency Audit evidence:

- PASS Test/implementation trace: every assertion shown in Tasks 1–9 maps to the concrete class/function body in its GREEN step; Task 10 maps doc assertions to named prose.
- PASS Per-task command executability: each test targets existing files or a file created earlier in the same task; certification CLI use occurs after Task 9 creates it.
- PASS File usage audit: catalog is imported by server/tests; certification is imported by acceptance; clean-install script is executed in Tasks 3 and 10.
- PASS Spec lifecycle audit: WS/TCP connection errors remain non-retrying for mutations; setup replaces artifacts only and Live reload is explicit.
- PASS Time source audit: this slice adds no new timestamps; existing snapshot Unix epoch milliseconds remain unchanged.
- PASS State scope audit: `CertificationReport._rows` is per CLI invocation; Browser visited state is per request; no new process-global mutable cache is introduced.
- PASS Environment audit: TCP and WS remain desktop-only loopback; clean-install uses a local temporary venv and deletes only its verified temp directory.
- N/A Browser event audit: Browser means Ableton's content Browser, not a web UI; no DOM/gesture test exists.
- PASS Lint/import audit: snippets use Python 3.10 syntax, declared dependencies, typed NumPy arrays, and existing Ruff/mypy/tsconfig gates.
- PASS Non-obvious API audit: `insertDevice(deviceName, index)` and getter-only `warpMarkers` are verified in the vendored SDK `dist/index.d.cts`; Browser/track fixes use observable collection/path readback rather than undocumented identity hooks.
