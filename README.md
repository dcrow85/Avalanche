# Avalanche

Avalanche is a pressure chamber for agent and raw-model cognition experiments.

Current focus:
- structured falsification under memory pressure
- agent shell vs raw-model comparison
- sterile VPS chamber at `89.167.102.244`
- public control room at `https://syntropy.city`

## Primary Paths

- `hypervisor_v44_codex.py`
  Codex-agent V4.4.1 apparatus
- `hypervisor_v44.py`
  raw-model V4.4.1 apparatus
- `v44_epistemics.py`
  basin/family/local dead-end state and validation
- `v43_metrics.py`
  shared telemetry helpers
- `dashboard.py`
  live dashboard server
- `generate_research_center.py`
  public run index / archive generator
- `syntropy-site/`
  public site assets

## Working Rule

Do not rely on memory or chat history as the source of truth.

At every meaningful step:
1. update code or docs
2. run the smallest useful verification
3. record the change in Git intentionally
4. update Kepler memory when the research state changes

## Process

See:
- `INSTRUMENTATION.md`
- `REPO_WORKFLOW.md`
