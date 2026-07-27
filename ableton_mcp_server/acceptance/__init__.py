"""Acceptance runner for the Ableton MCP Server.

This package owns the bridge certification pipeline. The legacy
monolithic ``acceptance.py`` module (134 KB / ~3.4 k lines) was split
into focused submodules in 2026-07-27; see
``docs/superpowers/specs/2026-07-27-acceptance-runner-refactor-design.md``.

Public API is re-exported below so existing imports (``cli.py``,
``_strict_fake.py``, all ``tests/test_acceptance*.py`` files) keep
working unchanged.
"""

from __future__ import annotations

# Certification re-exports.
from ..certification import CertificationReport, Verification

# Disposable Set snapshot.
from .baseline import (
    BaselineSnapshot,
    _discover_baseline,
    discover_baseline,
)

# Pure helpers.
from .helpers import (
    LIVE_FADE_UNITY_VALUE,
    _acceptance_safe_cue_times,
    _baseline_tool_names,
    _parameter_tolerance,
    _synthesize_offline_inputs,
    _test_tempo,
    _write_sine_wav,
)

# Probe groups + registry helpers.
from .probes import (
    _ALLOWED_UNAVAILABLE,
    BASELINE_PROBE_GROUPS,
    QUIT_ABLETON_MANUAL_REASON,
    _baseline_probe_names,
    _expand_profiles,
    assert_baseline_probe_coverage,
    expand_profiles,
)

# Verification recording + release policy.
from .report import (
    _is_full_baseline,
    _record_call,
    _record_unavailable,
    _release_ready,
    build_baseline_report,
    is_full_baseline,
    record_call,
    record_unavailable,
    release_ready,
)

# Restore engine.
from .restore import (
    RestoreEngine,
    RestoreOp,
)

# Orchestrator.
from .runner import (
    run_live_acceptance,
    run_offline_probes,
)

# Safety primitives.
from .safety import (
    AcceptanceClient,
    AcceptanceSafetyError,
    _resolve_track_id,
    resolve_track_id,
)

__all__ = [
    # Safety
    "AcceptanceClient",
    "AcceptanceSafetyError",
    "resolve_track_id",
    "_resolve_track_id",
    # Helpers
    "LIVE_FADE_UNITY_VALUE",
    "_test_tempo",
    "_acceptance_safe_cue_times",
    "_write_sine_wav",
    "_synthesize_offline_inputs",
    "_parameter_tolerance",
    "_baseline_tool_names",
    # Baseline
    "BaselineSnapshot",
    "discover_baseline",
    "_discover_baseline",
    # Restore
    "RestoreEngine",
    "RestoreOp",
    # Certification
    "CertificationReport",
    "Verification",
    # Probes
    "BASELINE_PROBE_GROUPS",
    "_ALLOWED_UNAVAILABLE",
    "QUIT_ABLETON_MANUAL_REASON",
    "_baseline_probe_names",
    "_expand_profiles",
    "expand_profiles",
    "assert_baseline_probe_coverage",
    # Report
    "_record_call",
    "_record_unavailable",
    "_is_full_baseline",
    "_release_ready",
    "build_baseline_report",
    "is_full_baseline",
    "record_call",
    "record_unavailable",
    "release_ready",
    # Orchestrator
    "run_live_acceptance",
    "run_offline_probes",
]