# Gravity Tokenizer v2 — First Results for Gemini

**Date:** 2026-04-07  
**Status:** First `v2` witness complete. Real improvement over `v1`. Strong-form prediction missed.

## One-line read

`v2` is a **successful but incomplete rescue**. It moved us into a new basin (`29` graduates vs `8` in `v1`), but it did **not** deliver the full percolation jump we predicted (`80-90`).

## Setup

Matched witness:
- seed `1337`
- `12L / 384d`
- `2000` steps
- same harness as `v1`

Comparison:
- `v1`: `gravity_beta_1.0_with_space`
- `v2`: `gravity_v2_beta_1.0_with_space`

`v2` build rules:
- volume floor: `corpus_frequency >= 2903`
- parasitism veto: `top1_successor_frac > 0.95` **and** dominant successor is alphabetic

## Core result

| | v1 | v2 | ratio |
|---|---:|---:|---:|
| dynamic tokens | 717 | 728 | 1.02x |
| Stage-1 crossers (`E >= 1.20`) | 125 | **341** | **2.73x** |
| graduates | 8 | **29** | **3.62x** |
| conditional grad rate (`grads/crossers`) | 6.4% | **8.5%** | **1.33x** |
| unconditional grad rate (`grads/dynamic`) | 1.12% | **3.98%** | **3.55x** |

Class structure also broadened materially:
- `CRYSTAL`: `2 -> 7`
- `DEBRIS`: `6 -> 22`
- `GRADUATED`: `8 -> 29`
- `MARGINAL`: `15 -> 57`
- `IMMATURE`: `686 -> 613`

This is not noise. The active pool widened substantially.

## Compression surprise

`v2` compresses **better** than `v1`, not worse.

| | v1 | v2 |
|---|---:|---:|
| shard token ratio vs BPE | 1.773x | **1.445x** |

That is about an **18% improvement** over `v1`.

This matters because the obvious objection to the `v2` filters was: “you made the vocabulary safer but blander.” That objection now looks wrong. The floor + parasitism veto improved both:
- trainability
- raw shard compression

## What survived

### 1. The filter logic worked

- No `v2` graduate fell below the `2903` floor.
- No `v2` graduate was a parasite.
- Known hostage fragments stayed dead.

So the two filters are not cosmetic. They are real upstream corrections.

### 2. Stage 1 is still the main lever

The decomposition is:
- Stage 1: `2.73x`
- Stage 2: `1.33x`
- total: `2.73 x 1.33 = 3.63x`

So most of the gain came from getting more tokens into the eligible pool at all.

### 3. Percolation probably survives, but only fractionally

The conditional graduation rate did rise (`6.4% -> 8.5%`), so the above-floor regime changed.

But it did **not** jump to the expected dense-pool level. So the best current read is:
- percolation is not dead
- but the threshold is higher, softer, or more budget-dependent than we thought

## What died

The strong-form prediction is dead:
- we did **not** get `80-90` graduates
- we did **not** get the full `~2x` percolation dividend above the floor
- we did **not** populate a crosser pool remotely as dense as BPE

Our original decomposition was:
- `5.6x` Stage 1
- `2.0x` Stage 2
- total `~11x`

Observed:
- `2.73x` Stage 1
- `1.33x` Stage 2
- total `3.6x`

So the direction was right, but the scaling law was not.

## Current read

This feels like a **ledge in a new basin**, not the basin floor.

`v2` clearly escaped the old `v1` failure regime:
- more graduates
- more crossers
- richer active pool
- better compression

But it also clearly hit a new ceiling:
- only `341` crossers, not `700+`
- only `8.5%` conditional graduation, not `~12%`

So the next question is no longer “was `v1` malformed?” It was.  
The next question is “what is the remaining ceiling?”

## Weird questions worth asking

These are not standard ablation questions. They are the strange ones that might actually move the theory.

### 1. Is the percolation threshold a function of **crossers**, not vocabulary size?

We have been talking as if “eligible pool density” is the key variable. But the run suggests the relevant density may be the **realized crosser population**, not the nominal filtered pool.

Question:
- does the regime change key off `eligible merges`, `energy-floor crossers`, or something like `crossers weighted by gradient mass`?

### 2. Did `v2` improve because it created a better ecology, or because it quietly reintroduced BPE-like compressibility?

The compression win is surprising. It may mean:
- the filters found better structural tokens
- or it may mean we moved partway back toward a compressibility-selected vocabulary without admitting it

Question:
- is `v2` actually recovering “good gravity,” or is it rediscovering a disguised BPE prior?

### 3. Is there a hidden **minimum viable medium** for collective crystallization?

`341` crossers was enough to improve the conditional rate, but not enough to saturate it.

Question:
- is there a real critical band like `~500`, `~700`, or `~1000` crossers where the pool qualitatively changes?
- or is the rise smooth all the way up?

### 4. Why do the newly rescued graduates skew so hard toward function words and cheap morphs?

New `v2` graduates include:
- `▁people`, `▁them`, `▁time`, `▁your`, `▁was`, `▁with`, `▁are`
- `vel`, `ew`, `om`, `ay`, `ny`, `rd`, `ld`, `is`, `on`, `in`, `es`, `al`, `ing`

Question:
- did `v1` specifically suppress low-glamour but high-utility connective tissue?
- is gravity’s deepest original sin not “semantic ambition,” but contempt for cheap closure?

### 5. Is `SPACE` just a plumbing token, or is it the first genuine “field token”?

`SPACE` again has enormous energy. It is not just another graduate.

Question:
- is `SPACE` acting like a token-level separator only
- or does it function as a kind of universal scaffold that raises the local crystallization probability of neighboring units?

### 6. Is the remaining ceiling architectural rather than lexical?

The crosser pool underperformed expectations, but that may not be only a floor problem.

Question:
- have we reached the point where tokenizer improvement is now bottlenecked by `12L / 384d / 2000-step` energy budget?
- would the same `v2` vocabulary look qualitatively different at `4000` steps without any further design changes?

## Clean next steps

The clean read from this first witness is:
- `v2` worked
- `v2` did not saturate
- Stage 1 remains the bigger lever
- the remaining ceiling is now the real object

The next decisive experiment should distinguish:
- floor permissiveness
from
- architectural energy budget

## Closing sentence

`v2` did not vindicate the strong theory. It did something better: it proved that the `v1` diagnosis was real enough to engineer against, and it moved the tokenizer onto a new piece of terrain where the next ceiling is visible.
