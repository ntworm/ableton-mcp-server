"""Bounded Standard MIDI File parsing and raw-deflate payload handling."""

from __future__ import annotations

import hashlib
import struct
import zlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from . import GrooveBlobRejected, GrooveMidiError
from .canonical import canonical_json, sha256_hex
from .constants import (
    MAX_COMPRESSED_BLOB,
    MAX_EVENTS,
    MAX_EXPANSION_RATIO,
    MAX_INPUT_BYTES,
    MAX_RAW_BLOB,
    MAX_TRACKS,
    RAW_BLOB_CODECS,
)
from .schema import (
    CompressedBlobV1,
    MidiEventV1,
    NoteEventV1,
    SmfFormatV1,
    TrackInfoV1,
)


@dataclass
class ParsedSmfV1:
    raw_bytes: bytes
    format: SmfFormatV1
    events: list[MidiEventV1]
    note_events: list[NoteEventV1]
    tracks: list[TrackInfoV1]
    source_events_digest: str
    length_ticks: int
    tempos: list[dict[str, int]]
    meters: list[dict[str, int]]


def _write_vlq(value: int) -> bytes:
    if value < 0 or value > 0x0FFFFFFF:
        raise GrooveMidiError("MIDI delta exceeds four-byte VLQ")
    encoded = bytearray([value & 0x7F])
    value >>= 7
    while value:
        encoded.insert(0, 0x80 | (value & 0x7F))
        value >>= 7
    return bytes(encoded)


def serialize_note_smf(
    notes: Sequence[NoteEventV1],
    *,
    ppq: int,
    length_ticks: int,
    meter: tuple[int, int] = (4, 2),
    tempos: Iterable[dict[str, int]] = (),
    track_names: dict[int, str] | None = None,
) -> bytes:
    """Build a small, canonical type-1 SMF from real note events.

    The writer is intentionally narrower than the lossless parser: generation
    emits only tempo/meter metadata and note tracks.  Parsing the returned bytes
    is therefore the authoritative source for all generated metadata.
    """

    if ppq <= 0 or ppq > 0x7FFF or length_ticks < 0:
        raise GrooveMidiError("PPQ and length must be positive")
    numerator, denominator_power = meter
    if numerator <= 0 or numerator > 0xFF or denominator_power < 0 or denominator_power > 7:
        raise GrooveMidiError("invalid MIDI meter")
    bounded_notes = [
        NoteEventV1(
            event_id=note.event_id,
            track_index=max(1, note.track_index),
            channel=note.channel,
            pitch=note.pitch,
            velocity=note.velocity,
            start_ticks=min(max(0, note.start_ticks), max(0, length_ticks - 1)),
            duration_ticks=max(1, min(note.duration_ticks, max(1, length_ticks))),
        )
        for note in notes
    ]
    last_track = max((note.track_index for note in bounded_notes), default=1)
    track_count = max(2, last_track + 1)

    tempo_rows = sorted(
        (
            max(0, int(row.get("absolute_ticks", 0))),
            max(1, min(0xFFFFFF, int(row.get("microseconds", 500_000)))),
        )
        for row in tempos
    )
    if not tempo_rows:
        tempo_rows = [(0, 500_000)]

    def chunk(body: bytes) -> bytes:
        return b"MTrk" + struct.pack(">I", len(body)) + body

    tempo_body = bytearray()
    previous = 0
    tempo_body.extend(_write_vlq(0))
    tempo_body.extend(b"\xff\x58\x04" + bytes((numerator, denominator_power, 24, 8)))
    for absolute, microseconds in tempo_rows:
        absolute = min(absolute, length_ticks)
        tempo_body.extend(_write_vlq(max(0, absolute - previous)))
        tempo_body.extend(b"\xff\x51\x03" + microseconds.to_bytes(3, "big"))
        previous = absolute
    tempo_body.extend(_write_vlq(max(0, length_ticks - previous)))
    tempo_body.extend(b"\xff\x2f\x00")
    tracks = [chunk(bytes(tempo_body))]

    by_track: dict[int, list[NoteEventV1]] = {index: [] for index in range(1, track_count)}
    for note in bounded_notes:
        by_track.setdefault(note.track_index, []).append(note)
    for track_index in range(1, track_count):
        events: list[tuple[int, int, bytes]] = []
        name = (track_names or {}).get(track_index, f"Generated {track_index}")
        name_bytes = name.encode("utf-8")[:127]
        events.append((0, -2, b"\xff\x03" + _write_vlq(len(name_bytes)) + name_bytes))
        for note in by_track.get(track_index, ()):
            start = min(max(0, note.start_ticks), max(0, length_ticks - 1))
            end = min(length_ticks, start + max(1, note.duration_ticks))
            on_status = 0x90 | note.channel
            off_status = 0x80 | note.channel
            events.append((start, 1, bytes((on_status, note.pitch, note.velocity))))
            events.append((end, 0, bytes((off_status, note.pitch, 0))))
        events.sort(key=lambda item: (item[0], item[1], item[2]))
        body = bytearray()
        previous = 0
        for absolute, _priority, payload in events:
            body.extend(_write_vlq(max(0, absolute - previous)))
            body.extend(payload)
            previous = absolute
        body.extend(_write_vlq(max(0, length_ticks - previous)) + b"\xff\x2f\x00")
        tracks.append(chunk(bytes(body)))

    header = b"MThd" + struct.pack(">IHHH", 6, 1, track_count, ppq)
    return header + b"".join(tracks)


def _read_vlq(data: memoryview, cursor: int, end: int) -> tuple[int, int]:
    value = 0
    for _count in range(4):
        if cursor >= end:
            raise GrooveMidiError("truncated VLQ")
        byte = data[cursor]
        cursor += 1
        value = (value << 7) | (byte & 0x7F)
        if byte < 0x80:
            return value, cursor
    raise GrooveMidiError("VLQ exceeds four bytes")


def _read_bytes(data: memoryview, cursor: int, size: int, end: int) -> tuple[bytes, int]:
    if size < 0 or cursor + size > end:
        raise GrooveMidiError("truncated MIDI event payload")
    return data[cursor : cursor + size].tobytes(), cursor + size


def parse_smf(payload: bytes) -> ParsedSmfV1:
    if len(payload) > MAX_INPUT_BYTES:
        raise GrooveMidiError("input size limit exceeded")
    if len(payload) < 14 or payload[:4] != b"MThd":
        raise GrooveMidiError("invalid MIDI header")
    header_length = struct.unpack_from(">I", payload, 4)[0]
    if header_length != 6 or len(payload) < 8 + header_length:
        raise GrooveMidiError("invalid MIDI header length")
    smf_type, track_count, division = struct.unpack_from(">HHH", payload, 8)
    if smf_type > 2:
        raise GrooveMidiError("unsupported MIDI format")
    if track_count > MAX_TRACKS:
        raise GrooveMidiError("track limit exceeded")
    if division & 0x8000:
        raise GrooveMidiError("SMPTE division is unsupported")
    if division == 0:
        raise GrooveMidiError("PPQ must be positive")

    memory = memoryview(payload)
    cursor = 14
    events: list[MidiEventV1] = []
    note_events: list[NoteEventV1] = []
    tracks: list[TrackInfoV1] = []
    tempos: list[dict[str, int]] = []
    meters: list[dict[str, int]] = []
    total_length = 0
    total_events = 0

    for track_index in range(track_count):
        if cursor + 8 > len(memory) or memory[cursor : cursor + 4].tobytes() != b"MTrk":
            raise GrooveMidiError("invalid track chunk")
        track_length = struct.unpack_from(">I", memory, cursor + 4)[0]
        track_start = cursor + 8
        track_end = track_start + track_length
        if track_end > len(memory):
            raise GrooveMidiError("truncated track chunk")
        cursor = track_start
        absolute_ticks = 0
        event_index = 0
        running_status: int | None = None
        open_notes: dict[tuple[int, int], list[int]] = {}
        track_name = ""

        while cursor < track_end:
            delta_ticks, cursor = _read_vlq(memory, cursor, track_end)
            absolute_ticks += delta_ticks
            if cursor >= track_end:
                raise GrooveMidiError("truncated event status")
            status_byte = memory[cursor]
            used_running_status = status_byte < 0x80
            if used_running_status:
                if running_status is None or running_status < 0x80 or running_status >= 0xF0:
                    raise GrooveMidiError("invalid running status")
                status = running_status
            else:
                cursor += 1
                status = status_byte
                running_status = status if 0x80 <= status <= 0xEF else None

            event_id = (track_index << 32) | event_index
            event_type = "midi"
            channel: int | None = None
            meta_type: int | None = None
            event_payload = b""
            if 0x80 <= status <= 0xEF:
                channel = status & 0x0F
                data_length = 1 if status >> 4 in (0xC, 0xD) else 2
                event_payload, cursor = _read_bytes(memory, cursor, data_length, track_end)
                if any(byte >= 0x80 for byte in event_payload):
                    raise GrooveMidiError("status byte in MIDI event data")
                if status >> 4 == 0x9 and event_payload[1] > 0:
                    open_notes.setdefault((channel, event_payload[0]), []).append(len(note_events))
                    note_events.append(
                        NoteEventV1(
                            event_id=event_id,
                            track_index=track_index,
                            channel=channel,
                            pitch=event_payload[0],
                            velocity=event_payload[1],
                            start_ticks=absolute_ticks,
                            duration_ticks=0,
                        )
                    )
                elif status >> 4 in (0x8, 0x9) and (
                    status >> 4 == 0x8 or event_payload[1] == 0
                ):
                    key = (channel, event_payload[0])
                    waiting = open_notes.get(key, [])
                    if waiting:
                        note_index = waiting.pop(0)
                        note = note_events[note_index]
                        note.duration_ticks = max(0, absolute_ticks - note.start_ticks)
                        note.close_event_id = event_id
                        note.close_order = event_index
            elif status == 0xFF:
                event_type = "meta"
                if cursor >= track_end:
                    raise GrooveMidiError("truncated meta event")
                meta_type = memory[cursor]
                cursor += 1
                size, cursor = _read_vlq(memory, cursor, track_end)
                event_payload, cursor = _read_bytes(memory, cursor, size, track_end)
                if meta_type == 0x03:
                    try:
                        track_name = event_payload.decode("utf-8")
                    except UnicodeDecodeError:
                        track_name = ""
                elif meta_type == 0x51 and len(event_payload) == 3:
                    tempos.append(
                        {
                            "track_index": track_index,
                            "absolute_ticks": absolute_ticks,
                            "microseconds": int.from_bytes(event_payload, "big"),
                        }
                    )
                elif meta_type == 0x58 and len(event_payload) >= 2:
                    meters.append(
                        {
                            "track_index": track_index,
                            "absolute_ticks": absolute_ticks,
                            "numerator": event_payload[0],
                            "denominator_power": event_payload[1],
                        }
                    )
            elif status in (0xF0, 0xF7):
                event_type = "sysex"
                size, cursor = _read_vlq(memory, cursor, track_end)
                event_payload, cursor = _read_bytes(memory, cursor, size, track_end)
            else:
                raise GrooveMidiError(f"unsupported status byte 0x{status:02x}")

            events.append(
                MidiEventV1(
                    track_index=track_index,
                    event_index=event_index,
                    event_id=event_id,
                    delta_ticks=delta_ticks,
                    absolute_ticks=absolute_ticks,
                    event_type=event_type,
                    channel=channel,
                    status=status,
                    payload_hex=event_payload.hex(),
                    meta_type=meta_type,
                )
            )
            event_index += 1
            total_events += 1
            if total_events > MAX_EVENTS:
                raise GrooveMidiError("event limit exceeded")
        total_length = max(total_length, absolute_ticks)
        tracks.append(
            TrackInfoV1(
                track_index=track_index,
                name=track_name,
                events_digest=sha256_hex(
                    canonical_json(
                        [
                            event.model_dump(mode="json")
                            for event in events
                            if event.track_index == track_index
                        ]
                    )
                ),
                event_count=event_index,
            )
        )
        cursor = track_end

    if cursor != len(memory):
        raise GrooveMidiError("trailing bytes after MIDI tracks")
    events_digest = sha256_hex(canonical_json([event.model_dump(mode="json") for event in events]))
    return ParsedSmfV1(
        raw_bytes=bytes(payload),
        format=SmfFormatV1(smf_type=smf_type, ppq=division, track_count=track_count),
        events=events,
        note_events=note_events,
        tracks=tracks,
        source_events_digest=events_digest,
        length_ticks=total_length,
        tempos=tempos,
        meters=meters,
    )


def serialize_generated_smf(parsed: ParsedSmfV1) -> bytes:
    """Serialize the lossless bytes held by a parsed/generated artifact."""

    return bytes(parsed.raw_bytes)


def compress_bounded(raw: bytes, codec: str) -> CompressedBlobV1:
    if codec not in RAW_BLOB_CODECS:
        raise GrooveBlobRejected("unsupported compression codec")
    compressor = zlib.compressobj(level=9, wbits=-15)
    blob = compressor.compress(raw) + compressor.flush()
    if len(blob) > MAX_COMPRESSED_BLOB:
        raise GrooveBlobRejected("compressed size limit exceeded")
    return CompressedBlobV1(
        codec=codec,
        raw_size=len(raw),
        compressed_size=len(blob),
        sha256=hashlib.sha256(raw).hexdigest(),
        blob=blob,
    )


def decompress_bounded(
    blob: bytes,
    *,
    codec: str,
    raw_size: int,
    max_compressed: int = MAX_COMPRESSED_BLOB,
    max_raw: int = MAX_RAW_BLOB,
    max_ratio: int = MAX_EXPANSION_RATIO,
) -> bytes:
    if codec not in RAW_BLOB_CODECS:
        raise GrooveBlobRejected("unsupported compression codec")
    if len(blob) > max_compressed or raw_size < 0:
        raise GrooveBlobRejected("compressed size limit exceeded")
    if raw_size > max_raw:
        raise GrooveBlobRejected("raw size limit exceeded")
    decoder = zlib.decompressobj(wbits=-15)
    output = bytearray()
    try:
        for start in range(0, len(blob), 64 * 1024):
            output.extend(
                decoder.decompress(
                    blob[start : start + 64 * 1024],
                    max_raw + 1 - len(output),
                )
            )
            if len(output) > max_raw:
                raise GrooveBlobRejected("raw size limit exceeded")
        output.extend(decoder.flush(max_raw + 1 - len(output)))
    except GrooveBlobRejected:
        raise
    except zlib.error as error:
        raise GrooveBlobRejected("malformed compressed stream") from error
    if len(output) > max_raw:
        raise GrooveBlobRejected("raw size limit exceeded")
    if len(output) > max_ratio * max(1, len(blob)):
        raise GrooveBlobRejected("decompression ratio exceeded")
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise GrooveBlobRejected("truncated or size-mismatched compressed BLOB")
    if len(output) != raw_size:
        raise GrooveBlobRejected("truncated or size-mismatched compressed BLOB")
    return bytes(output)
