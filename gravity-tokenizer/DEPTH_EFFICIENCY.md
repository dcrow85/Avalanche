## Your AI is Wasting Most of Its Brain on the Wrong Words

We ran a probe on Qwen 2.5, a 72-billion parameter language model with 80 layers of neural network depth. We measured how much work each layer does for every token in the vocabulary — 2,935 tokens, 100,000 tokens of text, one forward pass with hooks on all 80 layers.

The finding: the model doesn't use all 80 layers equally. Not even close.

### What we measured

For every token at every layer, we captured the **velocity** — how much the token's internal representation changes as it passes through that layer. High velocity means the model is actively processing. Low velocity means the layer is idle for that token. Zero velocity means the layer did nothing.

### What we found

**Semantically rich words use the full depth of the network.**

The word "blood" enters the model and is actively processed at every layer. Its velocity rises smoothly from layer 0 through layer 79. Each layer builds on the last. The model spends its full 80 layers of depth understanding this token in context.

```
"blood" — velocity by layer depth
L00:  ·
L10:  ·
L20:  #
L30:  ##
L40:  ###
L50:  ####
L60:  ########
L70:  #############
L79:  ████████████████████████████████████████ (peak)
```

**Fragments and single characters waste most of the network.**

The token "B" (a single capital letter) enters the model and sits idle for the first 40 layers. The model can't do anything useful with it — a lone letter has no semantic identity. Then at the final layer, the model panics: it must produce a prediction, so it crams all deferred processing into one catastrophic burst.

```
"B" — velocity by layer depth
L00:  ·
L10:  ·
L20:  ·
L30:  ·
L40:  ·
L50:  ···
L60:  ····
L70:  ·········
L79:  █████████████████████████████████████████████████ (panic)
```

The difference is not subtle. We measured it as a **panic ratio** — how much more work the final layer does compared to the middle layers. Semantically rich tokens have a panic ratio around 6. Single characters and fragments have a panic ratio above 10. The worst token we measured ("Our" at the start of a sentence) had a panic ratio of 12.75 — the model's final layer did nearly 13 times more work than the average middle layer.

### What this means

Every large language model uses a **tokenizer** — a system that breaks text into chunks before the model sees it. Standard tokenizers (called BPE) choose these chunks by frequency: common letter combinations become tokens regardless of whether they carry meaning.

This means a significant fraction of the vocabulary consists of fragments, partial words, and single characters that carry almost no semantic information. Our probe shows that for these tokens, **the model wastes 60 of its 80 layers doing nothing useful.**

Think of it this way: you're paying for an 80-story office building, but 60 floors are empty for a quarter of your tenants. The building is the same size. The electricity bill is the same. But only 20 floors are doing work.

### The numbers

| Token type | Example | Panic ratio | Layers effectively used |
|---|---|---|---|
| Rich words | blood, European, radiation | ~6 | ~60-70 of 80 |
| Common words | National, John, High | ~7-8 | ~40-60 of 80 |
| Single capitals | B, P, T | ~10-11 | ~15-20 of 80 |
| Fragments | -of, pre, rom | ~10-11 | ~15-20 of 80 |
| Sentence starters | Our, What, You | ~11-13 | ~10-15 of 80 |

### What can be done about it

Earlier this week, we submitted a tokenizer called the **Gravity Tokenizer** to OpenAI's Parameter Golf competition. Instead of selecting vocabulary tokens by frequency, it selects them by **structural importance** — measured by how much the model's predictions collapse when you remove a token from the vocabulary.

On a 12-layer model, replacing 86% of the vocabulary by this method improved compression by 0.212 bits per byte — more than any architectural change on the leaderboard. The submission beat every other entry with a vanilla transformer and no architectural novelties.

The depth probe explains why. The gravity tokenizer gives the model tokens it can actually use across its full depth. Standard BPE gives it fragments that waste most of the architecture.

This probe is the first measurement of depth efficiency across a full frontier-scale vocabulary. The same physics that works at 12 layers works at 80. The waste just gets more expensive.

### The data

All probe results are available in this repository. The probe ran on 2x A100 GPUs processing 100,000 tokens through Qwen 2.5-72B with velocity hooks on all 80 layers. Total compute cost: approximately $3.

- Probe results: [`data/qwen72b_depth_probe_results.json`](data/qwen72b_depth_probe_results.json)
- Probe script: [`scripts/qwen72b_depth_probe.py`](scripts/qwen72b_depth_probe.py)
- Gravity Tokenizer competition submission: [`parameter-golf/records/gravity_tokenizer/`](parameter-golf/records/gravity_tokenizer/)
- Full theoretical framework: [`GENERATIVE_CLOSURE.md`](../GENERATIVE_CLOSURE.md)
