"""Offline mix analysis, music generation, groove and journey tools."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from fastmcp.tools import ToolResult
from pydantic import Field

from . import models
from . import server as _s
from .analysis import analyze_audio as _analyze_audio
from .analysis import analyze_mix as _analyze_mix
from .analysis import extract_single_cycle as _extract_single_cycle
from .analysis import find_frequency_masking as _find_frequency_masking
from .groove_intelligence.evidence import compare as groove_compare_service
from .groove_intelligence.evidence import evidence as groove_evidence_service
from .groove_intelligence.fallback import generate_with_provider
from .groove_intelligence.mcp_models import (
    ApplyRequestV1,
    ArtifactId,
    ArtifactIdList,
    BpmRange,
    CompareRequestV1,
    Cursor,
    EvidenceRequestV1,
    FacetMap,
    FeatureConstraints,
    GenerateRequestV1,
    GenerationBars,
    GenerationSeed,
    GrooveSourceV1,
    MetricList,
    ProjectionIds,
    ProjectionSelection,
    QueryHash,
    QueryText,
    ReferenceArtifactIdList,
    SearchLimit,
    SearchRequestV1,
    SeedBundleId,
    TransformMap,
)
from .groove_intelligence.search import search as groove_search_service
from .journeys import plan_user_journey as _plan_user_journey
from .music_brain import Generation as _Generation
from .music_brain import Traits as _Traits
from .music_brain import generate_bass as _generate_bass
from .music_brain import generate_drum_groove as _generate_drum_groove
from .music_brain import plan_production as _plan_production
from .server import (
    _explicit_json_result,
    mcp,
)

# NOTE: v0.5.0 offline mix analysis wrappers (analyze_audio, find_frequency_masking,
# analyze_mix, extract_single_cycle) are defined below; the canonical PUBLIC_TOOL_FUNCTIONS
# tuple is assembled AFTER those definitions so all names are in scope.


# ---------------------------------------------------------------------------
# v0.5.0 — Offline Mix Analysis
# ---------------------------------------------------------------------------


@mcp.tool()
def analyze_audio(path: str) -> ToolResult:
    """Compute LUFS-I, true-peak, RMS, and per-band energy summary for a
    local audio file.

    Side effects: reads the file from disk.
    Example: ``analyze_audio(path="/stems/kick.wav")`` returns LUFS-I plus
    per-band energy summary.
    Edge cases: missing files and unsupported encodings return a structured
    ``{"ok": False, "reason": ...}``.
    """
    return _explicit_json_result(_analyze_audio(path))


@mcp.tool()
def find_frequency_masking(
    target_path: str,
    reference_path: str,
    threshold_db: float = 6.0,
) -> ToolResult:
    """Identify frequency bands where ``target_path`` exceeds ``reference_path``
    by ``threshold_db`` dB or more.

    Side effects: reads both files.
    Example: ``find_frequency_masking(target_path=master, reference_path=kick)``
    suggests band-level cuts.
    Edge cases: mismatched sample rates raise a structured error; identical
    paths are rejected at the model.
    """
    return _explicit_json_result(
        _find_frequency_masking(
            target_path=target_path,
            reference_path=reference_path,
            threshold_db=threshold_db,
        )
    )


@mcp.tool()
def analyze_mix(stems: list[str], target_lufs: float | None = None) -> ToolResult:
    """Run per-stem analysis and pair-wise masking across up to 16 local audio files.

    Side effects: reads each stem from disk.
    Example: ``analyze_mix(stems=["/stems/kick.wav", "/stems/bass.wav"])`` returns
    per-stem LUFS plus pair-wise masking scores.
    Edge cases: more than 16 stems raises a structured error; a
    ``target_lufs`` outside -40.0..-6.0 raises a structured error; missing
    files are reported per-stem via ``{"ok": False, "reason": ...}``.

    The optional ``target_lufs`` adds a gain staging plan: the trim that would
    bring each stem to that loudness, the peak it would reach after the trim,
    and a clip-risk flag. The plan is a suggestion for the user to review; it
    never changes the Live set and nothing is written to Live.
    """
    return _explicit_json_result(_analyze_mix(stems=stems, target_lufs=target_lufs))


@mcp.tool()
def extract_single_cycle(path: str, frame_size: int = 2048) -> ToolResult:
    """Find a candidate single-cycle loop in a local audio file plus its
    detected pitch.

    Side effects: reads the file from disk.
    Example: ``extract_single_cycle(path="/stems/kick.wav")`` returns the
    detected pitch plus the single-cycle sample buffer.
    Edge cases: aperiodic content returns ``{"ok": False, "reason": ...}``
    instead of crashing.
    """
    return _explicit_json_result(_extract_single_cycle(path=path, frame_size=frame_size))


def _engine_traits(traits: models.MusicTraits | None) -> _Traits:
    """Convert the validated request traits into the engine's plain vector."""
    if traits is None:
        return _Traits()
    return _Traits(
        groove=traits.groove,
        electro=traits.electro,
        weirdness=traits.weirdness,
        space=traits.space,
    )


def _music_payload(
    request: models.MusicGenerateDrumGrooveRequest,
    generation: _Generation,
) -> ToolResult | Any:
    """Return the generated notes, writing them into Live only when asked.

    One ``run_batch`` writes the clip and its notes in the same Live tick, so they are one undo
    step; a command that waits a tick would split them. ``create_clip`` refuses an occupied slot,
    so this path cannot overwrite material, and a failed batch is never retried.
    """
    notes = generation.notes
    payload: dict[str, Any] = {
        "applied": request.apply,
        "traits_applied": generation.traits_applied,
        "notes": notes,
    }
    if not request.apply:
        return _explicit_json_result(payload)

    target = {"track_index": request.track_index, "clip_index": request.clip_index}
    batch = models.RunBatchRequest.model_validate(
        {
            "commands": [
                {
                    "type": "create_clip",
                    "params": {**target, "length_beats": float(request.bars) * 4.0},
                },
                {"type": "add_notes_to_clip", "params": {**target, "notes": notes}},
            ]
        }
    )
    result = _s._remote("run_batch", batch)
    if isinstance(result, ToolResult):
        # The bridge failed and _remote already built the error envelope.
        return result
    # A batch that aborted wrote nothing: create_clip refuses an occupied slot,
    # so the notes never reached Live. Reporting applied at that point would
    # claim a write the caller does not have.
    if isinstance(result, dict) and result.get("aborted_at") is not None:
        payload["applied"] = False
    payload["bridge"] = result
    return _explicit_json_result(payload)


@mcp.tool()
def music_generate_drum_groove(
    bars: int = 4,
    seed: int = 1,
    traits: dict[str, float] | None = None,
    apply: bool = False,
    track_index: int | None = None,
    clip_index: int | None = None,
) -> ToolResult | Any:
    """Generate a deterministic kick-and-hat groove, optionally into a clip.

    Side effects: none unless ``apply`` is true, which creates one clip and its
    notes in a single undo step.
    Example: ``music_generate_drum_groove(bars=4, seed=7)`` returns the notes
    without touching Live.
    Edge cases: ``apply`` without ``track_index`` and ``clip_index`` is
    rejected at the model. ``traits`` accepts groove, electro, weirdness and
    space in 0..1, applied in that fixed order; the response names the axes
    that actually changed the notes under ``traits_applied``.
    """
    request = models.MusicGenerateDrumGrooveRequest.model_validate(
        {
            "bars": bars,
            "seed": seed,
            "traits": traits,
            "apply": apply,
            "track_index": track_index,
            "clip_index": clip_index,
        }
    )
    generation = _generate_drum_groove(
        bars=request.bars, seed=request.seed, traits=_engine_traits(request.traits)
    )
    return _music_payload(request, generation)


@mcp.tool()
def music_generate_bass(
    bars: int = 4,
    seed: int = 1,
    root_midi: int = 36,
    traits: dict[str, float] | None = None,
    apply: bool = False,
    track_index: int | None = None,
    clip_index: int | None = None,
) -> ToolResult | Any:
    """Generate a deterministic root-only bass line, optionally into a clip.

    Side effects: none unless ``apply`` is true, which creates one clip and its
    notes in a single undo step.
    Example: ``music_generate_bass(bars=4, seed=7, root_midi=40)`` returns an E
    bass line without touching Live.
    Edge cases: every note is ``root_midi`` in some octave, folded back into
    the MIDI range, octave leaps from ``weirdness`` included. ``traits`` behaves
    exactly as it does for the drum groove.
    """
    request = models.MusicGenerateBassRequest.model_validate(
        {
            "bars": bars,
            "seed": seed,
            "root_midi": root_midi,
            "traits": traits,
            "apply": apply,
            "track_index": track_index,
            "clip_index": clip_index,
        }
    )
    generation = _generate_bass(
        bars=request.bars,
        seed=request.seed,
        root_midi=request.root_midi,
        traits=_engine_traits(request.traits),
    )
    return _music_payload(request, generation)


@mcp.tool()
def music_plan_production(
    prompt: str, bars: int | None = None, bpm: float | None = None
) -> ToolResult:
    """Lay a conventional section grid over a prompt and report what is missing.

    Side effects: none; this tool never reaches Live.
    Example: ``music_plan_production(prompt="a track at 128 bpm", bars=64)``
    returns six tiled sections plus the resolved tempo.
    Edge cases: no language model backs this tool. It reads only what the
    prompt states literally and lists everything else under ``unresolved``
    instead of inventing it.
    """
    request = models.MusicPlanProductionRequest.model_validate(
        {"prompt": prompt, "bars": bars, "bpm": bpm}
    )
    return _explicit_json_result(
        _plan_production(prompt=request.prompt, bars=request.bars, bpm=request.bpm)
    )


def _groove_search_from_mapping(payload: Mapping[str, object]) -> ToolResult:
    request = SearchRequestV1.model_validate(payload)
    return _explicit_json_result(
        groove_search_service(_s.get_groove_runtime(), request).model_dump(
            mode="json", exclude_none=True
        )
    )


@mcp.tool()
def groove_search(
    schema_version: Literal["groove.search.request.v1"],
    query: QueryText | None = None,
    facets: FacetMap | None = None,
    feature_constraints: FeatureConstraints | None = None,
    bpm: BpmRange | None = None,
    meter: Annotated[str, Field(min_length=1, max_length=32)] | None = None,
    seed_bundle_id: SeedBundleId | None = None,
    required_projection_ids: ProjectionIds | None = None,
    projection_operator: Literal["all", "any"] = "all",
    limit: SearchLimit = 20,
    cursor: Cursor | None = None,
) -> ToolResult:
    """Search the configured immutable groove seed bundle.

    Side effects: none; this is an offline deterministic read.
    Example: ``groove_search(query="laid back", limit=5)``.
    Edge cases: invalid cursors and missing criteria fail before runtime I/O.
    """
    return _groove_search_from_mapping(locals())


def _groove_evidence_from_mapping(payload: Mapping[str, object]) -> ToolResult:
    request = EvidenceRequestV1.model_validate(payload)
    return _explicit_json_result(
        groove_evidence_service(_s.get_groove_runtime(), request).model_dump(
            mode="json", exclude_none=True
        )
    )


@mcp.tool()
def groove_evidence(
    schema_version: Literal["groove.evidence.request.v1"],
    *,
    artifact_id: ArtifactId,
    query_hash: QueryHash | None = None,
    include_projections: ProjectionSelection | None = None,
) -> ToolResult:
    """Return bounded provenance and projection evidence for one artifact.

    Side effects: none; this is an offline deterministic read.
    Example: ``groove_evidence(artifact_id="ga1_...")``.
    Edge cases: raw notes, payloads, paths, and SQL are never returned.
    """
    return _groove_evidence_from_mapping(locals())


def _groove_generate_from_mapping(payload: Mapping[str, object]) -> ToolResult:
    request = GenerateRequestV1.model_validate(payload)
    return _explicit_json_result(
        generate_with_provider(_s.get_groove_runtime(), request).model_dump(
            mode="json", exclude_none=True
        )
    )


@mcp.tool()
def groove_generate(
    schema_version: Literal["groove.generate.request.v1"],
    *,
    source: GrooveSourceV1,
    transforms: TransformMap,
    bars: GenerationBars,
    seed: GenerationSeed,
    provider: Literal["deterministic", "neural"] = "deterministic",
    reference_artifact_ids: ReferenceArtifactIdList | None = None,
) -> ToolResult:
    """Create a deterministic derived artifact in the local content store.

    Side effects: writes only a content-addressed local artifact; never calls Live.
    Example: ``groove_generate(source={"artifact_id": "ga1_..."}, transforms={}, bars=4, seed=7)``.
    Edge cases: rights, bounds, and unknown transform axes fail explicitly.
    """
    payload = dict(locals())
    if payload["reference_artifact_ids"] is None:
        payload["reference_artifact_ids"] = []
    return _s._groove_generate_from_mapping(payload)


def _groove_compare_from_mapping(payload: Mapping[str, object]) -> ToolResult:
    request = CompareRequestV1.model_validate(payload)
    return _explicit_json_result(
        groove_compare_service(_s.get_groove_runtime(), request).model_dump(
            mode="json", exclude_none=True
        )
    )


@mcp.tool()
def groove_compare(
    schema_version: Literal["groove.compare.request.v1"],
    *,
    artifact_ids: ArtifactIdList,
    metrics: MetricList,
    normalize: bool = True,
) -> ToolResult:
    """Compare bounded cards and projections without exposing event payloads.

    Side effects: none; this is an offline deterministic read.
    Example: ``groove_compare(artifact_ids=["ga1_...", "ga1_..."], metrics=["features"])``.
    Edge cases: incompatible projection sets remain explicit in compatibility.
    """
    return _groove_compare_from_mapping(locals())


@mcp.tool()
def groove_apply(
    schema_version: Literal["groove.apply.request.v1"],
    *,
    artifact_id: ArtifactId,
    track_index: Annotated[int, Field(ge=0)],
    clip_index: Annotated[int, Field(ge=0)],
    kit_mapping_profile: Annotated[
        str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    ],
    source_track_index: Annotated[int, Field(ge=0)] | None = None,
    source_channel: Annotated[int, Field(ge=0, le=15)] | None = None,
    mode: Literal["preview", "commit"] = "preview",
    expected_empty_slot: bool = True,
) -> ToolResult:
    """Preview or explicitly commit one mapped groove to one empty clip slot.

    Side effects: preview is offline; commit performs one guarded Live batch.
    Example: ``groove_apply(..., mode="preview")`` returns a bounded receipt.
    Edge cases: rights, mapping, capability, epoch, and slot races are explicit.
    """

    request = ApplyRequestV1.model_validate(locals())
    runtime = _s.get_groove_runtime(client=_s.get_client() if request.mode == "commit" else None)
    receipt = _s.apply_artifact(runtime, request)
    return _explicit_json_result(receipt.model_dump(mode="json", exclude_none=True))



@mcp.tool()
def plan_user_journey(
    journey_type: Literal[
        "sequence_drums", "compose_melody", "compose_harmony", "design_sound"
    ],
    traits: Annotated[str, Field(max_length=2000)],
) -> ToolResult:
    """Plan a capability-aware guided journey as a fixed stage grid.

    Side effects: none; the plan names tools but calls none of them.
    Example: ``plan_user_journey("sequence_drums", "half time, dark")``.
    Edge cases: identity or exact-copy language returns a clarification request.
    """

    request = models.PlanUserJourneyRequest.model_validate(locals())
    return _explicit_json_result(
        _plan_user_journey(request.journey_type, request.traits)
    )
