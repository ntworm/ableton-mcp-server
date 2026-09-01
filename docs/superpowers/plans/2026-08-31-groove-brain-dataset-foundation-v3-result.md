# Dataset foundation V3 — 1% build result

Gate D1, executed 2026-08-31. Two independent builds of the same 1% slice, from
`lab/scripts/build_dataset.py`.

## Verdict

| Gate | Condition | Result |
|---|---|---|
| **G2** | two builds produce identical digests | **pass** — manifests and all three shard digests identical |
| **G2** | round-trip exact for every example | **pass** — 2,747 windows, 85,619 cells, 0 divergences, re-verified from the written shards |
| **G2** | no content hash spans a split | **pass** — `verify_no_leakage` clean over byte, canonical and rhythm hashes |
| **G2** | largest cluster under 5% of examples | **pass** — largest holds 2 of 2,747, 0.073% |
| **G3** | notes fused at or under the declared budget | **pass** — 2.85% against a 4% budget |

## Counts

| Split | Windows | Share |
|---|---|---|
| train | 2,269 | 82.6% |
| validation | 226 | 8.2% |
| test | 252 | 9.2% |
| **total** | **2,747** | from 1,238 byte-unique files |

The ratios are set over files and reported over windows, which is where the drift
from 80/10/10 comes from: a file contributing several windows moves as one whole
cluster, exactly as specification 12.3 requires.

Clusters: 1,215 for 1,238 files, so almost every file is its own family at this
slice size. 358 windows, 13.0%, were looped from a file shorter than two bars and
carry the flag.

## Manifest digest

Both builds: `f2c3bc299d65c80bc2cc1763bc45c0d92e23886f9cf9b33433583a0c21788ad1`

Shard digests, identical across both builds:

| Split | Digest |
|---|---|
| train | `8369745d4ea5bcc0…` |
| validation | `01686a47ab4070bd…` |
| test | `5b02a64603b22fad…` |

## Three different losses, reported separately

Collapsing these into one number was the first thing this build got wrong, and
the fix is the reason the run was repeated.

| Measure | Value | What it means |
|---|---|---|
| notes unaccounted for | **0.0%** | the `subhits` channel accounts for every source note; nothing vanishes |
| notes fused | **2.85%** | notes a one-hit-per-cell grid would have dropped — the quantity the 4% budget was derived from |
| expression averaged | **5.48%** | notes sharing a cell, so storing one mean velocity and one mean offset for several events |

Reporting only the first would have been a comfortable zero hiding a real cost.
The budget is checked against the second because that is the definition the corpus
audit used when it measured 3.51% on a sixteenth grid.

The 2.85% here is *below* that 3.51%, and the cause is plan 2: the articulation
map moved hi-hats out of `other_percussion` into three lanes of their own, so
fewer events land in the same cell.

## Disk

24 MB for 1%, so roughly **2.4 GB** for the full 354,749 windows. The plan
estimated 1.8 GB from the dtypes alone; the difference is the JSONL index and the
per-shard directory overhead. Disk is not a constraint, as section 16.4 already
concluded.

## Gate G1 carried through

66 of 278 collections were excluded for leaving more than 10% of their note mass
in `other_percussion`. Corpus-wide unresolved share at build time: 6.48%.

## What this does not establish

The slice is a digest-ordered prefix, which is pseudorandom with respect to
content but is not the full corpus. The 10% and 100% builds are separate rungs
and may move any of these numbers.

Raw manifests: `F:\groove-brain\dataset\build-a\manifest.json` and `build-b`.
