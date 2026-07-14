# Certification policy

This document is canonical for how the acceptance runner classifies each
catalogued tool, what ``release_ready`` means, and how destructive
operations (``quit_ableton``, ``build_extension``) are gated.

The runner drives 65 catalogued tools (see ``ableton_mcp_server/catalog.py``)
through a real Bridge / Live round-trip and records one row per tool
into a ``CertificationReport``. Promotion is gated on the resulting row
mix, never on a synthetic green-wash.

## Verification status taxonomy

Every tool records exactly one of these statuses in the
``CertificationReport``:

| Status                | Meaning                                                                                          |
| --------------------- | ------------------------------------------------------------------------------------------------ |
| ``live_passed``       | Bridge mutation ran and a follow-up readback proved the mutation took effect.                    |
| ``offline_passed``    | Pure-Python or local-file probe ran and returned a valid result. Never touched the Live host.    |
| ``manual_passed``     | Owner manually confirmed the operation ran against Live. Used **only** after an out-of-band check. |
| ``manual_required``   | The runner did **not** execute the operation; an out-of-band owner confirmation is required before the row can flip to ``manual_passed``. |
| ``host_unavailable``  | The Live bridge exposed ``CAPABILITY_UNAVAILABLE`` for this seam.                                 |
| ``environment_unavailable`` | The probe could not run (Node missing, fire-clip flag off, etc.). Allowed only on the rows listed below. |
| ``failed``            | Probe ran but the readback diverged, or a cleanup/restore step diverged. Release blocker.        |

The runner never invents a ``manual_passed`` row by itself: the row
must either flip from ``manual_required`` via an out-of-band confirmation
recorded on the report, or come from a real readback-proven mutation.

## ``release_ready`` policy

The runner reports ``release_ready: True`` **only** when **all** of
the following hold simultaneously:

1. **No row is ``failed``.**
   Any ``failed`` row — whether caused by a mutation readback mismatch
   or by a cleanup/restore readback mismatch — blocks promotion.
2. **The selected profile set equals the full baseline set**
   (``offline``, ``composed``, ``tcp_reads``, ``websocket_reads``,
   ``mutations``). Partial profiles (e.g. ``tcp_reads`` alone) never
   claim ``release_ready`` regardless of the row mix.
3. ``fire_clip=True`` was passed to the runner.
   Without the flag the ``fire_clip`` row is recorded as
   ``environment_unavailable`` and ``release_ready`` is permanently
   ``False`` for that run.
4. ``build_extension`` was either not exercised at all, or recorded
   ``offline_passed``. A ``failed`` ``build_extension`` row blocks
   promotion; a ``missing`` ``build_extension`` row is **not** the
   same as ``offline_passed`` — the runner never invents success
   for a probe it did not actually run.
5. No row reports ``manual_required`` for an operation the runner
   could have exercised. The single documented exception is
   ``quit_ableton`` (see below).

Any other condition — including transient infra problems — must
surface as ``failed`` (with evidence) rather than as a green-washed
``live_passed`` / ``offline_passed``.

## ``build_extension`` (development-only)

``build_extension(project_path)`` is a development-only probe: it runs
``npm install`` + ``npm run build`` against the scaffolded extension
and records the outcome. The row outcome is policy-driven:

- **Node missing on PATH.** Row reads ``environment_unavailable``.
  The reason is logged on the row. Promotion is **not** blocked by
  this row alone because the artifact is a development convenience;
  production Live connectivity is proven separately by ``doctor`` /
  the guarded acceptance run on the owner machine.
- **Node present and the build succeeds.** Row reads
  ``offline_passed``. ``dist/extension.js`` (the entrypoint declared
  by the scaffolded ``package.json["main"]``) must exist on disk.
- **Node present and the build fails.** Row reads ``failed``. This
  *is* a release blocker: a broken TypeScript pipeline must be fixed
  before promotion.

The previous documentation referring to ``dist/index.js`` is obsolete.
The current scaffold produces a native ``AbletonMCPServer``-style
extension whose canonical entrypoint is ``dist/extension.js`` as
declared in ``package.json["main"]`` and ``manifest.json["entry"]``.

## ``quit_ableton`` and the destructive-profile policy

``quit_ableton`` closes the Live host. The automated acceptance runner
**never** invokes it during the baseline probe — doing so would
prevent every later probe from running. The row is therefore recorded
as:

- ``manual_required`` for every profile the automated runner
  exercises, with the documented reason
  ``quit_ableton requires out-of-band owner confirmation; automated
  probe never invokes a destructive shutdown``.
- ``manual_passed`` only after an explicit out-of-band owner
  confirmation (recorded manually on the report or via a dedicated
  flag). The CLI does not currently provide that flag; the operator
  must record the confirmation before promotion.

Because the automated run never flips ``quit_ableton`` out of
``manual_required``, a separate destructive-acceptance flow is
responsible for the destructive certification. The main baseline
``release_ready`` flag is independent of ``quit_ableton``'s
``manual_required`` row — the row is explicitly allowed by clause 5
of the ``release_ready`` policy above.

## Explicitly allowed unavailable rows

The following row may legitimately read ``environment_unavailable``
without blocking promotion, when the documented condition holds:

| Tool             | Allowed unavailable condition                                    |
| ---------------- | ----------------------------------------------------------------- |
| ``build_extension`` | Node executable not on PATH (development-only probe).         |

Note: running without ``--fire-clip`` records ``fire_clip`` as
``environment_unavailable``, which intentionally blocks ``release_ready``.
When Node is present, any failure in ``build_extension`` records ``failed``
and blocks promotion.

Any other ``environment_unavailable`` row is treated as a release
blocker (effectively a ``failed`` row). The runner enforces this in
``tests/test_acceptance_runner_integration.py``.


## Cleanup restore semantics

Before any mutation occurs, ``save_set`` certifies the clean baseline state of the loaded project file.

Every in-place reversible mutation (tempo, song position, loop boundaries, cue points, mixer properties, parameter values, and warp state) is captured in baseline snapshots and explicitly restored during cleanup. Each restoration is followed by a readback check; a readback mismatch — even when the initial mutation succeeded — downgrades the affected tool's status to ``failed``.

Structural additions (such as loading a device via ``load_device_to_track`` or creating new tracks via ``create_audio_track`` / ``create_midi_track``) persist as unsaved in-memory modifications in the open Live session. Because ``save_set`` runs prior to all mutations, closing Live without saving guarantees that the project on disk reverts cleanly to the saved baseline state. Manual cleanup instructions are also recorded in the audit artifact as an operational fallback reference. See ``tests/test_acceptance_audit_p0p1.py::test_p1_6_set_tempo_readback_fails_only_during_restore`` for the regression guard.

## Release candidate provenance & integrity

Every release candidate bundle published under ``releases/v<version>-rc<N>/`` is bound to a specific ``source_commit`` SHA-256 in its ``manifest.json``.

To ensure strict provenance:
1. The ``source_commit`` must contain 100% of the source code, unit/integration tests, and documentation required for gate verification. This commit must pass all quality gates (pytest, coverage, Ruff, mypy strict, build tests) independently.
2. The subsequent candidate generation commit must modify exclusively files under ``releases/v<version>-rc<N>/``. No test files, implementation logic, or documentation may be bundled into candidate commits.
3. Under ``release_ready`` policy, ``manual_required`` is permitted exclusively for ``quit_ableton`` and for ``save_set`` (when the host bridge reports ``api_available: false`` and the baseline snapshot was confirmed clean with ``is_dirty: false``). Any other tool with ``manual_required`` blocks release promotion.

## Probe groups and the 65-tool catalog

The catalog is the single source of truth for the FastMCP surface.
The runner derives its probe groups from the catalog and refuses to
finish until every catalogued tool has a recorded row. The current
catalog carries 65 entries and ``tests/test_tool_registry.py`` enforces
the count assertion.

## How to read the runner output

The full gated acceptance runner is driven with:

```powershell
.\.venv-cert\Scripts\ableton-mcp.exe acceptance `
  --profile baseline `
  --fire-clip `
  --confirm-project-name TESTE_CODEX `
  --track-index 0 `
  --clip-index 3 `
  --audio-track-index 2 `
  --audio-clip-index 0 `
  --json
```

This writes the full ``CertificationReport`` to stdout. The relevant fields:

- ``release_ready`` — the promotion gate. ``true`` only on the
  conditions listed above.
- ``tool_count`` — number of catalogued tools (must equal 65).
- ``tools`` — list of ``{tool, status, evidence}`` rows, one per
  catalogued tool.

The CLI exits non-zero when ``release_ready`` is ``false``, so any
``failed`` row surfaces as a non-zero exit code in CI.