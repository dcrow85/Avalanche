# Sterile Chamber Progress Note

Date: March 12, 2026

## Context

We moved Avalanche into the sterile VPS chamber at `89.167.102.244` under a clean `ava` user and ran the permutation-only, anti-cache V4.4.1 branch there.

Conditions now observed:

1. Codex agent, `gpt-5.3-codex`
2. Codex agent, `gpt-5.4`
3. Raw Qwen, `qwen/qwen3-coder`
4. Raw Grok, `xai/grok-4-1-fast-non-reasoning`
5. Raw Haiku, `anthropic/claude-haiku-4-5-20251001`

This is now a real sterile comparison between agent-shell organisms and raw-model organisms under the same chamber.

## What happened

### Sterile Codex agents

Both Codex organisms failed at 10 cycles in the sterile permutation chamber.

- `gpt-5.3-codex`
  - ended at `1` basin, `2` families, `3` locals
  - high baroque solver burden: final `ptolemaic_ratio = 12.0`
  - opinion language remained pivot / rebound / corridor geometry
- `gpt-5.4`
  - ended at `1` basin, `3` families, `4` locals
  - much cleaner hierarchy use: final `ptolemaic_ratio = 5.33`
  - still trapped in the same broad corridor / global-minimum family

Read: the sterile Codex shell still produces the strongest structured epistemics, but also the highest apparatus overhead and the strongest tendency toward elaborate geometric false-basin construction.

### Raw Qwen

Qwen survived a full 29-cycle run.

- final public state: `2` basins, `3` families, `4` locals
- latest recorded metric snapshot: `1` basin, `2` families, `3` locals
- final `ptolemaic_ratio = 3.5`
- final theory remained geometry-heavy: local maxima / descending-context logic

Read: Qwen is the steadiest raw organism so far. It is cheaper and cleaner than Codex, but still seems basin-bound and conservative in ontology movement.

### Raw Grok

Grok finished 29 cycles after we patched the ratchet timeout. It initially appeared stalled, but the actual issue was a non-terminating solver written by the organism. The raw hypervisor now has a hard solver execution timeout.

Grok’s trace is the most cognitively interesting raw run so far:

- it built real basin structure early
- it explicitly superseded old basins
- it dropped all active basins around cycles `17-19`
- it then created a new basin family centered on `first 1` / position-trigger logic
- by cycle 29 it had `1` active basin, `3` families, `1` local
- final `ptolemaic_ratio = 1.0`
- final `compression_ratio = 10.0`

But it is also the least coherent:

- at one point its active solver, opinions, and witness set did not agree at all
- mid-run it matched `0/4` current witness pairs while still carrying active theory structure
- it seems willing to destroy and replace ontology faster than it can stabilize mechanism

Read: Grok is the first raw organism that really looks capable of basin replacement mid-run. It is volatile, fragmented, and interesting.

### Raw Haiku

Haiku is alive in the chamber, but it is the least compliant raw organism.

- many early `FORMAT_FAIL`s before the first clean sync
- eventually completed 30 cycles
- final state: `1` basin, `2` families, `1` local
- final `ptolemaic_ratio = 1.5`
- final theory moved into a value/rank-style ontology:
  - "negate when value equals count of strictly lesser elements"
- the final basin was brand new (`B2`) while the last metric snapshot shows basin tenure reset to `1.0`

Read: Haiku did not collapse, but it looks bureaucratically brittle. It eventually found a more arithmetic / rank-like explanatory family than the other raw runs, but only after a very noisy climb through the chamber.

## Current comparative picture

### Agent vs raw

The split is now explicit:

- Codex agents are slower, heavier, and much better at maintaining hierarchy
- raw models are faster, cleaner, and cheaper per cycle
- raw models currently show less epistemic bureaucracy but also weaker solver/witness coherence

So Avalanche is now measuring two distinct things:

1. agent architecture under epistemic pressure
2. raw-model induction under epistemic pressure

That distinction is no longer theoretical. The traces now show it directly.

### Organism personalities inside the sterile chamber

- `gpt-5.3-codex`: durable but baroque
- `gpt-5.4`: durable and more disciplined
- Qwen-Raw: steady but basin-bound
- Grok-Raw: volatile, fast, willing to kill basins
- Haiku-Raw: brittle, noisy, eventually rank/arithmetic-leaning

## Most important findings

1. The sterile chamber works. We can now compare agent shells and raw models without Kepler-skill leakage.
2. Codex still uses the hierarchy best, but pays for it with much larger overhead and more elaborate false geometry.
3. Qwen proved the raw path is stable enough for long runs.
4. Grok exposed a new phenomenon: raw basin replacement without stable mechanism retention.
5. Haiku suggests a third raw behavior mode: format-fragile but capable of shifting into rank-like explanatory language.

## Questions for DeepThink

1. How should we interpret Grok’s behavior?
Is this the first genuine sign of raw-model basin replacement, or just unstable theory thrashing that looks deeper than it is?

2. Does Qwen’s steadiness represent healthier induction, or just lower-energy entrapment in a geometric basin?

3. Haiku is interesting because it drifted toward rank/count ontology rather than local geometry. Should we treat that as the most promising causal-family hint so far, or just another cheap arithmetic epicycle?

4. What should we optimize next for raw organisms:
- coherence between solver, opinions, and witness set
- higher promotion pressure
- or explicit penalties for basin churn without supporting local/family evidence?

5. Do the current results suggest that agent shells help mostly with epistemic bookkeeping while raw models expose the real inductive boundary?

6. Is the next best experiment:
- repeated raw trials for reproducibility
- another sterile Codex pass with token-burn instrumentation
- or the Friday Codex-vs-Claude-Code agent showdown?

7. Should Grok’s solver/witness incoherence be treated as a chamber bug, or as a real scientific signal that ontology migration can outrun local mechanism stabilization?
