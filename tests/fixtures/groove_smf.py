from __future__ import annotations

import zlib


def _chunk(tag: bytes, body: bytes) -> bytes:
    return tag + len(body).to_bytes(4, "big") + body


MINIMAL_TYPE1_SMF = (
    _chunk(b"MThd", b"\x00\x01\x00\x02\x01\xe0")
    + _chunk(b"MTrk", b"\x00\xff\x51\x03\x07\xa1\x20\x00\xff\x2f\x00")
    + _chunk(b"MTrk", b"\x00\x99\x24\x64\x81\x70\x89\x24\x00\x00\xff\x2f\x00")
)
MULTI_TRACK_SMF = MINIMAL_TYPE1_SMF.replace(b"\x99\x24\x64", b"\x99\x26\x70")
MALFORMED_RUNNING_STATUS = _chunk(b"MThd", b"\x00\x01\x00\x01\x01\xe0") + _chunk(
    b"MTrk", b"\x00\x24\x64\x00\xff\x2f\x00"
)
MULTI_HIT_SMF = _chunk(b"MThd", b"\x00\x01\x00\x01\x01\xe0") + _chunk(
    b"MTrk", b"\x00\x99\x26\x68\x00\x99\x26\x68\x81\x70\x89\x26\x00\x00\xff\x2f\x00"
)
NO_TEMPO_SMF = _chunk(b"MThd", b"\x00\x01\x00\x01\x01\xe0") + _chunk(
    b"MTrk", b"\x00\x99\x24\x64\x81\x70\x89\x24\x00\x00\xff\x2f\x00"
)
TIME_SIGNATURE_6_8_SMF = _chunk(b"MThd", b"\x00\x00\x00\x01\x25\x80") + _chunk(
    b"MTrk",
    b"\x00\xff\x58\x04\x06\x03\x18\x08\x00\x99\x24\x64"
    b"\x81\x70\x89\x24\x00\x00\xff\x2f\x00",
)


def _raw_deflate(value: bytes) -> bytes:
    compressor = zlib.compressobj(level=9, wbits=-15)
    return compressor.compress(value) + compressor.flush()


HIGH_EXPANSION_RAW = b"A" * 8192
HIGH_EXPANSION_BLOB = _raw_deflate(HIGH_EXPANSION_RAW)
WRAPPED_COMPRESSED_BLOB = zlib.compress(HIGH_EXPANSION_RAW)
MALFORMED_COMPRESSED_BLOB = b"\x01\x02\x03\x04\x05"
