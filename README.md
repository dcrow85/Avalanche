# Avalanche

Avalanche is an independent research program studying LLM cognition under pressure — how models build, revise, and abandon theories when confronted with problems they cannot solve immediately.

## The Gravity Tokenizer

The first public result from this program: a tokenizer optimization that produces the best known 16MB language model, submitted to the [OpenAI Parameter Golf Challenge](https://github.com/openai/parameter-golf).

**val_bpb: 1.0310** | Previous SOTA: 1.1194 | 15.6 MB artifact | 8xH100 SXM

At extreme parameter budgets, every vocabulary slot matters. Standard BPE allocates tokens by frequency. The Gravity Tokenizer allocates by **ablation leverage** — how much downstream loss increases when a token is shattered back to bytes. This single change, with a vanilla transformer and no architectural novelties, beats every submission on the leaderboard.

**Key findings:**
- Replacing 659 of 765 merge tokens by gravity scoring improves BPB by 0.139 at matched training budget
- The effect scales linearly with the number of swaps — no diminishing returns observed
- Bifurcation scoring (optimizing for leverage *jumps*) fails: tokens that look individually redundant are collectively essential
- Warm-starting embeddings fails: the crystallization plateau is a whole-model phase transition, not an embedding-local phenomenon

See [`gravity-tokenizer/`](gravity-tokenizer/) for the full pipeline, data, and competition submission materials.

The gravity tokenizer is an instance of the framework described in [`GENERATIVE_CLOSURE.md`](GENERATIVE_CLOSURE.md) — specifically, the crystallization of meaning through phase transitions at assembly thresholds (Section VIII). The vocabulary's leverage scores are a direct measurement of non-fungibility at the token level: the structural cost of shattering a committed unit back into interchangeable fragments.

## The Research Program

Beneath the tokenizer result is a broader investigation into the thermodynamics of LLM cognition. The Avalanche apparatus places a model in a long-running loop against an oracle and measures how its internal theory evolves. The theoretical framework for this program is described in [`GENERATIVE_CLOSURE.md`](GENERATIVE_CLOSURE.md).

### Core Questions

- How does structural knowledge crystallize under pressure?
- What is the relationship between search activity and epistemic progress?
- Can the history of ruled-out approaches (the "graveyard") carry more information than the model's active theory?

### Current Working Sentences

> The graveyard knows more than the model does.

> Thermodynamic activity measures search motion, not epistemic ascent.

### Active Fronts

1. **Graveyard Epistemics** (V4.7) — The graveyard as the primary epistemic artifact. Probe instruments can read directional structure out of accumulated failure more reliably than the live model can navigate by it. Cartography is ahead of navigation.

2. **Compression and Altitude** — Two distinct intervention families for steering model search. Compression reduces slot count. Altitude lifts the model into broader vocabulary or new ontology families, but usually one ridge at a time.

3. **The Gravity Tokenizer** — Vocabulary optimization for extreme parameter budgets, demonstrating that structural importance (measured by ablation leverage) diverges sharply from frequency at small vocabulary sizes.

### Key Findings

- Models under compression pressure rewrite rather than distill — compression changes ontology but does not induce stable distillation
- Search history is spiral/braided, not a monotonic ladder
- Narrative-shaped signals are dangerous in both prompts and probes; flat signals preserve inference pressure
- Graveyard volume and graveyard depth are not the same thing
- The crystallization cliff (a sharp phase transition during training) is a whole-model phenomenon — embeddings are entangled with transformer weights

## Primary Witnesses

| Run | Role | Key Observation |
|-----|------|-----------------|
| run-12 | Recovery witness | Thick basin lost, then recovered |
| run-39 | Structural lifecycle | Promotion, decay, fossil preservation |
| run-51 | Graveyard legibility | Richest fossils, saturated v1 altitude |
| run-55 | Phase 2b witness | Live one-ridge negative-space altitude |

## Apparatus

The V4.7 apparatus runs on three parallel backends:
- `hypervisor_v44.py` — raw model API (Qwen, Grok, Haiku)
- `hypervisor_v44_codex.py` — Codex agent shell
- `hypervisor_v44_claude.py` — Claude Code agent

Observation surface: live dashboards, spectral telemetry, compression assays, probe tooling.

Public control room: [syntropy.city](https://syntropy.city)

## Repo Structure

```
gravity-tokenizer/      Gravity Tokenizer pipeline and competition entry
  scripts/              Scoring, vocabulary construction, retokenization, generation
  data/                 Scored candidates, vocabularies, tokenizers, charts
  parameter-golf/       OpenAI competition fork (submodule)

compression_assay.py    V4.7 assay runner
hypervisor_v44.py       Raw-model hypervisor
hypervisor_v44_codex.py Codex-agent hypervisor
hypervisor_v44_claude.py Claude-agent hypervisor
v44_epistemics.py       Basin/family/local state and graveyard logic
v43_metrics.py          Shared telemetry and spectral probes
dashboard.py            Live dashboard server
haiku_probe.py          Read-only probe instrument
tests/                  Regression coverage (18 files)
docs/                   Architecture, project state, experiment index
local-runs/             Run archives (24+ historical runs)
syntropy-site/          Public site assets
```

## Documentation

- [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) — Current frontier and findings
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — Apparatus design and memory surfaces
- [`docs/EXPERIMENT_INDEX.md`](docs/EXPERIMENT_INDEX.md) — Experiment map and witness runs
- [`gravity-tokenizer/data/tokenizer_scrutiny_doc.md`](gravity-tokenizer/data/tokenizer_scrutiny_doc.md) — Tokenizer correctness documentation
