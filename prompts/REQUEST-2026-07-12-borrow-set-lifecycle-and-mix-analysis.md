# REQUEST: Borrow set lifecycle, fader fade, and offline mix analysis

**Author:** Worm (via Broc)
**Date:** 2026-07-12
**Status:** OPEN
**Target version:** v0.5.0 (single coherent PR; too small for v0.4.x carryover)
**Branch suggestion:** `feature/v0.5.0-lifecycle-and-mix-analysis`

---

## 1. Why this request exists

The Discord scan on 2026-07-10 plus the GitHub competitive analysis on 2026-07-12 surfaced **one fork and one extension** that solve problems our server does not. We are not the only ship in this category — `mlmil/Ableton-Live-MCP-ULTRA-v2` (a maintained fork of `bschoepke`) and `motodigitalguru-beep/ableton-mcp-extended` (a maintained fork of `ahujasid`) target the same niche from different angles.

| repo | stars/age | core idea | weaknesses vs us |
|---|---|---|---|
| [`mlmil/Ableton-Live-MCP-ULTRA-v2`](https://github.com/mlmil/Ableton-Live-MCP-ULTRA-v2) | 1★ (upstream bschoepke 195★), forked Jul 2026 | bschoepke base + 4 `live_*` set-lifecycle tools + `live_fade` smoothstep fader on Live main thread + 7 named ergonomic wrappers. MIT-licensed upstream. | Single-author fork, __version__ "0.2.0", runtime identity bumped on every release. The lifecycle helpers (`live_save_set`, `live_quit_ableton`) assume a macOS GUI fallback that is AppleScript-coupled; we run WSL↔Windows and need a different fallback surface. The `live_fade` blocks Live's main thread for up to 60 seconds, which is a new risk class for our bridge. |
| [`motodigitalguru-beep/ableton-mcp-extended`](https://github.com/motodigitalguru-beep/ableton-mcp-extended) | 2★ (upstream ahujasid 2788★), Jul 2026 | ahujasid base + offline `audio_analysis.py` module (LUFS, masking, single-cycle wavetable, auto-EQ loop). MIT-licensed upstream. | The `auto_fix_masking` mutator splits our safety model by writing EQ through a path that is not our `set_parameter_value` allowlist. Their `capture_track_to_wav` and `configure_sidechain` are live-side, which is out of scope here. Their `analyze_mix` has no documented stem cap. |

We should **not** wholesale-import either. We should:

1. **Adopt the gaps** that make our server less capable than theirs on **safe, well-isolated** primitives.
2. **Cite both projects** in the resulting PR descriptions and docs — credit, not clone.
3. **Stay focused** on what fits our `contracts.py` allowlist model, our existing TCP/Remote Script bridge, our Python-first tool layer, and our existing tests.

The implementing agent must **selectively** pick what to bring across. Not every idea below is in scope — pick the safe ones and stop.

## 2. Candidate features (the implementing agent curates)

### From `mlmil/Ableton-Live-MCP-ULTRA-v2`

| # | Feature | Why it matters | Safety check before adopting |
|---|---|---|---|
| ML-1 | `live_lifecycle_status` — reports `Song.save` and `Application.quit` callable status plus structured GUI-workflow fallback. | Today an agent has no canonical way to discover whether Live exposes the lifecycle APIs in this version. Without it, the agent guesses and either retries or falls back ungracefully. | **LOW RISK.** Read-only Live attribute probe; returns GUI workflow when APIs missing. Adopt. Mirror as `lifecycle_status` (no `live_` prefix in our naming convention). |
| ML-2 | `live_save_set(require_api: bool = False)` — `Song.save()` when callable, structured fallback otherwise. | Today an agent has no way to programmatically save the Set. Without it, edits are lost when Live quits or crashes. | **LOW RISK.** Pure LOM call when API present; structured fallback otherwise. Accept `run_batch` allowlist because it follows existing mutation semantics. Adopt. |
| ML-3 | `live_quit_ableton(save: bool = True, force_without_save: bool = False, quit_delay_ticks: int = 2)` — save first, schedule `Application.quit` after a small UI delay. | Today an agent has no programmatic way to close Live itself. Without it, tests and CI cadences that hand control back to a human are awkward. | **LOW RISK.** Already gated behind `save` and `force_without_save`. `schedule_message` is idempotent and bounded by tick delay. Adopt. |
| ML-4 | `live_fade(track_selector, target_percent | target_value, duration=10, steps=40, curve="smoothstep"|"linear", allow_over_unity=False)` — smoothstep-or-linear stepped fader fade on Live's main thread; 60-second cap. | Today writing a smooth mix-fade requires dozens of `create_clip_automation` invocations or extension-side helper devices. Without it, scripted fader transitions are inadmissible because of cost. | **MEDIUM RISK.** First command in our bridge that intentionally blocks the Live main thread for up to 60 seconds. Python MCP layer must auto-raise the RPC timeout to `duration + 10` so the existing timeout policy still applies. Adopt with explicit threading-timeout wiring. |
| ML-5 | `live_create_audio_track`, `live_rename_track`, `live_fire_clip`, `live_stop_clip`, `live_set_tempo` | We already have `create_midi_track` (v0.4.0) and `set_tempo` (existing). Missing are `create_audio_track`, ergonomic `rename_track`. | `create_audio_track` is **LOW RISK** — mirror `create_midi_track`'s path through `_create_track`-style helper. `rename_track`, `fire_clip`, `stop_clip` are already in v0.4.0 (`create_midi_track`/`rename_track`/`fire_clip` exist as tools). **Half-out-of-scope: adopt only `create_audio_track`. Reject the others as already shipped.** |
| ML-6 | `_rpc_lifecycle_status` exposes raw `Song.save` callable flag | Same as ML-1; redundant. | **OUT OF SCOPE.** ML-1 supersedes this. |

### From `motodigitalguru-beep/ableton-mcp-extended`

| # | Feature | Why it matters | Safety check before adopting |
|---|---|---|---|
| MD-1 | `analyze_audio(path)` — LUFS-I approximation, true-peak, RMS, per-band summary. | Today an agent has no offline way to quantify loudness or band balance of a stem before deciding whether to add EQ. Without it, EQ feedback loops must depend on live-side analysis that requires M4L. | **LOW RISK.** Pure read of a local file via `soundfile`; no Live, no Remote Script, no socket. Adopt. New module `ableton_mcp_server/analysis/audio.py`. |
| MD-2 | `find_frequency_masking(target_path, reference_path, threshold_db=6.0)` — per-band masking between two files. | Today an agent can only "feel" masking; with explicit masking scores it can stop over-cutting. | **LOW RISK.** Same offline shape. Adopt. |
| MD-3 | `analyze_mix(stems)` — pair-wise masking across up to 16 local files. | Same argument as MD-2, aggregated across the whole mix. | **LOW-MEDIUM RISK.** Adopt with explicit stem cap (`MAX_STEMS = 16`, mirror of `TRACK_LIMIT_REACHED`) so agent over-use doesn't lock the agent loop. |
| MD-4 | `extract_single_cycle(path, frame_size=2048)` — single-cycle wavetable candidate plus detected pitch. | Today an agent cannot easily turn a tonal sample into a wavetable source. Without it, the Wavetable device remains a manual-only workflow. | **LOW RISK.** Pure autocorrelation on the first 5 seconds. Accept "no clear periodicity" as a structured `{"ok": False, "reason": ...}` payload, not an exception. |
| MD-5 | `auto_fix_masking(...)` — applies EQ fixes through masking detection. | Tempting: closes the loop between analysis and EQ. | **HIGH RISK.** Splits our safety model by writing EQ through a path that is not our `set_parameter_value` allowlist. Agents should keep using `set_parameter_value` after reading `find_frequency_masking` suggestions. **REJECT for v0.5.0.** |
| MD-6 | `capture_track_to_wav(path, track_index)` — render a Live track to disk. | Closes the loop between Live and offline analysis. | **HIGH RISK.** Requires reading audio from Live's audio engine. Crosses our bridge. Out of scope for v0.5.0; defer to a future "live-side audio inspection" PR. |
| MD-7 | `configure_sidechain(route, source, target)` — wire a sidechain. | Today `create_track` has no sidechain support. | **HIGH RISK.** LOM routing is undocumented and version-fragile. Out of scope. |

## 3. Suggested v0.5.0 scope (implementer's starting point)

The implementing agent should **not exceed** this curated list. Each item is small enough to ship in one PR with full tests.

| Tool / change | Source | Backend | Notes |
|---|---|---|---|
| `lifecycle_status()` | ML-1 | TCP/JSONL | New `READ_COMMANDS` entry; new dispatch branch in `_dispatch_command_steps` |
| `save_set(require_api: bool = False)` | ML-2 | TCP/JSONL | New `ALLOWED_MUTATIONS` entry; deferred verification pattern matches `set_parameter_value` |
| `quit_ableton(save: bool = True, force_without_save: bool = False, quit_delay_ticks: int = 2)` | ML-3 | TCP/JSONL | Generator-style handler using `schedule_message`; new mutation entry; `quit_delay_ticks` clamp |
| `live_fade(track_index, target_percent, duration=10.0, steps=40, curve="smoothstep", allow_over_unity=False)` | ML-4 | TCP/JSONL (main-thread block) | First main-thread block; new `COMMAND_TIMEOUT_OVERRIDES` entry; new `LIVE_FADE_*` constants; Pydantic `model_validator` enforces exactly-one of `target_percent`/`target_value` |
| `create_audio_track(index=-1, name=None)` | ML-5 subset | TCP/JSONL | Same shape as existing `create_midi_track` |
| `analyze_audio(path)` | MD-1 | local | New `ableton_mcp_server/analysis/audio.py` module; no bridge |
| `find_frequency_masking(target_path, reference_path, threshold_db=6.0)` | MD-2 | local | Pydantic model validator rejects same path |
| `analyze_mix(stems: list[str])` | MD-3 | local | Stem count cap = 16 |
| `extract_single_cycle(path, frame_size=2048)` | MD-4 | local | Structural `{"ok": False, ...}` on no periodicity |
| Extend `request_timeout_seconds` work-units table | ML-4 | `contracts.py` | Add `live_fade` branch plus 60s override |
| New runtime identity bump | ML-* | Remote Script | Bump to `set-lifecycle-and-fade-1` (semver rule) |
| Add `numpy` + `soundfile` deps | MD-1..4 | `pyproject.toml` | Optional `[project.optional-dependencies.test]` group |

**Tool count grows:** `56 → 65` (4 lifecycle + 1 audio-track + 4 analysis).

**Reject for v0.5.0** (explicit non-goals this round):

- `auto_fix_masking` (MD-5) — splits our safety model; keep `set_parameter_value` as the only EQ path.
- `capture_track_to_wav` (MD-6) and `configure_sidechain` (MD-7) — cross the bridge; out of scope.
- ML-5's `live_create_audio_track` (adopted) but **NOT** `live_create_midi_track` / `live_rename_track` / `live_fire_clip` / `live_stop_clip` / `live_set_tempo` — already in v0.4.0.
- Reflection primitives — high risk; needs a flag-off-by-default gate; design first.
- M4L bridges, web dashboard, snapshots beyond devices, automation beyond Session clips, browser cache, creative generators beyond Euclidean, Arrangement operations, modulation matrix.
- Wholesale import of either competitor's code. Hand-written against our primitives.
- Bumping base `Live.live_fade` magic numbers from the upstream README without a justification comment in code.

## 4. License posture

- `mlmil/Ableton-Live-MCP-ULTRA-v2` is itself MIT-licensed via its upstream `bschoepke/ableton-live-mcp`. Integration is permitted with attribution. We **rewrite** handlers against in-repo primitives (`_required`, `_integer_param`, `_verified_*_steps`, `_dispatch_command_steps`); no source is copied verbatim.
- `motodigitalguru-beep/ableton-mcp-extended` is MIT-licensed via its upstream `ahujasid/ableton-mcp`. We **rewrite** analysis utilities from scratch against `numpy`/`soundfile`; no source is copied verbatim.
- Both projects are credited in the CHANGELOG entry and the resulting PR description. Their MIT LICENSE files are NOT vendored into our tree.

## 5. Acceptance criteria (what this PR must demonstrate)

1. `pytest -q` passes with **all v0.4.0 tests** plus new focused tests for lifecycle, fade, audio, masking, mix, single-cycle.
2. `ruff check` and `mypy --strict ableton_mcp_server ableton_mcp_server/analysis` pass.
3. `python scripts/vendor_contracts.py` regenerates `_contracts.py` unchanged except for the new entries.
4. Public MCP tool count is exactly **65** (`tests/test_tool_registry.py` invariant).
5. **All four new lifecycle commands** are exercised against a disposable Live Set by the owner before merging. The OFFLINE tests do not claim Live connectivity, undo behavior, or main-thread scheduling.
6. CHANGELOG.md gets one entry: `v0.5.0 — set lifecycle, fader fade, and offline mix analysis`.
