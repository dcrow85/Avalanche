"""
Experiment Orchestrator — Run the gravity tokenizer experiment.

Coordinates the entire experimental pipeline:
1. Generate candidate pool (if not already done)
2. Score candidates for leverage and breadth
3. Build vocabularies at each beta value
4. Build tokenizers for each vocabulary
5. Re-tokenize corpus for each condition
6. Train models for each condition (equalized on bytes seen)
7. Collect and analyze results

Design decisions (per Che):
- Pilot uses 3 conditions: beta=0.0 (BPE control), beta=0.3 (predicted sweet spot),
  beta=1.0 (predicted catastrophe). Validate the basic signal before finer sweep.
- Architecture (d_model, num_layers, etc.) is IDENTICAL across all conditions.
  All use vocab_size=1024 — only the token composition changes, not the embedding size.
- Training is equalized on BYTES SEEN, not steps. Conditions with longer sequences
  (gravity tokenizers sacrifice some frequency-optimal tokens) get fewer steps so
  every condition trains on the same amount of raw text.

Usage:
    python scripts/run_experiment.py --phase 1  # Candidate generation
    python scripts/run_experiment.py --phase 2  # Vocabulary construction
    python scripts/run_experiment.py --phase 3  # Training
    python scripts/run_experiment.py --phase 4  # Analysis
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np


# Experiment conditions — pilot is 3 conditions
BETA_PILOT = [0.0, 0.3, 1.0]
BETA_FULL_SWEEP = [0.0, 0.15, 0.25, 0.30, 0.35, 0.50, 0.75, 1.0]
GAMMA_DEFAULT = 0.0  # Deprecated — breadth dropped from composite
VOCAB_SIZE = 1024
SEEDS_PILOT = [1337]
SEEDS_FULL = [1337, 42, 2024]

# Training budget: equalized on bytes, not steps.
# The baseline (beta=0.0) runs for this many steps. Other conditions
# are adjusted so total bytes seen is the same.
BASELINE_ITERATIONS = 2000
TRAIN_BATCH_TOKENS = 65536
VAL_LOSS_EVERY = 500
WARMUP_STEPS = 5

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLF_ROOT = PROJECT_ROOT / "parameter-golf"
DATA_DIR = GOLF_ROOT / "data" / "datasets" / "fineweb10B_sp1024"
BASE_TOKENIZER = GOLF_ROOT / "data" / "tokenizers" / "fineweb_1024_bpe.model"
CANDIDATES_PATH = PROJECT_ROOT / "data" / "candidates.jsonl"
CANDIDATES_FILTERED = PROJECT_ROOT / "data" / "candidates_filtered.jsonl"
CANDIDATES_SCORED = PROJECT_ROOT / "data" / "candidates_scored.jsonl"
VOCAB_DIR = PROJECT_ROOT / "data" / "vocabularies"
TOKENIZER_DIR = PROJECT_ROOT / "data" / "tokenizers"
RESULTS_DIR = PROJECT_ROOT / "data" / "results"
CORPUS_SAMPLE = PROJECT_ROOT / "data" / "corpus_sample.txt"
SEQ_LENGTH_RATIOS = PROJECT_ROOT / "data" / "seq_length_ratios.json"


def run_cmd(cmd: list[str], desc: str = ""):
    """Run a command and print output."""
    print(f"\n{'='*60}")
    print(f"RUNNING: {desc or ' '.join(cmd)}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, capture_output=False, text=True)
    if result.returncode != 0:
        print(f"FAILED with return code {result.returncode}")
        return False
    return True


def compute_bytes_per_token(tokenizer_path: str, corpus_dir: Path,
                            base_tokenizer_path: str = None,
                            max_shards: int = 2) -> float:
    """Compute average bytes per token for a tokenizer on the corpus.

    Shards are encoded with the base BPE tokenizer. We decode with the base
    tokenizer to recover raw text, then re-encode with the target tokenizer
    to measure its compression ratio.
    """
    import sentencepiece as spm

    sp_target = spm.SentencePieceProcessor(model_file=tokenizer_path)
    # Use base tokenizer for decoding shards (they were encoded with it)
    if base_tokenizer_path and base_tokenizer_path != tokenizer_path:
        sp_decode = spm.SentencePieceProcessor(model_file=base_tokenizer_path)
    else:
        sp_decode = sp_target

    total_bytes = 0
    total_tokens = 0

    for shard_path in sorted(corpus_dir.glob("fineweb_train_*.bin"))[:max_shards]:
        header = np.fromfile(shard_path, dtype="<i4", count=256)
        num_tokens = int(header[2])
        tokens = np.fromfile(shard_path, dtype="<u2",
                             count=min(num_tokens, 2_000_000),
                             offset=256 * 4)
        text = sp_decode.decode(tokens.tolist())
        text_bytes = len(text.encode("utf-8"))

        # Re-encode with target tokenizer to count its tokens
        re_tokens = sp_target.encode(text)
        total_bytes += text_bytes
        total_tokens += len(re_tokens)

    return total_bytes / total_tokens if total_tokens > 0 else 1.0


def phase_0_setup():
    """Phase 0: Verify setup."""
    print("Phase 0: Verifying setup...")

    checks = {
        "parameter-golf repo": GOLF_ROOT.exists(),
        "Training data": DATA_DIR.exists(),
        "Base tokenizer": BASE_TOKENIZER.exists(),
        "Training shards": len(list(DATA_DIR.glob("fineweb_train_*.bin"))) > 0,
        "Validation shards": len(list(DATA_DIR.glob("fineweb_val_*.bin"))) > 0,
    }

    all_ok = True
    for name, ok in checks.items():
        status = "OK" if ok else "MISSING"
        print(f"  {name}: {status}")
        if not ok:
            all_ok = False

    return all_ok


def phase_1_candidates():
    """Phase 1: Generate and score candidate pool."""
    print("\n" + "="*60)
    print("PHASE 1: CANDIDATE GENERATION AND SCORING")
    print("="*60)

    # Step 1: Generate candidate pool
    if not CANDIDATES_PATH.exists():
        run_cmd([
            sys.executable, str(PROJECT_ROOT / "scripts" / "generate_candidates_sp.py"),
            "--tokenizer", str(BASE_TOKENIZER),
            "--data-dir", str(DATA_DIR),
            "--output", str(CANDIDATES_PATH),
            "--vocab-size", "8256",
            "--max-shards", "3",
        ], "Generate BPE candidate pool")
    else:
        print(f"Candidates already exist: {CANDIDATES_PATH}")

    # Step 2: Pre-filter by frequency
    if not CANDIDATES_FILTERED.exists():
        print("\nFiltering candidates by frequency...")
        candidates = []
        with open(CANDIDATES_PATH, "r", encoding="utf-8") as f:
            for line in f:
                c = json.loads(line)
                if c.get("corpus_frequency", 0) >= 1000:
                    candidates.append(c)

        CANDIDATES_FILTERED.parent.mkdir(parents=True, exist_ok=True)
        with open(CANDIDATES_FILTERED, "w", encoding="utf-8") as f:
            for c in candidates:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        print(f"  Filtered: {len(candidates)} candidates (freq >= 1000)")
    else:
        print(f"Filtered candidates already exist: {CANDIDATES_FILTERED}")

    # Step 3: Full scoring
    if not CANDIDATES_SCORED.exists():
        run_cmd([
            sys.executable, str(PROJECT_ROOT / "scripts" / "score_leverage.py"),
            "--candidates", str(CANDIDATES_FILTERED),
            "--output", str(CANDIDATES_SCORED),
            "--reference-model", "gpt2",
            "--corpus-dir", str(DATA_DIR),
            "--base-tokenizer", str(BASE_TOKENIZER),
            "--K", "10",
            "--contexts-per-candidate", "100",
            "--batch-size", "32",
            "--run-contamination-check",
        ], "Full ablation leverage scoring")


def phase_2_vocabularies(betas=None):
    """Phase 2: Build vocabularies and tokenizers for each beta."""
    if betas is None:
        betas = BETA_PILOT

    print("\n" + "="*60)
    print("PHASE 2: VOCABULARY CONSTRUCTION")
    print(f"  Conditions: beta = {betas}")
    print("="*60)

    if not CANDIDATES_SCORED.exists():
        print("ERROR: Scored candidates not found. Run phase 1 first.")
        return

    # Generate corpus sample if needed (for Unigram training in build_tokenizer)
    if not CORPUS_SAMPLE.exists():
        print("Generating corpus sample for tokenizer training...")
        import sentencepiece as spm
        sp = spm.SentencePieceProcessor(model_file=str(BASE_TOKENIZER))

        shard = sorted(DATA_DIR.glob("fineweb_train_*.bin"))[0]
        header = np.fromfile(shard, dtype="<i4", count=256)
        num_tokens = int(header[2])
        tokens = np.fromfile(shard, dtype="<u2", count=min(num_tokens, 5_000_000),
                             offset=256 * 4)

        # Decode in chunks, split into lines ≤4000 chars for SP compatibility
        chunk_size = 100_000
        CORPUS_SAMPLE.parent.mkdir(parents=True, exist_ok=True)
        with open(CORPUS_SAMPLE, "w", encoding="utf-8") as f:
            for i in range(0, len(tokens), chunk_size):
                chunk = tokens[i:i + chunk_size].tolist()
                text = sp.decode(chunk)
                for line in text.split("\n"):
                    if len(line) <= 4000 and line.strip():
                        f.write(line.strip() + "\n")
                    elif line.strip():
                        for sent in line.split(". "):
                            if sent.strip():
                                f.write(sent.strip() + "\n")
        print(f"  Saved corpus sample to {CORPUS_SAMPLE}")

    for beta in betas:
        tag = f"beta_{beta}"
        vocab_path = VOCAB_DIR / f"vocabulary_{tag}.json"
        tokenizer_path = TOKENIZER_DIR / f"gravity_{tag}.model"

        if not vocab_path.exists():
            run_cmd([
                sys.executable, str(PROJECT_ROOT / "scripts" / "build_vocabulary.py"),
                "--scored-candidates", str(CANDIDATES_SCORED),
                "--beta", str(beta),
                "--output", str(VOCAB_DIR),
            ], f"Build vocabulary beta={beta}")

        if beta > 0 and not tokenizer_path.exists():
            run_cmd([
                sys.executable, str(PROJECT_ROOT / "scripts" / "build_tokenizer.py"),
                "--vocabulary", str(vocab_path),
                "--output", str(tokenizer_path),
                "--corpus-sample", str(CORPUS_SAMPLE),
            ], f"Build tokenizer beta={beta}")

    # Compute sequence length ratios for bytes-seen equalization
    print("\nComputing sequence length ratios for bytes-seen equalization...")
    ratios = {}
    baseline_bpt = compute_bytes_per_token(str(BASE_TOKENIZER), DATA_DIR)
    ratios["beta_0.0"] = {"bytes_per_token": baseline_bpt, "seq_ratio": 1.0,
                          "iterations": BASELINE_ITERATIONS}

    for beta in betas:
        if beta == 0.0:
            continue
        tag = f"beta_{beta}"
        tokenizer_path = TOKENIZER_DIR / f"gravity_{tag}.model"
        if tokenizer_path.exists():
            bpt = compute_bytes_per_token(str(tokenizer_path), DATA_DIR,
                                          base_tokenizer_path=str(BASE_TOKENIZER))
            # Ratio: how many tokens does this tokenizer need per byte vs baseline
            seq_ratio = baseline_bpt / bpt  # >1 means longer sequences
            # Adjust iterations: same total bytes = same iterations * bpt
            adjusted_iters = int(BASELINE_ITERATIONS * baseline_bpt / bpt)
            ratios[f"beta_{beta}"] = {
                "bytes_per_token": bpt,
                "seq_ratio": seq_ratio,
                "iterations": adjusted_iters,
            }
            print(f"  beta={beta}: {bpt:.2f} bytes/token, "
                  f"ratio={seq_ratio:.3f}x, iterations={adjusted_iters}")

    SEQ_LENGTH_RATIOS.parent.mkdir(parents=True, exist_ok=True)
    with open(SEQ_LENGTH_RATIOS, "w") as f:
        json.dump(ratios, f, indent=2)
    print(f"  Saved to: {SEQ_LENGTH_RATIOS}")

    # Vocab diff report: which tokens did gravity swap in/out vs BPE (beta=0.0)?
    baseline_vocab_path = VOCAB_DIR / "vocabulary_beta_0.0.json"
    if baseline_vocab_path.exists():
        with open(baseline_vocab_path, encoding="utf-8") as f:
            baseline_tokens = {t["readable"] for t in json.load(f)["tokens"]}

        for beta in betas:
            if beta == 0.0:
                continue
            grav_vocab_path = VOCAB_DIR / f"vocabulary_beta_{beta}.json"
            if not grav_vocab_path.exists():
                continue

            with open(grav_vocab_path, encoding="utf-8") as f:
                grav_data = json.load(f)
            grav_tokens = {t["readable"]: t for t in grav_data["tokens"]}
            grav_set = set(grav_tokens.keys())

            swapped_in = grav_set - baseline_tokens
            swapped_out = baseline_tokens - grav_set

            diff_path = VOCAB_DIR / f"vocab_diff_beta_{beta}.txt"
            with open(diff_path, "w", encoding="utf-8") as f:
                f.write(f"Vocabulary diff: beta={beta} vs beta=0.0 (BPE)\n")
                f.write(f"Shared: {len(grav_set & baseline_tokens)}\n")
                f.write(f"Swapped IN  (gravity added):   {len(swapped_in)}\n")
                f.write(f"Swapped OUT (gravity removed):  {len(swapped_out)}\n\n")

                f.write("=== SWAPPED IN (sorted by leverage) ===\n")
                in_sorted = sorted(swapped_in,
                                   key=lambda r: grav_tokens[r].get("ablation_leverage", 0),
                                   reverse=True)
                for r in in_sorted:
                    t = grav_tokens[r]
                    f.write(f"  + {r!r:20s}  lev={t.get('ablation_leverage',0):.4f}"
                            f"  freq={t.get('corpus_frequency',0):>10,}"
                            f"  score={t.get('score',0):.6f}\n")

                f.write(f"\n=== SWAPPED OUT (sorted by frequency) ===\n")
                # For swapped-out tokens we need to reload baseline data
                with open(baseline_vocab_path, encoding="utf-8") as bf:
                    base_data = json.load(bf)
                base_lookup = {t["readable"]: t for t in base_data["tokens"]}
                out_sorted = sorted(swapped_out,
                                    key=lambda r: base_lookup[r].get("corpus_frequency", 0),
                                    reverse=True)
                for r in out_sorted:
                    t = base_lookup[r]
                    f.write(f"  - {r!r:20s}  lev={t.get('ablation_leverage',0):.4f}"
                            f"  freq={t.get('corpus_frequency',0):>10,}"
                            f"  score={t.get('score',0):.6f}\n")

            print(f"\n  Vocab diff beta={beta}: +{len(swapped_in)} / -{len(swapped_out)}")
            print(f"  Saved to: {diff_path}")


def phase_3_training(betas=None, seeds=None):
    """Phase 3: Train models for each condition.

    Training budget is equalized on bytes seen: each condition trains
    on the same total bytes of raw text. Conditions with lower bytes/token
    get fewer steps.
    """
    if betas is None:
        betas = BETA_PILOT
    if seeds is None:
        seeds = SEEDS_PILOT

    print("\n" + "="*60)
    print("PHASE 3: TRAINING")
    print(f"  Conditions: beta = {betas}")
    print(f"  Seeds: {seeds}")
    print("="*60)

    # Load sequence length ratios
    if SEQ_LENGTH_RATIOS.exists():
        with open(SEQ_LENGTH_RATIOS) as f:
            ratios = json.load(f)
    else:
        print("WARNING: No seq_length_ratios.json found. Using fixed iterations.")
        ratios = {}

    train_script = GOLF_ROOT / "train_gpt_win.py"

    for beta in betas:
        tag = f"beta_{beta}"
        ratio_key = f"beta_{beta}"

        if beta == 0.0:
            tokenizer_path = BASE_TOKENIZER
            data_path = DATA_DIR
        else:
            tokenizer_path = TOKENIZER_DIR / f"gravity_{tag}.model"
            data_path = GOLF_ROOT / "data" / "datasets" / f"fineweb_gravity_{tag}"

            if not data_path.exists():
                run_cmd([
                    sys.executable, str(PROJECT_ROOT / "scripts" / "retokenize_corpus.py"),
                    "--base-tokenizer", str(BASE_TOKENIZER),
                    "--gravity-tokenizer", str(tokenizer_path),
                    "--data-dir", str(DATA_DIR),
                    "--output-dir", str(data_path),
                    "--max-shards", "10",
                ], f"Re-tokenize corpus for beta={beta}")

        # Get iterations for this condition (bytes-equalized)
        if ratio_key in ratios:
            iterations = ratios[ratio_key]["iterations"]
            bpt = ratios[ratio_key]["bytes_per_token"]
            print(f"\n  beta={beta}: {bpt:.2f} bytes/token, {iterations} iterations")
        else:
            iterations = BASELINE_ITERATIONS
            print(f"\n  beta={beta}: using default {iterations} iterations")

        for seed in seeds:
            run_id = f"gravity_{tag}_seed{seed}"
            log_path = GOLF_ROOT / "logs" / f"{run_id}.txt"

            if log_path.exists():
                print(f"Skipping {run_id} (already exists)")
                continue

            print(f"\nTraining: {run_id}")
            env = os.environ.copy()
            env.update({
                "RUN_ID": run_id,
                "DATA_PATH": str(data_path),
                "TOKENIZER_PATH": str(tokenizer_path),
                "VOCAB_SIZE": str(VOCAB_SIZE),
                "SEED": str(seed),
                "ITERATIONS": str(iterations),
                "VAL_LOSS_EVERY": str(VAL_LOSS_EVERY),
                "TRAIN_BATCH_TOKENS": str(TRAIN_BATCH_TOKENS),
                "VAL_BATCH_SIZE": "65536",
                "MAX_WALLCLOCK_SECONDS": "0",
                "WARMUP_STEPS": str(WARMUP_STEPS),
                "PYTHONIOENCODING": "utf-8",
            })

            subprocess.run(
                [sys.executable, str(train_script)],
                env=env,
                cwd=str(GOLF_ROOT),
                capture_output=False,
            )


def phase_4_analysis():
    """Phase 4: Collect and analyze results."""
    print("\n" + "="*60)
    print("PHASE 4: ANALYSIS")
    print("="*60)

    results = []
    logs_dir = GOLF_ROOT / "logs"

    for log_file in sorted(logs_dir.glob("gravity_*.txt")):
        name = log_file.stem
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        final_bpb = None
        final_step = None
        for line in reversed(lines):
            if "val_bpb:" in line and "step:" in line:
                parts = line.strip().split()
                for part in parts:
                    if part.startswith("val_bpb:"):
                        final_bpb = float(part.split(":")[1])
                    if part.startswith("step:"):
                        final_step = part.split(":")[1]
                if final_bpb is not None:
                    break

        if final_bpb is not None:
            results.append({
                "run": name,
                "bpb": final_bpb,
                "final_step": final_step,
            })

    if not results:
        print("No results found yet.")
        return

    # Load sequence length ratios for context
    ratios = {}
    if SEQ_LENGTH_RATIOS.exists():
        with open(SEQ_LENGTH_RATIOS) as f:
            ratios = json.load(f)

    # Sort by BPB
    results.sort(key=lambda r: r["bpb"])

    print("\nResults (sorted by BPB):")
    print(f"{'Run':<55s} {'BPB':>8s} {'Step':>8s} {'B/T':>6s} {'SeqR':>6s}")
    print("-" * 85)
    for r in results:
        # Extract beta from run name
        beta_str = r["run"].split("beta_")[1].split("_")[0]
        ratio_key = f"beta_{beta_str}"
        bpt = ratios.get(ratio_key, {}).get("bytes_per_token", 0)
        seq_r = ratios.get(ratio_key, {}).get("seq_ratio", 0)
        print(f"{r['run']:<55s} {r['bpb']:>8.4f} {r.get('final_step','?'):>8s} "
              f"{bpt:>6.2f} {seq_r:>6.3f}")

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_DIR / "experiment_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {RESULTS_DIR / 'experiment_results.json'}")


def main():
    parser = argparse.ArgumentParser(description="Gravity Tokenizer Experiment")
    parser.add_argument("--phase", type=int, required=True,
                        choices=[0, 1, 2, 3, 4],
                        help="Which phase to run (0=setup, 1=candidates, 2=vocab, 3=train, 4=analyze)")
    parser.add_argument("--full-sweep", action="store_true",
                        help="Use full beta sweep instead of 3-condition pilot")
    args = parser.parse_args()

    betas = BETA_FULL_SWEEP if args.full_sweep else BETA_PILOT
    seeds = SEEDS_FULL if args.full_sweep else SEEDS_PILOT

    phases = {
        0: phase_0_setup,
        1: phase_1_candidates,
        2: lambda: phase_2_vocabularies(betas),
        3: lambda: phase_3_training(betas, seeds),
        4: phase_4_analysis,
    }

    phases[args.phase]()


if __name__ == "__main__":
    main()
