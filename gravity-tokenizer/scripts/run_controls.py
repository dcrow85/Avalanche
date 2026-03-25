"""
Step-count controls: run BPE baseline at 2870 and 4656 steps
to isolate vocabulary effect from training length effect.

- BPE at 2870 steps: matches β=0.3 step count (will see MORE text than β=0.3)
- BPE at 4656 steps: matches β=1.0 step count (will see MORE text than β=1.0)
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

VOCAB_SIZE = 1024
WARMUP_STEPS = 5
TRAIN_BATCH_TOKENS = 65536
VAL_LOSS_EVERY = 500

train_script = GOLF_ROOT / "train_gpt_win.py"

CONTROLS = [
    ("bpe_control_2870steps", 2870),  # matches β=0.3 step count
    ("bpe_control_4656steps", 4656),  # matches β=1.0 step count
]

start_time = time.time()

for run_id, iterations in CONTROLS:
    log_path = GOLF_ROOT / "logs" / f"{run_id}.txt"
    elapsed = (time.time() - start_time) / 60

    print(f"\n{'='*60}")
    print(f"CONTROL: {run_id}, iterations={iterations}")
    print(f"Elapsed: {elapsed:.1f} min")
    print(f"{'='*60}")

    if log_path.exists():
        print(f"  Log exists, skipping: {log_path.name}")
        continue

    env = os.environ.copy()
    env.update({
        "RUN_ID": run_id,
        "DATA_PATH": str(DATA_DIR),
        "TOKENIZER_PATH": str(BASE_TOKENIZER),
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

elapsed = (time.time() - start_time) / 60
print(f"\n{'='*60}")
print(f"ALL CONTROLS DONE. Total time: {elapsed:.1f} min")
print(f"{'='*60}")

logs_dir = GOLF_ROOT / "logs"
for run_id, _ in CONTROLS:
    log_path = logs_dir / f"{run_id}.txt"
    if log_path.exists():
        with open(log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        for line in reversed(lines):
            if "final_int8_zlib_roundtrip " in line and "val_bpb" in line:
                print(f"  {run_id}: {line.strip()[:100]}")
                break
