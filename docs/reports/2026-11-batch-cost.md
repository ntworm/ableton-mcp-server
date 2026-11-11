# Batch cost, measured in Live

Date: 2026-11-11. Live 12.4.25b1, Set `MCP_PROVAS`, reopened from disk before each
variant (`can_undo` false). Command: `python scripts/measure_batch_cost.py --target
live --variant A|B --confirm-project-name MCP_PROVAS`.

Both variants leave the same end state: 8 MIDI tracks created and renamed, one
4-beat clip with 16 notes on each, 8 cue points, one scene launch. Variant A makes
one tool call per operation; variant B uses `run_batch` for the 32 track, clip and
note commands and `bulk_create_cue_points` for the cue points. Variant A creates
the cue points in 8 undo steps, variant B in one.

Sizes are characters of compact JSON. `context_chars = calls x tools_list_chars +
argument_chars + result_chars` is the input an agent loop accumulates when the
client resends the tool list with every turn. `context_tokens_estimate` is
`context_chars / 4`, an estimate; the call count is exact.

| variant | calls | argument_chars | result_chars | tools_list_chars | context_chars | context_tokens_estimate |
|---|---|---|---|---|---|---|
| A | 42 | 9433 | 7360 | 64094 | 2708741 | 677185 |
| B | 4 | 10626 | 8205 | 64094 | 275207 | 68801 |
