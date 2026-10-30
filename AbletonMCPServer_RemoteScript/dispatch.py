"""Command dispatch, undo grouping and run_batch execution."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from ._contracts import (
    ALLOWED_MUTATIONS,
    ERROR_BAD_INPUT,
    ERROR_INTERNAL_ERROR,
    ERROR_INVALID_PARAMS,
    ERROR_LIVE_UNAVAILABLE,
    ERROR_READ_ONLY_VIOLATION,
    ERROR_UNKNOWN_COMMAND,
    READ_ONLY_COMMANDS,
    UNSUPPORTED_CAPABILITIES,
)
from .arrangement import (
    _delete_arrangement_clip_steps,
    _duplicate_session_clip_to_arrangement_steps,
    _move_arrangement_clip_steps,
    _set_arrangement_clip_properties_steps,
)
from .automation import _create_clip_automation_curve_steps, _create_clip_automation_steps
from .clips import _clear_clip_notes_steps, _set_clip_color_steps, _set_clip_properties_steps
from .common import RemoteError, _float_param, _required, _safe
from .cues import _bulk_create_cue_points_steps, _create_cue_point_steps, _delete_cue_point_steps
from .devices import _set_parameter_value_steps, _set_plugin_preset_steps
from .handlers import COMMAND_HANDLERS
from .preconditions import _admit_batch
from .tracks import _set_track_color_steps, _set_track_property_steps, cmd_unavailable_capability
from .transport import _verified_boolean_steps, _verified_numeric_steps, _verified_playhead_steps


def _begin_undo(target: Any) -> None:
    method = _safe(lambda: target.begin_undo_step, None)
    if not callable(method):
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live runtime does not expose begin_undo_step on the selected undo target.",
        )
    method()


def _end_undo(target: Any) -> None:
    method = _safe(lambda: target.end_undo_step, None)
    if not callable(method):
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live runtime does not expose end_undo_step on the selected undo target.",
        )
    method()


def _validated_batch_command(command: Any) -> tuple[Any, dict[str, Any]]:
    if not isinstance(command, dict):
        raise RemoteError(ERROR_INVALID_PARAMS, "Batch command must be an object.")
    command_type = command.get("type")
    command_params = command.get("params", {})
    if command_type == "run_batch":
        raise RemoteError(ERROR_BAD_INPUT, "run_batch cannot contain run_batch.")
    if command_type not in ALLOWED_MUTATIONS:
        raise RemoteError(
            ERROR_READ_ONLY_VIOLATION,
            "Batch command %r is not an allowed mutation." % command_type,
        )
    if not isinstance(command_params, dict):
        raise RemoteError(ERROR_INVALID_PARAMS, "Batch command params must be an object.")
    return command_type, command_params


def _run_batch_steps(
    song: Any,
    application: Any,
    params: dict[str, Any],
    undo_target: Any,
    control_surface: Any = None,
) -> Generator[None, None, dict[str, Any]]:
    commands = _required(params, "commands")
    if not isinstance(commands, list) or not commands:
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'commands' must be a non-empty list.")
    admission_error = (
        None
        if params.pop("__preconditions_admitted", False)
        else _admit_batch(song, params)
    )
    if admission_error is not None:
        return admission_error
    results = []
    completed = 0
    aborted_at = None
    for index, command in enumerate(commands):
        try:
            command_type, command_params = _validated_batch_command(command)
            result = yield from _command_steps(
                song,
                application,
                str(command_type),
                command_params,
                manage_undo=False,
                undo_target=undo_target,
                control_surface=control_surface,
            )
            results.append({"index": index, "status": "ok", "result": result})
            completed += 1
        except RemoteError as error:
            results.append({"index": index, **error.to_envelope()})
            aborted_at = index
            break
        except Exception as error:
            wrapped = RemoteError(ERROR_INTERNAL_ERROR, str(error))
            results.append({"index": index, **wrapped.to_envelope()})
            aborted_at = index
            break
    return {
        "results": results,
        "completed": completed,
        "aborted_at": aborted_at,
        "rolled_back": False,
    }


def _set_current_song_time_steps(song: Any, params: dict[str, Any]) -> Generator[None, None, Any]:
    target = _float_param(params, "time", 0.0, 100000.0)
    return (yield from _verified_playhead_steps(song, target))


def _set_tempo_steps(song: Any, params: dict[str, Any]) -> Generator[None, None, Any]:
    tempo = _float_param(params, "tempo", 20.0, 999.0)
    dry_run = params.get("dry_run", False)
    if dry_run:
        return {
            "tempo": tempo,
            "committed": False,
            "resolved": {"kind": "tempo", "tempo": tempo},
        }
    result: dict[str, Any] = yield from _verified_numeric_steps(
        song,
        attribute="tempo",
        expected=tempo,
        result_key="tempo",
    )
    result["resolved"] = {"kind": "tempo", "tempo": result["tempo"]}
    return result


def _start_playback_steps(song: Any, params: dict[str, Any]) -> Generator[None, None, Any]:
    return (
        yield from _verified_boolean_steps(
            song,
            attribute="is_playing",
            expected=True,
            setter=song.start_playing,
            result_key="is_playing",
        )
    )


def _stop_playback_steps(song: Any, params: dict[str, Any]) -> Generator[None, None, Any]:
    return (
        yield from _verified_boolean_steps(
            song,
            attribute="is_playing",
            expected=False,
            setter=song.stop_playing,
            result_key="is_playing",
        )
    )


def _set_loop_start_steps(song: Any, params: dict[str, Any]) -> Generator[None, None, Any]:
    start = _float_param(params, "start_beat", 0.0, 100000.0)
    return (
        yield from _verified_numeric_steps(
            song,
            attribute="loop_start",
            expected=start,
            result_key="loop_start",
        )
    )


def _set_loop_length_steps(song: Any, params: dict[str, Any]) -> Generator[None, None, Any]:
    length = _float_param(params, "length_beats", 0.0, 100000.0, strictly_positive=True)
    return (
        yield from _verified_numeric_steps(
            song,
            attribute="loop_length",
            expected=length,
            result_key="loop_length",
        )
    )


def _set_loop_steps(song: Any, params: dict[str, Any]) -> Generator[None, None, Any]:
    enabled = _required(params, "enabled")
    if not isinstance(enabled, bool):
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'enabled' must be boolean.")
    return (
        yield from _verified_boolean_steps(
            song,
            attribute="loop",
            expected=enabled,
            setter=lambda: setattr(song, "loop", enabled),
            result_key="loop",
        )
    )


def _command_step_functions() -> dict[str, Any]:
    """Map command names to the step generator that serves each one.

    The table is rebuilt on every dispatch so that every entry is looked up
    in this module's globals at call time: replacing a step function on the
    module (tests, live debugging) has to change what the dispatcher runs.
    """

    return {
        "create_cue_point": _create_cue_point_steps,
        "bulk_create_cue_points": _bulk_create_cue_points_steps,
        "delete_cue_point": _delete_cue_point_steps,
        "set_current_song_time": _set_current_song_time_steps,
        "set_tempo": _set_tempo_steps,
        "set_parameter_value": _set_parameter_value_steps,
        "set_plugin_preset": _set_plugin_preset_steps,
        "clear_clip_notes": _clear_clip_notes_steps,
        "set_track_property": _set_track_property_steps,
        "set_track_color": _set_track_color_steps,
        "set_clip_color": _set_clip_color_steps,
        "set_clip_properties": _set_clip_properties_steps,
        "create_clip_automation": _create_clip_automation_steps,
        "duplicate_session_clip_to_arrangement": _duplicate_session_clip_to_arrangement_steps,
        "delete_arrangement_clip": _delete_arrangement_clip_steps,
        "move_arrangement_clip": _move_arrangement_clip_steps,
        "create_clip_automation_curve": _create_clip_automation_curve_steps,
        "set_arrangement_clip_properties": _set_arrangement_clip_properties_steps,
        "start_playback": _start_playback_steps,
        "stop_playback": _stop_playback_steps,
        "set_loop_start": _set_loop_start_steps,
        "set_loop_length": _set_loop_length_steps,
        "set_loop": _set_loop_steps,
    }


def _dispatch_command_steps(
    song: Any,
    application: Any,
    normalized: str,
    params: dict[str, Any],
    undo_target: Any,
    control_surface: Any = None,
) -> Generator[None, None, Any]:
    if normalized == "run_batch":
        return (
            yield from _run_batch_steps(song, application, params, undo_target, control_surface)
        )
    if normalized == "quit_ableton":
        # Give Live's UI thread one cycle before scheduling application quit.
        yield
    step = _command_step_functions().get(normalized)
    if step is not None:
        return (yield from step(song, params))
    handler = COMMAND_HANDLERS.get(normalized)
    if handler is None:
        raise RemoteError(ERROR_UNKNOWN_COMMAND, "Unknown command %r." % normalized)
    if normalized == "quit_ableton":
        return handler(song, application, control_surface, params)
    if normalized == "live_fade":
        # ``live_fade_steps`` is a generator that distributes its writes
        # across ``duration`` of monotonic-clock time and yields between
        # writes; ``yield from`` keeps the Live main thread pumping while it
        # waits for each step's deadline.
        return (yield from handler(song, application, params))
    return handler(song, application, params)


def _command_steps(
    song: Any,
    application: Any,
    command: str,
    params: dict[str, Any],
    *,
    manage_undo: bool,
    undo_target: Any,
    control_surface: Any = None,
) -> Generator[None, None, Any]:
    normalized = command.strip().lower()
    if normalized in READ_ONLY_COMMANDS:
        raise RemoteError(
            ERROR_READ_ONLY_VIOLATION,
            "Command %r is blocked: creative mutation is not available." % command,
        )
    if normalized in UNSUPPORTED_CAPABILITIES:
        # Distinct from UNKNOWN_COMMAND on purpose: the operation is real in
        # Live's UI but has no supported entry point in the public LOM or the
        # Extension SDK, so no amount of bridge work will make it available.
        # The request is still validated against the real Set first, and no
        # undo step is opened because nothing is ever written.
        return cmd_unavailable_capability(song, application, {**params, "__command": normalized})
    if not isinstance(params, dict):
        raise RemoteError(ERROR_INVALID_PARAMS, "Request params must be an object.")
    if normalized == "run_batch":
        admission_error = _admit_batch(song, params)
        if admission_error is not None:
            return admission_error
        # Keep the exact admission result stable through the dispatch layer;
        # the batch implementation must not evaluate a precondition twice.
        params = {**params, "__preconditions_admitted": True}
    dry_run_only = _is_dry_run_only(normalized, params)
    owns_undo = normalized in ALLOWED_MUTATIONS and manage_undo and not dry_run_only
    if owns_undo:
        _begin_undo(undo_target)
    try:
        return (
            yield from _dispatch_command_steps(
                song,
                application,
                normalized,
                params,
                undo_target,
                control_surface,
            )
        )
    finally:
        if owns_undo:
            _end_undo(undo_target)


def _batch_commands_are_dry_run_only(commands: list[Any]) -> bool:
    for command in commands:
        if not isinstance(command, dict):
            return False
        if command.get("type") not in ("set_tempo", "create_clip"):
            return False
        command_params = command.get("params", {})
        if not isinstance(command_params, dict) or command_params.get("dry_run") is not True:
            return False
    return True


def _is_dry_run_only(normalized: str, params: dict[str, Any]) -> bool:
    if normalized in ("set_tempo", "create_clip"):
        dry_run = params.get("dry_run", False)
        if not isinstance(dry_run, bool):
            raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'dry_run' must be boolean.")
        return dry_run
    if normalized != "run_batch":
        return False

    commands = params.get("commands")
    if not isinstance(commands, list) or not commands:
        return False
    return _batch_commands_are_dry_run_only(commands)


def execute_command(
    song: Any,
    application: Any,
    command: str,
    params: dict[str, Any],
    *,
    manage_undo: bool = True,
    undo_target: Any = None,
) -> Any:
    """Synchronously drive a command for unit tests and immediate host callers."""

    target = undo_target if undo_target is not None else application
    steps = _command_steps(
        song,
        application,
        command,
        params,
        manage_undo=manage_undo,
        undo_target=target,
    )
    while True:
        try:
            next(steps)
        except StopIteration as completed:
            return completed.value


def _request_steps(
    song: Any,
    application: Any,
    command: str,
    params: dict[str, Any],
    undo_target: Any,
    control_surface: Any = None,
) -> Generator[None, None, Any]:
    """Build one request execution that may span multiple Live UI ticks."""

    return (
        yield from _command_steps(
            song,
            application,
            command,
            params,
            manage_undo=True,
            undo_target=undo_target,
            control_surface=control_surface,
        )
    )
