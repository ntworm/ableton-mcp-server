"""Live acceptance steps, part 1 of the lifted runner."""

from __future__ import annotations

import functools
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from ..errors import BridgeError
from ..groove_intelligence.mcp_models import GrooveSourceV1
from . import runner as _runner
from .helpers import _synthesize_offline_inputs


def _lifted_analyze(ctx: SimpleNamespace, ) -> dict[str, Any]:
    from ..analysis import audio as analysis_audio

    return analysis_audio.analyze_audio(str(ctx.inputs["target"]))


def _lifted_masking(ctx: SimpleNamespace, ) -> dict[str, Any]:
    from ..analysis import audio as analysis_audio

    return analysis_audio.find_frequency_masking(
        str(ctx.inputs["target"]), str(ctx.inputs["reference"])
    )


def _lifted_mix(ctx: SimpleNamespace, ) -> dict[str, Any]:
    from ..analysis import audio as analysis_audio

    return analysis_audio.analyze_mix([str(ctx.inputs["target"]), str(ctx.inputs["reference"])])


def _lifted_single_cycle(ctx: SimpleNamespace, ) -> dict[str, Any]:
    from ..analysis import audio as analysis_audio

    return analysis_audio.extract_single_cycle(str(ctx.inputs["short"]))


def _lifted_drum_groove(ctx: SimpleNamespace, ) -> list[dict[str, Any]]:
    from ..music_brain import generate_drum_groove

    return generate_drum_groove(bars=2, seed=1).notes


def _lifted_bass(ctx: SimpleNamespace, ) -> list[dict[str, Any]]:
    from ..music_brain import generate_bass

    return generate_bass(bars=2, seed=1, root_midi=36).notes


def _lifted_production_plan(ctx: SimpleNamespace, ) -> dict[str, Any]:
    from ..music_brain import plan_production

    return plan_production(prompt="offline certification probe", bars=8, bpm=120.0)


def _lifted_user_journey(ctx: SimpleNamespace, ) -> dict[str, Any]:
    from ..journeys import plan_user_journey

    return plan_user_journey("sequence_drums", "offline certification probe")


async def _lifted_groove_phase2(ctx: SimpleNamespace, ) -> None:
    lctx = SimpleNamespace(
        ctx=ctx,
    )
    from ..groove_intelligence.deterministic import deterministic_generate
    lctx.deterministic_generate = deterministic_generate
    from ..groove_intelligence.evidence import compare, evidence
    lctx.compare = compare
    lctx.evidence = evidence
    from ..groove_intelligence.mcp_models import (
        CompareRequestV1,
        EvidenceRequestV1,
        GenerateRequestV1,
        SearchRequestV1,
    )
    lctx.CompareRequestV1 = CompareRequestV1
    lctx.EvidenceRequestV1 = EvidenceRequestV1
    lctx.GenerateRequestV1 = GenerateRequestV1
    lctx.SearchRequestV1 = SearchRequestV1
    from ..groove_intelligence.search import search
    lctx.search = search
    from ..server import get_groove_runtime
    lctx.get_groove_runtime = get_groove_runtime

    try:
        lctx.runtime = lctx.get_groove_runtime()
    except Exception as error:  # noqa: BLE001 - preserve a complete report
        lctx.failure = f"groove seed bundle is unavailable: {type(error).__name__}: {error}"

        def unavailable() -> None:
            raise RuntimeError(lctx.failure)
        lctx.unavailable = unavailable

        for _loop_item_1 in (
            "groove_search",
            "groove_evidence",
            "groove_generate",
            "groove_compare",
        ):
            lctx.name = _loop_item_1
            await _runner._record_call(
                lctx.ctx.report, lctx.name, lctx.unavailable, passed="offline_passed"
            )
        return
    await _step_1(lctx)


def _lifted_logs(ctx: SimpleNamespace, ) -> str:
    """Real ``get_ableton_logs`` impl: read the tail of Log.txt."""
    from ..diagnostics import find_ableton_log_path

    path = find_ableton_log_path()
    if path is None:
        return "Ableton Log.txt path could not be resolved."
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            return "".join(handle.readlines()[-100:])
    except OSError as error:
        return f"Error reading Ableton Log.txt: {error}"


def _lifted_diff_tool(ctx: SimpleNamespace, ) -> dict[str, Any]:
    """Compare two snapshots through the real ``diff_snapshots`` impl."""
    from ..diff import diff_snapshots

    # Build two snapshots via ``take_snapshot`` semantics — same shape
    # the runner would observe; equality is preserved so the diff is
    # honest.
    snapshot_a = {
        "schema_version": 1,
        "captured_at_unix_ms": 1,
        "live_version": "12.0",
        "tempo": 120.0,
        "signature_numerator": 4,
        "signature_denominator": 4,
        "is_playing": False,
        "current_song_time": 0.0,
        "tracks": [{"index": 0, "name": "Bass"}],
        "control_surfaces": [],
        "browser_categories_count": 1,
    }
    snapshot_b = dict(snapshot_a)
    snapshot_b["tempo"] = 121.0
    return diff_snapshots(snapshot_a, snapshot_b)


def _lifted_scaffold(ctx: SimpleNamespace, ) -> dict[str, Any]:
    """Real ``scaffold_extension`` impl, validated by file presence."""
    import json

    from ..server import scaffold_extension

    out_dir = ctx.workdir / "scaffold"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = scaffold_extension(
        "MCP_ACCEPTANCE_SCAFFOLD",
        author="mcp-acceptance",
        output_directory=str(out_dir),
    )
    parsed = json.loads(result)
    project_path = Path(parsed["project_path"])
    # Verify the actual files exist on disk.
    for name in parsed.get("files", []):
        assert (project_path / name).is_file(), f"scaffold_extension did not create {name}"
    # Tag the directory as MCP acceptance artifact.
    (project_path / "MCP_ACCEPTANCE_ARTIFACT").write_text(
        "acceptance scaffold output", encoding="utf-8"
    )
    return cast(dict[str, Any], parsed)


def _lifted_build_ext(ctx: SimpleNamespace, ) -> dict[str, Any]:
    lctx = SimpleNamespace(
        ctx=ctx,
    )
    import json
    lctx.json = json

    from ..server import build_extension
    lctx.build_extension = build_extension

    _step_2(lctx)
    _step_3(lctx)
    return cast(dict[str, Any], lctx.parsed)


async def _step_1(lctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    lctx.first, lctx.second = (str(item) for item in lctx.runtime.index.manifest.artifact_ids[:2])
    lctx.search_request = lctx.SearchRequestV1(
        schema_version="groove.search.request.v1",
        facets={"feel": ["straight"]},
        limit=1,
    )
    lctx.evidence_request = lctx.EvidenceRequestV1(
        schema_version="groove.evidence.request.v1",
        artifact_id=lctx.first,
        include_projections=None,
    )
    lctx.generate_request = lctx.GenerateRequestV1(
        schema_version="groove.generate.request.v1",
        source=GrooveSourceV1(artifact_id=lctx.first),
        transforms={"density": 0.2},
        bars=4,
        seed=7,
        provider="deterministic",
    )
    lctx.compare_request = lctx.CompareRequestV1(
        schema_version="groove.compare.request.v1",
        artifact_ids=[lctx.first, lctx.second],
        metrics=["facets", "features", "hvo", "grammar"],
        normalize=True,
    )
    await _runner._record_call(
        lctx.ctx.report,
        "groove_search",
        lambda: lctx.search(lctx.runtime, lctx.search_request),
        passed="offline_passed",
    )
    await _runner._record_call(
        lctx.ctx.report,
        "groove_evidence",
        lambda: lctx.evidence(lctx.runtime, lctx.evidence_request),
        passed="offline_passed",
    )
    await _runner._record_call(
        lctx.ctx.report,
        "groove_generate",
        lambda: lctx.deterministic_generate(lctx.runtime, lctx.generate_request),
        passed="offline_passed",
    )
    await _runner._record_call(
        lctx.ctx.report,
        "groove_compare",
        lambda: lctx.compare(lctx.runtime, lctx.compare_request),
        passed="offline_passed",
    )


def _step_2(lctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    lctx.scaffold_dir = lctx.ctx.workdir / "scaffold"
    lctx.scaffold_dirs = [p for p in lctx.scaffold_dir.iterdir() if p.is_dir()]
    if not lctx.scaffold_dirs:
        raise RuntimeError("scaffold output missing for build_extension")
    lctx.project = lctx.scaffold_dirs[0]
    lctx.result_json = lctx.build_extension(str(lctx.project))
    lctx.parsed = lctx.json.loads(lctx.result_json)
    # Strict invariant: the build must report ``status == "built"``,
    # every step must have ``returncode == 0``, and the canonical
    # artefact — the entrypoint declared by the project's own
    # ``package.json["main"]`` (falling back to
    # ``manifest.json["entry"]``) — must exist on disk. ``status ==
    # "error"`` or a failed returncode cannot be reported as
    # ``offline_passed``. Per-step ``artifact`` is **not** part of
    # the contract — the runner does not require one.
    lctx.status = str(lctx.parsed.get("status", "")).strip().lower()
    if lctx.status != "built":
        raise AssertionError(
            f"build_extension status={lctx.status!r} expected 'built': {lctx.parsed}"
        )
    lctx.steps = lctx.parsed.get("steps", [])
    if not isinstance(lctx.steps, list) or not lctx.steps:
        raise AssertionError(f"build_extension missing steps list: {lctx.parsed}")
    for _loop_item_1 in enumerate(lctx.steps):
        lctx.index, lctx.step = _loop_item_1
        if int(lctx.step.get("returncode", -1)) != 0:
            raise AssertionError(
                f"build_extension step {lctx.index} returncode="
                f"{lctx.step.get('returncode')!r} expected 0: {lctx.step}"
            )
    lctx.entrypoint = lctx.parsed.get("entrypoint")
    if not isinstance(lctx.entrypoint, str) or not lctx.entrypoint.strip():
        raise AssertionError(f"build_extension response missing entrypoint: {lctx.parsed}")
    lctx.entrypoint_rel = lctx.entrypoint.strip()
    # Top-level artefacts must include the declared entrypoint.
    lctx.artifacts = lctx.parsed.get("artifacts", [])


def _step_3(lctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    if not isinstance(lctx.artifacts, list) or not lctx.artifacts:
        raise AssertionError(f"build_extension produced no artifacts: {lctx.parsed}")
    if lctx.entrypoint_rel not in lctx.artifacts:
        raise AssertionError(
            f"build_extension artifacts missing declared entrypoint "
            f"{lctx.entrypoint_rel!r}: {lctx.artifacts}"
        )
    lctx.canonical = lctx.project / lctx.entrypoint_rel
    if not lctx.canonical.is_file():
        raise AssertionError(f"build_extension entrypoint not on disk: {lctx.canonical}")
    # Tag built artefacts for cleanup.
    for _loop_item_2 in lctx.artifacts:
        lctx.artefact = _loop_item_2
        lctx.target = lctx.project / lctx.artefact
        if lctx.target.exists():
            (lctx.target.parent / "MCP_ACCEPTANCE_ARTIFACT").write_text(
                "acceptance built artifact", encoding="utf-8"
            )


async def _step_4(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx.inputs = _synthesize_offline_inputs(ctx.workdir)

    ctx.analyze = functools.partial(_lifted_analyze, ctx)


    ctx.masking = functools.partial(_lifted_masking, ctx)


    ctx.mix = functools.partial(_lifted_mix, ctx)


    ctx.single_cycle = functools.partial(_lifted_single_cycle, ctx)


    await _runner._record_call(ctx.report, "analyze_audio", ctx.analyze, passed="offline_passed")
    await _runner._record_call(
        ctx.report, "find_frequency_masking", ctx.masking, passed="offline_passed"
    )
    await _runner._record_call(ctx.report, "analyze_mix", ctx.mix, passed="offline_passed")
    await _runner._record_call(
        ctx.report, "extract_single_cycle", ctx.single_cycle, passed="offline_passed"
    )

    # The two generators are catalogued as COMPOSED because their opt-in
    # ``apply`` writes through the bridge. Generation itself is pure, so it is
    # probed here without Live; the write path is already covered by the
    # ``create_clip`` and ``add_notes_to_clip`` mutation rows.
    ctx.drum_groove = functools.partial(_lifted_drum_groove, ctx)


    ctx.bass = functools.partial(_lifted_bass, ctx)


    ctx.production_plan = functools.partial(_lifted_production_plan, ctx)


    await _runner._record_call(
        ctx.report, "music_generate_drum_groove", ctx.drum_groove, passed="offline_passed"
    )
    await _runner._record_call(ctx.report, "music_generate_bass", ctx.bass, passed="offline_passed")
    ctx.user_journey = functools.partial(_lifted_user_journey, ctx)


    await _runner._record_call(
        ctx.report, "music_plan_production", ctx.production_plan, passed="offline_passed"
    )
    await _runner._record_call(
        ctx.report, "plan_user_journey", ctx.user_journey, passed="offline_passed"
    )

    # Phase 2 groove tools run only against the host-configured immutable pilot
    # seed. They are local and never use the bridge client.
    ctx.groove_phase2 = functools.partial(_lifted_groove_phase2, ctx)


    await ctx.groove_phase2()


async def _step_5(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    await _runner._record_call(
        ctx.report,
        "groove_apply",
        lambda: ctx.preview_probe(
            confirm_project_name="TESTE_CODEX",
            expected_empty_slot=True,
            disposable=True,
        ),
        passed="offline_passed",
    )

    ctx.logs = functools.partial(_lifted_logs, ctx)


    await _runner._record_call(ctx.report, "get_ableton_logs", ctx.logs, passed="offline_passed")

    ctx.diff_tool = functools.partial(_lifted_diff_tool, ctx)


    await _runner._record_call(
        ctx.report, "diff_snapshots_tool", ctx.diff_tool, passed="offline_passed"
    )

    ctx.scaffold = functools.partial(_lifted_scaffold, ctx)


    await _runner._record_call(
        ctx.report, "scaffold_extension", ctx.scaffold, passed="offline_passed"
    )


async def _step_6(ctx: SimpleNamespace) -> None:
    """One step of the lifted acceptance runner."""
    ctx.build_ext = functools.partial(_lifted_build_ext, ctx)


    await _runner._record_call(
        ctx.report, "build_extension", ctx.build_ext, passed="offline_passed"
    )


async def _lifted_call_ws(
    ctx: SimpleNamespace,
    method: str,
    params: dict[str, Any] | None = None,
) -> Any:
    return await ctx.client.call_ws(method, params or {})


def _lifted_call(
    ctx: SimpleNamespace,
    command: str,
    params: Mapping[str, Any] | None = None,
) -> Any:
    return ctx.client.call(command, dict(params or {}), timeout=None)


async def _lifted_run_capability(ctx: SimpleNamespace,
    _tool: str,
    _request: dict[str, Any]              ) -> str:
    try:
        ctx.call(_tool, _request)
    except BridgeError as error:
        if error.code != "CAPABILITY_UNAVAILABLE":
            raise
        return f"{_tool} refused with CAPABILITY_UNAVAILABLE"
    raise AssertionError(
        f"{_tool} returned success; Live's public API cannot "
        "perform it, so the refusal contract is broken"
    )


async def _lifted_run_diagnose_clip_targets(ctx: SimpleNamespace, ) -> str:
    report_payload = ctx.call("diagnose_clip_targets", {})
    if not isinstance(report_payload, dict):
        raise AssertionError("diagnose_clip_targets must return a dict")
    for key in ("tracks", "session_clip_count", "arrangement_clip_count"):
        if key not in report_payload:
            raise AssertionError(
                f"diagnose_clip_targets response missing {key!r}"
            )
    return (
        f"session={report_payload['session_clip_count']} "
        f"arrangement={report_payload['arrangement_clip_count']}"
    )


async def _lifted_run_get_arrangement_clips(ctx: SimpleNamespace, ) -> str:
    listing = ctx.call("get_arrangement_clips", {"track_index": ctx.track_index})
    if not isinstance(listing, dict) or "clips" not in listing:
        raise AssertionError("get_arrangement_clips must return clips")
    return f"clips={listing.get('clip_count')}"


async def _lifted_run_get_device_chains(ctx: SimpleNamespace, ) -> str:
    rack_track_index, rack_device_index = ctx.rack_device_target
    payload = ctx.call(
        "get_device_chains",
        {
            "track_index": rack_track_index,
            "device_index": rack_device_index,
        },
    )
    if not isinstance(payload, dict) or "chains" not in payload:
        raise AssertionError("get_device_chains must return chains")
    return f"chains={payload.get('chain_count')}"


async def _lifted_run_get_midi_chain_report(ctx: SimpleNamespace, ) -> str:
    payload = ctx.call("get_midi_chain_report", {"track_index": ctx.track_index})
    if "rewrites_input" not in payload:
        raise AssertionError("get_midi_chain_report must report rewrites_input")
    return f"rewrites={payload['rewrites_input']}"
