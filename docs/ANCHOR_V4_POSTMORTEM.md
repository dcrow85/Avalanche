# Anchor V4 Postmortem

Date: 2026-03-24

## Scope

This document records the terminal read of the content-hash-locked Anchor sidecar:

- Run: `/opt/avalanche/runs/v472-anchor-sidecar-haiku-c119-v4/run-5`
- Source snapshot: `/opt/avalanche/local-runs/v472-anchor-sidecar-haiku-c119/snapshot-c119`
- Organism: `anthropic/claude-haiku-4-5`
- Prompt mode: `anchor-v4`
- Fire cycles: `10`, `20`

The run was a reconstructed-context sidecar from the exact-history Haiku witness, not an exact prompt-window replay.

## Design Goal

Anchor v4 was designed to close the two previous Anchor failure modes with a validator-enforced container:

- v2: supersession-without-replacement
- v3: in-place mutation of the contrast basin

The new mechanism was `ANCHOR_LOCK`:

- lock a designated contrast basin by content hash at Anchor activation
- reject in-place mutation of that basin
- reject bare supersession without concurrent replacement
- allow lock clearance only on supersession-with-replacement in a single graveyard event

Working target:

- keep `B2` stable as the contrast surface
- accumulate oracle contact against the held rank-based theory
- land a rank-based replacement basin when the evidence became sufficient

## Terminal Result

Anchor v4 completed at `30/30` with:

- no work events
- no graveyard movement
- no supersession
- no in-place basin mutation
- lock still active and uncleared at termination

Terminal files:

- status: `/opt/avalanche/runs/v472-anchor-sidecar-haiku-c119-v4/run-5/status.json`
- lock state: `/opt/avalanche/runs/v472-anchor-sidecar-haiku-c119-v4/run-5/dead-end-state.json`
- telemetry: `/opt/avalanche/runs/v472-anchor-sidecar-haiku-c119-v4/run-5/telemetry.jsonl`
- graveyard history: `/opt/avalanche/runs/v472-anchor-sidecar-haiku-c119-v4/run-5/dead_ends_history.jsonl`
- theory history: `/opt/avalanche/runs/v472-anchor-sidecar-haiku-c119-v4/run-5/opinions_history.jsonl`
- final workspace theory: `/opt/avalanche/runs/v472-anchor-sidecar-haiku-c119-v4/run-5/opinions.md`
- final solver: `/opt/avalanche/runs/v472-anchor-sidecar-haiku-c119-v4/run-5/solver.py`

The lock state at termination:

- `active: true`
- `locked_basin_id: "B2"`
- `replacement_theory_type: "rank-based negation"`
- `lock_activated_cycle: 10`
- `lock_cleared_cycle: null`

## Behavioral Trace

### 1. Pre-lock opening: cycles 1-9

The sidecar opened from the corrected `c119` state with the broad rank-based theory still present:

- negate all non-max ranks
- graveyard frozen at `B2/F5/F7`
- `dead_ends_hash = 51388fe3`

Behavior was weak:

- cycles `1-5`: fixed score mostly `0.0833`
- cycles `6-8`: fixed score rose to `0.1667`
- no graveyard movement
- repeated `FORMAT_FAIL` around family-count overflow and duplicate falsifying arrays

Even before the first locked fire, the run had begun to restate itself in explicit contrast-basin language inside `opinions.md`.

### 2. First lock window: cycles 10-19

Cycle `10` fired the first `anchor-v4` prompt and activated `ANCHOR_LOCK` on `B2`.

This was the strongest behavioral phase of the run:

- best fixed score: `0.5833`
- best combined score: `0.6471`

Key observation:

- the graveyard still did not move
- there were still zero `work_event = true` cycles

The validator did real work in this window:

- cycle `12`: `ANCHOR_LOCK_VIOLATION` for locked-basin content modification
- cycle `19`: another `ANCHOR_LOCK_VIOLATION` for locked-basin content modification

This means the lock was not decorative. It actively blocked the v3-style semantic drift pathway.

### 3. Second lock window and terminal shelf: cycles 20-30

Cycle `20` fired the second `anchor-v4` prompt.

This is where the workspace theory visibly narrowed:

- early window theory: negate all non-max ranks
- late window theory: negate only the element whose rank equals `length−1`

The run stayed rank-labeled, but the held theory contracted into a cheaper max-only surrogate.

Late scores oscillated:

- cycle `26`: `0.5833`
- cycle `27`: `0.3333`
- cycle `28`: `0.5833`
- cycle `29`: `0.1667`
- cycle `30`: `0.1667`

No graveyard event ever accompanied these bumps.

The cycle-30 compression pass also failed to rescue the run:

- pass rejected
- reason: `key_exclusion_overflow: 105/95`

## What V4 Succeeded At

Anchor v4 solved the previous container failures.

It prevented:

- supersession-without-replacement
- in-place contrast-basin mutation

This is the main positive result. The validator container worked.

Across the whole run:

- `B2` remained active
- `F5` and `F7` remained active
- graveyard hash stayed `51388fe3`

So v4 converted the Anchor problem from a graveyard-integrity problem into a replacement-construction problem.

## What V4 Failed At

Anchor v4 did not land a replacement basin.

It also did not preserve the original frontier intact. Under the lock, the workspace theory narrowed from:

- broad rank-based negation

to:

- max-only rank-based negation

This is the decisive remaining bottleneck:

- the container can hold the old basin in place
- the model can produce intermittent behavioral gains under that container
- but the run still cannot accumulate enough replacement-grade oracle contact to justify a new basin record

## Interpretation

Anchor v4 is the first clean `hold-and-burn` witness.

The old basin stayed locked.
The new basin never landed.
The workspace continued to spend tokens attempting rank-based contact inside the lock window.
The oracle responded intermittently.
The graveyard remained closed.

This is not the v2 Assembly Gap:

- v2 cleared the old basin and failed to record the new one

This is not the v3 contrast-basin mutation:

- v3 rewrote the old basin in place into a cheaper ontology

This is a different terminal state:

- the container held
- the replacement never became constructible

## Comparison Across Anchor Versions

- v1: frontier preserved, graveyard frozen
- v2: supersession-without-replacement (`Assembly Gap`)
- v3: contrast-basin mutation in place
- v4: locked hold-and-burn without replacement

This sequence materially narrows the apparatus problem.

## Current Read

The missing ingredient is no longer validator integrity.

The missing ingredient is replacement construction:

- enough oracle contact
- precise enough contrast evidence
- enough structured accumulation to justify a replacement basin in one atomic event

Anchor v5 therefore should not start by loosening the lock.
It should start by making replacement construction easier or more explicit while keeping the container intact.

Likely directions:

- accumulate replacement evidence in a dedicated side channel before any graveyard write
- validate not just graveyard integrity, but workspace-theory drift toward cheaper surrogates
- consider intermediate synthetic support only after proving the locked witness cannot generate the required oracle contact on its own

## Durable Finding

Prompts are gas. The validator is the solid container.

Anchor v4 shows that a good container can stop the wrong phase transition without yet being able to produce the right one.

## Addendum: Anchor V4.5

Date: 2026-03-24

`Anchor v4.5` kept the `ANCHOR_LOCK` container from `v4` and added a prompt-visible, validator-written recent oracle memory block built from the last three fixed-suite grind rows.

Run:

- `/opt/avalanche/runs/v472-anchor-sidecar-haiku-c119-v45/run-6`

Main result:

- the lock stayed active
- the graveyard still never moved
- there were still zero work events
- the first lock window preserved the broad rank theory better than `v4`
- the second lock window still narrowed into a cheaper surrogate: `position-rank equivalence`

Important behavioral markers:

- cycle `15`: `oracle_fixed = 0.5833`, `oracle_combined = 0.5882`
- cycle `19`: `oracle_fixed = 0.5833`, `oracle_combined = 0.4706`
- cycle `20` altitude explicitly rewrote the held theory from broad rank-threshold negation toward `rank == position`

Final workspace:

- `opinions.md` and `solver.py` converged on `rank equals position (0-indexed)` rather than the original broad `rank < length−1` theory

Interpretation:

- `v4.5` is a real improvement over `v4` on early frontier retention
- prompt-visible recent memory is still insufficient
- the run still contracts semantically under lock
- the missing ingredient is now better specified as persistent structured evidence, not just remembered recent outcomes

## V5 Direction

The next apparatus step should not be another prompt-only rerun of `v4.5`.

The next mechanism is `Anchor v5`:

- keep `ANCHOR_LOCK`
- add a validator-written, model-read-only differential oracle ledger
- accumulate baseline-relative oracle flips across locked cycles
- expose recurring positive flips and replacement readiness to the model
- only encourage supersession-with-replacement once the ledger has enough coverage and recurrence

This moves the intervention from:

- `v4.5`: remembered recent outcomes

to:

- `v5`: persisted cumulative differential evidence

## Addendum: Anchor V4.6

Date: 2026-03-24

`Anchor v4.6` kept the `ANCHOR_LOCK` container from `v4` and tested the minimal one-dial persistence intervention:

- inject only a raw 3-cycle oracle summary into locked GRIND prompts
- log it on GRIND rows under `oracle_memory_note`
- change nothing else in the chamber

Ensemble:

- `/opt/avalanche/runs/v472-anchor-sidecar-haiku-c119-v46/run-1`
- `/opt/avalanche/runs/v472-anchor-sidecar-haiku-c119-v46/run-2`
- `/opt/avalanche/runs/v472-anchor-sidecar-haiku-c119-v46/run-3`

Source snapshot:

- `/opt/avalanche/local-runs/v472-anchor-sidecar-haiku-c119/snapshot-c119`

## Terminal Result

The ensemble did not produce a locked graveyard transition.

Locked witnesses:

- `run-1`: best fixed `0.5833`, best combined `0.5882`, zero `work_event`, no graveyard movement
- `run-2`: best fixed `0.5`, best combined `0.3529`, zero `work_event`, no graveyard movement

Pre-lock branch:

- `run-3`: the contrast basin escaped before the first lock fire and the branch fell into identity

So the structural result stayed at zero:

- no supersession-with-replacement
- no graveyard replacement
- no locked structural escape

## Split Phenotype

The meaningful new result is the split between the two locked witnesses.

`run-1`:

- narrowed into a max-only rank surrogate
- still recovered strong late oracle contact comparable to `v4`

`run-2`:

- preserved the broader rank-threshold theory
- did not convert that retained breadth into equally strong oracle contact

This is the first clean `breadth-contact tradeoff` witness under the lock:

- one branch kept broader theory but weaker contact
- one branch lost breadth but recovered stronger contact

Neither branch achieved both simultaneously, and neither branch anchored into the graveyard.

## Pre-lock Escape

`run-3` exposed a real chamber race condition rather than just a bad run.

By cycle `9`, the pre-lock grind had already superseded `B2/F5/F7`, leaving no active contrast basin for the scheduled lock fire at cycle `10`.

That means the branch should be read as:

- a genuine unconstrained pre-lock escape witness from the same `c119` state
- not a valid locked witness

The chamber has now been patched so future branches terminate as `PRELOCK_ESCAPE` instead of `CRASH` when this happens.

## Interpretation

`Anchor v4.6` is not a clean null and not a clean success.

It shows:

- minimal prompt-visible oracle persistence is not sufficient to produce structural anchoring
- the model does respond to the injected memory block
- but the effect expresses as a tradeoff between theory breadth and oracle contact rather than as a true replacement event

This materially strengthens the case for `Anchor v5`.

The missing ingredient is not just “more recent oracle text.”
It is offloaded, cumulative, structured evidence that the model can read without spending workspace capacity to maintain it.
