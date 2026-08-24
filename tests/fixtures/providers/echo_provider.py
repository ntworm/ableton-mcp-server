"""Fixture provider source; tests may execute it in an isolated process."""

from __future__ import annotations

import json
import struct
import sys


def frame(value: dict[str, object]) -> None:
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(struct.pack(">I", len(raw)) + raw)
    sys.stdout.buffer.flush()


while True:
    header = sys.stdin.buffer.read(4)
    if not header:
        break
    size = struct.unpack(">I", header)[0]
    value = json.loads(sys.stdin.buffer.read(size))
    method = value.get("method")
    if method == "hello":
        frame({"method": "hello", "status": "ok", "provider_id": "fixture"})
    elif method == "generate":
        frame({"method": "generate", "status": "error", "code": "output_invalid"})
    elif method == "shutdown":
        frame({"method": "shutdown", "status": "ok"})
        break
