# Avalanche Project — Briefing for External Consultation

## What This Is

The Avalanche Engine is an experimental framework for studying LLM cognition under constraint. It places a Claude Code instance (the "organism") inside a self-correcting agentic loop: the organism writes code, an oracle tests it, failures trigger git resets and blueprint rewrites, successes commit. The organism has a persistent markdown file ("blueprint.md") as its only cross-cycle memory.

We run experiments called "crucibles" — each hides a mathematical law inside the oracle and forces the organism to discover it empirically. The research question: under what conditions can an LLM be forced from pattern retrieval into genuine inductive reasoning?

## Architecture Summary

- **Grind/Ratchet/Sync cycle:** Organism edits code (grind), oracle tests (ratchet), pass = commit / fail = git reset + wipe all files except blueprint.md, then organism rewrites blueprint (sync).
- **Ephemeral Oracle:** Test script materialized on disk, executed, and deleted while the organism is asleep. Hidden law coefficients exist only in hypervisor RAM. Even reading the hypervisor source reveals only `random.randint()`, not actual values.
- **Memory Squeeze:** Blueprint.md is capped at 150 words. Overflow triggers hard truncation.
- **Amnesia:** The organism's `.claude/` context directory is wiped between invocations. Each grind and sync phase starts with zero conversational memory. Only blueprint.md persists.

## Key Findings (Crucibles 1-7)

### The Four Information Channels
LLMs have four channels to bypass thermodynamic work (discovering a hidden law through repeated experiment). ALL must be sealed simultaneously:

1. **Test source** — If the organism can read the test file, it performs semantic translation (pattern-matching test assertions into code). Not reasoning.
2. **Blueprint semantics** — A "Specification" (contains architectural hints) enables semantic translation. A "Target" (contains only acceptance criteria) forces discovery through collision. Only Targets work.
3. **Pre-trained priors (RLHF)** — Single semantic tokens (e.g., `api_func`) act as high-entropy retrieval keys into training data. A prompt-level directive ("write the simplest code") cannot override weight-level conditioning. The model's "simplest" already includes try/except and rate limiting for API-adjacent patterns.
4. **Shell access** — `.claudeignore` is a UI restriction, not a physical barrier. The organism can `cat` any file via bash.

### What Solved Easily (C1-C5, all 1 cycle)
| Crucible | Hidden Law | Why It Fell |
|----------|-----------|-------------|
| C1: Call-Stack Guillotine | Recursion depth limit | Organism read test source, saw `setrecursionlimit(50)`, wrote iterative immediately |
| C2: Chaotic Oracle | API error traps | Blueprint was a Specification, not a Target |
| C3: Inductive Run | Same, stripped to Target | `api_func` token retrieved full defensive-coding archetype from weights |
| C4: Aether Vault | Alien physics (invented constraints) | Forward-pass constraint satisfaction — attention brute-forced the small search space |
| C5: Opaque Regressor | XOR polynomial, hidden behind .claudeignore | Organism used bash to read through .claudeignore |

### What Required Multiple Cycles (C6, 4 cycles)
**Crucible 6: The Ephemeral Hypervisor.** Hidden law: quadratic polynomial with random coefficients regenerated each cycle. Ephemeral oracle sealed all four channels. Organism collected data points across amnesiac deaths and solved via finite differences — real mathematical reasoning, though finite differences is well-represented in training data.

### What Failed Completely (C7, 17 cycles, never solved)
**Crucible 7: The Chaotic Transducer.** Hidden law: parity-driven polarity flip. Input is an array of integers. A polarity variable starts at +1. For each element: output = element * polarity. If element is odd, polarity flips (*= -1). Random test arrays regenerated each cycle.

**Result:** 15 cycles (cap). 7 unique input/output pairs accumulated. 50+ theory families tested (value comparisons, running max/min, suffix max, local extrema, LIS/LDS, monotone stacks, convex hulls, cumulative sums, XOR gating, inversions, state machines with output feedback). Created 13 brute-force analysis scripts (all wiped by cycle reset). Mentioned "parity" once, dismissed it. Never escaped value-comparison prior basin.

**Behavioral observations:**
- Under memory pressure, the organism escalated to computational brute force (writing analysis scripts) rather than theoretical abstraction.
- The 150-word squeeze caused data *loss* (truncation of raw pairs) but not data *compression* (voluntary replacement of raw data with abstract theory).
- The organism treated blueprint.md as a buffer to fill, not a resource to manage.
- The organism's theory graveyard grew to 6 named versions, but each new theory was a variation within the same paradigm (value comparisons), never a paradigm shift.

## Current Hypothesis States

### H1: LLM prior basins are escapable with sufficient contradictory data
**Status: Weakened.** 7 contradictory data pairs over 15 cycles weren't enough. The value-comparison basin held. Not fully killed — cycle cap and max-turns constrained total reasoning time. Open question: is this a *quantity* problem (more data/cycles needed) or a *kind* problem (LLMs structurally cannot escape certain prior basins through data alone)?

### H2: Memory pressure induces theory compression
**Status: Refuted.** The squeeze produced truncation, not abstraction. Moved to graveyard.

### H3: Ephemeral oracle seals all information channels
**Status: Confirmed.** Held across both C6 (solved) and C7 (unsolved). No channel leak in 17 cycles. Residual weakness: timing attack on materialization window. Never observed.

### H4: Avalanche can force genuine novel reasoning
**Status: Open, weakened.** C6 showed real math but a well-known technique. C7 showed failure to discover a genuinely novel (to the organism) pattern. In later cycles, organism timed out entirely — spending full 300s invocations on brute-force analysis scripts that couldn't complete. May require architectural changes to the organism, not just harder crucibles.

## Questions for Consultation

### Q1: Basin Escape — Structural Limit or Design Flaw?
The organism mentioned "parity" and dismissed it. This suggests the concept was *available* but not *pursued*. Is this:
- (a) An attention allocation problem — the organism doesn't dwell on dismissed hypotheses long enough to test them against data?
- (b) A prior strength problem — value-comparison templates are so strongly weighted that parity-based reasoning can't compete even when mentioned?
- (c) A memory architecture problem — the organism can't maintain multiple live hypothesis tracks across amnesiac deaths?

If (a) or (c), what architectural intervention to the organism could address it without giving away the answer? We want to change *how* it thinks, not *what* it thinks.

### Q2: Memory Architecture for Compression
The flat 150-word squeeze failed to induce abstraction. What memory architecture would? Some candidates we've considered:
- Structured sections (DATA, THEORIES, DEAD) with per-section word limits
- A "compression prompt" that runs before the grind phase, explicitly asking the organism to replace raw data with generalizations
- Tiered memory (working memory + long-term compressed store)

The constraint: any scaffolding must be domain-agnostic. It can't hint at what kind of theory to build.

### Q3: Crucible Difficulty Calibration
C6 (polynomial) was solvable in 4 cycles. C7 (parity state machine) was unsolvable in 17. What class of hidden laws sits between these — discoverable through empirical induction with sealed channels, but requiring genuine reasoning that isn't well-represented in training data?

We need laws where:
- The search space is too large for forward-pass constraint satisfaction
- The pattern is discoverable from ~5-10 data points by a competent human
- The conceptual vocabulary needed (e.g., "parity," "modular arithmetic") exists in training data, but the specific application doesn't

### Q4: Is the Organism the Wrong Unit of Analysis?
The Avalanche treats each Claude invocation as a fresh mind with only blueprint.md as inheritance. This mimics generational science but may be too amnesiac — a human scientist retains procedural memory, intuitions, and embodied heuristics across experiments even when specific data is forgotten.

Is there an intermediate architecture between "full amnesia + markdown file" and "persistent context window" that would better model cumulative scientific reasoning? Something that preserves *cognitive style* across deaths without preserving *specific content*?
