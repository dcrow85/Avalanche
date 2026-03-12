# Instrumentation Map

This file is the compact source of truth for Avalanche telemetry.

## Current Telemetry Surface

### Shared V4.4.1 telemetry

Implemented in:
- `v43_metrics.py`
- `v44_epistemics.py`
- `hypervisor_v44.py`
- `hypervisor_v44_codex.py`

Recorded in:
- `cycle_metrics.jsonl`
- `status.json`
- `cycle_snapshots.jsonl`

Core fields:
- `opinions_word_count`
- `opinions_jaccard_distance`
- `solver_ast_complexity`
- `solver_ast_delta`
- `turbulence_state`
- `ptolemaic_ratio`
- `ptolemaic_ratio_dominant_period`
- `ptolemaic_ratio_dominant_power_ratio`
- `ptolemaic_ratio_spectral_entropy`
- `ptolemaic_ratio_low_high_power_ratio`
- `ptolemaic_ratio_pink_beta`
- `ptolemaic_ratio_pink_distance`
- `ptolemaic_ratio_pink_closeness`
- `dead_ends_count`
- `dead_end_basin_count`
- `dead_end_family_count`
- `dead_end_local_count`
- `dead_end_family_retention`
- `dead_end_basin_retention`
- `dead_end_ontology_count`
- `ontology_migration_rate`
- `compression_ratio`
- `basin_tenure`

### Opinions spectrum telemetry

Implemented in:
- `v43_metrics.py:text_signal_metrics`

Current fields:
- `opinions_char_count`
- `opinions_line_count`
- `opinions_avg_line_length`
- `opinions_line_length_std`
- `opinions_char_entropy`
- `opinions_symbol_density`
- `opinions_uppercase_density`
- `opinions_digit_density`
- `opinions_entropy_pink_beta`
- `opinions_entropy_pink_distance`
- `opinions_entropy_pink_closeness`
- `opinions_entropy_pink_window`

Purpose:
- move beyond word count
- detect changes in compression style
- give a small spectral read on prose shape

### Raw API usage telemetry

Implemented in:
- `hypervisor_v44.py`

Current fields:
- `api_call_count_cycle`
- `api_prompt_tokens_cycle`
- `api_completion_tokens_cycle`
- `api_total_tokens_cycle`
- `api_reasoning_tokens_cycle`
- `token_pink_beta`
- `token_pink_distance`
- `token_pink_closeness`
- `token_pink_window`

Important:
- this only applies to runs launched after the instrumentation patch
- current in-flight processes do not retroactively gain these metrics

### Snapshot playback telemetry

Implemented in:
- `hypervisor_v44.py`
- `hypervisor_v44_codex.py`
- `dashboard.py`
- `generate_research_center.py`
- `syntropy-site/run.html`

Recorded in:
- `cycle_snapshots.jsonl`

Purpose:
- per-cycle `opinions.md` playback
- per-cycle `dead-ends.md` playback
- live and archive scrub-through

Important:
- old runs without `cycle_snapshots.jsonl` fall back to synthetic final-state playback

## Dashboard Surface

Implemented in:
- `dashboard.py`

Currently surfaced:
- `D_sem`
- `C_ast`
- `Delta C`
- `Dead Ends #`
- `DE Families`
- `Retention`
- `Ontology #`
- `Turbulence`
- `Tokens` (raw only, new launches)
- `H_char` (new launches)
- `P_beta`
- `OpPink`
- `TokPink`

## What Is Still Missing

Not yet implemented or not yet reliable:
- Codex-shell token accounting
- per-phase token accounting
- token cost per successful sync
- solver/witness coherence score as a first-class metric
- cross-run spectral comparison tooling
- automated Git commit metadata tied to run launches
- scale-domain pink-noise estimates (DFA / fluctuation style)

## Interpretation Notes

- displayed cycle count is not the same as meaningful metric count
- external provider limits can create fake `GRIND -> FORMAT_FAIL` tails
- raw token metrics are useful only when provider `usage` is actually returned
- `opinions_char_entropy` is a probe, not a settled theory metric
- Current pink-noise pass is frequency-domain only: log-log spectral slope over cycle-indexed telemetry.
- The main alternative branch is scale-domain fluctuation analysis (for example DFA / Hurst-style estimates). That branch is not implemented yet and should be treated as a separate probe family, not mixed silently into the current metrics.

## Minimum Read Before Changing Instrumentation

1. `hypervisor_v44.py`
2. `hypervisor_v44_codex.py`
3. `v43_metrics.py`
4. `dashboard.py`
5. this file
