# Generative Closure Fast Bench

This directory is the public Fast Bench bundle for the Generative Closure
program as of April 2026.

Contents:

- `FAST_BENCH_v0.2.2.md`
  The living Fast Bench spec for the binary cellular-automaton Drosophila.
- `campaign1_manifest.json`
  The frozen Campaign 1 hidden-rule manifest.
- `CAMPAIGN1_MANIFEST_MEMO.md`
  Human-readable explanation of the Campaign 1 manifest and adversarial
  screening logic.
- `assemble_manifest.py`
  The sole canonical manifest emitter for `campaign1_manifest.json`.
- `build_manifest.py`
  Shared primitive-library analysis helpers and sanity reporting. This script
  does not emit the canonical manifest artifact.
- `search_adversarial.py`
  Search procedure for the structured adversarial rules used in Campaign 1.
- `adversarial_selection.json`
  Intermediate search output consumed by `assemble_manifest.py`.

Campaign 1 notes:

- The local-functional primitive library is explicitly restricted to the 1024
  affine-linear functions of the 9 neighborhood bits.
- Changing the primitive library requires a new manifest version and rerun of
  adversarial screening before throughput claims can inherit the old pool.
- The Fast Bench separates exact knowledge from diagnostic memory: the exact
  posterior is distinct from the graveyard and diagnostic index.
