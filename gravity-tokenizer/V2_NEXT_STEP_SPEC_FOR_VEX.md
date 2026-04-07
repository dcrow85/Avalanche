# Gravity Tokenizer v2
## Next-Step Spec For Vex

**Date:** April 7, 2026  
**Author:** Kepler  
**Status:** Draft for execution  
**Purpose:** Pre-register the decision rule after the first `v2` witness and the in-flight `3500` floor ablation.

---

## 1. Executive Read

`v2` has already produced a real basin change:

- `8 -> 29` graduates (`3.6x`)
- `125 -> 341` Stage-1 crossers (`2.73x`)
- conditional graduation rate `6.4% -> 8.5%`
- materially broader active pool
- roughly `18%` better compression than `v1`

So the `v1` diagnosis was real enough to engineer against.

What did **not** happen is the strong-form `80-90` graduation outcome. The first `v2` witness therefore closes one question and opens a sharper one:

**Is the remaining ceiling mainly floor permissiveness, or mainly energy budget / geometric hardening?**

The current `3500` floor run is the cleanest cheap test of the first branch. The next expensive branch should be chosen from the pair, not from the `2903` run alone.

**Recommendation:** take path **A**, not path **B**.

- **A:** wait for the `3500` result, evaluate the pair, then choose
- **B:** pre-commit to `4000` steps regardless

Why `A`:
- `3500` is already almost finished
- it is the tightest clean floor comparison before vocab-size confounds dominate
- it resolves the most likely tokenizer-side ambiguity at trivial extra cost

This spec therefore pre-registers the decision rule for the `2903` vs `3500` pair and names the next run that should follow each branch.

---

## 2. Current State

### 2.1 Completed first `v2` witness (`2903` floor)

Matched witness:
- seed `1337`
- `12L / 384d`
- `2000` steps
- same harness as `v1`

Result:

| | v1 | v2-2903 | ratio |
|---|---:|---:|---:|
| dynamic tokens | 717 | 728 | 1.02x |
| Stage-1 crossers (`E >= 1.20`) | 125 | 341 | 2.73x |
| graduates | 8 | 29 | 3.62x |
| conditional grad rate | 6.4% | 8.5% | 1.33x |
| unconditional grad rate | 1.12% | 3.98% | 3.55x |

Interpretation:
- strong positive relative to `v1`
- clear miss relative to the original `80-90` prediction

### 2.2 In-flight `3500` floor ablation

Current telemetry at step `1600/2000`:

| step | v2-2903 | v2-3500 | delta |
|---|---:|---:|---:|
| 500 val_bpb | 1.8956 | 1.9092 | +0.7% |
| 1000 val_bpb | 1.6989 | 1.7204 | +1.3% |
| 1500 val_bpb | 1.6217 | 1.6337 | +0.7% |

Current read:
- `3500` is somewhat less compressive, as expected
- the validation gap is small and not widening catastrophically
- this remains a clean floor test, not an obvious failure witness

### 2.3 Why `3500` is the right boundary case

After parasitism veto:

| floor | merge survivors | interpretation |
|---|---:|---|
| 2903 | 966 | filtered gravity; leverage still has room to choose |
| 3500 | 772 | almost pure filter-determined vocabulary |
| 3529 | 765 | exact crossover; leverage does nothing |
| 3800 | 700 | undersubscribed |
| 5000 | 493 | badly undersubscribed |

This matters because `3500` is the tightest **clean** comparison:
- tighter than `2903`
- still effectively same slot budget
- not yet confounded by major vocab shrink

So `3500` is already the decisive tokenizer-side ablation.

---

## 3. Primary Question

The next branch should answer:

**Was `2903` too permissive for a `2000`-step witness, or is the remaining ceiling mostly energy budget / geometric hardening?**

Do **not** ask a broader question than that in the immediate next move.

---

## 4. Pre-Registered Decision Rule

Let:
- `G2903` = graduates in the completed `2903` witness (`29`)
- `G3500` = graduates in the `3500` witness
- `C2903` / `C3500` = Stage-1 crosser counts
- `R2903` / `R3500` = conditional graduation rates

### Branch 1: `3500` materially beats `2903`

Trigger:
- `G3500 >= 36`
or
- `G3500 - G2903 >= 5` **and** `R3500 > R2903` by a meaningful margin

Interpretation:
- `2903` was too permissive for the current budget
- the low-crossing `2903-5000` bin was indeed polluting the active medium

Next move:
- stay in the **floor-family** branch
- do **not** jump immediately to `4000` steps
- first tighten the design family around the boundary case:
  - either accept `3500` as the new main line
  - or run one deliberately documented near-boundary follow-up if needed

### Branch 2: `3500` ties or slightly loses to `2903`

Trigger:
- `G3500` in the neighborhood of `29`
or
- `G3500 < G2903 + 5`
with no strong conditional-rate improvement

Interpretation:
- floor permissiveness is **not** the main remaining bottleneck
- the next ceiling is more likely:
  - energy budget
  - geometric hardening
  - or both

Next move:
- launch the **time-evolution probe**:
  - same `v2-2903-with-space` witness
  - same seed
  - same architecture
  - extend to `4000` steps

This is the currently preferred branch.

### Branch 3: `3500` is much worse and collapses the active pool

Trigger:
- graduates fall materially below `2903`
and
- Stage-1 crossers collapse enough to clearly thin the medium

Interpretation:
- `3500` over-tightened the candidate ecology at this model/budget
- the `2903` choice was directionally right

Next move:
- abandon tighter floors for now
- go directly to the **time-evolution probe** on `2903`

This branch also resolves to the `4000`-step run.

---

## 5. Recommended Default

Unless `3500` clearly and materially outperforms `2903`, the next run should be:

## `v2-2903-with-space`, `4000` steps

That is the right next expensive run because it distinguishes:
- **energy budget ceiling**
from
- **early geometric lock-in**

This is the branch to take if `3500` ties, weakly improves, or loses.

---

## 6. Time-Evolution Probe Spec

### Fixed surface

- tokenizer: `gravity_v2_beta_1.0_with_space.model`
- vocabulary: `vocabulary_v2_beta_1.0_with_space.json`
- dataset: retokenized `v2-with-space` shards
- architecture: `12L / 384d / 6H / 2KV / 3x MLP`
- seed: `1337`

### Schedule

- extend training from `2000` to `4000` steps
- keep instrumentation on:
  - velocity / phase-space
  - coherence / magnitude
  - panic predictions if already part of the witness lane

### Primary measurements

At minimum, record:
- Stage-1 crossers over time
- graduates over time
- conditional graduation rate over time
- class counts at `500`-step cadence
- final `val_bpb`

### Decision matrix

If the `4000`-step run shows:

#### Case A: crosser pool inflates strongly
- e.g. `341 -> 500+`
- graduates and conditional rate rise meaningfully

Interpretation:
- the current ceiling was mostly **energy budget**
- the geometry was not fully hardened at `2000`
- more time allows more tokens to cross the floor and thickens the active medium

#### Case B: crosser pool stays near-flat
- crossers remain near the `2000`-step level
- graduates rise only weakly

Interpretation:
- the ceiling is mainly **geometric / lexical lock-in**
- by `2000`, most remaining candidates are already trapped outside the active medium

#### Case C: crossers rise but conditional rate stays flat

Interpretation:
- Stage 1 keeps improving
- Stage 2 remains the live bottleneck
- the next probe should then target above-floor collective behavior rather than the floor itself

---

## 7. Why Not Pre-Commit To `4000` Before `3500` Lands?

Because `3500` is already the clean tokenizer-side boundary case.

It is:
- almost finished
- cheap
- highly informative
- and the tightest floor test that does **not** immediately introduce a vocab-size confound

So pre-committing to `4000` before reading `3500` would throw away free information.

That said, note the shape of the decision tree:
- only a strong `3500` win blocks the `4000` run
- all other realistic outcomes point toward `4000`

So path `A` preserves rigor while still converging to the same likely next experiment in most branches.

---

## 8. Durable Summary

The correct next procedure is:

1. let the `3500` floor ablation finish  
2. compare it against `2903` using the pre-registered rule above  
3. if `3500` does **not** clearly beat `2903`, run `v2-2903-with-space` at `4000` steps  

Do **not** pre-commit to `4000` before reading `3500`.  
Do **not** tighten the floor beyond `3500` unless `3500` itself clearly wins.  

The current best guess is still that `4000` steps will be the next important run. But the honest move is to let `3500` earn or lose the right to redirect us first.
