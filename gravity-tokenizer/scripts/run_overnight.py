"""
Overnight batch: retokenize and train beta=0.3 and beta=1.0.
Beta=0.0 baseline already exists (val_bpb 1.4373).

Runs sequentially: retok 0.3 -> train 0.3 -> retok 1.0 -> train 1.0
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLF_ROOT = PROJECT_ROOT / "parameter-golf"
DATA_DIR = GOLF_ROOT / "data" / "datasets" / "fineweb10B_sp1024"
BASE_TOKENIZER = GOLF_ROOT / "data" / "tokenizers" / "fineweb_1024_bpe.model"
TOKENIZER_DIR = PROJECT_ROOT / "data" / "tokenizers"
SEQ_LENGTH_RATIOS = PROJECT_ROOT / "data" / "seq_length_ratios.json"

VOCAB_SIZE = 1024
WARMUP_STEPS = 5
TRAIN_BATCH_TOKENS = 65536
VAL_LOSS_EVERY = 500

with open(SEQ_LENGTH_RATIOS) as f:
    ratios = json.load(f)

CONDITIONS = [
    (0.3, ratios["beta_0.3"]["iterations"]),
    (1.0, ratios["beta_1.0"]["iterations"]),
]

train_script = GOLF_ROOT / "train_gpt_win.py"
retok_script = PROJECT_ROOT / "scripts" / "retokenize_corpus.py"

start_time = time.time()

for beta, iterations in CONDITIONS:
    tag = f"beta_{beta}"
    tokenizer_path = TOKENIZER_DIR / f"gravity_{tag}.model"
    data_path = GOLF_ROOT / "data" / "datasets" / f"fineweb_gravity_{tag}"
    run_id = f"gravity_{tag}_seed1337"
    log_path = GOLF_ROOT / "logs" / f"{run_id}.txt"

    elapsed = (time.time() - start_time) / 60
    print(f"\n{'='*60}")
    print(f"CONDITION: beta={beta}, iterations={iterations}")
    print(f"Elapsed: {elapsed:.1f} min")
    print(f"{'='*60}")

    # Skip if already done
    if log_path.exists():
        print(f"  Log exists, skipping: {log_path.name}")
        continue

    # Step 1: Retokenize
    if not data_path.exists():
        print(f"  Retokenizing corpus for beta={beta}...")
        result = subprocess.run(
            [sys.executable, str(retok_script),
             "--base-tokenizer", str(BASE_TOKENIZER),
             "--gravity-tokenizer", str(tokenizer_path),
             "--data-dir", str(DATA_DIR),
             "--output-dir", str(data_path),
             "--max-shards", "3"],
            capture_output=False,
        )
        if result.returncode != 0:
            print(f"  RETOKENIZE FAILED for beta={beta}")
            continue
    else:
        print(f"  Retokenized data exists: {data_path.name}")

    # Step 2: Train
    print(f"  Training {run_id} ({iterations} steps)...")
    env = os.environ.copy()
    env.update({
        "RUN_ID": run_id,
        "DATA_PATH": str(data_path),
        "TOKENIZER_PATH": str(tokenizer_path),
        "VOCAB_SIZE": str(VOCAB_SIZE),
        "SEED": "1337",
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

    elapsed = (time.time() - start_time) / 60
    print(f"  Done. Total elapsed: {elapsed:.1f} min")

# Summary
elapsed = (time.time() - start_time) / 60
print(f"\n{'='*60}")
print(f"ALL DONE. Total time: {elapsed:.1f} min")
print(f"{'='*60}")

# Quick results check
logs_dir = GOLF_ROOT / "logs"
for beta, _ in CONDITIONS:
    tag = f"beta_{beta}"
    log_path = logs_dir / f"gravity_{tag}_seed1337.txt"
    if log_path.exists():
        with open(log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        for line in reversed(lines):
            if "val_bpb:" in line and "step:" in line:
                print(f"  beta={beta}: {line.strip()[:100]}")
                break
            if "final_int8_zlib_roundtrip " in line:
                print(f"  beta={beta}: {line.strip()[:100]}")
                break
