"""
Frontier Depth Efficiency Probe
Measures residual velocity per layer per token across a large vocabulary model.

Target: Qwen2.5-72B (80 layers, 151K vocab)
Hardware: 2×A100 80GB SXM

Usage:
    python frontier_depth_probe.py [--model Qwen/Qwen2.5-72B] [--num-tokens 100000]

Output:
    - velocity_heatmap.npy: [vocab_size × num_layers] mean velocity per token per layer
    - depth_efficiency_report.json: per-token classification and summary statistics
"""

import argparse
import json
import os
import time
from collections import defaultdict

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# ── Argument parsing ─────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Frontier Depth Efficiency Probe")
parser.add_argument("--model", type=str, default="Qwen/Qwen2.5-72B",
                    help="HuggingFace model ID")
parser.add_argument("--num-tokens", type=int, default=100_000,
                    help="Total tokens to process")
parser.add_argument("--batch-seq-len", type=int, default=2048,
                    help="Sequence length per batch")
parser.add_argument("--output-dir", type=str, default="./probe_results",
                    help="Output directory")
parser.add_argument("--sample-text", type=str, default=None,
                    help="Path to raw text file for input. If None, uses FineWeb sample.")
args = parser.parse_args()

os.makedirs(args.output_dir, exist_ok=True)

# ── Load model ───────────────────────────────────────────────────────
print(f"Loading {args.model}...")
t0 = time.time()

tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    args.model,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    trust_remote_code=True,
)
model.eval()

num_layers = model.config.num_hidden_layers
vocab_size = model.config.vocab_size
print(f"Loaded in {time.time() - t0:.0f}s")
print(f"  Layers: {num_layers}")
print(f"  Vocab: {vocab_size}")
print(f"  Parameters: {sum(p.numel() for p in model.parameters()):,}")
print(f"  Device map: {set(str(p.device) for p in model.parameters())}")

# ── Prepare input text ───────────────────────────────────────────────
if args.sample_text and os.path.exists(args.sample_text):
    print(f"Loading text from {args.sample_text}...")
    with open(args.sample_text, "r", encoding="utf-8") as f:
        raw_text = f.read()
else:
    print("Generating sample text from built-in corpus...")
    # Use a diverse English sample — Wikipedia-style text
    # In production, download a FineWeb shard. For the probe, we generate
    # a request to HF datasets if available, otherwise use a fallback.
    try:
        from datasets import load_dataset
        print("Loading FineWeb sample from HuggingFace...")
        ds = load_dataset("HuggingFaceFW/fineweb", name="sample-10BT",
                          split="train", streaming=True)
        raw_text = ""
        for example in ds:
            raw_text += example["text"] + "\n"
            if len(raw_text) > args.num_tokens * 5:  # ~5 chars per token
                break
        print(f"  Loaded {len(raw_text):,} characters")
    except Exception as e:
        print(f"  FineWeb load failed ({e}), using fallback text generation")
        # Fallback: repeat a diverse paragraph
        fallback = (
            "The development of modern science required both theoretical insight and "
            "experimental verification. Because the relationship between theory and "
            "observation is fundamental to scientific progress, researchers must "
            "carefully design experiments that can distinguish between competing "
            "hypotheses. The history of physics demonstrates that breakthrough "
            "discoveries often emerge when existing frameworks fail to explain new "
            "observations, forcing scientists to develop entirely new conceptual "
            "structures. Education systems around the world have recognized the "
            "importance of teaching students not just scientific facts but the "
            "process of scientific reasoning itself. Government policies that "
            "support basic research have consistently generated economic returns "
            "that far exceed their initial investment, though the specific pathways "
            "from discovery to application are often unpredictable. "
        )
        raw_text = fallback * (args.num_tokens * 5 // len(fallback) + 1)

# Tokenize
print("Tokenizing...")
all_ids = tokenizer.encode(raw_text, add_special_tokens=False)
all_ids = all_ids[:args.num_tokens]
print(f"  Total tokens: {len(all_ids):,}")
print(f"  Unique token IDs: {len(set(all_ids)):,}")

# ── Set up velocity hooks ────────────────────────────────────────────
print(f"\nRegistering velocity hooks on {num_layers} layers...")

# Storage for pre/post residual states
layer_inputs = {}
layer_outputs = {}

def make_pre_hook(layer_idx):
    def hook(module, args, kwargs=None):
        # The input to the transformer block is the hidden state
        # For most architectures, it's the first positional argument
        if isinstance(args, tuple) and len(args) > 0:
            x = args[0]
        else:
            return
        layer_inputs[layer_idx] = x.detach()
    return hook

def make_post_hook(layer_idx):
    def hook(module, args, output):
        # The output is typically a tuple; first element is hidden state
        if isinstance(output, tuple):
            x = output[0]
        else:
            x = output
        layer_outputs[layer_idx] = x.detach()
    return hook

# Find the transformer blocks
# Qwen2: model.model.layers[i]
# Llama: model.model.layers[i]
if hasattr(model, 'model') and hasattr(model.model, 'layers'):
    blocks = model.model.layers
elif hasattr(model, 'transformer') and hasattr(model.transformer, 'h'):
    blocks = model.transformer.h
else:
    raise RuntimeError(f"Cannot find transformer blocks in {type(model)}")

hooks = []
for i, block in enumerate(blocks):
    h1 = block.register_forward_pre_hook(make_pre_hook(i))
    h2 = block.register_forward_hook(make_post_hook(i))
    hooks.append(h1)
    hooks.append(h2)

print(f"  Registered {len(hooks)} hooks")

# ── Accumulators ─────────────────────────────────────────────────────
# Per-token, per-layer velocity accumulation
# Use sparse tracking: only accumulate for tokens we've seen
token_velocity_sum = defaultdict(lambda: np.zeros(num_layers, dtype=np.float64))
token_velocity_count = defaultdict(lambda: np.zeros(num_layers, dtype=np.int64))

# Also track overall per-layer statistics
global_velocity_sum = np.zeros(num_layers, dtype=np.float64)
global_velocity_count = np.zeros(num_layers, dtype=np.int64)

# ── Run inference ────────────────────────────────────────────────────
seq_len = args.batch_seq_len
num_sequences = len(all_ids) // seq_len
total_tokens_processed = 0

print(f"\nRunning {num_sequences} sequences of length {seq_len}...")
print(f"  Total tokens to process: {num_sequences * seq_len:,}")

t_start = time.time()

for seq_idx in range(num_sequences):
    start = seq_idx * seq_len
    end = start + seq_len
    input_ids = torch.tensor([all_ids[start:end]], dtype=torch.long)

    # Move to same device as first embedding
    first_device = next(model.parameters()).device
    input_ids = input_ids.to(first_device)

    layer_inputs.clear()
    layer_outputs.clear()

    with torch.no_grad():
        _ = model(input_ids)

    # Compute velocity at each layer
    token_ids_np = all_ids[start:end]

    for layer_idx in range(num_layers):
        if layer_idx not in layer_inputs or layer_idx not in layer_outputs:
            continue

        pre = layer_inputs[layer_idx].float()   # [1, seq_len, dim]
        post = layer_outputs[layer_idx].float()  # [1, seq_len, dim]

        # Velocity = L2 norm of residual update per position
        velocity = (post - pre).norm(dim=-1)[0]  # [seq_len]
        velocity_np = velocity.cpu().numpy()

        # Accumulate per-token
        for pos in range(seq_len):
            tid = token_ids_np[pos]
            token_velocity_sum[tid][layer_idx] += velocity_np[pos]
            token_velocity_count[tid][layer_idx] += 1

        # Global accumulation
        global_velocity_sum[layer_idx] += velocity_np.sum()
        global_velocity_count[layer_idx] += seq_len

    total_tokens_processed += seq_len

    # Progress
    elapsed = time.time() - t_start
    tps = total_tokens_processed / elapsed if elapsed > 0 else 0
    eta = (num_sequences * seq_len - total_tokens_processed) / tps if tps > 0 else 0
    if (seq_idx + 1) % 5 == 0 or seq_idx == 0:
        print(f"  [{seq_idx+1}/{num_sequences}] {total_tokens_processed:,} tokens, "
              f"{tps:.0f} tok/s, ETA {eta:.0f}s")

    # Clear CUDA cache periodically
    if (seq_idx + 1) % 10 == 0:
        layer_inputs.clear()
        layer_outputs.clear()
        torch.cuda.empty_cache()

elapsed_total = time.time() - t_start
print(f"\nDone. {total_tokens_processed:,} tokens in {elapsed_total:.0f}s "
      f"({total_tokens_processed/elapsed_total:.0f} tok/s)")

# ── Remove hooks ─────────────────────────────────────────────────────
for h in hooks:
    h.remove()

# ── Compute statistics ───────────────────────────────────────────────
print("\nComputing per-token depth efficiency...")

# Build dense heatmap for tokens with enough observations
MIN_OBS = 10
observed_tokens = sorted([tid for tid, counts in token_velocity_count.items()
                          if counts.min() >= MIN_OBS])

print(f"  Tokens with >= {MIN_OBS} observations: {len(observed_tokens):,}")

# Compute mean velocity per token per layer
results = []
for tid in observed_tokens:
    counts = token_velocity_count[tid]
    mean_vel = token_velocity_sum[tid] / np.maximum(counts, 1)

    # Panic Ratio: v_last / mean(v_middle)
    # Middle layers: 25%-75% of depth
    mid_start = num_layers // 4
    mid_end = 3 * num_layers // 4
    last_layer_vel = mean_vel[-1]
    mid_vel = mean_vel[mid_start:mid_end].mean()
    panic_ratio = last_layer_vel / max(mid_vel, 1e-10)

    # Active Work: sum of all velocities
    active_work = mean_vel.sum()

    # Persistence Ratio: late / early (excluding last layer)
    early_vel = mean_vel[:num_layers//4].mean()
    late_vel = mean_vel[3*num_layers//4:-1].mean() if num_layers > 4 else mean_vel[-2]
    persistence_ratio = late_vel / max(early_vel, 1e-10)

    # Depth efficiency: 1.0 / coefficient of variation (higher = more uniform)
    vel_std = mean_vel.std()
    vel_mean = mean_vel.mean()
    cv = vel_std / max(vel_mean, 1e-10)
    depth_efficiency = 1.0 / max(cv, 1e-10)

    # Effective depth: layers where velocity > 10% of peak velocity
    peak_vel = mean_vel.max()
    active_layers = int((mean_vel > 0.1 * peak_vel).sum())

    # Token string
    try:
        token_str = tokenizer.decode([tid])
    except:
        token_str = f"<id_{tid}>"

    results.append({
        'token_id': int(tid),
        'token_str': token_str,
        'observations': int(counts.min()),
        'panic_ratio': float(panic_ratio),
        'active_work': float(active_work),
        'persistence_ratio': float(persistence_ratio),
        'depth_efficiency': float(depth_efficiency),
        'active_layers': active_layers,
        'effective_depth_pct': float(active_layers / num_layers * 100),
        'mean_velocity_per_layer': mean_vel.tolist(),
    })

# Sort by depth efficiency
results.sort(key=lambda x: x['depth_efficiency'], reverse=True)

# ── Summary statistics ───────────────────────────────────────────────
eff_depths = [r['effective_depth_pct'] for r in results]
panic_ratios = [r['panic_ratio'] for r in results]
active_works = [r['active_work'] for r in results]

summary = {
    'model': args.model,
    'num_layers': num_layers,
    'vocab_size': vocab_size,
    'tokens_processed': total_tokens_processed,
    'tokens_with_sufficient_obs': len(results),
    'min_observations': MIN_OBS,
    'processing_time_seconds': elapsed_total,
    'global_mean_velocity_per_layer': (global_velocity_sum / np.maximum(global_velocity_count, 1)).tolist(),
    'depth_efficiency_stats': {
        'mean_effective_depth_pct': float(np.mean(eff_depths)),
        'median_effective_depth_pct': float(np.median(eff_depths)),
        'std_effective_depth_pct': float(np.std(eff_depths)),
        'pct_tokens_using_less_than_50pct_depth': float(
            sum(1 for e in eff_depths if e < 50) / len(eff_depths) * 100
        ),
        'pct_tokens_using_less_than_25pct_depth': float(
            sum(1 for e in eff_depths if e < 25) / len(eff_depths) * 100
        ),
    },
    'panic_ratio_stats': {
        'mean': float(np.mean(panic_ratios)),
        'median': float(np.median(panic_ratios)),
        'p90': float(np.percentile(panic_ratios, 90)),
        'p99': float(np.percentile(panic_ratios, 99)),
    },
    'top_20_most_efficient': [
        {'token': r['token_str'], 'id': r['token_id'],
         'depth_eff': round(r['depth_efficiency'], 3),
         'active_layers': r['active_layers'],
         'eff_depth_pct': round(r['effective_depth_pct'], 1)}
        for r in results[:20]
    ],
    'bottom_20_least_efficient': [
        {'token': r['token_str'], 'id': r['token_id'],
         'depth_eff': round(r['depth_efficiency'], 3),
         'active_layers': r['active_layers'],
         'eff_depth_pct': round(r['effective_depth_pct'], 1)}
        for r in results[-20:]
    ],
}

# ── Print summary ────────────────────────────────────────────────────
print("\n" + "=" * 80)
print(f"DEPTH EFFICIENCY PROBE: {args.model}")
print(f"  {num_layers} layers, {vocab_size:,} vocab, {total_tokens_processed:,} tokens")
print("=" * 80)

print(f"\n  Tokens analyzed: {len(results):,}")
print(f"  Mean effective depth: {summary['depth_efficiency_stats']['mean_effective_depth_pct']:.1f}%")
print(f"  Median effective depth: {summary['depth_efficiency_stats']['median_effective_depth_pct']:.1f}%")
print(f"  Tokens using < 50% of layers: {summary['depth_efficiency_stats']['pct_tokens_using_less_than_50pct_depth']:.1f}%")
print(f"  Tokens using < 25% of layers: {summary['depth_efficiency_stats']['pct_tokens_using_less_than_25pct_depth']:.1f}%")

print(f"\n  TOP 20 (most efficient — using full depth):")
for r in summary['top_20_most_efficient']:
    print(f"    {r['token']:20s}  active_layers={r['active_layers']:3d}/{num_layers}  "
          f"eff_depth={r['eff_depth_pct']:5.1f}%")

print(f"\n  BOTTOM 20 (least efficient — wasting depth):")
for r in summary['bottom_20_least_efficient']:
    print(f"    {r['token']:20s}  active_layers={r['active_layers']:3d}/{num_layers}  "
          f"eff_depth={r['eff_depth_pct']:5.1f}%")

# ── Save results ─────────────────────────────────────────────────────
report_path = os.path.join(args.output_dir, "depth_efficiency_report.json")
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)
print(f"\n  Summary saved to {report_path}")

# Save full per-token results
full_path = os.path.join(args.output_dir, "depth_efficiency_full.json")
with open(full_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"  Full results saved to {full_path}")

# Save velocity heatmap as numpy
heatmap = np.zeros((len(results), num_layers), dtype=np.float32)
for i, r in enumerate(results):
    heatmap[i] = r['mean_velocity_per_layer']
heatmap_path = os.path.join(args.output_dir, "velocity_heatmap.npy")
np.save(heatmap_path, heatmap)
print(f"  Velocity heatmap saved to {heatmap_path}")

# Save token ID mapping for the heatmap
token_map = [{'row': i, 'token_id': r['token_id'], 'token_str': r['token_str']}
             for i, r in enumerate(results)]
token_map_path = os.path.join(args.output_dir, "heatmap_token_map.json")
with open(token_map_path, "w", encoding="utf-8") as f:
    json.dump(token_map, f, indent=2, ensure_ascii=False)
print(f"  Token map saved to {token_map_path}")

print(f"\nProbe complete. Total time: {elapsed_total:.0f}s")
