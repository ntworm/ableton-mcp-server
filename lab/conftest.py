"""Put the repository root on the path so the lab can import the product package.

The lab reuses the shipped parser, articulation map and v3 projection. It does
not install the product package, because that would drag FastMCP and the whole
server dependency tree into an environment that only needs to read MIDI.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
