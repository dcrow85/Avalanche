# Avalanche

Avalanche is an independent research program studying LLM cognition under pressure: how models build, revise, and abandon theories when the task resists immediate solution.

## What This Repo Is

This repository is a working research lab, not a single submission archive.

The current public frontier is:
- `V4.7.1` apparatus work on graveyard legibility, ontology traps, and intervention design
- the Generative Closure Fast Bench, a small public substrate for testing exact posterior vs diagnostic memory claims
- tokenizer and probe side-lines that remain useful as witnesses, controls, and negative results

## Current Questions

- What kind of epistemic object is the graveyard?
- Can a model read the shape of its own eliminations?
- Can that read change live search rather than only offline interpretation?
- How do thermodynamic activity, basin escape, and ontology change relate to one another?

## Current Read

- The graveyard is structured and path-dependent, but currently more legible than usable.
- Thermodynamic activity measures search motion, not epistemic ascent.
- Score and ontology dissociate sharply.
- Read-only probes become useful once enough assembly exists.
- In the Fast Bench, exact knowledge is separated from diagnostic memory; graveyard and index surfaces are not the posterior itself.

## Start Here

- [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) - compact public state of the research program
- [`docs/generative_closure/README.md`](docs/generative_closure/README.md) - Fast Bench spec and Campaign 1 manifest bundle
- [`GENERATIVE_CLOSURE.md`](GENERATIVE_CLOSURE.md) - March 2026 conceptual essay with April 2026 author note
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) - apparatus design and memory surfaces
- [`docs/EXPERIMENT_INDEX.md`](docs/EXPERIMENT_INDEX.md) - experiment map and witness runs

## Main Research Lines

1. **Avalanche apparatus** - Long-running oracle loops, graveyard formation, calorimetry, probe surfaces, and intervention design.
2. **Generative Closure Fast Bench** - A binary cellular-automaton Drosophila for exact closure, witness-budgeted probing, and manifest-controlled hidden-rule campaigns.
3. **Gravity tokenizer and token probes** - An earlier line of work around vocabulary structure, depth efficiency, and token crystallization. This line remains useful, but its older competition framing and stronger "gravity/lensing" claims should be read as historical artifacts rather than the current center of the project.

## Primary Witnesses

| Run | Role | Key Observation |
|-----|------|-----------------|
| run-12 | Recovery witness | Thick basin lost, then recovered |
| run-39 | Structural lifecycle | Promotion, decay, fossil preservation |
| run-51 | Graveyard legibility | Richest fossils, saturated altitude baseline |
| run-55 | Phase 2b witness | Best live negative-space altitude witness |

## Apparatus

The `V4.7` apparatus currently runs across three parallel backends:
- `hypervisor_v44.py` - raw model API
- `hypervisor_v44_codex.py` - Codex agent shell
- `hypervisor_v44_claude.py` - Claude Code agent

Observation surface:
- live dashboards
- spectral telemetry
- compression assays
- read-only probe tooling

Public control room: [syntropy.city](https://syntropy.city)

## Repo Structure

```text
docs/                   Architecture, project state, experiment index
docs/generative_closure/ Public Fast Bench bundle and Campaign 1 manifest

compression_assay.py    V4.7 assay runner
hypervisor_v44.py       Raw-model hypervisor
hypervisor_v44_codex.py Codex-agent hypervisor
hypervisor_v44_claude.py Claude-agent hypervisor
v44_epistemics.py       Basin/family/local state and graveyard logic
v43_metrics.py          Shared telemetry and spectral probes
dashboard.py            Live dashboard server
haiku_probe.py          Read-only probe instrument

gravity-tokenizer/      Earlier tokenizer line, probes, and archival submission materials
local-runs/             Run archives and witness outputs
syntropy-site/          Public site assets
tests/                  Regression coverage
```

## Notes On Historical Material

- Some documents in `gravity-tokenizer/` preserve the original competition-era framing because they are archival witnesses of that phase.
- Some conceptual language in [`GENERATIVE_CLOSURE.md`](GENERATIVE_CLOSURE.md) is stronger than the current empirical read; use the April 2026 author note and the Fast Bench bundle as the current public correction layer.
