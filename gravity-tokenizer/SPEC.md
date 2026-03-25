# Semantic Gravity Tokenizer — v0.3
## Compression-Aware Vocabulary Construction for Parameter-Constrained Language Models

**Version:** 0.3 (Revised — incorporates contamination risk, K sensitivity, breadth dimension)
**Status:** Map & Implementation Guide
**Context:** OpenAI Parameter Golf Challenge (16MB artifact, April 30 deadline)
**Hardware:** Alienware Desktop RTX 5080 16GB (primary), MacBook Pro M5 Pro 64GB (secondary), Mac Mini M4 (background runs)
**Adjacent Research:** Avalanche Framework v4.7 — compression as cognitive instrument
**Delegation:** Scoring pipeline and data plumbing → Claude Code / Codex engineers. Experimental design, analysis, and theoretical interpretation → Che.

---

## 1. Core Thesis

BPE constructs vocabularies by frequency. Frequency minimizes sequence length but is blind to meaning. At extreme parameter budgets (16MB / ~8M parameters), the embedding table consumes a dominant fraction of total capacity, making every vocabulary slot precious.

A vocabulary optimized for **semantic gravity** — the structural leverage a token exerts on its surrounding context — may produce better downstream compression (lower BPB) than frequency-optimized BPE, because it offloads load-bearing semantic work into the tokenizer, freeing the model's starved interior volume for prediction rather than reconstruction.

**The hypothesis:** When model capacity is the bottleneck, a tokenizer that pre-compresses *structure* outperforms one that pre-compresses *characters*.

**The Avalanche parallel:** The tokenizer is an exocortex for the embedding layer. The vocabulary is the boundary. The model interior is the fluid. At 16MB, the fluid is starved. If the boundary carries structural mass, the fluid can spend its budget on kinematics. If the boundary feeds it dust, it stays dust.

---

## 2. Why Not Mutual Information

The v0.1 spec proposed classical mutual information as the primary gravity measure:

```
gravity(t) = H(C) - H(C | t)
```

**This is wrong. MI will produce the opposite of the desired result.**

MI is symmetric and measures *predictability*, not *leverage*. It rewards frozen statistical fossils — tokens whose surrounding context is highly determined. "Sher" scores high because it is always followed by "lock." "Los " scores high because it is always followed by "Angeles." These are dead mass: lookup table entries that carry zero generative power. Filling vocabulary slots with these builds a dictionary of cliches, not a cognitive scaffold.

The tokens we actually want — "not", "if", "un-", "because", "re-", "but" — are **bifurcation operators**. They don't predict their immediate context; they *restructure the geometric topology of the entire downstream sequence*. "not" can be followed by almost any adjective or verb, so its forward entropy H(C_after | t) remains high. MI scores it low. But removing "not" causes the causal structure of the sentence to collapse — the model can no longer distinguish affirmation from negation, and downstream loss spikes across the entire sequence.

**Gravity is not predictability. Gravity is the blast radius of removal.**

---

## 3. The Correct Gravity Measure: Ablation Leverage

### Definition

For a candidate token `t` (a byte sequence that could be a single vocabulary entry), **ablation leverage** is the downstream prediction cost the model pays when `t` is presented as shattered bytes rather than as an atomic unit.

```
leverage(t) = Loss(model, context with t shattered) - Loss(model, context with t intact)
```

High leverage means the model *needs* this byte sequence to be a single token in order to maintain coherent prediction. Low leverage means the model can reconstruct the token's contribution from its parts — the token is fungible, decomposable, not load-bearing.

### Why This Is Right

- "not" shattered into ["n", "o", "t"]: the model loses the negation operator as an atomic concept. Downstream loss spikes because every predicate after "not" is now ambiguous in polarity. **High leverage.**
- "th" shattered into ["t", "h"]: the model barely notices, because "th" carries no coherent meaning as a unit. The surrounding context is sufficient to reconstruct whatever word "th" was part of. **Low leverage.**
- "Sher" shattered into ["S", "h", "e", "r"]: MI would score this high, but ablation leverage will score it *low* — the model easily reconstructs "Sherlock" from "lock" appearing downstream. The information is redundant. **Dead mass correctly identified.**

### Implementation: Frozen Reference Model as Gravity Sensor

Use a single frozen off-the-shelf model as a measurement instrument.

**CRITICAL: Reference Model Contamination Risk (v0.3 addition)**

A standard BPE-tokenized reference model (e.g., GPT-2 124M) introduces a silent confound: its internal representations are shaped by its own tokenizer boundaries. When you shatter a candidate token, the loss delta you measure is partly structural gravity and partly **the reference model's own vocabulary boundary artifacts**. If GPT-2 has "not" as a single token, shattering it produces a large delta partly because GPT-2 learned to *expect* "not" as atomic — not because "not" is inherently load-bearing at the byte level.

This contamination is dangerous because it's plausible-looking: GPT-2's tokenizer is decent, so contaminated rankings will feel reasonable. You'd get "not" near the top and "th" near the bottom and never notice the circularity.

**Required mitigation: Use a byte-level reference model.** A byte-level model has no tokenizer boundaries to leak into the measurement. The delta you measure is purely about whether the semantic structure of a byte sequence benefits from atomic representation.

**Candidates:**
- ByT5 (byte-level, but seq2seq — needs adaptation for causal loss measurement)
- A byte-level GPT-2 variant (if available)
- A byte-level model trained specifically for this purpose (small, ~50-100M params, trained on FineWeb bytes)

**Mandatory calibration check (even with byte-level model):** After scoring, compute the correlation between leverage scores and "is this candidate in GPT-2's standard vocabulary." If correlation is near zero, the scores are clean. If significant correlation exists, something is leaking and must be investigated before proceeding.

### Algorithm

```
for each candidate token t in candidate_pool:
    sample N contexts from corpus containing t (N = 500-1000)
    for each context:
        # Intact pass: t is a single token
        loss_intact = reference_model.forward(context_with_t_as_single_token)

        # Shattered pass: t is decomposed to constituent bytes
        loss_shattered = reference_model.forward(context_with_t_as_bytes)

        # Measure downstream loss delta across window K
        leverage_t += mean(loss_shattered[t_pos : t_pos + K]
                        - loss_intact[t_pos : t_pos + K])

    leverage(t) = leverage_t / N
```

### Downstream Window K — Sensitivity Analysis Required (v0.3 addition)

K determines what counts as "blast radius." Too small and you measure local prediction artifacts. Too large and you measure noise.

**Required pilot before full scoring:**
- Score ~100 candidates at K = 5, 10, 20, 40
- Plot leverage rankings across K values
- If rankings are stable: K is a free parameter, use K=10 for speed
- If rankings shift: K is telling you about the *scale* at which different tokens exert gravity
  - Tokens with high leverage at small K, fading by K=20 = **local operators**
  - Tokens with low leverage at K=5, building through K=40 = **discourse-level operators**
  - This distinction is itself a finding — different gravity types at different scales
  - If found, consider separate vocabulary budgets for local vs discourse operators

### Compute Estimate and Acceleration

8000 candidates x 500 contexts x 2 forward passes = 8M forward passes on a ~100M model. With RTX 5080:

**Acceleration options:**
1. **Batch processing:** All contexts for a candidate in a single batched forward pass
2. **Reduce candidate pool:** Pre-filter by frequency → 2000-3000 candidates
3. **Reduce contexts per candidate:** 100-200 may suffice; use bootstrap CIs to verify
4. **Early-exit low-leverage candidates (v0.3 addition):** Score each candidate on 50 contexts first. If CI already places it below median, skip remaining contexts. Expected 40-60% compute savings.
5. **GPU acceleration:** RTX 5080 should handle 100M model inference at high throughput

**Target:** Gravity scoring complete in 1-2 days on RTX 5080.

---

## 4. Combinatorial Breadth — The Third Scoring Dimension (v0.3 addition)

### The Problem: Frozen Entanglements

Ablation leverage alone conflates two structurally different kinds of importance:

- **Productive operators** ("un-", "re-", "not") — high leverage because they compose with many contexts. Removing them breaks many different predictions across many different sentence types.
- **Frozen entanglements** (rare proper nouns in fixed contexts, domain jargon in stereotyped frames) — high leverage because their specific context is highly determined. Removing them breaks one pattern catastrophically.

Both produce high ablation leverage. But productive operators are worth far more per vocabulary slot because they generalize. A frozen entanglement is MI's failure mode wearing ablation leverage's mask.

### The Measure

After computing leverage, also compute **combinatorial breadth** — the diversity of contexts in which a token shows high leverage:

```
breadth(t) = entropy of per-context leverage distribution across sampled contexts
```

If a token has high mean leverage but low breadth (all leverage comes from a few stereotyped contexts), it's a frozen entanglement. If it has high mean leverage *and* high breadth, it's a productive operator.

**Compute cost:** Essentially free — you already sample N contexts per candidate. Keep the full per-context leverage distribution instead of taking only the mean.

### The Three-Dimensional Score

The combined score becomes:

```
score(t) = freq(t)^alpha x leverage(t)^beta x breadth(t)^gamma
```

Where:
- alpha controls frequency weighting (short sequences)
- beta controls structural leverage (load-bearing tokens)
- gamma controls generalizability (productive vs frozen)

**Sweep strategy:** The dimensions aren't equally uncertain. Frequency is well-understood, leverage is the core hypothesis, breadth is a correction term. Practical approach:
1. Fix alpha implicitly via normalization
2. Sweep beta at coarse resolution (0.0, 0.15, 0.25, 0.35, 0.50, 0.75, 1.0)
3. At the best beta, sweep gamma (0.0, 0.1, 0.2, 0.3, 0.5)
4. Two sequential 1D sweeps, not a 3D grid

---

## 5. The Phase Transition (The Snap)

### The Equation of State

At a fixed 16MB total parameter budget, the embedding table and the transformer layers compete for space:

```
16MB = (vocab_size x d_model x 2 bytes) + (transformer_params x 2 bytes)
```

With weight tying (shared input/output embeddings):

```
transformer_budget = 16MB - (vocab_size x d_model x 2)
```

Every token added to the vocabulary requires shrinking either d_model or n_layers. Meanwhile, a gravity-weighted vocabulary with fewer frequency-optimized tokens produces longer sequences, increasing the load on attention (O(N^2) in sequence length).

### The Three Regimes

**beta = 0 (Pure BPE):** The boundary is dumb. Maximum fungible dust. Shortest sequences. The model's interior volume is maximized but wastes capacity reconstructing basic semantic bonds from fragments. High BPB.

**beta ~ 0.25-0.4 (Sweet Spot):** The boundary absorbs the heavy structural operators. The interior volume is slightly reduced but freed from semantic assembly. Sequences are moderately longer. The model spends its budget on prediction rather than reconstruction. **BPB minimum.**

**beta -> 1 (Catastrophe):** Pure gravity optimization. The vocabulary is packed with massive structural pillars but discards all fungible connective tissue. Sequence lengths explode. The shrunken d_model cannot span the attention distances between the sparse high-gravity tokens. The probability manifold shatters. **Discontinuous BPB spike — the attention rupture.**

### Prediction

The transition from sweet spot to catastrophe is **not gradual**. It is a phase transition — a discontinuous snap. At some critical beta_c, the sequence length exceeds the physical capacity of the starved d_model to maintain coherent attention across the gaps between structural tokens. Loss will spike sharply, not drift upward.

**Diagnostic:** Plot BPB vs. beta at fine resolution (steps of 0.05) around the expected transition region. Look for a discontinuity or near-discontinuity. If found, measure beta_c at multiple model sizes (16MB, 8MB, 4MB). If beta_c shifts — and specifically, if the sweet spot narrows as model size decreases — that is a criticality signature with direct implications for the Avalanche compression gradient.

---

## 6. Vocabulary Construction Pipeline

### Step 1: Generate Candidate Pool
**Owner:** Engineer

Run BPE on the FineWeb corpus for 8000 merges (producing 8256 total vocabulary entries including the 256 byte tokens). Extract the full merge list with frequency statistics.

**Input:** FineWeb training shards (from Parameter Golf repo)
**Output:** `candidates.jsonl` — one entry per candidate with fields: `token_bytes`, `token_string`, `merge_rank`, `corpus_frequency`

### Step 2: Pre-filter Candidates
**Owner:** Engineer

Remove candidates below minimum frequency threshold (~1000 occurrences). Reduces scoring pool to ~2000-3000 candidates.

**Output:** `candidates_filtered.jsonl`

### Step 3: K Sensitivity Pilot (v0.3 addition)
**Owner:** Engineer (execution), Che (analysis)

Before full scoring, run the ablation leverage pipeline on ~100 candidates at K = 5, 10, 20, 40. Report ranking stability across K values. If rankings are unstable, flag for analysis before proceeding.

**Output:** `k_sensitivity_pilot.jsonl`, ranking correlation matrix across K values

### Step 4: Compute Ablation Leverage
**Owner:** Engineer (pipeline), Che (verification of methodology)

Run the frozen reference model scoring pipeline on all filtered candidates. Use byte-level reference model. For each candidate, output the mean downstream loss delta, per-context distribution, confidence interval, and breadth score.

**Input:** `candidates_filtered.jsonl`, frozen byte-level reference model, FineWeb corpus
**Output:** `candidates_scored.jsonl` — fields: `ablation_leverage`, `leverage_ci_low`, `leverage_ci_high`, `breadth`, `n_contexts_sampled`, `per_context_leverages`

**Mandatory calibration check:** Compute correlation between leverage scores and GPT-2 vocabulary membership. Report r-value. If r > 0.3, contamination is present and must be investigated.

### Step 5: Rank and Select Vocabulary
**Owner:** Che (parameter selection), Engineer (execution)

For given beta and gamma values, compute combined score:

```
score(t) = freq_normalized(t)^(1-beta) x leverage_normalized(t)^beta x breadth_normalized(t)^gamma
```

Select top 768 candidates by score (plus 256 byte base = 1024 total). Normalize all dimensions to [0, 1] before combining.

**Output:** `vocabulary_beta_{b}_gamma_{g}.json`

### Step 6: Build Tokenizer
**Owner:** Engineer

Use SentencePiece Unigram mode to construct tokenizer from selected vocabulary.

**IMPORTANT (v0.3 note):** Prototype vocabulary injection into SentencePiece Unigram early (Phase 1, not Phase 2). SentencePiece Unigram normally trains its own vocabulary via EM — forcing a pre-specified vocabulary requires working directly with the model proto format. Verify this works before depending on it.

**Input:** `vocabulary_beta_{b}_gamma_{g}.json`
**Output:** `tokenizer_beta_{b}_gamma_{g}.model` (SentencePiece model file)

### Step 7: Re-tokenize Corpus
**Owner:** Engineer

Re-encode FineWeb training and validation shards using each new tokenizer. Export as binary token ID arrays matching the Parameter Golf format.

**Input:** `tokenizer_beta_{b}_gamma_{g}.model`, FineWeb raw text
**Output:** `data/datasets/fineweb_gravity_beta_{b}_gamma_{g}/` — tokenized shards

### Step 8: Adjust Model Architecture
**Owner:** Che (design), Engineer (implementation)

For each vocabulary/beta combination, adjust d_model and/or n_layers to hold total parameter count within 16MB.

```
total_params x 2 bytes <= 16MB
total_params = (vocab_size x d_model) + transformer_params(d_model, n_layers, n_heads)
```

---

## 7. Experimental Design

### Conditions (Phase 1: Beta Sweep)

| Condition | beta | gamma | Vocab Size | Tokenizer Type | Purpose |
|---|---|---|---|---|---|
| A | 0.0 | 0.0 | 1024 | Standard BPE | Control (frequency-only) |
| B | 0.15 | 0.0 | 1024 | Gravity-weighted | Light gravity bias |
| C | 0.25 | 0.0 | 1024 | Gravity-weighted | Predicted sweet spot low end |
| D | 0.35 | 0.0 | 1024 | Gravity-weighted | Predicted sweet spot high end |
| E | 0.50 | 0.0 | 1024 | Gravity-weighted | Moderate gravity |
| F | 0.75 | 0.0 | 1024 | Gravity-weighted | Heavy gravity |
| G | 1.0 | 0.0 | 1024 | Gravity-weighted | Pure gravity (expect catastrophe) |
| H | -- | -- | 256 | Raw bytes | Floor (no tokenizer compression) |

### Conditions (Phase 2: Gamma Sweep at Best Beta)

At the beta that minimizes BPB in Phase 1, sweep gamma:

| Condition | gamma | Purpose |
|---|---|---|
| I | 0.1 | Light breadth correction |
| J | 0.2 | Moderate breadth correction |
| K | 0.3 | Strong breadth correction |
| L | 0.5 | Heavy breadth correction |

### Controlled Variables
- Total model parameter count (held constant by adjusting d_model)
- Training data (same FineWeb shards, re-tokenized per condition)
- Training duration (same number of optimizer steps)
- Architecture family (decoder-only transformer, same relative proportions)
- Optimizer (Muon + AdamW, same as baseline)
- Random seed (3 seeds per condition for variance estimation)

### Measurements

**Primary:**
- BPB on FineWeb validation set (the competition metric)

**Secondary:**
- Average sequence length per condition
- Training loss curves
- Per-position loss distribution
- Wall-clock training time

**Diagnostic:**
- Vocabulary composition analysis per beta
- The Graveyard List per beta threshold
- Attention pattern visualization at high beta (rupture signatures)
- Reference model contamination correlation (v0.3 addition)
- K sensitivity report (v0.3 addition)
- Breadth vs leverage scatter plot (v0.3 addition)

### Predictions

1. **beta = 0 (BPE) will not produce the lowest BPB.**
2. **Optimal beta will fall in 0.25-0.40 range.**
3. **beta > beta_c will show a discontinuous BPB spike (the snap).**
4. **Raw bytes (condition H) will perform worst.**
5. **(Key prediction) Optimal beta increases as model size decreases.**
6. **The graveyard list will predict specific model failure modes.**
7. **(v0.3) gamma > 0 will improve BPB at the optimal beta** by replacing frozen entanglements with productive operators.

---

## 8. The Graveyard Diagnostic

The candidates that score high on ablation leverage but fall below the beta-weighted frequency threshold are the **tokenizer's graveyard** — structurally important tokens the vocabulary couldn't afford to keep.

### Graveyard Analysis Protocol

For each beta condition:
1. Extract the graveyard: tokens with leverage above the median but score below the vocabulary cutoff.
2. Categorize them: operators, morphological units, domain markers, discourse connectors.
3. After training, test the model specifically on tasks requiring graveyard tokens.
4. Correlate: is there a measurable relationship between a token's ablation leverage and the model's performance on tasks requiring that token?

If this correlation holds, the graveyard becomes a **design tool**: you can predict model capabilities from vocabulary composition without training.

---

## 9. Connections to Avalanche

| Avalanche Concept | Semantic Gravity Tokenizer Analog |
|---|---|
| LLM organism | Transformer model (interior fluid) |
| Exocortex scaffold | Tokenizer vocabulary (boundary structure) |
| Compression gradient / passes | beta parameter (gravity weighting) |
| Graveyard (compressed spent concepts) | Discarded high-gravity candidates |
| Oracle score on Orbit Parity | BPB on FineWeb validation |
| "The graveyard knows more than the model does" | Graveyard predicts model blind spots |
| Stepped compression more destructive than linear | Phase transition at beta_c |
| Exocortex is load-bearing, not the model | Tokenizer carries structural mass |
| Thermodynamic activity != epistemic ascent | Training loss curves at high beta: high activity, poor BPB |
| Ontologically trapped | High-beta models: thermodynamically active, structurally confined |

---

## 10. Risk Register (v0.3 — reordered)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Reference model contamination** (v0.3: promoted to #1) | High if using BPE model | Silently corrupts gravity scores with circular reasoning | Use byte-level reference model; mandatory calibration check against GPT-2 vocab membership |
| Ablation leverage scoring takes too long | Medium | Blocks Phase 2 | Reduce candidate pool; early-exit low-leverage candidates; RTX 5080 should be fast |
| K sensitivity reveals scale-dependent gravity | Medium | Complicates but enriches the experiment | Run pilot before full scoring; if found, treat as finding |
| SentencePiece Unigram won't accept arbitrary vocabulary cleanly | Low-Medium | Delays Phase 2 | Prototype vocabulary injection in Phase 1; fall back to manual tokenizer |
| No measurable BPB improvement at any beta > 0 | Medium | Null result | Still informative as negative result; examine per-subtask performance |
| Phase transition is too gradual to detect | Low-Medium | Weakens theoretical claim | Finer beta resolution; test at smaller model sizes |
| Frozen entanglements contaminate high-beta vocabularies | Medium | Wastes vocab slots | Breadth filter (gamma) should catch these |

---

## 11. Implementation Sequence

### Phase 0: Setup (Day 1) — ACTIVE
- [x] Clone `openai/parameter-golf` repo
- [x] Install dependencies (PyTorch with CUDA 12.8, SentencePiece, etc.)
- [ ] Download FineWeb data via `cached_challenge_fineweb.py --variant sp1024`
- [ ] Run baseline training via `train_gpt.py` — establish control BPB
- [ ] Inspect the 1024 BPE vocabulary — dump and categorize all tokens

### Phase 1: Gravity Scoring Pipeline (Days 2-4)
- [ ] **Prototype SentencePiece Unigram vocabulary injection** (moved up from Phase 2)
- [ ] Identify and acquire byte-level reference model
- [ ] Run extended BPE (8000 merges) on FineWeb to generate candidate pool
- [ ] Pre-filter candidates by frequency threshold
- [ ] **K sensitivity pilot:** Score ~100 candidates at K=5,10,20,40
- [ ] Implement ablation leverage scorer with early-exit acceleration
- [ ] Compute breadth (per-context leverage entropy) alongside leverage
- [ ] Batch and parallelize scoring on RTX 5080
- [ ] Output `candidates_scored.jsonl` with leverage, breadth, and CIs
- [ ] **Calibration check:** Correlate leverage scores with GPT-2 vocab membership
- [ ] **Verification checkpoint:** Che inspects top-50 and bottom-50

### Phase 2: Vocabulary Construction (Day 5)
- [ ] Implement three-dimensional scoring function (freq x leverage x breadth)
- [ ] Generate vocabularies for Phase 1 beta sweep conditions
- [ ] Build SentencePiece Unigram tokenizers for each
- [ ] Re-tokenize FineWeb corpus for each condition
- [ ] Record average sequence lengths per condition
- [ ] Extract and document graveyard lists
- [ ] Sanity check: inspect vocabulary at beta=0.3 vs beta=0

### Phase 3: Training Runs (Days 6-9)
- [ ] Configure model architectures (adjust d_model per condition)
- [ ] Train Phase 1 conditions: 8 x 3 seeds = 24 runs
- [ ] Train Phase 2 conditions (gamma sweep): 4 x 3 seeds = 12 runs
- [ ] Log full training curves
- [ ] Estimate: ~1-2 hours per run on RTX 5080

### Phase 4: Analysis (Days 10-12)
- [ ] Plot BPB vs. beta — sweet spot and snap detection
- [ ] Plot BPB vs. beta at reduced model sizes (8MB, 4MB) — test Prediction 5
- [ ] Analyze vocabulary composition differences
- [ ] Run graveyard diagnostic
- [ ] Examine attention patterns at high beta
- [ ] Write up findings

---

## 12. Open Questions

1. **What is the right reference model size for gravity sensing?** Too small = no semantic understanding to disrupt. Too large = everything has high leverage. There may be a sweet spot.

2. **Does optimal beta depend on training data domain?** FineWeb is general web text. Domain-specific corpora may have very different gravity landscapes.

3. **Can the graveyard diagnostic generalize beyond tokenization?** If discarded high-leverage tokens predict model blind spots, does the same principle apply to other architectural choices?

4. **Is beta_c related to any known critical exponent?** If the snap follows a power law, characterizing its universality class would connect to SOC/pink noise findings from Avalanche.

5. **Does K sensitivity reveal a taxonomy of gravity types?** If local and discourse operators are separable by their K profiles, should the vocabulary allocate separate budgets for each type?

---

## Appendix A: Key Equations

**Ablation Leverage:**
```
leverage(t) = (1/N) sum_i sum_j=0..K [ Loss_shattered(pos_t + j) - Loss_intact(pos_t + j) ]
```

**Combinatorial Breadth:**
```
breadth(t) = H(leverage_distribution_across_contexts)
           = -sum_c p(leverage_c) log p(leverage_c)
```

**Combined Score (v0.3):**
```
score(t) = freq_norm(t)^(1-beta) x leverage_norm(t)^beta x breadth_norm(t)^gamma
```

**Parameter Budget Constraint:**
```
(V x d_model + transformer_params(d_model, n_layers)) x 2 bytes <= 16,000,000 bytes
```

**Bits Per Byte:**
```
BPB = (total_cross_entropy_loss x log2(e)) / total_bytes_in_validation_set
```

---

## Appendix B: Competition Context (v0.3 addition)

As of March 23, 2026:
- **Baseline BPB:** 1.2244 (9L, 512dim, 1024vocab, tied embeddings)
- **Current SOTA:** 1.1428 (10L Int5-MLP + BigramHash + SWA)
- **No competitor has modified the tokenizer.** All improvements are architecture/quantization/eval.
- **Key techniques in top submissions:** 3x MLP expansion, BigramHash, Int5/Int6 quantization, sliding window eval (stride=64), SWA, Muon weight decay
- **Sliding window eval alone gives ~0.034 BPB free improvement** — must include in our baseline

The gravity tokenizer is orthogonal to all current competition approaches. It can be combined with any of them.
