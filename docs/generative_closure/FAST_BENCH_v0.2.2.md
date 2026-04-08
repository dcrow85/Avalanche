# Generative Closure — Cellular Automaton Drosophila

**Spec v0.2.2 — Fast Bench**

---

## 0. Purpose

This document specifies **v0.2.2** of the Fast Bench for empirical validation of the Generative Closure architecture on a binary cellular-automaton substrate.

The Fast Bench is designed to answer a narrow question:

> Does a generator, operating against an exact posterior and a diagnostic graveyard, produce monotonic closure, measurable structural fallout from broken high-assembly commitments, and a controllable transition between subcritical, critical, and supercritical wagering regimes?

The bench is deliberately **thermodynamic, not semantic**. The hidden truth is a finite binary object. Oracle interaction is a budgeted sequence of exact linear measurements. There is no language model inside the substrate and no ambiguity in the update rule.

v0.2.2 inherits the structural corrections of v0.2.1 and adds four implementation clarifications:

1. **The posterior is exact and affine.** It is not inferred from a graveyard complement.
2. **Bundle failure no longer over-eliminates.** Large conceptual wagers are probed through budgeted witness rows, not buried wholesale on a single binary fail.
3. **Criticality is measured in batched throughput mode.** A single 512-bit episode cannot support million-scale informative cycles.
4. **The bench claim is scope-limited.** v0.2.2 does not test whether graveyard residue alone constitutes epistemic memory; it tests whether generator access to prior contradictions, mediated by retrieval depth and constrained by an exact posterior, produces robust phase structure.

In particular, v0.2.2 requires that:

- pure-heat attempts are recorded in the diagnostic index rather than silently skipped,
- the diagnostic index $I_t$ is treated as the primary retrieval interface while $G_t$ remains an auxiliary algebraic operator,
- structurally ambitious generator policies perform a feasibility preflight against the current posterior before instantiating a family claim, and
- criticality estimation uses reset-aware robust spectral methods rather than raw log-log regression alone.

The Drosophila is not a model of cognition. It is an instrument for measuring whether the mechanics of Generative Closure survive exact bookkeeping.

---

## 1. Substrate

The hidden truth is a binary cellular automaton rule on a Moore neighborhood of radius 1.

- **Cell state:** $\{0,1\}$
- **Neighborhood size:** 9 cells (center + 8 Moore neighbors)
- **Configuration count:** $2^9 = 512$
- **Rule space:** $\mathbb{F}_2^{512}$
- **Hidden truth:** a single rule vector $T \in \mathbb{F}_2^{512}$

A coordinate $T_i$ is the output bit for neighborhood configuration $i$ under a fixed global indexing of the 512 neighborhoods.

### 1.1 Hidden-rule pool

The initial campaign must use a **stratified pool**, not a single curated bucket.

Minimum Day-1 requirement:

- **5 library-aligned structured rules**
  - e.g. Life-like / outer-totalistic rules and other rules strongly aligned with the primitive library.
- **5 structured but adversarial rules**
  - rules with real internal structure that are only weakly aligned, or misaligned, with the primitive library.
- **5 random rules**
  - uniform samples from $\mathbb{F}_2^{512}$.

This prevents the bench from “validating” only because the primitive library was pre-fit to the truth distribution.

The exact rule identities for each stratum must be fixed in a **versioned manifest** before the first throughput run.

For a given manifest version, that manifest artifact is **canonical**. Supporting analysis scripts may verify primitive ranks, search adversarial candidates, or print sanity tables, but they must not overwrite the canonical manifest unless they are the single final assembly step that emits the frozen campaign artifact.

---

## 2. State Representation

v0.2.2 separates **exact knowledge** from **diagnostic memory**.

### 2.1 Exact knowledge operator

The exact posterior is maintained as an affine constraint system

$$
\mathcal{A}_t = \{x \in \mathbb{F}_2^{512} : M_t x = b_t\}
$$

where:

- $M_t \in \mathbb{F}_2^{m_t \times 512}$ is maintained in reduced row-echelon form
- $b_t \in \mathbb{F}_2^{m_t}$ is the corresponding right-hand side
- $m_t = \mathrm{rank}(M_t)$

The remaining uncertainty is

$$
d_t = 512 - m_t
$$

which is both:

- the **affine dimension** of the posterior, and
- the **log-posterior size in bits**, since $|\mathcal{A}_t| = 2^{d_t}$.

This quantity is the entropy analog for the Fast Bench. Define

$$
H_t = d_t
$$

in bits.

- **Initial state:** $M_0$ empty, $b_0$ empty, $d_0 = 512$
- **Terminal state:** $d_t = 0$, equivalently $m_t = 512$

Closure means the posterior contains exactly one rule.

### 2.2 Diagnostic graveyard

The graveyard is **not** the posterior.

It is a diagnostic operator

$$
G_t \in \mathbb{F}_2^{g_t \times 512}
$$

maintained in RREF, whose row span contains the witness rows on which prior family predictions were contradicted by the oracle.

The graveyard exists to answer questions of the form:

- Which structural directions has the generator been wrong about before?
- Is it rebuilding on previously falsified conceptual scaffolding?
- Does increasing retrieval depth reduce repeated rebuilding on dead ground?

The graveyard has no authority to eliminate candidate rules by itself. Only the exact knowledge operator $(M_t, b_t)$ updates the posterior.

The graveyard should be understood as an **auxiliary algebraic operator**, not the main semantic retrieval surface. Its raw RREF rows are useful for overlap arithmetic and diagnostics, but meaningful retrieval-depth behavior is expected to flow primarily through the indexed family metadata in $I_t$.

### 2.3 Diagnostic index

Maintain a secondary index $I_t$ over historical family wagers. Each record stores:

- cycle id
- episode id
- family type and metadata
- nominal family rank
- novel family rank at query time
- witness rows actually queried
- predicted witness bits
- observed witness bits
- mismatch mask
- pure-heat / no-witness flag
- links to retrieved prior families, if any

The generator may consult $I_t$. It does **not** need to search raw history.

For v0.2.2, $I_t$ is the **primary retrieval object** for the generator. It is the place where prior contradictions, redundancies, and pure-heat attempts become legible as reusable structure. The graveyard $G_t$ remains available for algebraic overlap calculations, but the generator is not expected to recover semantic family boundaries from raw RREF rows alone.

### 2.4 Point hypothesis

Each cycle the generator also maintains a point hypothesis

$$
h_t \in \mathcal{A}_t
$$

used for:

- producing concrete predictions for witness rows,
- instantiating family templates, and
- logging the generator’s current guess.

---

## 3. Conceptual Wagers, Families, and Witnesses

The generator does **not** wager the entire posterior on a single binary bundle test.

Instead, each cycle it proposes a **conceptual family**

$$
\mathcal{F}_t = (C_t, \text{metadata}_t)
$$

where:

- $C_t \in \mathbb{F}_2^{k_t \times 512}$ is a row matrix representing a family of linear observables,
- $k_t = \mathrm{rank}(C_t)$ is the **nominal family rank**, and
- the metadata records the primitive composition and construction history.

The generator also outputs a point hypothesis $h_t \in \mathcal{A}_t$, which induces the family prediction

$$
\hat y_t = C_t h_t \in \mathbb{F}_2^{k_t}
$$

after the same row operations used to reduce $C_t$ to a basis.

The family is the **conceptual stake**. The bench does not immediately query all $k_t$ rows. Instead it projects the family against current knowledge, then samples a fixed-budget witness set from the novel fragment.

### 3.1 Witness budget

Let $B_q$ be the fixed per-cycle oracle budget, in rows. Default:

$$
B_q = 8
$$

The witness budget is a load-bearing control parameter. Without it, a single large family could collapse the entire 512-bit posterior in a handful of cycles, making cross-policy comparisons meaningless.

### 3.2 Pure heat

A cycle is **pure heat** if the proposed family contains no novel directions after projection against the current exact knowledge operator.

Such cycles still count toward total cycle count in throughput mode, but they do not reduce posterior uncertainty.

---

## 4. Primitive Library

Each family is composed from one or more primitive templates. A primitive contributes a row matrix (or a family of row matrices) and metadata about its assembly depth.

### 4.1 Atomic coordinate families (assembly index 1)

Query a set of explicit rule coordinates:

$$
T_i, \quad i \in Q \subseteq \{0,\dots,511\}
$$

Matrix form: rows are standard basis vectors $e_i$.

- Nominal rank: $|Q|$
- Cheap
- Granular
- No built-in structural leverage

### 4.2 Symmetry families (high assembly)

A symmetry family asserts that the rule behaves as though generated by a spatial or color symmetry. Operationally, it contributes equality or affine-equality rows between coordinates related by the corresponding action.

Examples:

1. **90° rotation ($C_4$)**
   - rows of the form $e_i + e_{g(i)}$
   - exact nominal rank: **372**

2. **Horizontal reflection ($\mathbb{Z}_2$)**
   - rows of the form $e_i + e_{g(i)}$
   - exact nominal rank: **224**

3. **Full dihedral symmetry ($D_4$)**
   - rows induced by the full orbit-equivalence relation
   - exact nominal rank: **410**

4. **Color inversion / complement symmetry**
   - rows of the form $e_i + e_{\bar i}$
   - exact nominal rank: **256**
   - note: the predicted bit need not be zero; a complement-symmetric hypothesis predicts 1 on these rows

5. **Outer-totalistic reduction**
   - rows equating all coordinates with the same $(\text{center bit}, \text{neighbor live count})$ class
   - exact nominal rank: **494**

All nominal ranks must be programmatically derived from the instantiated row matrices used by the implementation. The above values are the exact targets for the standard 3×3 Moore indexing.

### 4.3 Local functional families (assembly index 2–3)

v0.2.2 replaces the ambiguous “conservation” language from the early draft with **local functional families**.

A local functional family is generated from a function

$$
\psi : \{0,1\}^9 \to \{0,1\}
$$

and predicts output bits for a selected set of neighborhoods according to $\psi$.

**Campaign-1 restriction (load-bearing):** for the first throughput campaign governed by the v0.2.2 manifest, the local-functional primitive library is restricted to the **1024 affine linear functions** of the 9 neighborhood bits, including constant:

$$
\psi(b) = a_0 b_0 \oplus \cdots \oplus a_8 b_8 \oplus c,
\qquad a_i, c \in \{0,1\}.
$$

This restricted family is the one used for manifest construction, adversarial-stratum screening, and first-campaign generator instantiation. An unrestricted class of all Boolean $\psi$ is **not** intended here, because that would trivialize adversariality: every hidden rule is itself some local function.

Examples:

- total live count mod 2
- center-cell copy
- diagonal parity
- custom linear functionals over the 9 neighborhood bits

Operationally, these families query coordinate rows $e_i$, while the hypothesis $h_t$ is sampled or constructed so that its queried outputs match $\psi$ where possible.

**Important:** true global conservation laws are not part of v0.2 Fast Bench semantics. They require rollout-level or temporal constraints and belong in a later rollout-augmented bench.

Nonlinear local templates such as thresholds, majorities, low-degree polynomials, or other finite $\psi$ families may be added only in a later manifest version with the extended primitive library explicitly enumerated and the adversarial search rerun against that enlarged library before throughput claims are made.

### 4.4 Composition

A family may combine primitives from any categories. Its nominal row matrix is the union of the constituent rows, reduced to a basis.

The implementation must log:

- primitive counts
- nominal family rank
- construction path / assembly index

---

## 5. Oracle

The oracle is a deterministic vector oracle:

$$
\Omega(W_t) = W_t T
$$

for any witness matrix

$$
W_t \in \mathbb{F}_2^{q_t \times 512}
$$

where $q_t \le B_q$.

The oracle has:

- no memory
- no gradient
- no opinion
- no access to $h_t$

It returns exact bits for the queried witness rows and nothing else.

### 5.1 Diagnostic pass/fail

Bundle pass/fail is **derived**, not fundamental.

Given predicted witness bits $\hat y_t^{(W)}$ and observed witness bits $y_t^{(W)}$, define the mismatch vector

$$
m_t = y_t^{(W)} \oplus \hat y_t^{(W)}
$$

and mismatch rate

$$
\rho_t = \frac{\mathrm{wt}(m_t)}{q_t}
$$

A family can be:

- perfectly matched,
- partially contradicted, or
- fully contradicted,

with no invalid posterior update.

---

## 6. Projection, Novelty, and Witness Selection

The core cognitive loop is not “search all prior stakes.” It is:

> Given a conceptual family $C_t$, which part of it is still novel relative to exact knowledge?

### 6.1 Novel family basis

Project the family against the current knowledge operator by eliminating $C_t$ against $M_t$.

This yields a novelty basis $B_t$ such that

$$
\mathrm{rowspan}(B_t)
= \mathrm{rowspan}(C_t) \big/ \big( \mathrm{rowspan}(C_t) \cap \mathrm{rowspan}(M_t) \big)
$$

Define:

- $k_t = \mathrm{rank}(C_t)$ = nominal family rank
- $k_t^{\mathrm{nov}} = \mathrm{rank}(B_t)$ = novel family rank
- $\mathrm{gap}_t = k_t - k_t^{\mathrm{nov}}$ = redundancy / assembly gap

Every row operation applied to $C_t$ during projection must also be applied to the predicted vector $\hat y_t$.

### 6.2 Witness selection

If $k_t^{\mathrm{nov}} = 0$, the cycle is pure heat.

Otherwise, choose a witness set

$$
W_t \subseteq B_t, \quad q_t = \min(B_q, k_t^{\mathrm{nov}})
$$

using a fixed witness-selection policy.

**Default policy:** seeded uniform sample from the rows of an RREF basis for $B_t$.

This policy must be held fixed across the **main generator sweeps**. After the main sweep, the best and worst observed regimes must be rerun under a **random-basis-mixing** witness policy, obtained by left-multiplying the novelty basis by a seeded random invertible matrix over $\mathbb{F}_2$ before witness sampling, to test sensitivity to basis choice without changing the queried subspace.

### 6.3 Cost model

The per-cycle oracle cost is $q_t$ queried rows.

This keeps cross-policy comparisons honest:

- large conceptual families are allowed,
- structural depth is allowed,
- but raw information acquisition per cycle is budgeted.

---

## 7. Exact Update and Diagnostic Update

### 7.1 Exact posterior update

Given witness matrix $W_t$ and oracle response

$$
y_t^{(W)} = W_t T
$$

append the affine constraints

$$
W_t x = y_t^{(W)}
$$

to the exact knowledge operator and reduce to RREF:

$$
(M_{t+1}, b_{t+1}) = \mathrm{rref\_affine}(M_t, b_t; W_t, y_t^{(W)})
$$

The rank gain is

$$
\Delta m_t = m_{t+1} - m_t \le q_t
$$

and the posterior bits remaining become

$$
d_{t+1} = 512 - m_{t+1}
$$

This update is exact.

### 7.2 Graveyard update

For every witness row on which the prediction was wrong, append that row to the graveyard operator and record the mismatch in the diagnostic index.

That is, if a witness row $w$ satisfies

$$
w h_t \ne w T
$$

then $w$ is eligible for graveyard insertion.

The graveyard therefore tracks **falsified structural directions**, not the full posterior.

### 7.3 What propagates “for free”

The exact knowledge operator propagates all linear consequences of the witness rows that have actually been measured.

This is the correct version of cascading consequence in v0.2.2:

- measured rows generate exact downstream implications through the posterior,
- repeated rebuilding on already implied directions shows up as projection loss,
- no unmeasured family is buried wholesale on a single scalar contradiction.

---

## 8. Per-Cycle Algorithm

```text
cycle(t):
    1. generator reads (M_t, b_t), G_t, I_t, h_{t-1}, D_R
    2. generator emits h_t in A_t and conceptual family C_t
    3. reduce C_t to a basis and compute predicted family bits yhat_t = C_t h_t
    4. project C_t against M_t to obtain novelty basis B_t
    5. compute:
           k_t        = rank(C_t)
           k_t_nov    = rank(B_t)
           gap_t      = k_t - k_t_nov
    6. if k_t_nov == 0:
           log pure heat to I_t with no-witness flag and family metadata
           keep (M_t, b_t) unchanged
           keep G_t unchanged
           continue
    7. choose witness matrix W_t from B_t with q_t = min(B_q, k_t_nov)
    8. compute predicted witness bits yhat_t^(W)
    9. query oracle: y_t^(W) = W_t T
   10. mismatch mask m_t = y_t^(W) xor yhat_t^(W)
   11. update exact knowledge:
           (M_{t+1}, b_{t+1}) = rref_affine(M_t, b_t; W_t, y_t^(W))
   12. update graveyard G_t and diagnostic index I_t with mismatched witness rows
   13. compute d_{t+1} = 512 - rank(M_{t+1})
   14. if d_{t+1} == 0:
           close episode
```

---

## 9. Experimental Modes

### 9.1 Closure mode

A single hidden rule $T$ is sampled and held fixed until the posterior closes.

Primary outputs:

- cycles to closure
- informative cycles to closure
- total oracle rows consumed
- efficiency (bits learned per queried row)
- redundancy statistics
- mismatch statistics

### 9.2 Throughput mode

To study long-horizon phenomenology, run the same generator policy over many episodes.

Protocol:

1. sample $T$
2. run closure mode until $d_t = 0$
3. log episode summary
4. reset $(M_t, b_t)$, $G_t$, and $I_t$
5. resample $T$
6. continue

This mode is required for $10^6+$ total-cycle experiments.

A single 512-bit episode cannot sustain million-scale informative cycles. That is a property of the substrate, not a failure of the architecture.

### 9.3 Reset handling

Spectral analysis in throughput mode must account for episode resets.

Required procedure:

- keep explicit reset markers,
- compute windowed statistics either within episodes or on concatenated traces with reset-aware segmentation,
- apply tapered windows at episode boundaries or an equivalent reset-aware method to suppress reset artifacts,
- report whether the criticality signal survives segmentation choices.

---

## 10. Generator and Retrieval Depth

The generator remains the central experimental unknown, but v0.2.2 fixes its interface.

Inputs:

- exact knowledge operator $(M_t, b_t)$
- point hypothesis history
- graveyard operator $G_t$
- diagnostic index $I_t$
- retrieval depth $D_R$

Retrieval should be implemented **index-first**: the generator primarily consults $I_t$ and may use $G_t$ as an auxiliary algebraic structure for overlap or novelty calculations.

Outputs per cycle:

- a point hypothesis $h_t \in \mathcal{A}_t$
- a conceptual family $C_t$

### 10.1 Retrieval depth

$D_R$ is the number of prior graveyard/index records the generator may consult when constructing the next family.

This parameter is intended to regulate whether the generator:

- ignores prior falsification and rebuilds on dead ground,
- cautiously avoids all overlap,
- or enters a critical regime with sparse but consequential collisions.

### 10.2 Baseline generator policies for first campaign

The first campaign must implement at least three baseline policies:

1. **Atomic novelty policy**
   - samples $h_t$ from the current posterior
   - proposes mostly atomic families
   - serves as a low-assembly control

2. **Family-first structural policy**
   - attempts to instantiate symmetry or affine-linear local-functional templates consistent with the current posterior
   - performs a feasibility preflight (e.g. `is_consistent(C_t, M_t, b_t)` or equivalent) before emitting a structural family claim
   - degrades gracefully to a lower-assembly family if the intended structural claim is inconsistent with the current posterior
   - prefers high nominal rank families
   - expected to probe the supercritical edge

3. **Adaptive mixed policy**
   - mixes atomic and structural families
   - adjusts family choice using recent redundancy and mismatch statistics
   - intended as the main candidate for a critical regime

The initial sweep should evaluate:

$$
D_R \in \{1, 5, 25, 125, 625\}
$$

across all baseline policies.

---

## 11. Instrumentation

### 11.1 Per-cycle observables

1. **$k_t$** — nominal family rank
2. **$k_t^{\mathrm{nov}}$** — novel family rank after projection
3. **$q_t$** — witness rows actually queried
4. **$\mathrm{gap}_t = k_t - k_t^{\mathrm{nov}}$** — redundancy / assembly gap
5. **$\rho_t$** — witness mismatch rate
6. **$\Delta m_t$** — exact rank gain in the posterior
7. **family composition** — atomic / symmetry / local-functional counts
8. **$d_t$** — posterior bits remaining
9. **pure-heat indicator**
   $$
   \mathbf{1}[k_t^{\mathrm{nov}} = 0]
   $$

### 11.2 Episode observables

1. **cycles to closure**
2. **informative cycles to closure**
3. **oracle rows to closure**
4. **efficiency**
   $$
   \eta = \frac{m_{\text{final}} - m_{\text{initial}}}{\sum_t q_t}
   $$
5. **pure-heat fraction**
6. **family fallout score**

### 11.3 Family fallout score

To operationalize “cascade” without invalid rank arithmetic:

- identify contradiction events involving high-assembly families,
- over a fixed horizon $H$, measure the average redundancy gap, pure-heat rate, and witness mismatch rate for later families whose metadata overlap the contradicted family class,
- compare against matched low-assembly controls.

Matching is required, not optional. Unless a stricter preregistered rule is supplied, controls must be matched within:

- the same hidden-rule stratum,
- the same generator policy,
- a posterior-dimension band satisfying
  $$
  |d_t - d_t'| \le 16,
  $$
- and the same decile of cumulative prior contradictions in the affected family-class bucket.

A genuine cascading effect means that breaking a high-assembly family measurably increases downstream overlap and/or contradiction in related future families.

### 11.4 Throughput observables

Over sliding windows in throughput mode, compute:

1. **novel-rank spectrum** of $\{k_t^{\mathrm{nov}}\}$
   - this is the **primary critical observable**, since it measures information-bearing structure after projection against exact knowledge.
2. **windowed pure-heat fraction**
   - this is the co-primary confabulation / dead-ground observable.
3. **family-rank spectrum** of $\{k_t\}$
   - retained as a proposal diagnostic showing what the generator attempted, not just what survived projection.
4. **gap distribution**
5. **mismatch-burst distribution**

Estimate the spectral exponent $\alpha$ using a **reset-aware robust spectral method** (for example segmented Welch / multitaper PSD estimation with uncertainty reporting or an equivalent preregistered estimator). Simple linear regression on a raw log-log plot is **not sufficient as the sole estimator**. The analysis must report uncertainty and separation from the required nulls.

The working hypothesis remains:

- **critical:** $\alpha \approx -1$ in the novel-rank spectrum, with intermediate pure-heat fraction
- **subcritical:** steeper spectra with tiny families and low contradiction
- **supercritical:** flatter spectra with frequent large, wasteful wagers and elevated pure heat

---

## 12. Controls and Nulls

Criticality claims are only meaningful against explicit nulls.

The first campaign must include:

1. **Projection-disabled null**
   - same generator family proposals, but no novelty reduction against $M_t$
   - tests whether the critical signal is actually due to closure mechanics

2. **Size-matched random-family null**
   - preserves the empirical family-size distribution but randomizes family content
   - tests whether spectra come from size statistics alone

3. **Order-shuffled null**
   - shuffles the cycle order within windows or episodes where appropriate
   - tests whether temporal organization, not merely marginals, carries the signal

4. **Atomic-only baseline**
   - rules out the trivial possibility that all interesting behavior is just an artifact of basic bit acquisition

No regime should be called “critical” unless it separates from these nulls.

---

## 13. Success Criteria

The Fast Bench is considered to have validated the core engine only if all of the following hold across multiple hidden-rule strata.

1. **Exact monotonic closure**
   - $d_t$ is non-increasing
   - closure $d_t = 0$ occurs in finite oracle budget for at least some generator configurations

2. **Structural fallout exists**
   - contradiction of high-assembly families produces elevated downstream redundancy and/or contradiction in related future families relative to controls

3. **A controlled critical window exists**
   - there exists at least one $(D_R, \text{policy})$ setting for which the **novel-rank throughput spectrum** is consistent with a stable critical band near $\alpha \approx -1$
   - the corresponding windowed pure-heat fraction is stably intermediate between overcautious and confabulatory regimes
   - and this separation survives the required nulls

4. **Phenotype separation**
   - sweeping $D_R$ and policy produces qualitatively distinct regimes:
     - subcritical sliver-carver
     - supercritical confabulator
     - critical mixed regime
   - these regimes differ measurably in closure efficiency, redundancy, and mismatch structure

5. **Rule-pool robustness**
   - the above phenomena are not confined to only library-aligned truths

Negative results remain informative. In particular:

- if closure is easy but no critical window appears, the thermodynamic story is too strong;
- if a critical-looking spectrum appears only in the nulls, it is a generator artifact;
- if the phenomena collapse outside the aligned rule pool, the primitive library is overfit.

---

## 14. Open Questions / Deferred Decisions

1. **Generator composition policy**
   - still the central unknown

2. **Witness-selection robustness**
   - fixed seeded RREF-basis sampling is the default for the main sweep
   - the best and worst observed regimes must then be rerun under the random-basis-mixing witness policy as a required sensitivity check
   - adaptive witness choice remains a later design question, not a first-campaign sweep axis

3. **Rule-pool design**
   - exact membership of aligned, adversarial, and random strata is fixed by the versioned manifest
   - changing the primitive library, including broadening the Campaign-1 affine-linear local-functional family, invalidates the current adversarial screen and requires a new manifest version before throughput claims can inherit the old pool
   - expanding beyond the minimum 5 / 5 / 5 first-campaign pool remains open

4. **Feedback from pure-heat cycles**
   - pure-heat cycles must be recorded in $I_t$ and therefore are visible to generator retrieval
   - whether they also directly alter generator control-state beyond indexed retrieval remains open

5. **Rollout-augmented conservation bench**
   - true conservation and Noether-like structure require temporal rollout constraints and belong in a later bench version

6. **Graduation criteria for Slow Bench**
   - v0.2.2 should only graduate to Lean / theorem-bearing substrates if it shows robust separation from controls here

---

## 15. Minimal Implementation Requirements

A v0.2.2 implementation is not considered faithful unless it includes all of the following:

- exact affine posterior maintenance $(M_t, b_t)$ in RREF
- separate diagnostic graveyard $G_t$
- novelty reduction of conceptual families against $M_t$
- fixed witness budget $B_q$
- fixed main-sweep witness-selection policy plus required random-basis-mixing robustness rerun
- reset-aware throughput mode
- required null experiments
- stratified hidden-rule pool
- versioned hidden-rule manifest fixed before first throughput run
- a single canonical manifest-emission path for each manifest version; exploratory analysis or search scripts must not overwrite the frozen manifest artifact
- first-campaign local-functional primitives explicitly restricted to the affine-linear family used in manifest screening; any primitive-library extension requires a new manifest version and rerun of adversarial screening
- index-first retrieval with $I_t$ as the primary generator-facing diagnostic surface
- pure-heat attempts recorded in $I_t$ with no-witness flags
- feasibility preflight for the family-first structural policy or a documented equivalent fallback
- reset-aware robust spectral estimation, not naive log-log regression alone
- full logging of family metadata, witness rows, predictions, outcomes, and pure-heat indicators

Anything less risks reintroducing the ambiguities v0.2 is meant to remove.

---

## 16. One-Sentence Summary

The v0.2.2 Fast Bench tests Generative Closure by letting a generator propose large conceptual families over a 512-bit CA rule space, projecting those families against an exact affine posterior, sampling a fixed witness budget, updating knowledge exactly, and measuring whether retrieval-guided access to indexed prior contradictions produces real phase structure rather than rhetorical thermodynamics.
