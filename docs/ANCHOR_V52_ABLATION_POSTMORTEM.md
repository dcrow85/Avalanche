# Anchor V5.2 Ablation Postmortem

Date: 2026-03-25

## Scope

This document records the terminal read of the 100-cycle Anchor layer-ablation ensemble launched from the corrected Haiku `c119` snapshot.

Branches:

- `A` full apparatus: `/opt/avalanche/runs/v472-anchor-sidecar-haiku-c119-v52/run-A/run-1`
- `B` ledger only: `/opt/avalanche/runs/v472-anchor-sidecar-haiku-c119-v52/run-B/run-1`
- `C` lock only: `/opt/avalanche/runs/v472-anchor-sidecar-haiku-c119-v52/run-C/run-1`
- `D` unconstrained baseline: `/opt/avalanche/runs/v472-anchor-sidecar-haiku-c119-v52/run-D/run-1`

All four used:

- organism: `anthropic/claude-haiku-4-5`
- source snapshot: `/opt/avalanche/local-runs/v472-anchor-sidecar-haiku-c119/snapshot-c119`
- budget: `100` cycles
- full three-surface instrumentation

The question was not just whether any branch moved. It was whether any branch produced a **correct replacement crossing**: supersede the old inversion-count basin with a structurally valid replacement basin.

## Terminal Table

| Run | Layers | Crossed | Filtered macrostate transitions | Work events | Best fixed | Best combined | FORMAT_FATAL | Final active basin |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `A` | lock + ledger + scaffold | no | `0` | `0` | `0.5833` | `0.4118` | `46` | `B2` locked inversion-count basin |
| `B` | lock + ledger | no | `0` | `0` | `0.5833` | `0.4706` | `0` | `B2` locked inversion-count basin |
| `C` | lock only | no | `0` | `0` | `0.5833` | `0.6471` | `8` | `B2` locked inversion-count basin |
| `D` | no lock, no ledger, no scaffold | no | `7` | `2` | `0.5833` | `0.5882` | `7` | `B1` wrong-basin parity rule |

All four terminated at `100/100` with `MAX_CYCLES`.

## Primary Result

No branch produced a correct locked replacement crossing.

This kills the simple extended-budget hope:

- `100` cycles was not enough for `anchor-v5.2`
- `100` cycles was not enough for `anchor-v5`
- `100` cycles was not enough for `anchor-v4`
- `100` cycles without Anchor did not solve the problem either

But the branches did not fail in the same way.

## Branch Read

### A — Full apparatus

`A` was the most heavily scaffolded branch and the least mechanically healthy.

Terminal state:

- lock active and uncleared
- ledger active and `READY`
- active basin still `B2`
- zero work events
- zero filtered macrostate transitions
- `46` `FORMAT_FATAL`

The scaffold did not produce a crossing. It also did not produce superior oracle contact or superior structure relative to the simpler locked branches.

Current read:

- the four-line transaction scaffold did not unlock legal replacement execution
- it appears to have increased output fragility materially

### B — Ledger only

`B` was the cleanest locked witness.

Terminal state:

- lock active and uncleared
- ledger active and `READY`
- active basin still `B2`
- zero work events
- zero filtered macrostate transitions
- `0` `FORMAT_FATAL`

It preserved the most stable branch dynamics under lock, but still never converted ledger readiness into graveyard replacement.

Current read:

- the ledger is useful as state support
- it is not sufficient to cause a crossing
- removing the scaffold helped mechanical cleanliness, not structural success

### C — Lock only

`C` was the strongest locked branch on raw behavioral contact.

Terminal state:

- lock active and uncleared
- no ledger
- active basin still `B2`
- zero work events
- zero filtered macrostate transitions
- best combined score `0.6471`

This is important. The lock-only branch matched or exceeded the more elaborate locked branches behaviorally while still producing no structural conversion.

Current read:

- strong oracle contact is not enough
- the missing ingredient is not simply "more score" or "more time"

### D — Unconstrained baseline

`D` was the only branch with genuine macrostate movement.

Filtered transition pipeline result:

- `7` filtered macrostate transitions
- `2` work events

The transition path was:

1. tombstone `B2`
2. no-basin gap
3. `B1 = rightward dominance`
4. `B1 = right neighbor comparison`
5. `B1 = maximum preservation / negate non-maximum`
6. `B1 = inversion by rightward comparison`
7. `B1 = no negation`
8. `B1 = position-based parity rule`

Terminal active state:

- `B1` active
- claim: `position-based parity rule determines negation`

This branch moved, but it moved into cheaper wrong basins instead of a correct replacement.

Current read:

- unconstrained exploration produces motion
- the lock is not merely suppressive; it prevents cheap wrong-basin drift

## Structural Hygiene Result

The filtered transition pass matters here.

Raw graveyard hash changes were:

- `A`: `1`
- `B`: `0`
- `C`: `1`
- `D`: `7`

But after canonical transition extraction and macrostate filtering:

- `A`: `0`
- `B`: `0`
- `C`: `0`
- `D`: `7`

So the apparent motion in `A` and `C` was not a real basin crossing. It was hash churn without macrostate change.

Filtered artifacts:

- `C:\Avalanche\local-runs\v472-anchor-sidecar-haiku-c119-v52-ablation-mirror\postmortem-transitions`
- `C:\Avalanche\local-runs\v472-anchor-sidecar-haiku-c119-v52-ablation-mirror\postmortem-kramers`

## Main Findings

### 1. Extended budget alone is insufficient

None of the four branches crossed in `100` cycles.

That includes:

- full apparatus
- ledger-only
- lock-only
- unconstrained baseline

### 2. The scaffold is not load-bearing

`A` underperformed `B` mechanically and did not outperform it structurally.

The current evidence says:

- ledger-only > scaffolded ledger

for this organism on this branch point.

### 3. The lock is doing real work

The unconstrained branch was the only one that moved, and it moved in the wrong direction.

So the lock is not just preventing progress. It is also preventing wrong-basin drift.

### 4. Strong oracle contact does not imply replacement construction

`A`, `C`, and `D` all reached `0.5833`.
`C` reached `0.6471` combined.

None of that was enough to land the correct replacement under lock.

### 5. The ledger is a state aid, not a crossing mechanism

`B` stayed the cleanest locked branch with the ledger active and `READY`, but it still never crossed.

That means the ledger solved part of the bookkeeping problem, not the whole construction problem.

## Interpretation

The ensemble outcome is:

- no correct crossing at any layer
- wrong-basin motion only in the unconstrained branch
- best locked cleanliness in `B`
- best locked behavioral peak in `C`
- worst fragility in `A`

The current apparatus picture is therefore:

- `lock` is useful as containment
- `ledger` is useful as stable state support
- `scaffold` is not currently helping
- `time` alone is not enough

## Research Consequence

This does not support more prompt-side elaboration on the hot-witness problem.

`v5.2` was explicitly treated as the last clean prompt scaffold. The ablation result reinforces that decision:

- no crossing with scaffold
- no crossing without scaffold
- no crossing with ledger
- no crossing without ledger

The next experiment should therefore be a **blinded transfer problem** using the same architecture family, not a `v5.3` prompt elaboration on the same known-answer branch.

## Durable Summary

The 100-cycle Anchor ablation answered the layer question cleanly:

- no layer stack crossed
- the scaffold was not load-bearing
- the unconstrained branch was the only branch with genuine macrostate motion
- that motion went into the wrong basin

The lock prevented wrong-basin drift.
The ledger supported clean locked persistence.
Neither was sufficient for a correct replacement crossing in Haiku from `c119`.
