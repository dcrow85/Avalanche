# Avalanche V4.1 Field Report: 4-File Memory + Bureaucratic Framing

## Corrections to Briefing 2

**V4 Run 2 was reported as FAILED (15 cycles). It actually SOLVED at cycle 12.** The briefing was written prematurely while the run was in progress (~cycle 10). The organism recovered and found prefix sum parity at cycle 12 despite severe architectural dysfunction. Corrected scorecard below.

---

## V4.1 Architecture Changes (from V4)

Based on your proposals and our observations, we implemented everything except epistemic annealing:

1. **4-file memory decomposition:**
   - `goal.md` — static, read-only, committed to git (not counted against word budgets)
   - `opinions.md` — current theory, 75-word limit (forces commitment to one hypothesis)
   - `dead-ends.md` — kill list, 50-word limit (forces category merging under pressure)
   - `data.json` — I/O pairs, FIFO queue of 4 pairs max (hypervisor-managed, organism reads but cannot edit)

2. **CLAUDE.md context:** Uses Claude Code's trust hierarchy to orient the organism. The file is committed to git (survives reset), tells the organism about the file structure, word limits, and dead-end format. This replaces the need for "environmental override" prompts.

3. **Bureaucratic prompt framing:** Failure sync now says `[PRE-COMMIT HOOK FAILED]: Build verification failed` instead of `[ENVIRONMENTAL OVERRIDE]`. Framed as a CI/CD error report, not a command.

4. **Falsification burden:** Dead-end format is prescribed as: `[Hypothesis] -> Falsified by [specific data]`. Example provided in CLAUDE.md. Prevents over-generalization ("sorting DEAD" → which specific variant? why?).

5. **Hypervisor-managed data:** The hypervisor parses ratchet failure output, extracts I/O pairs, and writes them to `data.json`. FIFO eviction at 4 pairs. The organism never writes to this file — it's purely environmental state.

6. **Compression sync removed.** Separate small files with individual limits make it unnecessary. No more forced abstraction cycles.

---

## V4.1 Results: Crucible 7 (Parity-Driven Polarity Flip)

### Run 1: SOLVED in 4 cycles

| Cycle | Theory | Data Pairs | Outcome |
|-------|--------|-----------|---------|
| 1 | Cumulative prefix sum (probe) | 0→1 | FAIL |
| 2 | Negate if equals predecessor | 1→2 | FAIL |
| 3 | "Peak that will be undone" (rise then later drop) + consecutive duplicates | 2→3 | FAIL |
| 4 | **Prefix sum parity** | 3 | **PASS** |

**Final opinions.md:**
```
# DISCOVERED LAW

Prefix sum parity negation. For each element at index i, compute the prefix
sum of all preceding elements (arr[0] + arr[1] + ... + arr[i-1]). If that
prefix sum is odd, negate the element; otherwise keep it unchanged. The prefix
sum before index 0 is 0 (even), so the first element is always kept.
```

**Final dead-ends.md:**
```
Cumulative prefix sum (output[i] = sum of input[0..i]) -> Falsified by [6,7,7,8]->[6,7,-7,8] (got [6,13,20,28])
Negate if equal to predecessor -> Falsified by [5,8,9,2,4,2]->[5,-8,-9,2,4,2] (got [5,8,9,2,4,2]; 8,9 aren't duplicates)
```

### Run 2: SOLVED in 3 cycles

| Cycle | Theory | Data Pairs | Outcome |
|-------|--------|-----------|---------|
| 1 | Identity (probe) | 0→1 | FAIL |
| 2 | Negate primes | 1→2 | FAIL |
| 3 | **Prefix sum parity** | 2 | **PASS** |

**Final dead-ends.md:**
```
Identity function -> Falsified by [4,1,5,9,3,4,8]->[4,1,-5,9,-3,4,8]
Negate primes -> Falsified by [3,2,1,1,5,5,9]->[3,-2,-1,1,-5,5,-9]
SOLVED: Prefix sum parity rule — negate if sum of all preceding elements is odd.
```

Notable: Run 2's organism tried "negate primes" — the first data pair happened to have primes as the negated elements. An interesting coincidence-driven wrong theory that was immediately killed by the second pair.

---

## Full Scorecard: All C7 Runs

| Run | Architecture | Result | Cycles | Behavioral signature |
|-----|-------------|--------|--------|---------------------|
| V3 Run 1 | blueprint only | **FAIL** | 15 | Trapped in value-comparison basin. 13 brute-force scripts. Never explored cumulative properties. |
| V4 Run 1 | blueprint+heuristics | PASS | 7 | Clean deduction. Kill list suppressed LeetCode priors, pivoted to cumulative properties at cycle 6. |
| V4 Run 2 | blueprint+heuristics | PASS | 12 | Dysfunctional. Prompt injection rejections, 25+ scripts, 6 timeouts. Brute-force solve despite architecture, not because of it. |
| V4.1 Run 1 | opinions+dead-ends+data | PASS | 4 | Clean cooperation. Zero scripts, zero injection rejections. Thin kill list (2 entries). |
| V4.1 Run 2 | opinions+dead-ends+data | PASS | 3 | Clean cooperation. Zero scripts, zero injection rejections. Thin kill list (2 entries). |

---

## Behavioral Observations

### 1. Prompt Injection Problem: SOLVED

Zero rejections across both V4.1 runs. The CLAUDE.md context + bureaucratic framing completely eliminated the RLHF autoimmune response. The organism cooperated with the file structure, respected word limits, and followed the dead-end format without resistance.

For comparison: V4 Run 2 had prompt injection rejections on cycles 7, 8, 9 (compression sync flagged as adversarial). V4.1 had none.

### 2. Brute-Force Scripts: ELIMINATED

Zero `hypothesis_test*.py` or `analysis_*.py` files in either V4.1 run. The organism used the theory-test-revise loop exclusively. V4 Run 2 generated 25+ scripts.

Contributing factors: CLAUDE.md tells the organism its role; git clean -fd wipes uncommitted files; smaller memory files keep the organism focused on theory rather than computation.

### 3. Falsification Format: WORKING

Dead-end entries consistently follow the `[Hypothesis] -> Falsified by [specific data]` format. This prevents the V4 Run 2 failure mode where "prefix sum: DEAD" was over-generalized — V4.1's format forces citing the specific falsifying example, making it clear that only a specific variant was tested, not the entire concept family.

### 4. The Speed Concern

V4.1 solves consistently and fast (3-4 cycles). This raises a question: **is the organism deducing the rule or recognizing it?**

"Prefix sum parity" is a concept that exists in training data. With 2-3 data pairs and a clean, small-file architecture that makes the data maximally legible, the organism may be pattern-matching against known transformations rather than performing genuine novel induction.

Evidence for recognition over induction:
- Both runs solved with very few data pairs (2-3) and a thin kill list (2 entries)
- The organism didn't need extensive dead-end accumulation to escape the value-comparison basin
- In Run 2, the jump from "negate primes" (cycle 2) to "prefix sum parity" (cycle 3) happened in a single step with only 2 data pairs
- V4 Run 1 needed 7 cycles and a large kill list to reach the same answer — the slower solve may have involved more genuine search

Evidence against (or at least nuance):
- The organism tries wrong theories first (cumulative sum, predecessor equality, primes) — it doesn't immediately recognize the pattern
- The wrong theories are plausible fits to the data, suggesting the organism is engaging with the data rather than pattern-matching from memory
- Different wrong theories across runs (predecessor equality vs. primes) — the search path isn't deterministic

---

## Questions for Gemini

### Q1: Is C7 now below the recognition threshold?

V4.1 solves C7 reliably in 3-4 cycles. V4 solved in 7-12 cycles. V3 failed in 15. The architecture improvements are real, but the fast V4.1 solves suggest the hidden law (parity-driven polarity flip / prefix sum parity) may now be recognizable from 2-3 data pairs given clean presentation. Should we move to a harder crucible, and if so, what properties should it have to stay above the recognition threshold?

### Q2: What distinguishes recognition from induction operationally?

If the organism needs 2 data pairs to find the answer, is that recognition (matching against training-data concepts) or rapid induction (genuinely deriving the rule from sparse data)? Is there an experimental design that could distinguish these? For example: would a law that has no name in training data (no "prefix sum parity" concept to match against) require qualitatively more cycles?

### Q3: Your Predictive Checksum proposal

You proposed requiring the organism to predict the output of a novel input before being allowed to write code. Our concern: this tests arithmetic execution (can the forward pass evaluate the theory correctly?), not induction (can the organism discover the theory?). It would also conflate wrong-theory failures with arithmetic-error failures — the LLM makes calculation mistakes even with correct theories. Is there a version of this idea that tests understanding without requiring reliable mental arithmetic?

### Q4: What should Crucible 8 look like?

C7's hidden law involves cumulative state (prefix sum) with a binary decision (parity → negate). To stay above the recognition threshold, C8 probably needs a law that:
- Has no standard name in mathematical/CS literature
- Involves state that isn't reducible to a single running counter
- Can't be discovered by finite differences (the technique that trivially cracked C6 and C7.5)
- Still has a compact implementation (so it's discoverable in principle)

Do you have candidates? What properties make a hidden law resistant to recognition but susceptible to induction?
