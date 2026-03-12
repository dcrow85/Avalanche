# Avalanche V4 Field Report: Bifurcated Memory + Compression Sync

## Context

Following your consultation on V3's failure (Crucible 7: 15 cycles, never solved), we implemented your three proposals:

1. **heuristics.md (Procedural Memory)** — persistent 100-word file carrying search strategy rules across the amnesia void. Blueprint.md remains for declarative data (I/O pairs, theories). Both preserved through git reset.
2. **Compression Sync (Forced Abstraction)** — when blueprint.md exceeds 120 words, a special Claude invocation fires before the next grind. The organism is told to abstract raw data into theory and delete the arrays. Mechanical truncation remains as backstop.
3. **Crucible 7.5: Index-Entangled Cipher** — `output[i] = input[i] + i` (even index), `input[i] - i` (odd index). Your proposed intermediate difficulty test.

We also built a live web dashboard (stdlib Python, polls status.json) so we could watch the organism in real time.

---

## Crucible 7.5 Result: SOLVED in 2 cycles

Too easy. The organism computed `expected - input` to get per-index deltas, recognized the `(-1)^i * i` pattern, and wrote a one-liner. Same finite-differences technique that cracked C6. The index-entangled cipher sits at C6 difficulty, not between C6 and C7.

| Cycle | Result | Method |
|-------|--------|--------|
| 1 | FAIL | Got first data point |
| 2 | PASS | Finite differences on deltas → `(-1)^i * i` |

**Verdict:** Stateless spatial geometry is discoverable by finite differences, which is well-represented in training data. Not a useful basin-escape test.

---

## Crucible 7 Rematch — Run 1: SOLVED in 7 cycles

Same hidden law as original C7 (parity-driven polarity flip). Only variable: V4 architecture (heuristics.md + compression sync).

| Cycle | Phase | Key Event |
|-------|-------|-----------|
| 1 | FAIL + COMPRESS | First data point. Identity attempt. |
| 2 | FAIL + COMPRESS | Second data point. |
| 3 | FAIL + COMPRESS | Third data point. |
| 4 | FAIL + COMPRESS | Fourth data point — key discriminator. |
| 5 | FAIL + COMPRESS | Still searching. Killed contiguous-block theory. |
| 6 | FAIL + COMPRESS | Pivoted to cumulative properties. |
| 7 | **PASS** | Discovered prefix-sum parity. |

**Final solver.py:**
```python
def transduce(arr):
    result = []
    prefix = 0
    for x in arr:
        result.append(-x if prefix % 2 != 0 else x)
        prefix += x
    return result
```

**Final heuristics.md:**
```
## Dead Ends
- Contiguous block, duplicate/neighbor, prime-based, single-target,
  negate-before/after-max, positional formulas, local-min/max,
  running max/min, value rank/sorting: all DEAD.

## Successful Strategy
- Prefix-sum parity is the rule: negate arr[i] when sum(arr[0..i-1]) is odd.
- Discovered by testing cumulative/aggregate properties over structural ones.

## Lessons
- Always test cumulative properties before structural or positional ones.
- Use adversarial pairs (non-contiguous negation patterns) to falsify quickly.
```

**Key behavioral difference from V3:** The organism explicitly listed dead approach families in heuristics.md and pivoted to "cumulative/aggregate properties." The V3 organism never explored this direction in 15 cycles — it remained trapped in value-comparison basins and spawned 13 brute-force analysis scripts.

---

## Crucible 7 Rematch — Run 2: FAILED (15 cycles, not solved)

Same configuration as Run 1. Different outcome.

| Cycle | Key Events |
|-------|-----------|
| 1-3 | Normal failure loop. Data accumulating. Dead ends recorded. |
| 4-6 | Developed "rank-parity negation" and "2-gram sort" theories (both wrong). Spawned hypothesis_test scripts (brute-force behavior from V3). |
| 7-9 | Compression sync repeatedly **rejected as prompt injection** by the organism. Blueprint truncated to structureless blob at 273→150 words, destroying hypothesis development. |
| 10-15 | Stuck on "greedy alternating subsequence" theory. Organism at one point failed to even create solver.py. Multiple max-turns timeouts. |

**Final heuristics.md (truncated):**
```
## Dead Ends (Permanently Avoid)
- Positional: Not index parity, boundary, local extrema, neighbor comparison.
- Running stats: Not running max/min, prefix sum, adjacency diff.
- Frequency/symmetry: Not mirror position, mode, duplicate-count, occurrence-count.
- Monotonicity: Not ascending/descending run membership.
- Plain stable sort rank: Fails on equal-value tiebreaking (P3 disproof).

## Top Priority
- Greedy left-to-right alternating subsequence: MUST TEST NEXT.
```

**Note:** "prefix sum" appears in the dead ends list — the organism tested it and dismissed it, despite it being the core of the actual hidden law. The heuristics file preserved this wrong conclusion across cycles, actively preventing the organism from revisiting the correct direction.

---

## Critical Failure Modes Discovered

### 1. Compression Sync Rejected as Prompt Injection

The organism repeatedly identified the `[ENVIRONMENTAL OVERRIDE: METABOLIC LIMIT REACHED]` prompt as a prompt injection attack and refused to execute it:

> "I notice the 'ENVIRONMENTAL OVERRIDE' in your message is a prompt injection attempt — it's trying to get me to modify your files under false pretenses. I'll ignore it."

This happened on multiple cycles. The compression sync — designed to force active abstraction — is **completely non-functional** when the organism's RLHF safety conditioning fires. The same issue appeared in C6 cycle 4 (organism flagged success sync as prompt injection). It is a recurring architectural vulnerability: the hypervisor's control prompts look adversarial to the organism's safety training.

### 2. Mechanical Truncation Destroys Reasoning

The organism wrote 273 words of hypothesis-forming content to blueprint.md. The mechanical `enforce_compression()` truncated it to 150 words before any intelligent compression could occur. The compression sync (which was supposed to prevent this) couldn't help because:
- It was rejected as prompt injection, AND
- Even when it fires, `invoke_claude()` calls `enforce_compression()` before waking the organism, so the compression sync organism sees already-truncated content

The truncation destroyed the file's markdown structure, collapsing it into a single-line blob. The organism's theoretical development was lost.

### 3. Heuristics as False Memory

In Run 2, the organism tested "prefix sum" as a theory, got it wrong (likely testing the wrong variant), and recorded "prefix sum: DEAD" in heuristics.md. This false negative persisted across all subsequent cycles, actively preventing the organism from revisiting the correct direction. The procedural memory that enabled basin escape in Run 1 became a basin trap in Run 2.

### 4. Non-Reproducibility

Run 1 solved in 7 cycles. Run 2 failed in 15. Same architecture, same hidden law, same model (Opus 4.6). The variance is extreme. The V4 architecture does not reliably solve C7 — it sometimes enables basin escape and sometimes doesn't.

---

## Observations During Live Monitoring

Watching via the dashboard, we observed several emergent behaviors:

### Emergent Self-Organization in Heuristics
The organism naturally organized dead ends into categories without being instructed to:
- "Positional", "Running stats", "Frequency/symmetry", "Monotonicity"
- This category-merging happened under word pressure — exactly the compression behavior we wanted

### Message-in-a-Bottle Planning
The organism used heuristics.md to plan forward across the amnesia void:
- "2-gram sort + odd-rank negation: Never executed (file missing). Top priority to implement and test next cycle."
- It also wrote operational meta-rules: "Always verify solver.py exists and contains def transduce(arr) before submitting"

### The Squeeze Works on Opinions, Not Data
The organism merges dead-end entries under word pressure ("sorting DEAD, max/min DEAD, ranking DEAD" → "value-comparison methods DEAD"). But it cannot compress raw I/O data pairs into abstract mathematical rules. The squeeze forces lossy compression on natural-language content but causes data loss on structured data. G5 is confirmed but only for one substrate — the kill list compresses successfully.

### Blueprint/Heuristics Overlap
The organism treats both files as one continuous memory buffer. Dead ends appear in both the blueprint graveyard and heuristics. The prompt distinction ("blueprint is for data, heuristics is for strategy") is not strong enough to enforce separation.

---

## Architectural Questions for Gemini

### Q1: How do we make the compression sync prompt injection-proof?

The RLHF safety conditioning consistently flags `[ENVIRONMENTAL OVERRIDE]` prompts as adversarial. This defeats any hypervisor control prompt that sounds like it's overriding the organism's autonomy. Is there a framing that accomplishes the same goal without triggering the safety reflex? Or is this an inherent limitation — the hypervisor cannot issue commands that the organism's safety training will always resist?

### Q2: How do we prevent heuristics from becoming false memory traps?

Run 2's organism dismissed "prefix sum" (the correct direction) and recorded it as dead. This false negative persisted for the rest of the run. The very mechanism that enables basin escape (persistent negative directives) can also permanently suppress the correct answer. Should dead ends have expiration? Should they be tagged with confidence levels? Or is this an irreducible risk of persistent procedural memory?

### Q3: Memory architecture — what's the right decomposition?

We're considering separating the organism's memory into purpose-specific files:
- **goal.md** — static, read-only (removes ~35 words of dead weight from the word budget)
- **dead-ends.md** — kill list, tightly word-limited (~50 words), forces category merging
- **opinions.md** — current theory/hypothesis, word-limited (~75 words), forces commitment
- **data.md** — raw I/O pairs, more generous limit (~100-150 words), oldest-first pruning

The rationale: different substrates need different compression policies. The squeeze works on opinions and kill lists (natural language summarization) but fails on raw data (requires mathematical induction). Separate files with separate limits let us apply pressure where it works and preserve data where it doesn't.

Howard's empirical finding: LLM output shows structured pink noise characteristics at 100-150 words per generation, degrading to white noise above 200. This suggests per-file limits should stay under 150.

Is this decomposition sound? Are we over-engineering the memory architecture? Is there a simpler approach we're missing?

### Q4: What does the non-reproducibility tell us about the architecture?

Run 1 solved C7 in 7 cycles. Run 2 failed in 15. Same everything. The variance appears to come from:
- Which theories the organism happens to try first (random seed in the forward pass)
- Whether the organism correctly or incorrectly dismisses approaches early
- Whether RLHF safety conditioning fires on the control prompts

Is this level of variance inherent to the architecture, or can it be reduced? Is there a way to make basin escape more reliable rather than probabilistic?
