# Groove Seed V3 Regeneration — Result

Executed 2026-09-02 against plan `2026-09-01-groove-seed-v3-regeneration.md`.

## What shipped

Six commits, no push, no release:

| Commit | What |
| --- | --- |
| `eb35206` | Pin the v2 and v3 role behaviour before touching anything |
| `0bcca26` | Read the vendor genre and tempo labels at build time |
| `924114a` | Derive `kit` from whichever HVO the caller passes; add the `genre` and `bpm` facets |
| `1a1ea3d` | Store the v3 articulation projection on every artifact |
| `f530e0b` | Bump the index, seed and taxonomy versions to v3 |
| `feddfb2` | Union the vendor genre with the path genre instead of replacing it |

## The defect this fixes

The role map only knew General MIDI percussion, pitches 35 to 81. Everything
outside became `other_percussion`. Measured over 6,000 unique files and 361,264
notes, that was **24.34%** of the note mass, and 63.6% of those notes sat outside
the GM range entirely — pitches 22, 21, 26, 25, 24, which the Toontrack libraries
use for hi-hat articulations, and 60 to 63, which they use for cymbals.

With the per-collection articulation map applied, hi-hat mass rises from
**5.67%** to **21.95%** and `other_percussion` falls from **24.34%** to
**6.48%**. No role that General MIDI already resolved was demoted. The map covers
229 collections, 199 at high confidence and 30 at medium.

## What the old seed actually contained

Two files are in play and they are not the same seed. `HEAD` carries the
promoted 1,685-representative bundle (27,201,536 bytes); the working tree
carries the disposable 500-item experiment of decision S1, which is what
`seed-backup-20260902` preserved. The committed bundle is the one that means
"shipped", so it is the reference below.

| Axis | Artifacts carrying it (of 1,685) |
| --- | --- |
| `collection`, `density`, `feel`, `kit`, `license`, `microtiming` | 1,685 |
| `section` | 1,344 |
| `style` | 1,089 |
| `genre` | 982 |
| `source_category` | 375 |
| `subgenre` | 328 |
| `bpm` | 0 |

`kit` carried 7,998 facet rows, of which **1,008 (12.6%)** were
`other_percussion` — the third most common kit value in the shipped seed. The
500-item experiment agrees within a fraction of a point: 310 of 2,416 rows,
12.8%, and genre on 292 of 500.

This table corrects section 13.5 of the extension design, which claims the folder
hierarchy carries genre *and* BPM. It is half right: the hierarchy yields a genre
for 982 of 1,685 artifacts, 58.3%, but it never produced a single BPM row.

## The genre decision

The vendor sidecar covers 109,554 paths, every one with a genre and a tempo,
across 15 genres — `Pop/Rock/Country` alone accounts for 57,670 files and `Metal`
for 21,672.

The first implementation let the vendor label overwrite the path label. That was
wrong and was caught before the seed was built: the path vocabulary is the finer
of the two, so an artifact that said `rock` would have been rewritten to
`pop_rock_country`, which lumps three genres into one token. A search for `rock`
would then have missed it. Both labels now sit on the same axis.

## The identity decision

The v3 projection digest joins the artifact identity, so every artifact id in the
new seed differs from the old one. The articulation map is a data file that can
be rebuilt, and a rebuild moves roles; an identity blind to the v3 digest would
hand two materially different artifacts the same id, and an index could not tell
that its stored content had gone stale.

The public MCP surface is unchanged. `ProjectionId` still names only the three v2
projections, the artifact card still lists only those three, and `runtime.card`
does not materialise the v3 blob — search builds a card per candidate row, so
decompressing a training projection there would be paid on the hot path for a
value no caller can read.

## Three positional assumptions the fourth projection exposed

Adding a fourth projection broke three places that had picked projections by
position rather than by name:

- `cards.py` sliced `artifact.projections[:3]`, silently dropping the grammar
  reference once `hvo_v3` was inserted ahead of it;
- `runtime.py` did the same in its card builder;
- the provider test fixture took `manifest.artifact_ids[1]` as "the row with a
  payload", which stopped being true when the identity change reshuffled the
  manifest order.

All three now select by the property they actually mean. The fixture's pinned
artifact id, a hand-copied literal, is now derived from the pilot bundle.

## The version bump that broke ninety tests

`SQLITE_USER_VERSION` moved to 3, but the index DDL carried
`PRAGMA user_version = 2` as a literal inside a SQL string. The plan's search for
the identifier could not see it. The writer stamped 2, the reader demanded 3, and
every bundle the suite built was rejected by its own reader — 90 failures from
one unsearchable literal. The DDL now interpolates the constant.

## The curated selection cap

`build_curated_bundle` refused any `max_files` above 2,048, so the 4,000
representatives decision S2 asks for could not be requested at all. The bound is
now the named constant `MAX_CURATED_REPRESENTATIVES = 4096`. It bounds the count,
not the size; the bundle keeps its own byte cap, and `regenerate_seed.py` reports
when the byte cap rather than the request decided the final count.

## Regenerated seed

Built 2026-09-02, 3,695 seconds (62 minutes) end to end. The scan found 183,429
files, 180,614 of them valid and 2,815 rejected. Promoted to
`ableton_mcp_server/resources/groove_seed/`.

| | Committed v2 seed | Promoted v3 seed |
| --- | --- | --- |
| Artifacts | 1,685 | 4,000 |
| `index.sqlite` | 27,201,536 bytes | 73,007,104 bytes |
| Collections represented | — | 266 |
| Projections per artifact | 3 | 4 |
| `kit` coverage | 1,685 (100%) | 4,000 (100%) |
| `genre` coverage | 982 (58.3%) | 3,434 (85.8%) |
| `bpm` coverage | 0 | 2,469 (61.7%) |
| Distinct genres | — | 47 |
| `other_percussion` share of `kit` rows | 1,008 of 7,998 (12.6%) | 943 of 20,236 (**4.7%**) |

`groove.hvo.v2` and `groove.hvo.v3` are both present on all 4,000 artifacts.
The selection was never shrunk: 4,000 requested, 4,000 delivered, zero reduction
attempts, well inside the 256 MB byte cap.

Digests:

- manifest `cb61b67a99d0bd71877a95bc6b2974617048169f83bb2ec3169fc71ec22cc791`
- logical index `c6b53be306b52c9b9dccebdf693f34ee0ff1e573ae9e740b47100b916774321d`

### The hi-hats came back

The old seed's ten most common kit values contained no hi-hat lane at all. The
new one carries three, together the largest instrument group after kick and
snare:

| Kit value | Facet rows |
| --- | --- |
| `kick` | 3,705 |
| `snare` | 3,450 |
| `crash` | 1,778 |
| `tom_low` | 1,668 |
| `tom_high` | 1,372 |
| `tom_mid` | 1,265 |
| `hat_open` | 1,208 |
| `hat_pedal` | 1,124 |
| `hat_closed` | 1,102 |
| `ride` | 1,016 |
| `other_percussion` | 943 |

### Both genre vocabularies survive

47 distinct genres against the vendor's 15, which is the union doing its job.
`pop_rock_country` (1,147 artifacts, vendor) sits alongside `rock` (597), `pop`
(171) and `country` (62) from the paths, so a search for any of the four finds
the artifacts that carry it.

`bpm` reaches 61.7% rather than 100% because the vendor sidecar covers 109,554
of the 180,614 valid files — 60.7%. The axis is as complete as its source, and a
groove outside the vendor databases has no tempo label to carry.

## Backup

`seed-backup-20260902` under `%LOCALAPPDATA%\AbletonMCPServer` holds
`index.sqlite`, `manifest.json` and `SHA256SUMS`, verified byte-identical to the
working-tree resource before promotion. That is the 500-item experiment, not the
promoted seed.

The promoted 1,685-item bundle needs no directory backup: it is committed, so
`git show HEAD:ableton_mcp_server/resources/groove_seed/index.sqlite` restores it
exactly. The file backup covers the one copy git does not have.

## Verification

`918 passed, 4 failed, 2 skipped` against the promoted seed. Ruff clean across
`ableton_mcp_server/groove_intelligence`, `scripts/regenerate_seed.py` and
`tests`. Mypy reports three errors, all in the uncommitted prototype below.

The two failures that this plan introduced and then resolved were
`test_canonical_offline_runner_uses_packaged_seed_without_env_override` and
`test_open_readonly_index_accepts_the_packaged_seed`: between the version bump
and the promotion the code demanded a v3 bundle while the packaged resource was
still v2. Promotion cleared both.

### The four remaining failures, all from uncommitted prototypes

| Test | Cause |
| --- | --- |
| `test_groove_generation.py::test_nonzero_transform_changes_real_note_events_and_payload` | swing/polyrhythm prototype in `deterministic.py` reads `note.start_tick`; the field is `start_ticks` |
| `test_groove_generation.py::test_negative_timing_transforms_move_directionally_with_clamp[swing-240]` | same |
| `test_remote_socket.py::test_fallback_control_surface_lifecycle_delegates_to_socket_server` | uncommitted `AbletonMCPServer_RemoteScript/realtime_server.py` |
| `test_tool_registry.py::test_real_fastmcp_listing_matches_models_and_count_proxy` | uncommitted `plan_user_journey` tool in `server.py` and `journeys.py` |

All four predate this work and none were touched. `server.py` additionally has a
live Ruff `F821` for `_plan_user_journey`, which is undefined — worth a look, but
not this plan's to fix.
