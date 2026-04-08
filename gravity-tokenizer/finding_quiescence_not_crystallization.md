# Finding: Quiescence, Not Crystallization

**Date:** April 8, 2026  
**Run family:** `gravity_v2_beta_1.0_with_space`, seed `1337`  
**Status:** Active interpretation. Supersedes the April 8 metastable-boundary framing.

## Headline

The moving phase-space classifier was not measuring tokens that were "newly crystallizing." It was measuring a **relative quiet corner** of phase space.

The correct pairing is:

- classifier class: `QUIESCENT`
- replay object: `FIXED_QUIET`

The fixed-threshold replay shows that the apparent rotating boundary mixed two distinct populations:

1. **pure quantile drift inside a stable quiet pool**
2. **real outward motion out of the quiet pool**

## The corrected anatomy of the 52-token classifier union

Against the step-4000 thresholds:

- `188` tokens are `FIXED_QUIET` at **every** snapshot
- the classifier's durable backbone is only `11` tokens
- the classifier union across all snapshots is `52` tokens

That `52` splits cleanly into four groups:

| group | count | interpretation |
|---|---:|---|
| stable core | 11 | classifier-`QUIESCENT` and `FIXED_QUIET` throughout |
| quiet rotating frontier | 19 | always `FIXED_QUIET`, but only intermittently classifier-`QUIESCENT` |
| brief excursion | 1 | mostly `FIXED_QUIET`, one temporary marginal blip (`own`) |
| real departures | 21 | classifier-`QUIESCENT` early, but no longer `FIXED_QUIET` by step 4000 |

So the earlier "metastable boundary layer" story was only half right. The boundary was not one phenomenon.

## The 21 real departures

The 21 tokens that left `FIXED_QUIET` by step 4000 are:

`er, es, in, ld, om, end, ven, ut, ind, ip, ort, bal, ear, ee, ill, air, ng, rd, um, ▁Ca, ▁Re`

Destination at step 4000:

- `19` moved to `FIXED_MARGINAL`
- `2` moved to `FIXED_DEBRIS`
- `0` remained `FIXED_QUIET`

This is genuine raw-metric movement. These tokens did not merely drift out of a quantile ranking while staying quiet; their `active_work` grew past the late `work_floor`, or their panic grew past the late panic threshold.

## What the classifier is actually measuring

`QUIESCENT` does **not** mean:

- learned in an absolute sense
- semantically important
- permanently graduated

It means:

- low panic relative to the snapshot population
- low work relative to the snapshot population

More sharply:

> In this apparatus, `QUIESCENT` means the optimizer is not doing much with the token *right now* relative to the rest of the dynamic pool.

That makes the old label `GRADUATED` too strong.

## Null result: leverage does not separate drift vs departure

We tested whether the real-departure tokens were the "productive" ones the model kept working on by comparing their static ablation leverage against the pure-drift tokens.

Result: **null**.

| group | n | median leverage | mean leverage |
|---|---:|---:|---:|
| stable core | 11 | 0.607 | 0.587 |
| drift-only | 20 | 0.652 | 0.664 |
| real departures | 21 | 0.613 | 0.653 |

Mann-Whitney U (departures vs drift): `p = 0.54`

So static leverage does **not** explain which quiet tokens stay quiet and which later become active.

## What survives

- the `11`-token stable core is real
- the `v2 > v1` ordering is real
- the classifier was mixing drift and real motion
- the rename to `QUIESCENT` is justified

## What dies

- "metastable boundary layer" as a single mechanism
- "slow stabilizers" as tokens entering quietness late
- any reading of the classifier class as absolute crystallization

## Working language going forward

- **Classifier label:** `QUIESCENT`
- **Replay label:** `FIXED_QUIET`

Recommended sentence:

> In the `v2-4000` trajectory, `11` tokens were stably quiet from the start, `19` more cycled in and out of the classifier's quiet slice while staying raw-quiet throughout, and `21` tokens left the quiet region entirely by step 4000. The apparent boundary layer was therefore a roughly even mix of quantile-ranking drift and real outward motion.
