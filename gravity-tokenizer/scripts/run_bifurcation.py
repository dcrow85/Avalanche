"""
Train the bifurcation-scored gravity tokenizer condition.
Uses delta-leverage scoring instead of absolute leverage.

Expects retokenized data to already exist at:
  parameter-golf/data/datasets/fineweb_gravity_bifurcation_beta_0.3/
"""
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLF_ROOT = PROJECT_ROOT / "parameter-golf"
DATA_DIR = GOLF_ROOT / "data" / "datasets" / "fineweb_gravity_bifurcation_beta_0.3"
TOKENIZER_PATH = PROJECT_ROOT / "data" / "tokenizers" / "gravity_bifurcation_beta_0.3.model"

VOCAB_SIZE = 1024
WARMUP_STEPS = 5
TRAIN_BATCH_TOKENS = 65536
VAL_LOSS_EVERY = 500
ITERATIONS = 2783  # bytes-equalized: 2000 * 2.4463 / 1.7576

train_script = GOLF_ROOT / "train_gpt_win.py"
run_id = "gravity_bifurcation_beta_0.3_seed1337"
log_path = GOLF_ROOT / "logs" / f"{run_id}.txt"

if not DATA_DIR.exists():
    print(f"ERROR: Retokenized data not found: {DATA_DIR}")
    print("Run retokenize_corpus.py first.")
    sys.exit(1)

if not TOKENIZER_PATH.exists():
    print(f"ERROR: Tokenizer not found: {TOKENIZER_PATH}")
    sys.exit(1)

if log_path.exists():
    print(f"Log already exists, skipping: {log_path}")
    sys.exit(0)

print(f"Training bifurcation condition: {run_id}")
print(f"  Tokenizer: {TOKENIZER_PATH.name}")
print(f"  Data: {DATA_DIR.name}")
print(f"  Iterations: {ITERATIONS} (bytes-equalized)")
print(f"  Log: {log_path}")

start_time = time.time()

env = os.environ.copy()
env.update({
    "RUN_ID": run_id,
    "DATA_PATH": str(DATA_DIR),
    "TOKENIZER_PATH": str(TOKENIZER_PATH),
    "VOCAB_SIZE": str(VOCAB_SIZE),
    "SEED": "1337",
    "ITERATIONS": str(ITERATIONS),
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
print(f"\nDone. Elapsed: {elapsed:.1f} min")

# Quick results check
if log_path.exists():
    with open(log_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    for line in reversed(lines):
        if "final_int8_zlib_roundtrip" in line or "val_bpb" in line:
            print(f"  Result: {line.strip()[:120]}")
            break
