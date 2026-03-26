"""
Run the lensing probe on both the step-100 and step-11000 checkpoints.
Saves results separately for the two-panel comparison graphic.
"""
import os
import sys
import json
import codecs

sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, errors='replace')

import torch

SCRIPT_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
GOLF_ROOT = os.path.join(SCRIPT_DIR, "..", "parameter-golf")

# Import from the probe script
sys.path.insert(0, SCRIPT_DIR)
from gravity_lensing_probe import load_model, run_lensing_probe
import numpy as np

device = "cuda" if torch.cuda.is_available() else "cpu"
tokenizer = os.path.join(DATA_DIR, "tokenizers", "gravity_beta_1.0.model")

def save_results(results, path):
    def convert(obj):
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj
    clean = json.loads(json.dumps(results, default=convert))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)
    print(f"Saved: {path}")

# === Run 1: Step 100 (13L smoke test) ===
print("=" * 60)
print("PROBE 1: Step 100 (13L smoke test checkpoint)")
print("=" * 60)
ckpt_100 = os.path.join(GOLF_ROOT, "final_model.int8.ptz")
model_100, sp = load_model(ckpt_100, tokenizer, num_layers=13, device=device)
print(f"Loaded. Params: {sum(p.numel() for p in model_100.parameters()):,}")
results_100 = run_lensing_probe(model_100, sp, device)
for r in results_100:
    r['model_stage'] = 'step_100'
save_results(results_100, os.path.join(DATA_DIR, "lensing_step100.json"))
del model_100
torch.cuda.empty_cache()

# === Run 2: Step 11000 (12L seed 137, fully trained) ===
print("\n" + "=" * 60)
print("PROBE 2: Step 11000 (12L seed 137, fully trained)")
print("=" * 60)
ckpt_11k = os.path.join(GOLF_ROOT, "logs", "gravity_12L_seed137.int8.ptz")
model_11k, sp = load_model(ckpt_11k, tokenizer, num_layers=12, device=device)
print(f"Loaded. Params: {sum(p.numel() for p in model_11k.parameters()):,}")
results_11k = run_lensing_probe(model_11k, sp, device)
for r in results_11k:
    r['model_stage'] = 'step_11000'
save_results(results_11k, os.path.join(DATA_DIR, "lensing_step11000.json"))

print("\n" + "=" * 60)
print("BOTH PROBES COMPLETE")
print("=" * 60)
