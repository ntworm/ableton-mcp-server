"""Clip automation envelope reads and writes."""

from __future__ import annotations

import math
import re
from collections.abc import Generator
from typing import Any

from ._contracts import (
    ERROR_AMBIGUOUS_MATCH,
    ERROR_BAD_INPUT,
    ERROR_INVALID_PARAMS,
    ERROR_LIVE_UNAVAILABLE,
    ERROR_WRONG_TYPE,
)
from .common import (
    RemoteError,
    _float_param,
    _integer_param,
    _optional_float,
    _required,
    _safe,
    _string_param,
)
from .lom import _chain_at, _clip_slot, _track_at


def _clip_automation_absent(
    track_index: int, clip_index: int, parameter: Any, parameter_name: str
) -> dict[str, Any]:
    """Report a clip that exposes no envelope for the parameter."""
    return {
        "track_index": track_index,
        "clip_index": clip_index,
        "parameter_name": str(_safe(lambda: parameter.name, parameter_name)),
        "has_envelope": False,
        "samples": [],
    }


def _clip_automation_samples(
    clip: Any, value_at_time: Any, resolution: float
) -> list[dict[str, Any]]:
    """Sample the envelope curve of one clip at the requested resolution."""
    length = float(_safe(lambda: clip.length, 0.0) or 0.0)
    samples = []
    time = 0.0
    while time < length - 1e-9 and len(samples) < 2000:
        samples.append({"time": round(time, 4), "value": _optional_float(value_at_time(time))})
        time += resolution
    return samples


def _clip_automation_envelope_result(
    track_index: int,
    clip_index: int,
    parameter: Any,
    parameter_name: str,
    resolution: float,
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the readback of a clip envelope that exists."""
    values = [item["value"] for item in samples if item["value"] is not None]
    return {
        "track_index": track_index,
        "clip_index": clip_index,
        "parameter_name": str(_safe(lambda: parameter.name, parameter_name)),
        "has_envelope": True,
        "resolution": resolution,
        "sample_count": len(samples),
        "min_value": min(values) if values else None,
        "max_value": max(values) if values else None,
        "samples": samples,
    }


def cmd_get_clip_automation(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Sample one clip envelope so a caller can read back what it wrote.

    The LOM exposes no breakpoint list, only ``value_at_time``, so the envelope
    is reported as a sampled curve. That is what Live can actually answer; a
    caller comparing intent against reality gets the shape, not a promise.
    """

    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    parameter_name = _string_param(params, "parameter_name")
    device_index = params.get("device_index")
    resolution = float(params.get("resolution", 0.25))
    if resolution <= 0 or resolution > 16:
        raise RemoteError(ERROR_BAD_INPUT, "Parameter 'resolution' must be in (0, 16].")

    _track, slot = _clip_slot(song, track_index, clip_index)
    clip = _safe(lambda: slot.clip, None)
    if clip is None:
        raise RemoteError(ERROR_BAD_INPUT, "Session slot %s is empty." % clip_index)
    parameter = _automation_parameter(
        _track_at(song, track_index),
        parameter_name,
        device_index,
        params.get("chain_index"),
        params.get("chain_device_index"),
    )
    if parameter is None:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Parameter %r was not found on track %s." % (parameter_name, track_index),
        )
    envelope_getter = _safe(lambda: clip.automation_envelope, None)
    if not callable(envelope_getter):
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live runtime does not expose the clip automation envelope API.",
        )
    envelope = envelope_getter(parameter)
    if envelope is None:
        return _clip_automation_absent(track_index, clip_index, parameter, parameter_name)
    value_at_time = _safe(lambda: envelope.value_at_time, None)
    if not callable(value_at_time):
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live runtime does not expose value_at_time on the clip envelope.",
        )
    samples = _clip_automation_samples(clip, value_at_time, resolution)
    return _clip_automation_envelope_result(
        track_index, clip_index, parameter, parameter_name, resolution, samples
    )


def _expand_curve(
    control_points: list[tuple[float, float]],
    shape: str,
    resolution: float,
) -> list[tuple[float, float]]:
    """Densify control points into contiguous steps.

    Live's clip envelope only accepts steps, so a smooth ramp is a dense
    staircase. Expanding server-side is what keeps a caller from shipping
    hundreds of breakpoints over the wire for one crescendo.
    """

    expanded: list[tuple[float, float]] = []
    pairs = zip(control_points, control_points[1:], strict=False)
    for (time_a, value_a), (time_b, value_b) in pairs:
        span = time_b - time_a
        if span <= 0:
            continue
        if shape == "hold":
            expanded.append((time_a, value_a))
            continue
        steps = max(1, int(math.ceil(span / resolution)))
        for step in range(steps):
            progress = step / steps
            if shape == "exp":
                weight = progress**2.0
            elif shape == "log":
                weight = 1.0 - (1.0 - progress) ** 2.0
            else:
                weight = progress
            expanded.append((time_a + progress * span, value_a + (value_b - value_a) * weight))
    expanded.append(control_points[-1])
    deduped: list[tuple[float, float]] = []
    for point in expanded:
        if deduped and abs(point[0] - deduped[-1][0]) < 1e-6:
            deduped[-1] = point
            continue
        deduped.append(point)
    return deduped


def _create_clip_automation_curve_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    track_index = _integer_param(params, "track_index")
    _clip_index = _integer_param(params, "clip_index")
    _parameter_name = _string_param(params, "parameter_name")
    raw_points = _required(params, "control_points")
    shape = str(params.get("shape", "linear")).strip().lower()
    resolution = float(params.get("resolution", 0.25))
    if shape not in ("linear", "exp", "log", "hold"):
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Parameter 'shape' must be one of linear, exp, log, hold.",
        )
    if resolution <= 0 or resolution > 16:
        raise RemoteError(ERROR_BAD_INPUT, "Parameter 'resolution' must be in (0, 16].")
    if not isinstance(raw_points, list) or len(raw_points) < 2 or len(raw_points) > 200:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Parameter 'control_points' must hold between 2 and 200 points.",
        )
    control: list[tuple[float, float]] = []
    for raw_point in raw_points:
        if not isinstance(raw_point, dict):
            raise RemoteError(ERROR_INVALID_PARAMS, "Each control point must be an object.")
        control.append(
            (
                _float_param(raw_point, "time", 0.0, 100000.0),
                _float_param(raw_point, "value", -100000.0, 100000.0),
            )
        )
    control.sort(key=lambda item: item[0])
    expanded = _expand_curve(control, shape, resolution)
    if len(expanded) > 500:
        raise RemoteError(
            ERROR_BAD_INPUT,
            "The expansion produced %s steps; raise 'resolution' or shorten the span "
            "so it stays inside Live's 500-step envelope budget." % len(expanded),
        )
    forwarded = dict(params)
    forwarded["automation_points"] = [{"time": time, "value": value} for time, value in expanded]
    result = yield from _create_clip_automation_steps(song, forwarded)
    result["control_points"] = len(control)
    result["shape"] = shape
    result["resolution"] = resolution
    result["track_index"] = track_index
    return result


def _automation_mixer_parameter(track: Any, normalized: str) -> tuple[bool, Any]:
    """Return ``(True, value)`` for a mixer name and ``(False, None)`` otherwise."""
    mixer = _safe(lambda: track.mixer_device, None)
    if normalized == "volume":
        return True, _safe(lambda: mixer.volume, None)
    if normalized in ("pan", "panning"):
        return True, _safe(lambda: mixer.panning, None)
    send_match = re.fullmatch(r"send_([a-h])", normalized)
    if send_match is not None:
        index = ord(send_match.group(1)) - ord("a")
        sends = list(_safe(lambda: mixer.sends, []))
        return True, sends[index] if index < len(sends) else None
    return False, None


def _automation_device_index(devices: list[Any], device_index: Any) -> int:
    """Check that a device index addresses one of the devices of the track."""
    if isinstance(device_index, bool) or not isinstance(device_index, int):
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'device_index' must be an integer.")
    if device_index < 0 or device_index >= len(devices):
        raise RemoteError(
            ERROR_INVALID_PARAMS, "Device index %s does not exist." % device_index
        )
    return device_index


def _automation_chain_mixer(chain: Any, parameter_name: str) -> Any:
    """Resolve a mixer parameter of a device chain."""
    mixer = _safe(lambda: chain.mixer_device, None)
    alias = {"volume": "volume", "pan": "panning", "panning": "panning"}.get(
        parameter_name.strip().casefold()
    )
    if mixer is None or alias is None:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "A chain mixer exposes 'volume' and 'panning'; pass "
            "'chain_device_index' to reach a device inside the chain.",
        )
    return _safe(lambda: getattr(mixer, alias), None)


def _automation_chain_device_parameter(inner_device: Any, parameter_name: str) -> Any:
    """Find the parameter on one device of a chain."""
    for parameter in _safe(lambda: inner_device.parameters, []):
        if str(_safe(lambda parameter=parameter: parameter.name, "")) == parameter_name:
            return parameter
    return None


def _automation_chain_parameter(
    devices: list[Any],
    parameter_name: str,
    device_index: Any,
    chain_index: Any,
    chain_device_index: Any,
) -> Any:
    """Resolve a parameter of a device chain: its mixer or one of its devices."""
    if device_index is None:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Addressing a chain parameter needs 'device_index' as well as 'chain_index'.",
        )
    device_index = _automation_device_index(devices, device_index)
    chain = _chain_at(devices[device_index], chain_index, -1, device_index)
    if chain_device_index is None:
        return _automation_chain_mixer(chain, parameter_name)
    inner_devices = list(_safe(lambda: chain.devices, []))
    if (
        isinstance(chain_device_index, bool)
        or not isinstance(chain_device_index, int)
        or chain_device_index < 0
        or chain_device_index >= len(inner_devices)
    ):
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Chain device %s does not exist in chain %s."
            % (chain_device_index, chain_index),
        )
    return _automation_chain_device_parameter(inner_devices[chain_device_index], parameter_name)


def _automation_device_matches(
    devices: list[Any], parameter_name: str, device_index: Any
) -> list[tuple[int, Any]]:
    """Collect the devices of the track that expose the parameter."""
    matches = []
    for position, device in enumerate(devices):
        for parameter in _safe(lambda device=device: device.parameters, []):
            if str(_safe(lambda parameter=parameter: parameter.name, "")) == parameter_name:
                matches.append((position if device_index is None else device_index, parameter))
    return matches


def _automation_match(matches: list[tuple[int, Any]], parameter_name: str) -> Any:
    """Return the only match of a parameter name or name the candidates."""
    if not matches:
        return None
    if len(matches) > 1:
        # Silently taking the first match is how an envelope lands on the wrong
        # rack: "Macro 1" exists on every rack of a track. Name the candidates
        # and let the caller disambiguate with device_index.
        raise RemoteError(
            ERROR_AMBIGUOUS_MATCH,
            "Parameter %r exists on devices %s of this track. Pass 'device_index' "
            "to choose one." % (parameter_name, [position for position, _ in matches]),
            details={"candidates": [position for position, _ in matches]},
        )
    return matches[0][1]


def _automation_parameter(
    track: Any,
    parameter_name: str,
    device_index: Any = None,
    chain_index: Any = None,
    chain_device_index: Any = None,
) -> Any:
    normalized = parameter_name.casefold().replace(" ", "_")
    handled, mixer_parameter = _automation_mixer_parameter(track, normalized)
    if handled:
        return mixer_parameter
    devices = list(_safe(lambda: track.devices, []))
    if chain_index is not None:
        return _automation_chain_parameter(
            devices, parameter_name, device_index, chain_index, chain_device_index
        )
    if device_index is not None:
        device_index = _automation_device_index(devices, device_index)
        devices = [devices[device_index]]
    matches = _automation_device_matches(devices, parameter_name, device_index)
    return _automation_match(matches, parameter_name)


def _clip_automation_raw_points(raw_points: Any) -> list[Any]:
    """Check the automation points of a request before the clip is touched."""
    if not isinstance(raw_points, list) or not raw_points or len(raw_points) > 500:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "automation_points must contain between 1 and 500 points.",
        )
    return raw_points


def _clip_automation_points(
    raw_points: list[Any], minimum: float, maximum: float, parameter_name: str
) -> list[tuple[float, float]]:
    """Read and check the automation points that are written to one envelope."""
    points: list[tuple[float, float]] = []
    for raw_point in raw_points:
        if not isinstance(raw_point, dict):
            raise RemoteError(ERROR_INVALID_PARAMS, "Each automation point must be an object.")
        point_time = _float_param(raw_point, "time", 0.0, 100000.0)
        value = _float_param(raw_point, "value", -1000000.0, 1000000.0)
        if value < minimum or value > maximum:
            raise RemoteError(
                ERROR_INVALID_PARAMS,
                "Automation value %s is outside [%s, %s] for parameter %r."
                % (value, minimum, maximum, parameter_name),
            )
        points.append((point_time, value))
    points.sort(key=lambda point: point[0])
    return points


def _clip_automation_envelope(clip: Any, parameter: Any) -> Any:
    """Clear the envelope of a clip and read or create the envelope of a parameter."""
    envelope_getter = _safe(lambda: clip.automation_envelope, None)
    envelope_creator = _safe(lambda: clip.create_automation_envelope, None)
    clear_envelope = _safe(lambda: clip.clear_envelope, None)
    if (not callable(envelope_getter) and not callable(envelope_creator)) or not callable(
        clear_envelope
    ):
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live runtime does not expose the clip automation envelope API.",
        )
    clear_envelope(parameter)
    envelope = None
    if callable(envelope_getter):
        envelope = envelope_getter(parameter)
    if envelope is None and callable(envelope_creator):
        envelope = envelope_creator(parameter)
    if envelope is None:
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live runtime failed to retrieve or create the clip automation envelope.",
        )
    return envelope


def _clip_automation_insert_steps(envelope: Any, points: list[tuple[float, float]]) -> None:
    """Write the automation steps of one envelope."""
    insert_step = _safe(lambda: envelope.insert_step, None)
    if not callable(insert_step):
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live runtime does not expose automation envelope insertion.",
        )
    for index, (point_time, value) in enumerate(points):
        # A zero-length step writes a value that occupies no time, so the
        # envelope falls back to the parameter value between breakpoints and
        # the curve reads as a comb of spikes. Each step has to reach the next
        # breakpoint for the envelope to be continuous; the last one keeps the
        # zero length because there is nothing after it to cover.
        duration = points[index + 1][0] - point_time if index + 1 < len(points) else 0.0
        insert_step(point_time, duration, value)


def _create_clip_automation_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    parameter_name = _string_param(params, "parameter_name")
    raw_points = _clip_automation_raw_points(_required(params, "automation_points"))
    track, slot = _clip_slot(song, track_index, clip_index)
    clip = _safe(lambda: slot.clip, None)
    if clip is None:
        raise RemoteError(ERROR_BAD_INPUT, "Clip slot is empty.")
    if not bool(_safe(lambda: clip.is_session_clip, True)):
        raise RemoteError(ERROR_WRONG_TYPE, "Automation is limited to Session clips.")
    parameter = _automation_parameter(
        track,
        parameter_name,
        params.get("device_index"),
        params.get("chain_index"),
        params.get("chain_device_index"),
    )
    if parameter is None:
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter %r was not found." % parameter_name)
    if not bool(_safe(lambda: parameter.is_enabled, True)):
        raise RemoteError(ERROR_WRONG_TYPE, "Parameter %r is disabled." % parameter_name)
    minimum = float(_safe(lambda: parameter.min, 0.0))
    maximum = float(_safe(lambda: parameter.max, 1.0))
    points = _clip_automation_points(raw_points, minimum, maximum, parameter_name)
    envelope = _clip_automation_envelope(clip, parameter)
    _clip_automation_insert_steps(envelope, points)
    yield
    if not bool(_safe(lambda: clip.has_envelopes, False)):
        raise RemoteError(ERROR_LIVE_UNAVAILABLE, "Clip automation write was not observed.")
    return {
        "parameter_name": str(_safe(lambda: parameter.name, parameter_name)),
        "points_written": len(points),
        "times": [point_time for point_time, _value in points],
        "clip_id": "track:%s/clipslot:%s/clip" % (track_index, clip_index),
    }
