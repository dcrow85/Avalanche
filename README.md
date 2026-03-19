# Avalanche

Avalanche is a pressure chamber for agent and raw-model cognition experiments.

The current research program studies how a model's active theory, graveyard of ruled-out approaches, and contact with an oracle co-evolve over long runs on hard problems the system cannot solve immediately.

The present target is `Orbit Parity`:
- input: a 1-indexed permutation
- task: decompose it into disjoint cycles
- output rule: negate elements that belong to even-length cycles

This problem matters because the current scaffold can preserve and elaborate wrong theories, but still tends to collapse into local comparison heuristics instead of reaching cycle structure.

## Current Frontier

Avalanche is now past basic apparatus bring-up. The active frontier is:
- `V4.7` apparatus work on top of the `V4.6` Orbit Parity finding
- compression and altitude as distinct intervention families
- read-only probes over accumulated run state
- the graveyard as the primary epistemic artifact

The strongest current working sentence is:

> The graveyard knows more than the model does.

## Start Here

If you are new to the repo, read these in order:

1. [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md)
   Current frontier, key findings, live branches, and what matters now.
2. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
   The apparatus, memory surfaces, interventions, and evidence classes.
3. [`docs/EXPERIMENT_INDEX.md`](docs/EXPERIMENT_INDEX.md)
   A compact map of the major experiment lines and witness runs.
4. [`INSTRUMENTATION.md`](INSTRUMENTATION.md)
   Telemetry and dashboard surface.
5. [`REPO_WORKFLOW.md`](REPO_WORKFLOW.md)
   How to change the repo without muddying the evidence.

## Repo Shape

Core apparatus:
- `compression_assay.py`
  V4.7 assay runner for compression and altitude experiments.
- `hypervisor_v44.py`
  raw-model V4.4.1/V4.7-compatible hypervisor.
- `hypervisor_v44_codex.py`
  Codex-agent hypervisor.
- `v44_epistemics.py`
  basin/family/local state, validation, and graveyard logic.
- `v43_metrics.py`
  shared telemetry helpers and spectral probes.

Observation surface:
- `dashboard.py`
  live dashboard server
- `generate_research_center.py`
  public run index / archive generator
- `syntropy-site/`
  public control-room assets

Supporting tools:
- `haiku_probe.py`
  read-only probe for re-prompting frozen run snapshots
- `tests/`
  focused regression coverage

## Project Shape

There are now three main research surfaces in Avalanche:

- `live runs`
  organism behavior under pressure in the chamber
- `archaeology`
  post-hoc reading of run traces, graveyards, and superseded theories
- `probes`
  cheap read-only re-reads of frozen state, including synthetic and grafted conditions

The project has gradually shifted from "make the apparatus work" toward:
- reading the shape of structured failure
- understanding ridge-by-ridge search
- separating cartography from navigation

## Working Rule

Do not rely on memory or chat history as the source of truth.

At every meaningful step:
1. update code or docs
2. run the smallest useful verification
3. record the change in Git intentionally
4. update Kepler memory when the research state changes
