# Architecture

Avalanche is a closed-loop cognition apparatus.

At a high level:
- give the organism a hard problem
- let it form a theory and solver
- test against an oracle
- preserve only the memory surfaces the scaffold provides
- repeat over many cycles

## Core Loop

Each cycle broadly consists of:
- `GRIND`
  produce or update the current theory and solver
- `RATCHET`
  test against the oracle and collect contradictions
- `SYNC_FAILURE` / repair
  integrate falsification into the exocortex

Depending on branch/condition, extra intervention cycles can fire.

## Memory Surfaces

Avalanche currently has two main exocortical surfaces:

- `opinions.md`
  active working memory
  - overwritten frequently
  - cheap
  - fungible
  - tracks what the model believes now

- `dead-ends.json`
  live graveyard surface
  - accumulated ruled-out approaches
  - basin/family/local structure
  - path-dependent
  - much less fungible

Deeper archaeological surfaces also matter:
- `dead-end-state.json`
- `superseded_theories.jsonl`

These preserve more of the construction history than the thin live graveyard view alone.

## Boundary

The oracle is the boundary between theory and reality.

Without oracle contact:
- failures are not anchored
- tombstones are not trustworthy
- the graveyard loses epistemic force

The graveyard's meaning comes from repeated falsification, not from description alone.

## Intervention Families

### Compression

Compression experiments test what happens when working memory is pressured or rewritten.

Important distinction:
- prompt-budget compression
- structured rewrite
- true compression

These are not the same mechanism.

### Altitude

Altitude experiments interrupt ordinary search and ask the model to reflect on its own history.

Important distinction:
- survey/comparison altitude
- negative-space altitude

The second asks what the pattern of elimination has left untested.

### Probes

Probes are read-only interventions on frozen state.

They do not modify live runs.
They let us ask:
- what the model can read from active theory
- what it can read from the graveyard
- what it can infer from the gap left by eliminations

Probe classes used so far:
- offline probe
- synthetic probe
- graft probe
- chronology probe

## Evidence Classes

Avalanche now uses several distinct evidence classes:

- `live-run`
  direct behavior inside the chamber
- `archaeology`
  post-hoc reading of traces and fossils
- `offline-probe`
  read-only prompting of frozen run state
- `synthetic-probe`
  read-only prompting of constructed state
- `control`
  comparison condition for interpreting a probe
- `contaminated`
  mechanically compromised evidence that should not carry the whole claim

These should not be mixed casually.

## Current Architectural Tension

The strongest current architectural tension is:

- the graveyard can be read better than it can be used

That is why the project now distinguishes:
- `cartography`
  reading the structure of the graveyard
- `navigation`
  getting a live organism to move through that structure

## Canonical Files

Main code paths:
- `compression_assay.py`
- `hypervisor_v44.py`
- `hypervisor_v44_codex.py`
- `v44_epistemics.py`
- `v43_metrics.py`

Observation and archive:
- `dashboard.py`
- `generate_research_center.py`
- `syntropy-site/`

Probe surface:
- `haiku_probe.py`
