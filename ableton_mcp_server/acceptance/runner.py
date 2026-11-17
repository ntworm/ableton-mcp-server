"""Live acceptance runner for the Ableton MCP Server.

This module drives the real bridge through every catalogued tool so the
``release_ready`` flag in ``CertificationReport`` reflects what the bridge
actually did. The runner is intentionally paranoid:

- Probes are split into groups; partial profiles run only their groups.
- ``release_ready`` is **only** ``True`` when the baseline profile completes
  end-to-end with no failed tool. Partial profiles and the ``quit``
  profile never claim ``release_ready``.
- Most mutations are followed by a readback *before* the verification row
  is recorded, and readback mismatches flip the row to ``failed``. A few are
  certified by their own reply or only by returning without error;
  ``scripts/summarize_acceptance.py`` lists which.
- The disposable Set preserves and restores the original track names,
  mixer state, and clip contents. Track creation happens last so we can
  restore everything else from the original three-track layout.
- Audio clip guards use ``get_clip_info.is_audio_clip`` (the real bridge
  exposes this), not the legacy ``is_audio_clip`` on ``get_clip_summary``.
- Offline probes call the **real** implementation of each helper
  (``get_ableton_logs``, ``diff_snapshots``, ``scaffold_extension``,
  ``build_extension``) — never synthetic stand-ins.
"""

from __future__ import annotations

import shutil
from collections.abc import (
    Awaitable,
    Callable,
)
from pathlib import Path
from types import SimpleNamespace
from typing import (
    Any,
)

from ..certification import (
    CertificationReport,
)
from .baseline import BaselineSnapshot, _discover_baseline  # noqa: F401  (mypy-only)
from .live_steps_1 import _step_4, _step_5, _step_6
from .live_steps_8 import _step_49
from .live_steps_9 import _step_67
from .probes import (
    load_device as _load_device,
)
from .report import _record_call as _record_call
from .report import (
    _record_unavailable,
)
from .safety import (
    AcceptanceClient,
)

# Rows the runner records after cleanup. The load probe uses the empty MIDI
# track that create_midi_track adds, so it never touches the user's tracks.
_STRUCTURAL_TOOLS = ("create_audio_track", "create_midi_track", *_load_device.TOOLS)

# ---------------------------------------------------------------------------
# Offline probes
# ---------------------------------------------------------------------------


async def run_offline_probes(report: CertificationReport, workdir: Path) -> None:
    """Drive the four offline mix analysis probes, 4 helpers and 3 music probes.

    Each helper calls the **real** implementation rather than returning a
    synthetic object, so an upstream regression cannot be hidden by a
    hard-coded response. ``build_extension`` is the only legitimate
    ``environment_unavailable`` — and only when ``node`` is genuinely
    absent from PATH.
    """
    ctx = SimpleNamespace(
        report=report,
        workdir=workdir
    )
    await _step_4(ctx)

    # Phase 3 apply is certified offline through its preview/refusal contract;
    # this probe never opens a Live connection or performs a commit.
    from .probes.groove_apply import preview_probe
    ctx.preview_probe = preview_probe

    await _step_5(ctx)

    # ``build_extension`` runs ``npm install`` + ``tsc``. It is only
    # ``environment_unavailable`` when Node is genuinely absent; otherwise
    # we exercise the real implementation against the scaffold we just
    # wrote so the runner proves the build actually completes.
    if shutil.which("node") is None:
        _record_unavailable(
            ctx.report,
            "build_extension",
            "node executable not found on PATH",
        )
        return

    await _step_6(ctx)


# ---------------------------------------------------------------------------
# Live acceptance runner
# ---------------------------------------------------------------------------


async def run_live_acceptance(
    client: AcceptanceClient,
    *,
    confirm_project_name: str,
    track_index: int,
    clip_index: int,
    audio_track_index: int | None = None,
    audio_clip_index: int | None = None,
    profiles: tuple[str, ...] = ("baseline",),
    fire_clip: bool = False,
    offline_probes: Callable[[CertificationReport, Path], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Exercise the real bridge after exact disposable-project confirmation.

    Every selected tool gets a Certification row. A read row is ``live_passed``
    when the call returns a valid answer; most mutation rows only after a later
    read of the Set proves the write, a few by their own reply or by returning
    without error (``scripts/summarize_acceptance.py`` lists which). ``failed``
    rows propagate to ``release_ready=False`` and to a non-zero CLI exit code.
    """
    ctx = SimpleNamespace(
        client=client,
        confirm_project_name=confirm_project_name,
        track_index=track_index,
        clip_index=clip_index,
        audio_track_index=audio_track_index,
        audio_clip_index=audio_clip_index,
        profiles=profiles,
        fire_clip=fire_clip,
        offline_probes=offline_probes
    )
    await _step_49(ctx)

    await _step_67(ctx)
    return {
        "project": ctx.confirm_project_name,
        "track_index": ctx.track_index,
        "clip_index": ctx.clip_index,
        "audio_track_index": ctx.audio_track_index,
        "audio_clip_index": ctx.audio_clip_index,
        "profiles": list(ctx.profiles),
        "fire_clip": ctx.fire_clip,
        "status": ctx.status,
        "artifacts": ctx.artifacts,
        "certification": ctx.certification,
    }
