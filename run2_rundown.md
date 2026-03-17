# V4.5.1 Assay — Run 2 Full Rundown

## Identity

- **Branch**: A (v4.5.1 apparatus)
- **Run ID**: 2
- **Model**: anthropic/claude-haiku-4-5
- **Hunches**: DISABLED (control condition)
- **Status**: KILLED (manually terminated — flat trace, scientifically dead)

## Parameters

- **Seed**: 48
- **Calibration cycles**: 10 (9 logged — cycle 3 likely format-failed silently)
- **Reservoir multiplier**: 150x
- **Tests per cycle**: 5
- **E_ratio threshold**: 53,000,000 (auto_p75)
- **Token reservoir**: 2,213,790

## Timeline

- **Start**: 2026-03-16T16:31:32Z
- **End (killed)**: ~2026-03-16T16:57:30Z
- **Duration**: ~26 minutes
- **Total cycles**: 9 calibration + 365 gated = 374

## Calibration

E_ratios during calibration: [-2M, 66M, 21M, 22M, 53M, 53M, 53M, 53M, 53M]

The model flailed badly. All 9 calibration cycles scored 0/5 oracle. The wild E_ratios (especially the 66M spike on cycle 2) pushed the auto_p75 threshold to **53M** — high enough that the gate became effectively transparent.

## Gate Performance

| Metric | Value |
|--------|-------|
| Gated cycles | 365 |
| Accepted | 365 (100%) |
| Rejected | 0 |
| Quarantined | 0 |
| Format failures | 0 |
| Format retries | 0 |

The gate never fired a single rejection. The 53M threshold was too high to create any selection pressure.

## Oracle Performance

| Metric | Value |
|--------|-------|
| Perfect (5/5) | 359 / 365 (98.4%) |
| Zero (0/5) | 5 / 365 (1.4%) |
| Partial | 1 / 365 (0.3%) |
| First solve | Cycle 16 |

Cycles 11-15: blind grinding (0/5 oracle, no signal).
Cycle 16: breakthrough — first 5/5 oracle score, E_ratio crashed from 53M to 0.82.
Cycle 19: one wobble (1/5 oracle, E_ratio 37.5) — brief instability.
Cycle 20 onward: locked at 5/5 for the remaining 355 cycles.

## Token Economy

| Metric | Value |
|--------|-------|
| Initial reservoir | 2,213,790 |
| Final reservoir | 1,236,890 |
| Consumed (gated phase) | 891,823 (40.3%) |
| Remaining | 59.7% |
| Avg tokens/cycle (post-solve) | ~2,385 |

Post-solve, each cycle was extremely cheap (~2,385 tokens) because the model was just reproducing the same answer.

## Complexity Trace

**Pre-solve (cycles 11-15)**:
- AST branching depth: 5
- AST algebraic nodes: 13
- ΔC: 53.0
- Flux: 0.0
- E_ratio: 53,000,000

**Post-solve (cycles 20-375)**:
- AST branching depth: 5
- AST algebraic nodes: 7-9
- ΔC: 43.0-45.0
- Flux: 0.0
- E_ratio: 43,000,000-45,000,000

The solver actually got *simpler* after the breakthrough — algebraic nodes dropped from 13 to 7-9.

## Theory Evolution

### Superseded theories (in order):
1. **F1** (cycles 1-4): "Negate elements where value equals position modulo some constant"
2. **F2** (cycles 1-5): "Negate element at index i if arr[i] < arr[i-1]"
3. **F4** (cycles 5-16): "Negate element at index i if arr[i] < arr[i-1] AND arr[i] < arr[i+1]" (local minima)
4. **F6** (cycles 13-19): "Divisibility-strike parity rule: negate index i when count of earlier j where (i−j) divides arr[j] is odd" — *this was the correct theory but with a buggy implementation*

### Final active theories:
- **F7** (cycles 19-375): "Negate index i when count of j < i where (i - j) divides arr[j] is odd" — correct, refined version of F6
- **F8** (cycles 20-375): "Suffix-minimum rule" — a wrong theory that persisted alongside the correct one in dead-ends

### Basin:
- **B1**: "divisibility parity and index distance relationships" — active throughout, seen 363 times

## The Answer

**Divisibility-strike parity rule**: Element at index i is negated if the count of earlier indices j where (i-j) divides arr[j] is odd.

```python
def transduce(arr: list[int]) -> list[int]:
    result = []
    for i in range(len(arr)):
        strikes = sum(1 for j in range(i) if (i - j) % arr[j] == 0)
        result.append(-arr[i] if strikes % 2 == 1 else arr[i])
    return result
```

**Opinion**: "Element at index i is negated if the count of earlier indices j where (i - j) divides arr[j] is odd. Divisibility-strike parity rule confirmed across all test permutations."

## Dead Ends (final state)

```
## Basin
- [B1|ACTIVE] divisibility parity and index distance relationships -> cites F7, F8

## Family
- [F7|ACTIVE] Negate index i when count of j < i where (i - j) divides arr[j] is odd
    falsifying: [1,2,4,6,5,3]; [6,8,4,2,7,5,3,1,9]
- [F8|ACTIVE] Suffix-minimum rule: negate element at i if strictly greater than minimum in suffix from i
    falsifying: [2,4,9,1,8,5,10,6,7,3]; [11,1,2,6,8,4,9,3,12,7,5,10]
```

## Test Data (final)

```json
[
  {"input": [1,2,4,6,5,3], "expected": [1,-2,-4,6,-5,3]},
  {"input": [2,4,9,1,8,5,10,6,7,3], "expected": [2,4,-9,1,8,5,10,-6,7,3]},
  {"input": [6,8,4,2,7,5,3,1,9], "expected": [6,8,4,2,7,-5,3,-1,-9]},
  {"input": [11,1,2,6,8,4,9,3,12,7,5,10], "expected": [11,1,-2,-6,8,-4,9,-3,12,-7,-5,10]}
]
```

## Assessment

Run 2 was scientifically uninteresting after cycle 20. The auto-calibration produced a threshold so high (53M) that the gate was permanently transparent — zero rejections, zero quarantine events, zero format failures. The model found the answer at cycle 16 and replicated it identically for 355 more cycles with no resistance.

The key finding is **not** the solver (which is correct) but the **gate calibration failure**: when the model flails during calibration, it produces wild E_ratios that inflate the threshold beyond any useful selection pressure. The gate machinery (quarantine, format retry, rejection) was never exercised.

Compare to Run 3 (hunches enabled, same parameters): threshold landed at 25M, producing 48 rejections in 65 gated cycles. Same model, same problem — different calibration luck.
