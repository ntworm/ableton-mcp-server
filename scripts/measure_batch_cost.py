"""Measure what one scenario costs an agent with unit calls against batched calls.

Both variants leave the same end state in Live: 8 MIDI tracks created and
renamed, one 4-beat clip with 16 notes on each, 8 cue points, one scene launch.
They differ in agent turns (tool calls), in what each turn carries, and in undo
steps (variant A creates the cue points in 8 undo steps, B in one).

Variant A makes one tool call per operation (42 calls). Variant B makes 4:
``get_track_list``, one ``run_batch`` with the 32 track, clip and note
commands, ``bulk_create_cue_points`` and ``fire_scene``.

Sizes are ``len()`` of ``json.dumps(value, separators=(",", ":"),
ensure_ascii=False)``: arguments as sent, results as the MCP content blocks the
in-memory client receives, and the ``tools/list`` response (each tool as
``model_dump(mode="json", exclude_none=True)``). An MCP client resends the tool
schema with every turn, so ``context_chars = calls * tools_list_chars +
argument_chars + result_chars`` is the input an agent loop accumulates.
``context_tokens_estimate`` is ``context_chars / 4``: an estimate, not a
tokenizer count. Call counts are exact.

``--target fake`` runs without Live against ``tests/_strict_fake.py``. Its
``run_batch`` is a fixed reply, so it reproduces call counts and argument sizes
only; result sizes and the context estimate are reported for ``--target live``.

Usage::

    python scripts/measure_batch_cost.py --target fake
    python scripts/measure_batch_cost.py --target live --variant A \
        --confirm-project-name TESTE_CODEX --markdown docs/reports/batch-cost-A.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for _entry in (ROOT, ROOT / "scripts"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from fastmcp import Client as FastMCPClient  # noqa: E402
from report_privacy import require_public  # noqa: E402

from ableton_mcp_server import server  # noqa: E402
from ableton_mcp_server.acceptance.safety import require_fresh_set  # noqa: E402

TRACKS = 8
NOTES_PER_CLIP = 16
CLIP_BEATS = 4.0
CUE_GRID = 8.0
CUES = 8


def _size(value: Any) -> int:
    return len(json.dumps(value, separators=(",", ":"), ensure_ascii=False))


def _notes() -> list[dict[str, Any]]:
    step = CLIP_BEATS / NOTES_PER_CLIP
    return [
        {"pitch": 60 + (i % 12), "start_time": i * step, "duration": step, "velocity": 100}
        for i in range(NOTES_PER_CLIP)
    ]


def base_index(track_rows: list[dict[str, Any]]) -> int:
    """Insertion index after the regular tracks (returns and master come last)."""
    return sum(1 for row in track_rows if row.get("type") in ("midi", "audio"))


def cue_times(song_length: float, locators: list[dict[str, Any]]) -> list[float]:
    """8-beat cells strictly below the song length, away from existing locators."""
    occupied = {round(float(item.get("time", -1.0)) / CUE_GRID) for item in locators}
    cells = int(song_length // CUE_GRID)
    if cells * CUE_GRID >= song_length:
        cells -= 1
    free = [i * CUE_GRID for i in range(cells + 1) if i not in occupied]
    if len(free) < CUES:
        raise SystemExit(
            f"need {CUES} free 8-beat cells below song length {song_length}; "
            f"found {len(free)}. Use a Set with at least 64 beats and no locator."
        )
    return free[:CUES]


def track_commands(base: int) -> list[tuple[str, dict[str, Any]]]:
    """The 32 track, clip and note mutations, in execution order."""
    commands: list[tuple[str, dict[str, Any]]] = []
    for k in range(TRACKS):
        index = base + k
        commands += [
            ("create_midi_track", {"name": f"Batch {k + 1}", "index": index}),
            ("rename_track", {"track_index": index, "new_name": f"Batch cost {k + 1}"}),
            ("create_clip", {"track_index": index, "clip_index": 0, "length_beats": CLIP_BEATS}),
            ("add_notes_to_clip", {"track_index": index, "clip_index": 0, "notes": _notes()}),
        ]
    return commands


def plan_variant(variant: str, base: int, times: list[float]) -> list[tuple[str, dict[str, Any]]]:
    """Tool calls after the shared ``get_track_list``."""
    cues = [{"name": f"Cue {i + 1}", "time": t} for i, t in enumerate(times)]
    if variant == "A":
        calls = track_commands(base)
        calls += [("create_cue_point", cue) for cue in cues]
    else:
        batch = [{"type": name, "params": params} for name, params in track_commands(base)]
        calls = [("run_batch", {"commands": batch}), ("bulk_create_cue_points", {"items": cues})]
    return calls + [("fire_scene", {"scene_index": 0})]


class Meter:
    """Counts tool calls and the characters each one carries."""

    def __init__(self, client: Any) -> None:
        self.client = client
        self.calls = 0
        self.argument_chars = 0
        self.result_chars = 0
        self.errors: list[str] = []

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        result = await self.client.call_tool(name, arguments, raise_on_error=False)
        blocks = [block.model_dump(mode="json", exclude_none=True) for block in result.content]
        self.calls += 1
        self.argument_chars += _size(arguments)
        self.result_chars += _size(blocks)
        if result.is_error:
            self.errors.append(f"{name}: {_text(result)[:200]}")
        return _parsed(result)


def _text(result: Any) -> str:
    return "".join(getattr(block, "text", "") for block in result.content)


def _parsed(result: Any) -> Any:
    if result.structured_content is not None:
        content = result.structured_content
        return content.get("result", content) if isinstance(content, dict) else content
    try:
        return json.loads(_text(result))
    except json.JSONDecodeError:
        return _text(result)


async def _preflight(client: Any, target: str, project: str | None) -> tuple[float, list[Any]]:
    """Uncounted reads shared by both variants: Set identity, song length, locators."""
    if target == "live":
        metadata = (await client.call_tool("get_project_metadata", {})).structured_content or {}
        metadata = metadata.get("result", metadata)
        if metadata.get("song_name") != project:
            raise SystemExit(f"open Set is {metadata.get('song_name')!r}, not {project!r}")
        require_fresh_set(metadata)
    length = _parsed(await client.call_tool("get_song_length", {}))
    locators = _parsed(await client.call_tool("get_locators", {}))
    return float(length["song_length"]), list(locators or [])


async def measure(variant: str, target: str, project: str | None = None) -> dict[str, Any]:
    """Run one variant through the in-memory MCP client and return its figures."""
    async with FastMCPClient(server.mcp) as client:
        tools = await client.list_tools()
        tools_chars = _size([tool.model_dump(mode="json", exclude_none=True) for tool in tools])
        song_length, locators = await _preflight(client, target, project)
        meter = Meter(client)
        rows = await meter.call("get_track_list", {})
        base = base_index(rows if isinstance(rows, list) else [])
        for name, arguments in plan_variant(variant, base, cue_times(song_length, locators)):
            await meter.call(name, arguments)
    return _figures(variant, target, meter, tools_chars)


def _figures(variant: str, target: str, meter: Meter, tools_chars: int) -> dict[str, Any]:
    figures: dict[str, Any] = {
        "variant": variant,
        "target": target,
        "calls": meter.calls,
        "argument_chars": meter.argument_chars,
        "tools_list_chars": tools_chars,
        "errors": meter.errors,
    }
    if target == "live":
        context = meter.calls * tools_chars + meter.argument_chars + meter.result_chars
        figures.update(
            result_chars=meter.result_chars,
            context_chars=context,
            context_tokens_estimate=context // 4,
        )
    return figures


def use_fake_bridge() -> None:
    """Point the server at the in-process strict fake (no socket, no Live)."""
    from tests._strict_fake import StrictFakeBridge

    server._client = StrictFakeBridge()  # type: ignore[assignment]


def markdown(rows: list[dict[str, Any]]) -> str:
    columns = (
        "variant",
        "calls",
        "argument_chars",
        "result_chars",
        "tools_list_chars",
        "context_chars",
        "context_tokens_estimate",
    )
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(c, "n/a")) for c in columns) + " |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=("fake", "live"), default="fake")
    parser.add_argument("--variant", choices=("A", "B"))
    parser.add_argument("--confirm-project-name")
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)
    if args.target == "live" and not (args.variant and args.confirm_project_name):
        parser.error("--target live needs --variant and --confirm-project-name")
    variants = [args.variant] if args.variant else ["A", "B"]
    rows = []
    for variant in variants:
        if args.target == "fake":
            use_fake_bridge()
        rows.append(asyncio.run(measure(variant, args.target, args.confirm_project_name)))
    require_public(rows)
    print(json.dumps(rows, indent=2))
    if args.markdown:
        args.markdown.write_text(markdown(rows), encoding="utf-8")
    return 1 if any(row["errors"] for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
