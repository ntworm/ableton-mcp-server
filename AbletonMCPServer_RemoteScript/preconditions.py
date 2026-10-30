"""Validation and evaluation of mutation preconditions."""

from __future__ import annotations

from typing import Any

from ._contracts import ERROR_PRECONDITION_FAILED, ERROR_PRECONDITION_INVALID
from .common import RemoteError, _safe
from .lom import _clip_slot


def _precondition_indices(params: dict[str, Any]) -> tuple[int, int] | None:
    """Return the slot indices of a ``slot_empty`` precondition, if valid."""
    track_index = params.get("track_index")
    clip_index = params.get("clip_index")
    if (
        isinstance(track_index, bool)
        or not isinstance(track_index, int)
        or track_index < 0
        or isinstance(clip_index, bool)
        or not isinstance(clip_index, int)
        or clip_index < 0
    ):
        return None
    return track_index, clip_index


def _precondition_error(item: Any) -> tuple[RemoteError | None, tuple[int, ...]]:
    """Return the first error of one precondition item and its slot indices.

    An acceptable item yields ``(None, indices)``; a rejected one yields
    ``(error, ())``.
    """
    if not isinstance(item, dict):
        return RemoteError(ERROR_PRECONDITION_INVALID, "precondition must be an object."), ()
    if set(item) != {"type", "version", "params"}:
        return RemoteError(ERROR_PRECONDITION_INVALID, "precondition fields are invalid."), ()
    if item.get("type") != "slot_empty" or item.get("version") != "v1":
        return (
            RemoteError(ERROR_PRECONDITION_INVALID, "unsupported precondition type or version."),
            (),
        )
    params = item.get("params")
    if not isinstance(params, dict) or set(params) != {"track_index", "clip_index"}:
        return RemoteError(ERROR_PRECONDITION_INVALID, "slot_empty params are invalid."), ()
    indices = _precondition_indices(params)
    if indices is None:
        return (
            RemoteError(ERROR_PRECONDITION_INVALID, "slot indices must be non-negative integers."),
            (),
        )
    return None, indices


def _validate_preconditions(raw: Any) -> tuple[list[dict[str, Any]] | None, RemoteError | None]:
    """Validate the closed, pre-undo ``run_batch`` admission surface.

    Validation deliberately visits every item before returning.  This keeps a
    malformed request from making its outcome depend on list ordering and
    gives callers one stable error category before any Live mutation begins.
    """

    if raw is None:
        return [], None
    if not isinstance(raw, list):
        return None, RemoteError(ERROR_PRECONDITION_INVALID, "preconditions must be a list.")
    if len(raw) > 16:
        return None, RemoteError(
            ERROR_PRECONDITION_INVALID, "at most 16 preconditions are allowed."
        )
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, int]] = set()
    first_error: RemoteError | None = None
    for item in raw:
        error, indices = _precondition_error(item)
        if error is not None:
            first_error = first_error or error
            continue
        track_index, clip_index = indices
        key = ("slot_empty", "v1", track_index, clip_index)
        if key in seen:
            first_error = first_error or RemoteError(
                ERROR_PRECONDITION_INVALID,
                "preconditions must not contain duplicates.",
            )
            continue
        seen.add(key)
        normalized.append(
            {
                "type": "slot_empty",
                "version": "v1",
                "params": {"track_index": track_index, "clip_index": clip_index},
            }
        )
    return normalized, first_error


def _evaluate_preconditions(song: Any, preconditions: list[dict[str, Any]]) -> RemoteError | None:
    """Evaluate all slot predicates, returning the first failure by index."""

    first_failure: RemoteError | None = None
    for index, item in enumerate(preconditions):
        params = item["params"]
        try:
            _track, slot = _clip_slot(song, int(params["track_index"]), int(params["clip_index"]))
            occupied = bool(
                _safe(
                    lambda slot=slot: slot.has_clip,
                    _safe(lambda slot=slot: slot.clip is not None, False),
                )
            )
        except RemoteError as error:
            failure = RemoteError(
                ERROR_PRECONDITION_INVALID,
                str(error),
                details={"index": index, "bridge_stage": "precondition"},
            )
            first_failure = first_failure or failure
            continue
        if occupied:
            failure = RemoteError(
                ERROR_PRECONDITION_FAILED,
                "slot is not empty.",
                details={
                    "index": index,
                    "bridge_stage": "precondition",
                    "track_index": params["track_index"],
                    "clip_index": params["clip_index"],
                },
            )
            first_failure = first_failure or failure
    return first_failure


def _admit_batch(song: Any, params: dict[str, Any]) -> dict[str, Any] | None:
    preconditions, validation_error = _validate_preconditions(params.get("preconditions"))
    if validation_error is not None:
        return validation_error.to_envelope()
    assert preconditions is not None
    failure = _evaluate_preconditions(song, preconditions)
    return failure.to_envelope() if failure is not None else None
