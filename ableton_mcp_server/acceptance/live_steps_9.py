"""Live acceptance steps, part 9 of the lifted runner."""

from __future__ import annotations

import tempfile
from types import SimpleNamespace

from ..certification import Verification
from . import live_steps_4 as _steps_4
from . import live_steps_5 as _steps_5
from . import live_steps_6 as _steps_6
from . import live_steps_7 as _steps_7
from . import live_steps_8 as _steps_8
from .probes import BASELINE_PROBE_GROUPS
from .safety import AcceptanceSafetyError, _resolve_track_id


async def _step_61(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    for _loop_item_18 in BASELINE_PROBE_GROUPS.get("mutations", ()):
        ctx.tool = _loop_item_18
        if ctx.tool not in ctx.report.recorded:
            ctx.report.record(
                Verification(
                    ctx.tool,
                    "failed",
                    f"mutations setup failed: {ctx.mutations_error}",
                )
            )


async def _step_62(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    for _loop_item_21 in enumerate(ctx.device_params):
        ctx.dev_idx, ctx.dev_entry = _loop_item_21
        if isinstance(
            ctx.dev_entry, dict
        ) and ctx.dev_entry.get("parameters"):
            ctx.params_list = ctx.dev_entry.get("parameters")
            if isinstance(ctx.params_list, list):
                await _steps_8._step_57(ctx)
                if ctx.discovered_param_name is not None:
                    break


async def _step_63(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    for _loop_item_6 in ctx.search_tracks:
        ctx.t_idx = _loop_item_6
        try:
            ctx.dev_list = ctx.call("get_device_list", {"track_index": ctx.t_idx})
            if isinstance(ctx.dev_list, list) and ctx.dev_list:
                ctx.t_id = _resolve_track_id(ctx.client, ctx.t_idx)
                ctx.device_params = ctx.call(
                    "list_device_params", {"track_id": ctx.t_id}
                )
                if isinstance(ctx.device_params, list):
                    await _step_62(ctx)
                    if ctx.discovered_param_name is not None:
                        break
        except Exception:
            pass

    await _steps_8._step_60(ctx)


async def _step_64(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx.baseline = None


async def _step_65(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    await _steps_6._step_29(ctx)
    await _steps_6._step_30(ctx)
    # Restore per-track mute/solo/arm so the
    # disposable Set comes back to its pre-run state.
    # ``set_track_property(mute/solo/arm)`` is rejected
    # by Live for master (mute/solo) and for master +
    # returns (arm). Skip those indices; the baseline
    # already recorded their values for symmetry with
    # other track states but cleanup must not mutate
    # them.
    await _steps_6._step_31(ctx)
    await _steps_6._step_32(ctx)
    # Restore each track's palette slot. Tracks whose
    # baseline colour the bridge never reported are
    # skipped: writing a default would recolour a Set the
    # runner was never able to read.
    await _steps_7._step_33(ctx)
    # Restore the live_fade target volume to its
    # Restore the live_fade mixer volume to its pre-fade value.
    # ``live_fade`` mutates
    # ``track.mixer_device.volume``; we restore by
    # issuing another ``live_fade`` with
    # ``duration=0`` and ``target_value=original``
    # so the round-trip goes through the same code
    # path as the original mutation — never via
    # ``set_parameter_value`` on a device.
    await _steps_7._step_34(ctx)
    # Any cleanup failure downgrades the affected
    # tool rows to ``failed`` so ``release_ready``
    # cannot be green. We never introduce a
    # ``cleanup_failed`` status; the audit
    # explicitly preferred ``failed`` plus
    # ``cleanup/readback failed`` evidence.
    await _steps_7._step_35(ctx)


async def _step_66(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if "mutations" in ctx.expanded:
        # ----- mutation surface -----
        #
        # All mutations run inside a single try / finally so
        # cleanup can restore the original Set state from the
        # ``baseline`` snapshot. Every mutation is followed
        # by a readback before its row is recorded.

        # Discover a usable MIDI track for the clip mutations.
        await _steps_7._step_36(ctx)
        await _steps_7._step_37(ctx)

        try:
            # ----- save_set -----
            await _steps_4._step_14(ctx)


            await _steps_4._step_15(ctx)

            await _steps_4._step_16(ctx)


            await _steps_5._step_17(ctx)
            import contextlib
            ctx.contextlib = contextlib

            await _steps_5._step_18(ctx)

            # ----- set_clip_color + readback -----
            # Only runs when create_clip produced a clip we own;
            # recolouring a pre-existing clip would change the
            # operator's Set beyond what cleanup restores.
            await _steps_5._step_19(ctx)

            # ----- Arrangement round trip: place, move, delete -----
            # Everything happens far past the end of the Set so the
            # probe cannot collide with real material, and the clip
            # it creates is removed by the last step of the trip.
            await _steps_8._step_56(ctx)

        except Exception as mutations_error:
            ctx.mutations_error = mutations_error
            await _step_61(ctx)

        finally:
            # ----- cleanup restore -----
            await _step_65(ctx)

        await _steps_7._step_38(ctx)

    await _steps_7._step_43(ctx)


async def _step_67(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    with tempfile.TemporaryDirectory(prefix="ableton-mcp-acceptance-") as ctx.tmp:
        await _steps_8._step_51(ctx)

        await _steps_8._step_52(ctx)

        if {"tcp_reads", "mutations", "websocket_reads", "capability"} & set(ctx.expanded):
            await _step_64(ctx)
            try:
                await _steps_7._step_39(ctx)
                await _steps_8._step_59(ctx)

                await _step_63(ctx)

                await _step_66(ctx)

            except AcceptanceSafetyError as safety_error:
                # Bridge refused to send mutations. Mark every selected
                # mutation as ``failed`` so the report cannot pass with
                # zeros, then re-raise so the CLI still observes the
                # refusal.
                ctx.safety_error = safety_error
                await _steps_8._step_55(ctx)
            except Exception as outer_error:  # noqa: BLE001
                # Any uncaught failure during the live probe phase marks
                # every still-missing tool as ``failed`` so the report
                # cannot pass with zeros.
                ctx.outer_error = outer_error
                await _steps_8._step_58(ctx)

    # Compute the set of selected tools (resolved across profiles).
    await _steps_8._step_50(ctx)
