# Avalanche V4.3 C9 Comparison: 20-Cycle Baseline

Generated: 2026-03-10

## Scope

This note summarizes the first full 20-cycle V4.3 Codex runs on Crucible 9 (`Harmonic Sieve`) for:

- `gpt-5.3-codex` in `C:\terrarium-v43-codex`
- `gpt-5.4` in `C:\terrarium-v43-codex-54`

Both runs used the V4.3 Codex hypervisor and dashboard:

- `C:\Avalanche\hypervisor_v43_codex.py`
- `C:\Avalanche\v43_metrics.py`
- `C:\Avalanche\dashboard.py`
- `C:\Avalanche\dashboard_v43_codex.py`

Both are now being continued beyond 20 cycles, but this memo is only about the initial 20-cycle baseline.

## V4.3 Additions Over V4.1

- `D_sem`: semantic distance between consecutive `opinions.md` states
- `C_ast`: solver structural complexity via Python AST branching/loop counts
- `Delta C`: cycle-to-cycle change in solver complexity
- `Dead Ends #`: count of falsification tuples in `dead-ends.md`
- `Turbulence` classifier:
  - `BOOTSTRAP`
  - `STABLE_PATCHING`
  - `EPICYCLE_ACCUMULATION`
  - `ONTOLOGY_CHANGE`
  - `PRODUCTIVE_TURBULENCE`
- dashboard trend graphs for `D_sem`, `C_ast`, and turbulence timeline

## Shared Bottom Line

Both models failed at `20/20`.

Both showed repeated ontology shifts and real productive-turbulence events.

Neither showed a decisive phase change into the true hidden-law family. The search stayed on basin-floor geometry: peaks, minima, anchors, prefix regimes, local rebounds, visible segment structure.

## Final Failures

### `gpt-5.3-codex`

- Final failing input: `[5,7,2,2,1,8,7,6]`
- Expected: `[5,7,2,2,-1,-8,7,6]`
- Got: `[5,7,2,2,1,-8,7,6]`

Final theory:

- `a1 > a0` and `a2 <= a1` branch
- flip rightmost value `> a1`
- also flip `j-1` when it is a descending valley below `a0`

Interpretation:

- highly conditional local regime logic
- still surface-structural, not positional/divisibility-based

### `gpt-5.4`

- Final failing input: `[5,7,2,2,1,8,7,6]`
- Expected: `[5,7,2,2,-1,-8,7,6]`
- Got: `[5,7,2,2,1,8,7,6]`

Final theory:

- use the global minimum as anchor
- if repeated, negate from first minimum through before last minimum
- if unique interior minimum, negate the minimum and rising run after it
- edge cases for minimum at index `0` or the end

Interpretation:

- more global than `5.3`, but still a visible-shape theory
- still basin-bound

## Comparative Read

### `gpt-5.3-codex`

Strengths:

- steadier early trajectory
- several clear simplification events
- telemetry successfully exposed real reorganization

Weaknesses:

- `dead_ends_count` stayed flat at `1`
- late-run complexity explosion was severe:
  - cycle 17: `C_ast` jump `13 -> 50`
  - final `C_ast = 54`
- ended in a bloated local/regime taxonomy

Key telemetry:

- productive turbulence at cycles `10`, `13`, `15`
- otherwise mostly `ONTOLOGY_CHANGE`

Read:

- stable but basin-persistent
- good evidence of search, weak evidence of escape

### `gpt-5.4`

Strengths:

- more globally descriptive theories earlier
- more frequent productive-turbulence events
- more willingness to re-simplify after complexity spikes
- `dead_ends_count` reached `2` multiple times

Weaknesses:

- still repeatedly re-expanded into wrong-axis structure
- also suffered major complexity spikes:
  - cycle 14: `+25`
  - cycle 15: `+12`
  - cycle 18: `+22`
- final theory still wrong-axis anchor geometry

Key telemetry:

- productive turbulence at cycles `4`, `6`, `9`, `12`, `13`, `16`, `19`, `20`

Read:

- more exploratory and dynamically alive than `5.3`
- better search shape, same eventual failure

## Strongest Findings

1. V4.3 telemetry is useful.
   It exposed real simplification events that would have been easy to miss from prose alone.

2. Productive turbulence is real, but not sufficient.
   Both models produced it multiple times without escaping into the true causal family.

3. `gpt-5.4` appears cognitively stronger than `gpt-5.3-codex`, but not decisively.
   It reorganized more often and more aggressively, but still failed in the same broad basin class.

4. `dead-ends.md` is underperforming as negative memory.
   `Dead Ends #` remained too low in both runs. The organisms are not building a durable map of rejected families; they are mostly overwriting one or two slots.

5. No true phase change was observed.
   The runs mapped the basin floor rather than discovering the hidden positional/divisibility mechanism.

## Open Questions

1. Does productive turbulence predict anything beyond local cleanup?
   We now have many productive-turbulence events. Do any precede real basin escape, or are they just oscillations within the same wrong manifold?

2. Is `gpt-5.4` actually better, or just more theatrically exploratory?
   It looks stronger on search shape, but the endpoint did not improve.

3. Is the negative-memory channel too weak?
   A dead-end count that hovers around `1-2` suggests the hypervisor is not forcing durable falsification structure strongly enough.

4. Are we still giving the organism too many visible handholds?
   Both models remained attracted to peaks, minima, anchors, prefix regimes, and rebound geometry.

5. Is C9 just too deceptive for this memory budget?
   The 75-word / 50-word split may still allow local geometry compression without forcing the deeper abstraction we want.

6. Are the turbulence labels too permissive?
   Late `gpt-5.4` events were classified as productive turbulence because complexity dropped, but they still did not represent true causal-family migration.

## Likely Hypervisor Changes

1. Strengthen negative memory.

- Require `dead-ends.md` to preserve multiple distinct failures rather than overwriting a single slot.
- Possible change: minimum two or three live falsification tuples before compression.
- Possible change: separate `dead-ends.md` into compact bullet tuples that are machine-countable and harder to erase implicitly.

2. Try the adversarial oracle mode.

- V4.3 already has this path.
- This is the clearest next intervention to break visible-pattern matching.
- If the current theory says `peaks` or `minimum anchor`, the oracle should return bland counterexamples that specifically kill that family without offering a new surface motif.

3. Reconsider the turbulence classifier.

- Current rule is useful but still crude.
- Potential refinement: distinguish `complexity drop within same noun-family` from `complexity drop after causal-family migration`.
- That likely needs one more automated feature, such as noun-family overlap or dead-end family carryover.

4. Improve continuity telemetry.

- V4.3 continuation now loads prior `cycle_metrics.jsonl` and resumes cycle numbering.
- Good.
- Next step: optionally display session boundary markers in the dashboard so post-cap continuations are visually explicit.

5. Keep workspace hygiene strict.

- Codex tried to create extra helper files during early V4.3 smoke testing.
- The cleanup path is necessary and should remain part of the hypervisor.

## Recommendation for Next Steps

Priority order:

1. Continue both runs a bit longer only to collect more telemetry, not because the current condition looks close to a solve.
2. Run at least one V4.3 continuation or fresh run with `--oracle-mode adversarial`.
3. Strengthen `dead-ends.md` so negative memory becomes a real structure rather than a single overwritten note.
4. Compare whether adversarial oracle changes `5.4` more than `5.3`.

What not to do:

- do not treat "more cycles on unchanged condition" as the main path to success
- do not over-interpret productive turbulence as phase change
- do not pivot the research toward long-run temporal claims yet; we still need better evidence on basin escape first

## Questions for Gemini

1. Both models showed repeated productive-turbulence events but no true phase change. Does that mean our turbulence metric is too weak, or does it suggest that local basin remapping naturally contains many false-positive simplification events?

2. `gpt-5.4` looks more globally exploratory and more linguistically descriptive than `gpt-5.3-codex`, yet both failed on the same visible-structure basin. How should we interpret "better search shape, same endpoint"?

3. The weakest part of V4.3 appears to be negative memory. How would you redesign `dead-ends.md` so it forces retention of distinct falsified hypothesis families instead of a single overwritten slot?

4. Given these results, is the adversarial oracle now the highest-value next intervention, or is there a more important change to make first?

5. Do these runs support the view that C9 is primarily a basin-floor mapping problem under current memory constraints, and if so, what would count as the first unmistakable sign of a real phase change?
