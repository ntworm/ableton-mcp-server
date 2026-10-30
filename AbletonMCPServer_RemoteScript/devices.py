"""Device parameter reads and writes, and plugin preset selection."""

from __future__ import annotations

import difflib
from collections.abc import Generator
from typing import Any

from ._contracts import (
    ERROR_AMBIGUOUS_MATCH,
    ERROR_CAPABILITY_UNAVAILABLE,
    ERROR_INTERNAL_ERROR,
    ERROR_INVALID_PARAMS,
    ERROR_VERIFICATION_FAILED,
    ERROR_WRONG_TYPE,
    PLUGIN_NOT_CONFIGURED,
    PLUGIN_NOT_CONFIGURED_HINT,
    is_plugin_device_class,
)
from .common import RemoteError, _float_param, _integer_param, _safe, _string_param
from .lom import (
    _capture_parameter,
    _chain_at,
    _configured_parameter_count,
    _device_at,
    _plugin_state,
    _resolve_track_id,
)


def _missing_parameter_error(device: Any, parameter_name: str, names: list[str]) -> RemoteError:
    """Build the INVALID_PARAMS envelope for an unresolved parameter name.

    On a plugin whose Configure list is empty the close-match suggestion has
    nothing to work with, so the envelope carries the Configure explanation
    instead of a bare "not found" the caller cannot act on.
    """

    suggestions = difflib.get_close_matches(parameter_name, names, n=3, cutoff=0.5)
    suffix = " Did you mean: %s?" % ", ".join(suggestions) if suggestions else ""
    class_name = str(_safe(lambda: device.class_name, ""))
    if is_plugin_device_class(class_name) and not _configured_parameter_count(
        [{"name": name} for name in names]
    ):
        return RemoteError(
            ERROR_INVALID_PARAMS,
            "Parameter %r was not found: plugin %r exposes no configured parameters."
            % (parameter_name, str(_safe(lambda: device.name, ""))),
            hint=PLUGIN_NOT_CONFIGURED_HINT,
            details={"hint_code": PLUGIN_NOT_CONFIGURED, "class_name": class_name},
        )
    return RemoteError(
        ERROR_INVALID_PARAMS,
        "Parameter %r was not found.%s" % (parameter_name, suffix),
    )


def cmd_get_parameter_value(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    track_index = _integer_param(params, "track_index")
    device_index = _integer_param(params, "device_index")
    parameter_name = _string_param(params, "parameter_name")
    chain_index = params.get("chain_index")
    chain_device_index = params.get("chain_device_index")
    _track, parameter, path_id = _resolve_device_parameter(
        song, track_index, device_index, parameter_name, chain_index, chain_device_index
    )
    return _capture_parameter(parameter, path_id)


def _plugin_device_at(song: Any, track_index: int, device_index: int) -> tuple[Any, Any]:
    """Resolve a device and refuse when it is not a plugin wrapper."""

    track, device = _device_at(song, track_index, device_index)
    class_name = str(_safe(lambda: device.class_name, ""))
    if not is_plugin_device_class(class_name):
        raise RemoteError(
            ERROR_WRONG_TYPE,
            "Device %s on track %s is %r, not a plugin; presets are a "
            "PluginDevice capability." % (device_index, track_index, class_name),
        )
    return track, device


def _plugin_presets(device: Any) -> list[str]:
    return [str(preset) for preset in _safe(lambda: device.presets, []) or []]


def cmd_get_plugin_presets(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    track_index = _integer_param(params, "track_index")
    device_index = _integer_param(params, "device_index")
    track, device = _plugin_device_at(song, track_index, device_index)
    presets = _plugin_presets(device)
    selected = _safe(lambda: device.selected_preset_index, None)
    parameters = [
        {"name": str(_safe(lambda parameter=parameter: parameter.name, ""))}
        for parameter in _safe(lambda: device.parameters, [])
    ]
    result: dict[str, Any] = {
        "id": "track:%s/device:%s" % (track_index, device_index),
        "track_index": track_index,
        "device_index": device_index,
        "track_name": str(_safe(lambda: track.name, "")),
        "device_name": str(_safe(lambda: device.name, "")),
        "class_name": str(_safe(lambda: device.class_name, "")),
        "presets": presets,
        "preset_count": len(presets),
        "selected_preset_index": int(selected) if isinstance(selected, int) else None,
    }
    plugin_state = _plugin_state(result["class_name"], parameters)
    if plugin_state is not None:
        result["plugin_state"] = plugin_state
    return result


def _resolve_preset_index(device: Any, presets: list[str], params: dict[str, Any]) -> int:
    """Resolve ``preset_index`` or ``preset_name`` to one in-range index."""

    has_index = params.get("preset_index") is not None
    has_name = params.get("preset_name") is not None
    if has_index == has_name:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Provide exactly one of 'preset_index' or 'preset_name'.",
        )
    if not presets:
        raise RemoteError(
            ERROR_CAPABILITY_UNAVAILABLE,
            "Plugin %r exposes no presets through the Live Object Model."
            % str(_safe(lambda: device.name, "")),
        )
    if has_index:
        index = _integer_param(params, "preset_index")
        if index < 0 or index >= len(presets):
            raise RemoteError(
                ERROR_INVALID_PARAMS,
                "Preset index %s is outside [0, %s]." % (index, len(presets) - 1),
            )
        return index
    name = _string_param(params, "preset_name")
    matches = [index for index, preset in enumerate(presets) if preset == name]
    if not matches:
        suggestions = difflib.get_close_matches(name, presets, n=3, cutoff=0.5)
        suffix = " Did you mean: %s?" % ", ".join(suggestions) if suggestions else ""
        raise RemoteError(ERROR_INVALID_PARAMS, "Preset %r was not found.%s" % (name, suffix))
    if len(matches) > 1:
        raise RemoteError(
            ERROR_AMBIGUOUS_MATCH,
            "Preset name %r matches %s presets; use 'preset_index'." % (name, len(matches)),
        )
    return matches[0]


def _set_plugin_preset_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    track_index = _integer_param(params, "track_index")
    device_index = _integer_param(params, "device_index")
    track, device = _plugin_device_at(song, track_index, device_index)
    presets = _plugin_presets(device)
    target = _resolve_preset_index(device, presets, params)
    previous = _safe(lambda: device.selected_preset_index, None)

    observed: Any = previous
    for _attempt in range(2):
        device.selected_preset_index = target
        yield
        observed = _safe(lambda: device.selected_preset_index, None)
        if isinstance(observed, int) and observed == target:
            return {
                "id": "track:%s/device:%s" % (track_index, device_index),
                "selected_preset_index": target,
                "preset_name": presets[target],
                "previous_preset_index": int(previous) if isinstance(previous, int) else None,
                "preset_count": len(presets),
                "resolved": {
                    "kind": "device",
                    "track_index": track_index,
                    "device_index": device_index,
                    "track_name": str(_safe(lambda: track.name, "")),
                    "device_name": str(_safe(lambda: device.name, "")),
                },
            }
    raise RemoteError(
        ERROR_VERIFICATION_FAILED,
        "Plugin preset did not change: requested %s, observed %r." % (target, observed),
    )


def _chain_mixer_parameter(
    chain: Any, base_id: str, chain_index: int, parameter_name: str
) -> tuple[Any, str]:
    """Resolve a chain mixer's own volume or panning control.

    A chain blends its members through its mixer, so the mixer's controls are
    the ones a rack exposes without naming a device inside the chain.
    """

    mixer = _safe(lambda: chain.mixer_device, None)
    normalized = parameter_name.strip().casefold()
    alias = {"volume": "volume", "pan": "panning", "panning": "panning"}.get(normalized)
    if mixer is None or alias is None:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "A chain mixer exposes 'volume' and 'panning'; pass "
            "'chain_device_index' to reach a device inside the chain.",
        )
    parameter = _safe(lambda: getattr(mixer, alias), None)
    if parameter is None:
        raise RemoteError(
            ERROR_CAPABILITY_UNAVAILABLE,
            "This chain does not expose %r on its mixer." % alias,
        )
    return parameter, "%s/chain:%s/mixer:%s" % (base_id, chain_index, alias)


def _chain_device_owner(chain: Any, chain_index: int, chain_device_index: int) -> Any:
    """Return the device at ``chain_device_index`` inside ``chain``."""

    devices = list(_safe(lambda: chain.devices, []))
    if chain_device_index < 0 or chain_device_index >= len(devices):
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Chain device %s does not exist in chain %s."
            % (chain_device_index, chain_index),
        )
    return devices[chain_device_index]


def _named_parameter(parameters: list[Any], parameter_name: str) -> Any:
    """Return the parameter called ``parameter_name``, or None when there is none."""

    return next(
        (
            item
            for item in parameters
            if str(_safe(lambda item=item: item.name, "")) == parameter_name
        ),
        None,
    )


def _resolve_device_parameter(
    song: Any,
    track_index: int,
    device_index: int,
    parameter_name: str,
    chain_index: Any = None,
    chain_device_index: Any = None,
) -> tuple[Any, Any, str]:
    """Resolve a parameter at top level, inside a chain, or on a chain's mixer.

    Live nests the controls that matter: the Velocity device that caps a drum
    track and the volume that balances one guitar articulation against another
    both live inside rack chains, where a top-level lookup cannot reach them.
    """

    track, device = _device_at(song, track_index, device_index)
    base_id = "track:%s/device:%s" % (track_index, device_index)
    if chain_index is None:
        parameters = list(_safe(lambda: device.parameters, []))
        owner = device
    else:
        if isinstance(chain_index, bool) or not isinstance(chain_index, int):
            raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'chain_index' must be an integer.")
        chain = _chain_at(device, chain_index, track_index, device_index)
        if chain_device_index is None:
            # No inner device named: the target is the chain's own mixer, which
            # is how a rack blends its chains.
            parameter, path_id = _chain_mixer_parameter(
                chain, base_id, chain_index, parameter_name
            )
            return track, parameter, path_id
        if isinstance(chain_device_index, bool) or not isinstance(chain_device_index, int):
            raise RemoteError(
                ERROR_INVALID_PARAMS, "Parameter 'chain_device_index' must be an integer."
            )
        owner = _chain_device_owner(chain, chain_index, chain_device_index)
        parameters = list(_safe(lambda: owner.parameters, []))
        base_id = "%s/chain:%s/device:%s" % (base_id, chain_index, chain_device_index)
    parameter = _named_parameter(parameters, parameter_name)
    if parameter is None:
        names = [str(_safe(lambda item=item: item.name, "")) for item in parameters]
        raise _missing_parameter_error(owner, parameter_name, names)
    return track, parameter, "%s/param:%s" % (base_id, parameters.index(parameter))


def _resolved_parameter(
    track: Any,
    device: Any,
    track_index: int,
    device_index: int,
    parameter_name: str,
    chain_index: Any,
    chain_device_index: Any,
) -> dict[str, Any]:
    """Say which parameter a write landed on, and where that parameter lives."""

    resolved: dict[str, Any] = {
        "kind": "device",
        "track_index": track_index,
        "device_index": device_index,
        "parameter_name": parameter_name,
    }
    if chain_index is not None:
        resolved["chain_index"] = chain_index
    if chain_device_index is not None:
        resolved["chain_device_index"] = chain_device_index
    track_name = str(_safe(lambda: track.name, ""))
    device_name = str(_safe(lambda: device.name, ""))
    if track_name:
        resolved["track_name"] = track_name
    if device_name:
        resolved["device_name"] = device_name
    return resolved


def _set_parameter_value_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    track_index = _integer_param(params, "track_index")
    device_index = _integer_param(params, "device_index")
    parameter_name = _string_param(params, "parameter_name")
    requested = _float_param(params, "value", -1000000.0, 1000000.0)
    chain_index = params.get("chain_index")
    chain_device_index = params.get("chain_device_index")
    track, parameter, _path_id = _resolve_device_parameter(
        song,
        track_index,
        device_index,
        parameter_name,
        chain_index,
        chain_device_index,
    )
    _track_for_name, device = _device_at(song, track_index, device_index)
    if not bool(_safe(lambda: parameter.is_enabled, True)):
        raise RemoteError(ERROR_WRONG_TYPE, "Parameter %r is disabled." % parameter_name)
    minimum = float(_safe(lambda: parameter.min, 0.0))
    maximum = float(_safe(lambda: parameter.max, 1.0))
    if requested < minimum or requested > maximum:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Value %s is outside [%s, %s] for parameter %r."
            % (requested, minimum, maximum, parameter_name),
        )
    is_quantized = bool(_safe(lambda: parameter.is_quantized, False))
    observed = float(_safe(lambda: parameter.value, minimum))
    for _attempt in range(2):
        parameter.value = requested
        yield
        observed = float(parameter.value)
        if is_quantized or abs(observed - requested) < 1e-6:
            resolved = _resolved_parameter(
                track,
                device,
                track_index,
                device_index,
                parameter_name,
                chain_index,
                chain_device_index,
            )
            return {
                "target": requested,
                "value": observed,
                "is_quantized": is_quantized,
                "resolved": resolved,
            }
    raise RemoteError(
        ERROR_INTERNAL_ERROR,
        "Parameter %r did not converge: target=%s observed=%s delta=%s."
        % (parameter_name, requested, observed, abs(observed - requested)),
    )


def cmd_list_device_params(
    song: Any, _application: Any, params: dict[str, Any]
) -> list[dict[str, Any]]:
    track_id = _string_param(params, "track_id")
    track_index, track = _resolve_track_id(song, track_id)
    entries = []
    for device_index, device in enumerate(_safe(lambda: track.devices, [])):
        parameters = [
            _capture_parameter(
                parameter,
                "track:%s/device:%s/param:%s" % (track_index, device_index, parameter_index),
            )
            for parameter_index, parameter in enumerate(
                _safe(lambda device=device: device.parameters, [])
            )
        ]
        class_name = str(_safe(lambda device=device: device.class_name, ""))
        entry: dict[str, Any] = {
            "device_id": "track:%s/device:%s" % (track_index, device_index),
            "device_name": str(_safe(lambda device=device: device.name, "")),
            "parameters": parameters,
        }
        plugin_state = _plugin_state(class_name, parameters)
        if plugin_state is not None:
            entry["plugin_state"] = plugin_state
        entries.append(entry)
    return entries
