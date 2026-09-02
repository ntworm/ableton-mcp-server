# Baselines and evaluation — gate G5 result

**The masked HVO transformer does not beat retrieval. Gate G5 fails.**

Measured 2026-08-31 on the 1% dataset, three M1 seeds from plan 6, validation
split, identical cases for every system.

## The declared primary metric

Hit F1 on masked target cells over the infill family — `temporal_infill`,
`lane_infill`, `fill`, `continuation` — declared in the plan before the run.

| System | seed 0 | seed 1 | seed 2 | mean |
|---|---|---|---|---|
| masked HVO | 0.4650 | 0.5494 | 0.4990 | **0.5045** |
| retrieval | 0.4552 | 0.5426 | 0.5037 | **0.5005** |
| marginal sampler | 0.1673 | 0.1837 | 0.1861 | 0.1790 |

| G5 condition | Result |
|---|---|
| Beats the best baseline on every seed | **no** — retrieval wins seed 2 |
| Margin over the baseline's own seed spread | **no** — margin 0.0040 against a spread of 0.0874 |

The margin is 22 times smaller than the noise it has to clear.

Both systems comfortably beat the marginal sampler, which is the one piece of
good news: the model has learned real structure, not just density. It has simply
not learned more of it than looking the answer up in the corpus.

## A methodological weakness in the primary metric, named rather than hidden

The seed controls two things at once here: which checkpoint is loaded *and* which
task masks the cases get. Retrieval has no model seed, so its 0.0874 spread is
entirely case-draw variance — task difficulty, not system variance. Comparing a
model-versus-baseline difference against that number is very conservative and
somewhat mis-specified.

The sharper test is paired: for each individual case, did the model beat
retrieval on the same window with the same mask? That removes case difficulty
completely. Run over 115 infill cases:

| Seed | Model wins | Retrieval wins | Ties | Win rate among decided |
|---|---|---|---|---|
| 0 | 46 | 44 | 25 | 51.1% |
| 1 | 51 | 40 | 24 | 56.0% |
| 2 | 45 | 46 | 24 | 49.5% |

A coin flip. With about 90 decided cases per seed, none of these is
distinguishable from 50%. The paired test is reported as supplementary evidence;
the declared primary metric still governs the gate, and it fails either way.

## Musicality, where the gap is not close

Free generation, 64 samples per seed, lane profile distance to the corpus, lower
is better:

| System | Lane distance to corpus |
|---|---|
| marginal sampler | **0.041** |
| masked HVO | **1.204** |

The sampler that knows nothing but per-cell hit rates is **29 times closer** to
the corpus lane profile than the trained model. This is the plan 6 finding turned
into a number: the model clears every structural gate and still puts hits in the
wrong lanes.

## Originality

Both the model and the sampler score a 0.0% exact repeat rate against the train
split, well under the corpus's own 26.0% internal repeat rate.

Retrieval is excluded from this comparison because it returns real corpus windows
and its repeat rate is 100% by construction. That was stated in the plan before
the run rather than discovered afterwards. It is also the one dimension where a
neural model has a structural advantage over the incumbent, and it is worth
remembering when reading the F1 tie: the two systems achieve the same score by
different means, and only one of them is capable of producing something new.

## What follows

Specification 23 already committed to this outcome: *"the model has to beat
retrieval and deterministic in blind evaluation and anti-copy"*, and *"the
deterministic product stays useful if the neural fails"*. Retrieval plus the
deterministic transforms remain the product.

This is a result, not a failed project. The programme was built so this answer
would be survivable and legible, and it took four measured gates to get here
rather than an opinion.

Three things are worth trying before concluding that a neural model cannot win
here, in rough order of expected value:

1. **More data.** This is 1% — 2,269 training windows against a 354,749-window
   corpus. Retrieval already has the whole corpus in the sense that matters; the
   model has one hundredth of it. Rung M2 exists for this.
2. **Fix the lane collapse.** A distance of 1.204 against a trivial sampler's
   0.041 is not a subtle miss. The positive weighting fixed the silence and left
   the model dumping into `hat_pedal`; a per-lane weighting is the obvious next
   thing to measure.
3. **Ask a question retrieval cannot answer.** The tie is on infill, which is
   where nearest-neighbour lookup is strongest. Conditioned free generation and
   the reference task are where a model would differ, and neither is what this
   gate measured.

None of that is a reason to move a threshold. It is the list of experiments a
future rung would run.

Raw data: `F:\groove-brain\runs\gate_g5.json` and `g5_paired.json`.
