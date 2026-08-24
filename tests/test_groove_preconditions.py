from __future__ import annotations

import pytest
from pydantic import ValidationError

from ableton_mcp_server.models import RunBatchRequest


def test_run_batch_accepts_bounded_slot_empty_preconditions() -> None:
    request = RunBatchRequest(
        commands=[{"type": "set_tempo", "params": {"tempo": 120}}],
        preconditions=[
            {"type": "slot_empty", "version": "v1", "params": {"track_index": 0, "clip_index": 2}}
        ],
    )
    assert request.preconditions[0].params.track_index == 0


def test_run_batch_rejects_duplicate_and_unknown_preconditions() -> None:
    item = {"type": "slot_empty", "version": "v1", "params": {"track_index": 0, "clip_index": 2}}
    with pytest.raises(ValidationError, match="duplicates"):
        RunBatchRequest(
            commands=[{"type": "set_tempo", "params": {"tempo": 120}}], preconditions=[item, item]
        )
    with pytest.raises(ValidationError):
        RunBatchRequest(
            commands=[{"type": "set_tempo", "params": {"tempo": 120}}],
            preconditions=[{**item, "extra": 1}],
        )


def test_run_batch_rejects_more_than_sixteen_preconditions() -> None:
    items = [
        {"type": "slot_empty", "version": "v1", "params": {"track_index": i, "clip_index": 2}}
        for i in range(17)
    ]
    with pytest.raises(ValidationError):
        RunBatchRequest(
            commands=[{"type": "set_tempo", "params": {"tempo": 120}}], preconditions=items
        )
