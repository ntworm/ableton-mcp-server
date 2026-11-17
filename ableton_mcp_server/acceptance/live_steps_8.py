"""Live acceptance steps, part 8 of the lifted runner."""

from __future__ import annotations

import functools
from pathlib import Path
from types import SimpleNamespace

from ..certification import Verification
from . import live_steps_1 as _steps_1
from . import live_steps_2 as _steps_2
from . import live_steps_3 as _steps_3
from . import live_steps_5 as _steps_5
from . import live_steps_7 as _steps_7
from . import runner as _runner
from .helpers import _baseline_tool_names
from .probes import BASELINE_PROBE_GROUPS, QUIT_ABLETON_MANUAL_REASON, _expand_profiles
from .probes import composed as _composed
from .probes import quit as _quit
from .report import _release_ready, build_baseline_report


async def _step_46(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    for _loop_item_7 in ctx._capability_requests.items():
        ctx._tool, ctx._request = _loop_item_7
        if ctx._request is None:
            # No Group Track in this Set, so a well-formed
            # request cannot be built. The row still reads
            # capability_unavailable — the operation has no
            # public API either way — but the evidence says
            # plainly that the refusal was not exercised here.
            ctx.report.record(
                Verification(
                    ctx._tool,
                    "capability_unavailable",
                    "not exercised: this Set has no Group Track to build a "
                    "well-formed request from; the refusal is proven by the "
                    "unit tests. Use a Set containing groups for full "
                    "hierarchy coverage.",
                )
            )
            continue

        ctx.run_capability = functools.partial(
            _steps_1._lifted_run_capability, ctx, _tool=ctx._tool, _request=ctx._request
        )


        await _runner._record_call(
            ctx.report,
            ctx._tool,
            ctx.run_capability,
            passed="capability_unavailable",
        )


async def _step_47(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx.probe_beat = 4096.0

    ctx.arrangement_clip_at = functools.partial(
        _steps_2._lifted_arrangement_clip_at, ctx
    )


    ctx.run_duplicate_to_arrangement = functools.partial(
        _steps_3._lifted_run_duplicate_to_arrangement, ctx
    )


    await _runner._record_call(
        ctx.report,
        "duplicate_session_clip_to_arrangement",
        ctx.run_duplicate_to_arrangement,
    )

    ctx.run_add_notes_pattern = functools.partial(
        _steps_3._lifted_run_add_notes_pattern, ctx
    )


    await _runner._record_call(
        ctx.report, "add_notes_pattern", ctx.run_add_notes_pattern
    )

    ctx.run_create_clip_automation_curve = functools.partial(
        _steps_3._lifted_run_create_clip_automation_curve, ctx
    )


    await _runner._record_call(
        ctx.report,
        "create_clip_automation_curve",
        ctx.run_create_clip_automation_curve,
    )

    ctx.run_set_arrangement_clip_properties = functools.partial(
        _steps_3._lifted_run_set_arrangement_clip_properties, ctx
    )


    await _runner._record_call(
        ctx.report,
        "set_arrangement_clip_properties",
        ctx.run_set_arrangement_clip_properties,
    )

    ctx.run_move_arrangement_clip = functools.partial(
        _steps_3._lifted_run_move_arrangement_clip, ctx
    )


async def _step_48(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    await _runner._record_call(
        ctx.report,
        "move_arrangement_clip",
        ctx.run_move_arrangement_clip,
    )

    ctx.run_delete_arrangement_clip = functools.partial(
        _steps_3._lifted_run_delete_arrangement_clip, ctx
    )


    await _runner._record_call(
        ctx.report,
        "delete_arrangement_clip",
        ctx.run_delete_arrangement_clip,
    )


async def _step_49(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx.expanded = _expand_profiles(ctx.profiles)

    ctx.call_ws = functools.partial(_steps_1._lifted_call_ws, ctx)


    ctx.call = functools.partial(_steps_1._lifted_call, ctx)


    ctx.audio_track_index = int(
        ctx.audio_track_index if ctx.audio_track_index is not None else ctx.track_index
    )
    ctx.audio_clip_index = int(
        ctx.audio_clip_index if ctx.audio_clip_index is not None else ctx.clip_index
    )

    ctx.report = build_baseline_report(profiles=ctx.profiles)

    # Track every artifact the runner persists to disk so the owner can
    # decide what to undo / clean up after the run.
    ctx.artifacts = {
        "tags": [],  # MCP_ACCEPTANCE_* names placed in the Set
        "files": [],  # files created on disk (scaffold, build, etc.)
        "tracks_created": [],  # track indexes that the runner appended
        "manual_cleanup": [],  # anything requiring owner-side cleanup
    }


async def _step_50(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx.selected_tools = set()
    for _loop_item_1 in ctx.expanded:
        ctx.group = _loop_item_1
        ctx.selected_tools.update(BASELINE_PROBE_GROUPS[ctx.group])

    # Tools outside the selected profiles are pre-classified as
    # ``environment_unavailable`` so ``finish()`` does not raise for
    # missing rows. ``release_ready`` policy still refuses promotion
    # for any partial profile, so this cannot greenwash a release.
    ctx.catalog_names = _baseline_tool_names()
    for _loop_item_2 in ctx.catalog_names:
        ctx.tool = _loop_item_2
        if ctx.tool in ctx.report.recorded:
            continue
        if ctx.tool in ctx.selected_tools:
            continue
        ctx.report.record(
            Verification(
                ctx.tool,
                "environment_unavailable",
                f"not covered by selected profiles: {list(ctx.expanded)}",
            )
        )

    # Compute ``release_ready`` using the documented policy.
    ctx.ready = _release_ready(ctx.report, ctx.profiles, fire_clip=ctx.fire_clip)
    # Re-run ``finish()`` only after every selected tool is recorded;
    # if anything is still missing, ``finish`` raises — the runner
    # cannot greenwash the report.
    ctx.certification = ctx.report.finish()
    ctx.certification["release_ready"] = ctx.ready
    ctx.status = "ok" if ctx.ready else "failed"


async def _step_51(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx.offline_dir = Path(ctx.tmp) / "offline"
    # The offline probe set only runs when the operator actually selects
    # it (either via the ``offline`` group or the ``baseline`` umbrella).
    # Partial profiles such as ``tcp_reads`` must not trigger the
    # scaffold / npm / mix-analysis pipeline.
    if "offline" in ctx.expanded:
        # ``offline_probes`` is injectable so unit tests of the
        # runner can skip the (slow) ``scaffold_extension`` /
        # ``build_extension`` / npm / tsc pipeline. Production CLI
        # callers pass ``None`` and use the real
        # ``run_offline_probes`` implementation. Exactly one
        # end-to-end environmental test exercises the real
        # implementation; every other test that needs the offline
        # rows uses the injection point.
        #
        # The default is resolved via the package facade (not the
        # local module namespace) so that the test fixture which
        # monkey-patches ``ableton_mcp_server.acceptance.run_offline_probes``
        # is honored by this submodule.
        if ctx.offline_probes is None:
            import sys as _sys
            ctx._sys = _sys

            ctx.probe_callable = ctx._sys.modules[
                "ableton_mcp_server.acceptance"
            ].run_offline_probes
        else:
            ctx.probe_callable = ctx.offline_probes
        await ctx.probe_callable(ctx.report, ctx.offline_dir)
        # Mark scaffold/build artifacts that the offline probe produced.
        ctx.scaffold_dir = ctx.offline_dir / "scaffold"
        if ctx.scaffold_dir.exists():
            for _loop_item_3 in ctx.scaffold_dir.rglob("*"):
                ctx.path = _loop_item_3
                ctx.relative_parts = ctx.path.relative_to(ctx.scaffold_dir).parts
                if "node_modules" in ctx.relative_parts or ".git" in ctx.relative_parts:
                    continue
                if ctx.path.is_file():
                    ctx.artifacts["files"].append(str(ctx.path))

    if "composed" in ctx.expanded:
        await _composed.run(ctx.report, client=ctx.client)


async def _step_52(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if "quit" in ctx.profiles and not {
        "tcp_reads",
        "mutations",
        "websocket_reads",
        "capability",
    } & set(ctx.expanded):
        await _quit.run(ctx.report)


async def _step_53(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx.candidate_slots = ctx.call(
        "get_clip_summary", {"track_index": ctx.candidate_track_index}
    )
    if ctx.occupied_clip_target is None and isinstance(
        ctx.candidate_slots, list
    ):
        ctx.occupied_slot = next(
            (
                item
                for item in ctx.candidate_slots
                if isinstance(item, dict) and bool(item.get("has_clip"))
            ),
            None,
        )
        if ctx.occupied_slot is not None:
            ctx.occupied_clip_target = (
                ctx.candidate_track_index,
                int(ctx.occupied_slot["index"]),
            )

    ctx.candidate_devices = ctx.call(
        "get_device_list", {"track_index": ctx.candidate_track_index}
    )


async def _step_54(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if ctx.rack_device_target is None and isinstance(
        ctx.candidate_devices, list
    ):
        for _loop_item_16 in enumerate(
            ctx.candidate_devices
        ):
            ctx.candidate_device_index, ctx.candidate_device = _loop_item_16
            if not isinstance(ctx.candidate_device, dict):
                continue
            ctx.class_name = str(ctx.candidate_device.get("class_name", ""))
            ctx.device_name = str(ctx.candidate_device.get("name", ""))
            if ctx.class_name.endswith(
                "GroupDevice"
            ) or "Rack" in ctx.device_name:
                ctx.rack_device_target = (
                    ctx.candidate_track_index,
                    ctx.candidate_device_index,
                )
                break


async def _step_55(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    for _loop_item_8 in BASELINE_PROBE_GROUPS.get("mutations", ()):
        ctx.tool = _loop_item_8
        if ctx.tool not in ctx.report.recorded:
            ctx.report.record(
                Verification(
                    ctx.tool,
                    "failed",
                    f"bridge refused to send mutations: {ctx.safety_error}",
                )
            )
    # Also mark websocket_reads when refused.
    for _loop_item_9 in BASELINE_PROBE_GROUPS.get("websocket_reads", ()):
        ctx.tool = _loop_item_9
        if ctx.tool not in ctx.report.recorded:
            ctx.report.record(
                Verification(
                    ctx.tool,
                    "failed",
                    f"bridge refused to send mutations: {ctx.safety_error}",
                )
            )
    # ``quit_ableton`` is never invoked when refused. Until an
    # out-of-band owner confirmation arrives, the row reads
    # ``manual_required`` rather than claiming success for an
    # operation that was never executed.
    if "quit" not in ctx.profiles and ("quit_ableton" not in ctx.report.recorded):
        ctx.report.record(
            Verification(
                "quit_ableton",
                "manual_required",
                QUIT_ABLETON_MANUAL_REASON,
            )
        )
    raise ctx.safety_error


async def _step_56(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if not ctx.create_clip_ok:
        for _loop_item_17 in (
            "duplicate_session_clip_to_arrangement",
            "move_arrangement_clip",
            "delete_arrangement_clip",
            "set_arrangement_clip_properties",
            "add_notes_pattern",
            "create_clip_automation_curve",
        ):
            ctx.arrangement_tool = _loop_item_17
            ctx.report.record(
                Verification(
                    ctx.arrangement_tool,
                    "failed",
                    "Skipped: create_clip dependency failed",
                )
            )
    else:
        await _step_47(ctx)


        await _step_48(ctx)

    # ----- delete_clip + readback -----
    await _steps_5._step_20(ctx)
    await _steps_5._step_21(ctx)

    await _steps_5._step_22(ctx)


async def _step_57(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    for _loop_item_23 in ctx.params_list:
        ctx.p = _loop_item_23
        if not isinstance(ctx.p, dict):
            continue
        if (
            ctx.p.get("is_enabled") is False
            or ctx.p.get("enabled") is False
        ):
            continue
        ctx.p_name = ctx.p.get("name")
        if not isinstance(
            ctx.p_name, str
        ) or not ctx.p_name:
            continue
        ctx.min_val = float(ctx.p.get("min", 0.0))
        ctx.max_val = float(ctx.p.get("max", 1.0))
        ctx.is_quant = bool(
            ctx.p.get("is_quantized", False)
        )

        ctx.discovered_param_track_index = ctx.t_idx
        ctx.discovered_param_device_index = ctx.dev_idx
        ctx.discovered_param_name = ctx.p_name
        ctx.discovered_param_min = ctx.min_val
        ctx.discovered_param_max = ctx.max_val
        ctx.discovered_param_is_quantized = ctx.is_quant
        break


async def _step_58(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    for _loop_item_10 in ("mutations", "websocket_reads"):
        ctx.group = _loop_item_10
        for _loop_item_15 in BASELINE_PROBE_GROUPS.get(ctx.group, ()):
            ctx.tool = _loop_item_15
            if ctx.tool not in ctx.report.recorded:
                ctx.report.record(
                    Verification(
                        ctx.tool,
                        "failed",
                        f"{type(ctx.outer_error).__name__}: {ctx.outer_error}",
                    )
                )
    # ``quit_ableton`` is unavailable under any non-quit
    # profile regardless of readback outcome; until an
    # out-of-band owner confirmation arrives it reads
    # ``manual_required`` instead of being green-washed.
    if "quit" not in ctx.profiles and ("quit_ableton" not in ctx.report.recorded):
        ctx.report.record(
            Verification(
                "quit_ableton",
                "manual_required",
                QUIT_ABLETON_MANUAL_REASON,
            )
        )


async def _step_59(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    for _loop_item_4 in sorted(ctx.baseline["track_names"]):
        ctx.candidate_track_index = _loop_item_4
        try:
            await _step_53(ctx)
            await _step_54(ctx)
        except Exception:
            continue

    await _steps_7._step_40(ctx)


async def _step_60(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if "capability" in ctx.expanded:
        # Prove the refusal, not the operation. Each of these
        # tools must reject a *well-formed* request with
        # CAPABILITY_UNAVAILABLE and leave the Set untouched. A
        # success is a hard failure: it would mean the tool found
        # some unverified path into the Set.
        await _steps_7._step_44(ctx)
        await _steps_7._step_45(ctx)
        await _step_46(ctx)

    await _steps_7._step_41(ctx)

    await _steps_7._step_42(ctx)
