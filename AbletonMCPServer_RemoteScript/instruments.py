"""Device chain, MIDI effect chain and instrument reports."""

from __future__ import annotations

from typing import Any

from ._contracts import ERROR_WRONG_TYPE, is_plugin_device_class
from .common import RemoteError, _integer_param, _optional_float, _safe
from .lom import _configured_parameter_count, _device_at, _track_at

# ---------------------------------------------------------------------------
# v0.5.6 — Instrument comprehension and authoring shorthands
# ---------------------------------------------------------------------------
_MIDI_EFFECT_CONSEQUENCES = {
    "MidiVelocity": (
        "Rewrites incoming velocity. 'Out Low' and 'Out Hi' are the real "
        "dynamic floor and ceiling of this track, whatever the clip says."
    ),
    "MidiNoteLength": (
        "Overrides note duration. With 'Sync On' off the length comes from "
        "'Time Length'; 'Gate' only acts in synced mode."
    ),
    "MidiPitcher": "Transposes every note; the clip's written pitches are not what sounds.",
    "MidiArpeggiator": (
        "Generates its own note stream from held notes; written rhythm is a source, not the result."
    ),
    "MidiChord": "Adds intervals to every note, so one written note sounds as a chord.",
    "MidiScale": "Snaps pitches to a scale; out-of-scale notes are moved, not refused.",
    "MidiRandom": "Randomises pitch, so exact written pitches are not guaranteed.",
}

_INSTRUMENT_CLASSES = (
    "InstrumentGroupDevice",
    "PluginDevice",
    "InstrumentVector",
    "MultiSampler",
    "SimplerDevice",
    "Operator",
    "InstrumentImpulse",
    "DrumGroupDevice",
    "UltraAnalog",
    "Collision",
    "Tension",
    "Electric",
    "Wavetable",
)


def _chain_mixer_state(chain: Any) -> dict[str, Any]:
    mixer = _safe(lambda: chain.mixer_device, None)
    volume = _safe(lambda: mixer.volume, None) if mixer is not None else None
    panning = _safe(lambda: mixer.panning, None) if mixer is not None else None
    return {
        "volume": _optional_float(_safe(lambda: volume.value, None)),
        "volume_min": _optional_float(_safe(lambda: volume.min, None)),
        "volume_max": _optional_float(_safe(lambda: volume.max, None)),
        "panning": _optional_float(_safe(lambda: panning.value, None)),
        "muted": bool(_safe(lambda: chain.mute, False)),
        "soloed": bool(_safe(lambda: chain.solo, False)),
    }


def cmd_get_device_chains(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Open one rack: its chains, their mixer state and the devices inside.

    ``get_device_list`` stops at the top level, so a rack reads as a wall of
    macros. What actually shapes the sound — the sampler in chain three, the
    Velocity device hidden in a MIDI rack — only appears here.
    """

    track_index = _integer_param(params, "track_index")
    device_index = _integer_param(params, "device_index")
    _track, device = _device_at(song, track_index, device_index)
    chains = _safe(lambda: device.chains, None)
    if chains is None:
        raise RemoteError(
            ERROR_WRONG_TYPE,
            "Device %s on track %s is not a rack; it exposes no chains."
            % (device_index, track_index),
        )
    captured = []
    for chain_index, chain in enumerate(list(chains)):
        devices = []
        for inner_index, inner in enumerate(list(_safe(lambda chain=chain: chain.devices, []))):
            parameters = list(_safe(lambda inner=inner: inner.parameters, []))
            devices.append(
                {
                    "id": "track:%s/device:%s/chain:%s/device:%s"
                    % (track_index, device_index, chain_index, inner_index),
                    "chain_index": chain_index,
                    "device_index": inner_index,
                    "name": str(_safe(lambda inner=inner: inner.name, "")),
                    "class_name": str(_safe(lambda inner=inner: inner.class_name, "")),
                    "is_active": bool(_safe(lambda inner=inner: inner.is_active, True)),
                    "parameter_count": len(parameters),
                    "parameter_names": [
                        str(_safe(lambda parameter=parameter: parameter.name, ""))
                        for parameter in parameters[:24]
                    ],
                }
            )
        captured.append(
            {
                "id": "track:%s/device:%s/chain:%s" % (track_index, device_index, chain_index),
                "chain_index": chain_index,
                "name": str(_safe(lambda chain=chain: chain.name, "")),
                "devices": devices,
                **_chain_mixer_state(chain),
            }
        )
    return {
        "track_index": track_index,
        "device_index": device_index,
        "device_name": str(_safe(lambda: device.name, "")),
        "chain_count": len(captured),
        "chains": captured,
    }


def _midi_effect_finding(device: Any, path: str, device_index: int) -> dict[str, Any] | None:
    class_name = str(_safe(lambda: device.class_name, ""))
    consequence = _MIDI_EFFECT_CONSEQUENCES.get(class_name)
    if consequence is None:
        return None
    values = {}
    for parameter in list(_safe(lambda: device.parameters, [])):
        name = str(_safe(lambda parameter=parameter: parameter.name, ""))
        values[name] = _optional_float(_safe(lambda parameter=parameter: parameter.value, None))
    return {
        "path": path,
        "device_index": device_index,
        "name": str(_safe(lambda: device.name, "")),
        "class_name": class_name,
        "is_active": bool(_safe(lambda: device.is_active, True)),
        "consequence": consequence,
        "values": values,
    }


def cmd_get_midi_chain_report(
    song: Any, _application: Any, params: dict[str, Any]
) -> dict[str, Any]:
    """Report the MIDI effects that rewrite what a clip says, before writing one.

    Racks are walked, not just listed: the Velocity device that caps a drum
    track's dynamics usually sits inside a MIDI Effect Rack chain, where a
    top-level scan cannot see it.
    """

    track_index = _integer_param(params, "track_index")
    track = _track_at(song, track_index)
    findings: list[dict[str, Any]] = []
    for device_index, device in enumerate(list(_safe(lambda: track.devices, []))):
        path = "track:%s/device:%s" % (track_index, device_index)
        finding = _midi_effect_finding(device, path, device_index)
        if finding is not None:
            findings.append(finding)
        chains = list(_safe(lambda device=device: device.chains, []) or [])
        for chain_index, chain in enumerate(chains):
            for inner_index, inner in enumerate(
                list(_safe(lambda chain=chain: chain.devices, []))
            ):
                inner_path = "%s/chain:%s/device:%s" % (path, chain_index, inner_index)
                inner_finding = _midi_effect_finding(inner, inner_path, device_index)
                if inner_finding is not None:
                    inner_finding["chain_index"] = chain_index
                    inner_finding["chain_name"] = str(_safe(lambda chain=chain: chain.name, ""))
                    findings.append(inner_finding)
    return {
        "track_index": track_index,
        "rewrites_input": bool(findings),
        "devices": findings,
    }


def _instrument_device(track: Any) -> tuple[Any, int] | None:
    """Find the track's instrument device and the index it sits at."""

    for device_index, device in enumerate(list(_safe(lambda: track.devices, []))):
        class_name = str(_safe(lambda device=device: device.class_name, ""))
        drum_capable = bool(_safe(lambda device=device: device.can_have_drum_pads, False))
        if class_name in _INSTRUMENT_CLASSES or drum_capable:
            return device, device_index
    return None


def _setup_requests(is_plugin: bool, configured: int, named: list[str]) -> list[str]:
    """State what the user must still set up on this instrument."""

    setup_requests: list[str] = []
    if is_plugin and not configured:
        setup_requests.append(
            "This plugin exposes no automatable parameter. In Live, open the "
            "device, press Configure, move the controls an agent should drive, "
            "then leave Configure."
        )
    macros = [name for name in named if name.startswith("Macro ")]
    if len(macros) >= 8:
        setup_requests.append(
            "The rack's macros still carry default names. Map each macro to the "
            "parameter it should drive and rename it: a unique name is what "
            "lets an agent address it without ambiguity."
        )
    return setup_requests


def cmd_describe_instrument(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Describe a track's instrument and state what the user must still set up.

    An agent cannot control what it cannot address. When a plugin exposes no
    configured parameter, or a rack's macros are unmapped and unnamed, the fix
    belongs to the user inside Live — so the answer carries the request to
    make, not only the gap.
    """

    track_index = _integer_param(params, "track_index")
    track = _track_at(song, track_index)
    found = _instrument_device(track)
    if found is None:
        return {
            "track_index": track_index,
            "has_instrument": False,
            "setup_requests": [
                "This track has no instrument device; load one before writing notes."
            ],
        }

    instrument, instrument_index = found
    class_name = str(_safe(lambda: instrument.class_name, ""))
    parameters = list(_safe(lambda: instrument.parameters, []))
    captured = [
        {
            "name": str(_safe(lambda parameter=parameter: parameter.name, "")),
            "value": _optional_float(_safe(lambda parameter=parameter: parameter.value, None)),
            "min": _optional_float(_safe(lambda parameter=parameter: parameter.min, None)),
            "max": _optional_float(_safe(lambda parameter=parameter: parameter.max, None)),
            "quantized": bool(_safe(lambda parameter=parameter: parameter.is_quantized, False)),
        }
        for parameter in parameters
    ]
    named = [item["name"] for item in captured]
    is_plugin = is_plugin_device_class(class_name)
    configured = _configured_parameter_count([{"name": name} for name in named])
    setup_requests = _setup_requests(is_plugin, configured, named)
    return {
        "track_index": track_index,
        "has_instrument": True,
        "device_index": instrument_index,
        "name": str(_safe(lambda: instrument.name, "")),
        "class_name": class_name,
        "is_plugin": is_plugin,
        "configured_parameter_count": configured,
        "parameter_count": len(captured),
        "parameters": captured,
        "setup_requests": setup_requests,
    }
