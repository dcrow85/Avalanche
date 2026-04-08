# Classifier Rename Proposal: GRADUATED → QUIESCENT

**Date:** April 8, 2026
**Author:** Vex
**Status:** Executed via Option C. Harness-side rename lives on the `parameter-golf`
research branch `research/quiescence-rename-2026-04-08` (dcrow85 fork). Avalanche
analysis scripts now normalize legacy `GRADUATED` data to `QUIESCENT` on read.

## Motivation

The April 8 fixed-threshold replay showed that the phase-space classifier's
`GRADUATED` label does not measure token crystallization in any absolute sense.
It measures a relative top slice of the quiescence quadrant (`panic_ratio <
panic_threshold AND active_work < work_floor`, both thresholds per-snapshot
0.75/0.25 quantiles).

The word "graduated" carries strong connotations of completed learning,
achievement, and absolute success. Those connotations were the seed for the
"metastable boundary layer" misinterpretation we had to retract — the
intuition that tokens were either "graduated" (success) or "waiting to
graduate" (in-progress) pulled analysis toward a promotion/acceptance narrative
that the data does not support.

A neutral, mechanism-accurate name prevents future misreadings.

## Proposed name

**`QUIESCENT`**

Reasons:
- Precise: literally "low activity," which is exactly what `work < work_floor`
  plus `panic < panic_threshold` measures.
- Neutral: no implied value judgment about whether quiescence is good or bad.
  (A token can be quiescent because it was learned cleanly, OR because it's
  low-signal and never became active. Both are legitimate routes to
  quiescence.)
- Matches established usage in neural dynamics literature (quiescent =
  low firing rate / low update).
- Short and typable.

Alternatives considered and rejected:
- `SETTLED`: softer, but still connotes success.
- `LOW_ACTIVITY`: descriptive but verbose, and clashes with `ACTIVE_WORK` naming.
- `DORMANT`: too close to "inactive" (could imply the token isn't used).
- `STABLE_QUIET`: compound, awkward.

The other classifier classes stay as-is:
- `CRYSTAL`: stable AND active (low panic, high work). This is the class
  that most closely resembles the colloquial "graduated." It's stable AND
  contributing.
- `DEBRIS`: high panic. Chaotic. Good name.
- `MARGINAL`: in between. Good name.
- `IMMATURE`: not yet calibrated. Good name.
- `STATIC`: core seed token. Good name.

## Impact surface

### Harness (2 files)

- `velocity.py` line 139: `return "GRADUATED"` → `return "QUIESCENT"`
- `mutation_engine.py` line 123: `{"DEBRIS", "GRADUATED"}` → `{"DEBRIS", "QUIESCENT"}`

### Analysis scripts (15+ files in `scripts/`)

Every analysis that filters by `classification == "GRADUATED"` or checks
`class_counts["GRADUATED"]`. Files touched:

- `analyze_bigram_entropy.py` (4 occurrences)
- `analyze_bpe_coherence.py` (1)
- `analyze_predecessor_entropy.py` (3)
- `analyze_v2_4000_trajectory.py` (3)
- `frequency_matched_graduation_compare.py` (2)
- `probe_record_formation_rate_coarse.py` (5+)
- `stage2_decision_tree.py` (1)
- `tuesday_protocol.py` (8+)
- `v2_4000_fixed_replay.py` (1)
- `v2_4000_fixed_threshold_replay.py` (1 + docstring)
- `wednesday_protocol.py` (4)

### Data files

Every existing phase_space snapshot JSON and coherence_snapshot JSON contains
the literal string `"GRADUATED"` in per-token classification fields and in
`class_counts` dicts. That's hundreds of files across:
- `parameter-golf/logs/coherence_seed_1337/`
- `parameter-golf/logs/coherence_bpe_seed_1337/`
- `parameter-golf/logs/coherence_v2_seed_1337/` (including all 8 v2-4000 step snapshots)
- `/workspace/logs/` on any future pod

## Migration strategy

**Option A: Hard rename, break old data.** Simplest to code. Old snapshots
become unreadable by new analysis scripts. Bad.

**Option B: Hard rename, one-time migration script.** Write a script that
walks all JSON files and rewrites `"GRADUATED"` → `"QUIESCENT"`. Then update
code. Old data stays analyzable but only after migration. Medium invasive.

**Option C: Rename at source, compat-shim at read.** Harness emits
`"QUIESCENT"` going forward. Every analysis script that reads phase_space
snapshots includes a one-line normalization:
```python
cls = row.get("classification")
if cls == "GRADUATED":
    cls = "QUIESCENT"
```
Or a shared helper. Old data works without migration; new data is clean.
Requires updating every analysis script that reads the field, but the change
is mechanical. **Recommended.**

**Option D: No code rename. Documentation only.** Keep `GRADUATED` as the
string literal in code and data. Require all writeups, plots, and memory
entries to say "classifier QUIESCENT class (legacy label: GRADUATED)". Least
invasive but highest risk of the misread recurring, because the string literal
is the primary artifact future readers encounter.

## Recommendation

**Option C.** Source-side rename + normalization helper at read time. Concrete
steps:

1. Add `QUIESCENT_ALIASES = {"GRADUATED", "QUIESCENT"}` to a shared module
   (e.g., `coherence.py` or a new `classification.py`).
2. Add `normalize_classification(cls)` that returns `"QUIESCENT"` for either input.
3. Update `velocity.py` line 139 to return `"QUIESCENT"`.
4. Update `mutation_engine.py` line 123 to use the alias set.
5. Update each analysis script to call `normalize_classification()` at the
   single point it reads `classification` from a row. Alternatively, a
   wrapper `load_phase_space_snapshot()` that normalizes on load.
6. Add a unit test that loads an old snapshot and confirms normalization.
7. Leave existing JSON data files untouched.

Estimated time: 1-2 hours of careful editing, plus running the full analysis
pipeline on the existing data to confirm nothing breaks.

## Risk: breaking existing analysis reproducibility

Anyone re-running an old analysis script on old data will get the same numbers
they did before (the data hasn't moved). Anyone running a new analysis script
on old data gets normalized behavior. Anyone running a new script on new data
sees the clean name. The only break is: old scripts on new data without the
normalization helper. Acceptable as long as new scripts are the canonical path.

## Decision outcome

Che approved Option C and the `QUIESCENT` name.

What was executed:
1. `velocity.py` now emits `QUIESCENT` instead of `GRADUATED`.
2. A shared compatibility helper normalizes legacy snapshots on read.
3. Active analysis scripts now speak `QUIESCENT` / `FIXED_QUIET`.
4. Historical JSON artifacts were left untouched, preserving reproducibility.

This file remains as the design rationale behind the change.
