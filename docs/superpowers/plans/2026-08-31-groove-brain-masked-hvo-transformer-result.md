# Masked HVO transformer — M0, M1 and gate G4 result

Executed 2026-08-31 on CPU, 1% dataset (`build-a`), step-token tokenisation,
32 decoding steps, temperature 1.0.

## Verdict

**Gate G4 passes on all five declared clauses.** It passed only after a real
failure was found and fixed, and both results are below because the first one is
the more instructive.

**G4 is a smoke test.** It says the pipeline works and the model is neither mute
nor frozen. It does not say the model is musical, and section "What G4 does not
say" below shows a measurement where it plainly is not.

## The first run failed, and the reason was a defect the specification had named

| Clause | Value | Threshold | |
|---|---|---|---|
| M0 final train loss | 0.0240 | < 0.05 | pass |
| Structural validity | 100% | 100% | pass |
| Diversity across seeds | 0.0046 | ≥ 0.05 | **fail**, 11× below |
| Diversity within a seed | 0.0039 | ≥ 0.05 | **fail**, 13× below |
| Hits per bar | **0.67** | 8 to 32 | **fail** |

The model had collapsed to near-silence: 0.67 hits per bar is about 1.3 notes in
a 576-cell window.

Diagnosis, measured rather than guessed:

- the training data carries a hit in **5.51%** of cells, so there are 18.15
  negatives for every positive;
- the trained model predicted a mean hit probability of **0.65%**, 8.4× below the
  base rate, with a mean logit of **−10.6**.

Plain binary cross-entropy against that ratio is minimised by predicting silence,
and that is what the model learned. Specification 12.1 asks for "BCE **or focal
loss** for hit **according to the imbalance**"; the first implementation used
plain BCE and never measured the imbalance, so it implemented half the sentence.

**This is specification risk 13 in the open.** Validation loss across the three
seeds sat at 0.165 to 0.175 and fell smoothly the whole way. The curves looked
like a healthy run. The output was silence. Without the hits-per-bar clause the
gate would have reported success, and the bake-off would have compared silence
against retrieval.

Remedy: `pos_weight = 18.15`, derived from the measured 5.51% rate, which is the
remedy the specification named. **No threshold was moved.** The failed result is
archived at `F:\groove-brain\runs-bce-only\` with its gate output.

## The second run, with the weighted loss

| Clause | Value | Threshold | |
|---|---|---|---|
| M0 final train loss | 0.0463 | < 0.05 | pass |
| Structural validity | 100% (192 samples) | 100% | pass |
| Diversity across seeds | 0.1141 | ≥ 0.05 | pass |
| Diversity within a seed | 0.0730 | ≥ 0.05 | pass |
| Hits per bar | 24.2 | 8 to 32 | pass |

One caveat on the first row: the 0.05 threshold was declared against the
unweighted loss, and `pos_weight` inflates the scale because positives now count
18× more. 0.0463 under the weighted loss is a stronger memorisation than 0.0240
was under the unweighted one, not a weaker one. The two numbers are not directly
comparable and neither is being presented as an improvement over the other.

## Runs

| Run | Examples | Steps | Final train | Best validation | Wall |
|---|---|---|---|---|---|
| M0 seed 0 | 64 | 3000 | 0.0463 | 0.2699 | 538 s |
| M1 seed 0 | 2,269 | 4047 | 0.2851 | 0.6331 | ~1210 s |
| M1 seed 1 | 2,269 | 4047 | 0.3637 | 0.6095 | ~1210 s |
| M1 seed 2 | 2,269 | 4047 | 0.3712 | 0.6319 | ~1210 s |

All four on one CPU thread each, run in parallel. M0 memorises — train loss falls
while validation rises, which is the behaviour section 17 asks that rung to prove.

## What G4 does not say

Generated lane distribution against the corpus, hits per two-bar window, seed 0,
32 samples:

| Lane | Generated | Corpus |
|---|---|---|
| `hat_pedal` | **14.94** | 2.38 |
| `snare` | 11.09 | 7.85 |
| `kick` | 4.31 | 8.26 |
| `hat_closed` | **0.00** | 4.99 |
| `ride` | 0.28 | 3.11 |
| `hat_open` | **0.00** | 1.03 |
| `tom_low` | 3.53 | 0.98 |
| total | 43.62 | 31.73 |

The model empties almost everything into `hat_pedal`, six times the corpus rate,
and never once produces `hat_closed` — the lane plan 2 spent its whole effort
recovering. Kick is at half its corpus rate.

This is not a groove. It clears every G4 clause because those clauses ask
whether the model is mute, frozen or structurally invalid, and it is none of
those. Per-lane plausibility is a musicality metric, and specification 18.3
already lists "distribution by lane and position" among them, so it belongs to
the evaluation harness in plan 5 rather than being retrofitted into a gate whose
thresholds were declared before these runs.

Reading a passing G4 as "the model works" would be the same mistake as reading
the first run's smooth validation curve that way.

## Not attempted

Gate G5, the bake-off, is not attempted here: it requires beating the best
baseline, and the baselines are plan 5. Rung M2, the 10% run, is not attempted
either; it wants three seeds over ten times the data, which is where the GPU
workspace of plan 1 stops being optional.

Raw records: `F:\groove-brain\runs\*\run.json` and `F:\groove-brain\runs\gate_g4.json`.
