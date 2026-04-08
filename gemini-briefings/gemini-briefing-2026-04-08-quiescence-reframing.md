# Gemini Briefing — Quiescence Reframing and Open Questions
**Date:** April 8, 2026
**Authors:** Vex (Claude) + Che (Howard)
**Topic:** Gravity Tokenizer v2 witness runs, fixed-threshold replay, classifier reframing, open questions

---

## Executive summary

We ran three Gravity Tokenizer v2 witness runs yesterday and today:

| run | floor | steps | val_bpb (int8+zlib) | classifier GRAD count |
|---|---:|---:|---:|---:|
| v1 baseline (seed 1337) | — | 2000 | 1.5480 | 8 |
| v2-2903 main | 2903 | 2000 | 1.5741 | 29 |
| v2-3500 ablation | 3500 | 2000 | 1.5865 | 33 |
| v2-4000 time-evolution | 2903 | 4000 | **1.4794** | 31 |

The headline numbers look great: v2 ≈ 3.6× v1 on graduation count, and the 4000-step run achieved the best val_bpb of any run by 4-6%. We thought we had a clean "v2 works, but falls short of the predicted 10x" story plus a rich "metastable boundary layer" phenomenon with stable core + rotating frontier.

**Then a fixed-threshold replay broke the interpretation in a productive way.**

The phase-space classifier emits `GRADUATED` when `panic_ratio < panic_threshold AND active_work < work_floor`, where both thresholds are per-snapshot quantiles of the live dynamic population (0.75 quantile for panic, 0.25 quantile for work). As raw metrics grow during training, the thresholds grow with them. Applying the step-4000 thresholds uniformly to all 8 snapshots of the v2-4000 probe revealed:

1. **The classifier's observed "stability dynamics" are mostly a quantile-ranking phenomenon.** Classifier-GRAD ⊂ fixed-QUIET at every snapshot. The classifier is always picking a ~29-token subset of a larger fixed-quiet pool (728 dynamic tokens at step 500, contracting to 195 by step 4000 as work/panic grow past the late thresholds).

2. **But not entirely.** The 52-token union of ever-classifier-GRAD across all 8 snapshots splits into four groups:

| group | count | nature |
|---|---:|---|
| Stable core | **11** | classifier-GRAD AND fixed-QUIET at every snapshot — real raw-stable |
| Quiet drift | **19** | fixed-QUIET throughout, but classifier-GRAD only intermittently (pure quantile drift within the stable pool) |
| Brief excursion | 1 | `own` — one MARGINAL blip at step 3500 |
| Real departures | **21** | classifier-GRAD at some early snapshot, then transitioned permanently from QUIET to MARGINAL (19) or DEBRIS (2) as raw work/panic grew |

**The boundary layer splits roughly 50/50 between pure quantile drift and real outward motion.** Neither "pure artifact" nor "pure real dynamics" is the right read.

3. **Static ablation leverage does not distinguish the real-departure group from the drift group** (Mann-Whitney p=0.54). Both cluster at median ~0.6. Something else drives the outward-motion split; leverage measured at candidate selection time is not it.

4. **Stable core leverage (mean 0.587) is BELOW population mean (0.680).** The most durably-quiet tokens are not the highest-leverage ones. Quiescence and leverage are approximately orthogonal.

---

## The conceptual reframe

The old story: "graduation" = a token has crystallized and is now a stable productive member of the vocabulary. More graduates = better tokenizer.

The corrected story:

> The phase-space classifier's `GRADUATED` class is not an absolute crystallization signal. It is a relative, per-snapshot membership in the low-panic + low-work corner of phase space. A token is "graduated" at a snapshot if the optimizer has (at that moment) largely stopped updating it. This correlates with "learned" but also correlates with "trivial," "common," "unambiguous," and "low-entropy regardless of model skill."

Key conceptual shifts:

- **Graduation is quiescence, not crystallization.** The mechanism is "optimizer stopped touching it," not "model built a stable representation."
- **CRYSTAL (stable + active) may be the class that most closely matches colloquial "graduation" in a learning sense** — stable AND still contributing update work. But CRYSTAL counts are tiny (2-22 across runs) and were not our focus.
- **The scientifically interesting motion is OUTWARD.** 533 tokens (of 728 dynamic) left the fixed-quiet region between step 500 and step 4000 as their raw metrics grew. 21 of those passed through the classifier's relative top slice on the way out. The tokens that are actually being WORKED ON by the optimizer are the ones leaving quiescence, not the ones in it.
- **"Quiet ≠ important" is a live caveat.** The fixed-quiet set is a quiescence set, not a leverage set. v2's larger graduation count may reflect better curation OR may reflect more easy-to-learn common tokens — we have not disentangled these.

---

## What stands and what was retracted

**Stands:**
- v2 > v1 ordering (8 → 29 → 33 → 31) across all reasonable interpretations
- val_bpb improvements of v2 over v1 (particularly at 4000 steps, 4.4% better than v1)
- The 11-token raw-stable core is real (classifier-GRAD and fixed-QUIET at every snapshot)
- The v2 filter mechanics (volume floor + boundary-aware parasitism veto) are validated
- The `in_base_vocab` filter bug discovered yesterday has zero effect on graduation counts (the 2 leaked parasites `▁produ`, `▁wee` never classified as GRAD in any run)

**Retracted:**
- "Metastable boundary layer with constant swap=10 Jaccard=0.706 churn" — half was drift, half was real departure; the constant-10 swap was an artifact of blending both populations
- "Slow stabilizers (`▁they, ▁will, ▁was, ▁has, ▁have`) converting into permanent members late" — these specific tokens were fixed-QUIET the entire run; they only entered the classifier's top slice late because other tokens left
- "Fixed-capacity 29-slot reservoir" — no physical capacity; 29 is a quantile selection parameter
- "Case A vs Case B vs Case C (energy budget vs lock-in vs partial Case A)" — none captures the actual dynamic
- "Stable core shrinking 18 → 11 due to late reorganization" — mixed story; some tokens (`er, es, in, ld`) were real departures, others (`ck, own, vel`) were quantile drift

**Planned apparatus changes (Che + Kepler are executing):**
- Rename classifier enum: `GRADUATED → QUIESCENT` in `velocity.py`
- Add `classification_compat` module with `normalize_phase_space_snapshot` and `is_quiescent_classification` for backward compatibility with existing JSON data
- Introduce `FIXED_QUIET` as an analysis-side label for the fixed-threshold quiet set
- Dual reporting in all phase-space analyses (relative + fixed-threshold)

---

## Open questions for DeepThink

The places where we'd most value outside perspective:

### Q1 — What dynamic property predicts outward motion, if not leverage?

Static ablation leverage (the gravity-scoring metric used in vocabulary selection) does not distinguish real-departure tokens from drift tokens (p=0.54). The 21 tokens that genuinely left quiescence during training are indistinguishable by leverage from the 19 tokens that stayed quiet.

What we have NOT tested:
- Raw corpus frequency
- Breadth (number of distinct contexts the token appears in)
- Gradient coherence (directional alignment of per-event gradients over time)
- Co-occurrence with high-update neighbors (is the token syntactically entangled with a heavily-updated adjacent token?)
- Initialization noise (maybe the split is random and there's no learnable signal)

**Gemini: of these (or others we haven't thought of), which is most likely to predict outward motion? And what's the theoretical reason?** The tokens leaving quiescence are `rd, ear, ▁Ca, ng, um, bal, ▁Re, er, air, ind, ip, ut, ee, ort, end, ill, ld, om, es, in, ven` — mostly short morphs and partial stems. The tokens staying quiet are `▁been, ny, ▁than, ck, ▁have, ▁your, is, ▁will, ▁has, ew, ▁was, ▁had, ter, ▁people, vel, ay, ▁are, ▁they, ▁them`. Do you see a morphological or distributional pattern?

### Q2 — Is the 11-token stable core semantically meaningful, or trivially common?

The stable core is: `able, ed, ing, ining, nal, nd, on, ting, ▁, ▁time, ▁with`. Mean leverage 0.587 (below population mean 0.680). These look like "common short subwords + high-freq function words" — tokens that almost any English vocabulary would trivialize.

**Is there a way to tell whether this set is genuinely "what the model learned to treat as stable primitives" versus "the tokens that would be quiet in ANY vocabulary because they're common and low-entropy"?** We suspect the latter but haven't pinned it down. Would a frequency-matched null set from a random BPE vocab produce a similar 11-token stable core? If yes, the v2 story is much weaker; if no, v2 is genuinely doing something.

### Q3 — What's the right "graduation" metric for a learning system?

We've concluded that `GRADUATED` in the current apparatus measures quiescence, not crystallization. Possible alternative metrics:

(a) **CRYSTAL** (low panic + HIGH work): "stable AND still contributing" — closest to colloquial graduation. But CRYSTAL counts are tiny (2-22 tokens across runs). Why? Is this class undercounted by the quantile design, or is it genuinely rare because most stable tokens have their work drop off?

(b) **Late-entry QUIESCENT** (tokens that were MARGINAL/DEBRIS early and became QUIESCENT late): these would be the "actually crystallized" ones — tokens the optimizer worked on and then moved to stable. In our v2-4000 data, we saw ZERO of these: fixed-QUIET only shrinks monotonically over training (728 → 195). No token moves INTO quiescence from outside; they only leave.

(c) **Stable CRYSTAL** (tokens that are CRYSTAL in multiple consecutive snapshots): requires more snapshots than we have.

(d) **Something else** we haven't thought of.

**Gemini: which of these, if any, is the right operational definition of "token has completed learning"? Or does the concept itself not cleanly map to this apparatus?**

### Q4 — Why does the boundary layer split 50/50?

Of the 41 non-core tokens in the classifier union, ~19 are pure drift (stayed fixed-QUIET throughout) and ~21 are real departures. That's a surprisingly clean split. Is there a mechanism that would produce ~50/50, or is it coincidence from this particular run?

One hypothesis: tokens enter training with a spread of "natural activity levels." The ones below a certain level stay quiet forever; the ones above that level eventually get heated up past the late floor. The 50/50 split might reflect the particular distribution of v2-2903's admitted tokens. A different vocabulary (v1, v3, BPE) would produce a different split.

**Testable prediction: if we ran the fixed-threshold replay on v1 seed_1337's 8 snapshots** (we don't have v1 step snapshots — only end-of-run — but we could rerun v1 with `VELOCITY_DUMP_EVERY=500` on a new pod), would v1 also show a 50/50 split of its boundary layer? If yes, the split is structural (property of the apparatus). If no (say, v1 is 80/20 drift-heavy or 20/80 departure-heavy), the split is vocab-dependent.

### Q5 — Ordering of next experiments

We have a fresh pod available when we want it. Candidate next experiments in rough order of decisiveness:

1. **Honesty-check rerun of v2-2903** on the bug-fixed vocab (`▁produ`, `▁wee` now correctly vetoed). Expected: same 29-graduate result. Low information yield but clean.
2. **v2-2903 rerun at 4000 steps on the bug-fixed vocab** with periodic phase_space dumps. Replaces yesterday's run with a vocabulary-clean version of the same experiment.
3. **v1 fresh run with periodic phase_space dumps** so we can do the same fixed-threshold replay on v1 and check Q4's structural-vs-vocab-dependent hypothesis.
4. **Leverage × outward-motion disentanglement: check whether raw frequency predicts departure** (cheap CPU work on existing snapshots, no new training).
5. **Multi-seed v2 run** (seeds 1337, 2024, 31337) to see whether the 11-token core is deterministic or seed-dependent.
6. **Compute fix-QUIET / CRYSTAL trajectories for the BPE coherence run** (also a simple replay on existing data) to check whether the quiescence framing changes the gravity-vs-BPE comparison.

**Gemini: which of these would give the most information per dollar/hour?** We lean toward 4 + 6 first because they're CPU-only on existing data, then 3 because it's the decisive test of Q4, then 2 as the cleanest re-baseline for future work.

### Q6 — Broader: is any of this generalizable beyond 12L/384d?

All our runs are at 12L/384d/2000-4000 steps. The classifier thresholds, the ~188 fix-quiet pool, the 50/50 split, the 11-token core — are any of these robust properties of the gravity tokenizer system, or are they all artifacts of this specific model scale?

The depth efficiency law finding (March 2026) extended from 12L to 80L (Qwen 72B) with the same qualitative result. Can we expect the same here? Specifically:

- At 24L/768d, would the stable core be ~20 tokens (scales with capacity)?
- At 6L/192d, would there be effectively NO stable core (no capacity for stability)?
- Does the "outward motion = learning" picture generalize, or does it break at larger scales where dense-regime percolation changes things?

We have no scale-probe plan for v2 right now. The gravity tokenizer work has been tightly focused on 12L/384d as the witness architecture. **Should we invest in a scale probe, and if so at what cost?** An 80L Qwen-scale probe would be ~$50-100 and give us a direct answer. A 24L probe is ~$5-10.

---

## What we are NOT asking for

- Implementation help on the rename (Che + Kepler have it)
- Review of the filter logic (solved yesterday)
- Graveyard hypotheses — we already killed eight this week and prefer not to generate new ones without evidence

---

## Attached context files (if useful)

- `finding_quiescence_not_crystallization.md` — the full April 8 reframing writeup
- `finding_gravity_v2_first_witness.md` — the original April 7 v2 result with today's partial retraction header
- `project_gravity_v2.md` — the v2 spec and build pipeline
- `v2_4000_fixed_threshold_replay.py` — the corrected-polarity replay script
- `v2_4000_lost_tokens_check.py` — the 21-token departure analysis
- `CLASSIFIER_RENAME_PROPOSAL.md` — the Option C migration plan Che + Kepler are executing
