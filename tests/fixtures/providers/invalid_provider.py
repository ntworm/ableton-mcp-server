from __future__ import annotations

import json
import struct
import sys

header = sys.stdin.buffer.read(4)
if header:
    size = struct.unpack(">I", header)[0]
    sys.stdin.buffer.read(size)
    raw = json.dumps({"method": "exec", "path": "C:\\private"}).encode("utf-8")
    sys.stdout.buffer.write(struct.pack(">I", len(raw)) + raw)
    sys.stdout.buffer.flush()
