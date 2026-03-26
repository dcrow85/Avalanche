"""
Depth Efficiency Probe for Qwen2.5-72B
Measures residual velocity (L2 norm of layer update) per token per layer.
Produces a [vocab_size x num_layers] heatmap of where each token's processing lives.

Requirements: 2x A100 80GB (or equivalent ~160GB VRAM), transformers, accelerate, datasets
Run time: ~30 minutes including model download
Cost: ~$3 on RunPod

Usage:
    export HF_HOME=/workspace/hf_cache  # point to large disk
    python qwen72b_depth_probe.py
"""
import torch
import json
import time
import numpy as np
from collections import defaultdict
from transformers import AutoModelForCausalLM, AutoTokenizer
from datasets import load_dataset

print('=== Qwen2.5-72B Depth Efficiency Probe ===')
print(f'CUDA devices: {torch.cuda.device_count()}')
for i in range(torch.cuda.device_count()):
    print(f'  GPU {i}: {torch.cuda.get_device_name(i)}')

# Load model
print('\nLoading Qwen2.5-72B (bf16, auto device map)...')
t0 = time.time()
model_name = 'Qwen/Qwen2.5-72B'
tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    dtype=torch.bfloat16,
    device_map='auto',
    trust_remote_code=True,
)
model.eval()
print(f'Model loaded in {time.time()-t0:.1f}s')

# Count layers
num_layers = len(model.model.layers)
vocab_size = tokenizer.vocab_size
print(f'Layers: {num_layers}, Vocab size: {vocab_size}')

# Velocity capture hooks
velocities = {}  # layer_idx -> list of [seq_len] tensors

def make_hook(layer_idx):
    def hook_fn(module, input, output):
        x_in = input[0] if isinstance(input, tuple) else input
        x_out = output[0] if isinstance(output, tuple) else output
        with torch.no_grad():
            # Handle cross-device tensors from device_map='auto'
            vel = (x_out.to(x_in.device) - x_in).float().norm(dim=-1)  # [batch, seq_len]
            if layer_idx not in velocities:
                velocities[layer_idx] = []
            velocities[layer_idx].append(vel.cpu())
    return hook_fn

# Register hooks
hooks = []
for i, layer in enumerate(model.model.layers):
    h = layer.register_forward_hook(make_hook(i))
    hooks.append(h)
print(f'Registered {len(hooks)} velocity hooks')

# Load sample data
print('\nLoading wikitext-103...')
ds = load_dataset('wikitext', 'wikitext-103-raw-v1', split='train')
ds = [x for x in ds if len(x.get('text', '')) > 100]

# Accumulate per-token velocity statistics
token_velocity_sum = defaultdict(lambda: np.zeros(num_layers, dtype=np.float64))
token_velocity_count = defaultdict(lambda: np.zeros(num_layers, dtype=np.int64))

TARGET_TOKENS = 100_000
total_tokens = 0
batch_count = 0

print(f'\nRunning inference on ~{TARGET_TOKENS} tokens...')
t0 = time.time()

for sample in ds:
    text = sample.get('text', '') if isinstance(sample, dict) else sample['text']
    if len(text) < 100:
        continue

    # Truncate to ~512 tokens worth
    text = text[:2048]

    inputs = tokenizer(text, return_tensors='pt', truncation=True, max_length=512)
    input_ids = inputs['input_ids']  # [1, seq_len]
    seq_len = input_ids.shape[1]

    if seq_len < 10:
        continue

    # Move to model's device
    input_ids = input_ids.to(model.device)

    # Forward pass
    velocities.clear()
    with torch.no_grad():
        model(input_ids)

    # Accumulate per-token stats
    ids = input_ids[0].cpu().numpy()
    for layer_idx in range(num_layers):
        vel = velocities[layer_idx][0][0].numpy()  # [seq_len]
        for pos in range(seq_len):
            tid = int(ids[pos])
            token_velocity_sum[tid][layer_idx] += vel[pos]
            token_velocity_count[tid][layer_idx] += 1

    total_tokens += seq_len
    batch_count += 1

    if batch_count % 20 == 0:
        elapsed = time.time() - t0
        tps = total_tokens / elapsed
        print(f'  {total_tokens:>8d} tokens | {batch_count:>4d} docs | {tps:.0f} tok/s | {elapsed:.1f}s')

    if total_tokens >= TARGET_TOKENS:
        break

elapsed = time.time() - t0
print(f'\nDone: {total_tokens} tokens from {batch_count} docs in {elapsed:.1f}s')

# Compute means
print('\nComputing per-token velocity profiles...')
results = {
    'model': model_name,
    'num_layers': num_layers,
    'vocab_size': vocab_size,
    'total_tokens_processed': total_tokens,
    'num_documents': batch_count,
    'tokens': {}
}

for tid in sorted(token_velocity_sum.keys()):
    counts = token_velocity_count[tid]
    sums = token_velocity_sum[tid]

    # Only include tokens with enough observations
    min_obs = counts.min()
    if min_obs < 5:
        continue

    mean_vel = sums / counts.clip(min=1)

    # Compute metrics
    early_vel = mean_vel[:num_layers//4].mean()
    mid_vel = mean_vel[num_layers//4:3*num_layers//4].mean()
    late_vel = mean_vel[3*num_layers//4:].mean()

    panic_ratio = late_vel / mid_vel if mid_vel > 1e-6 else 0.0
    active_work = mean_vel.sum()
    uniformity = mean_vel.std() / mean_vel.mean() if mean_vel.mean() > 1e-6 else 999.0

    token_str = tokenizer.decode([tid])

    results['tokens'][str(tid)] = {
        'token_string': token_str,
        'observations': int(min_obs),
        'total_observations': int(counts.sum()),
        'velocity_profile': mean_vel.tolist(),
        'early_mean': float(early_vel),
        'mid_mean': float(mid_vel),
        'late_mean': float(late_vel),
        'panic_ratio': float(panic_ratio),
        'active_work': float(active_work),
        'uniformity_cv': float(uniformity),
    }

print(f'Tokens with sufficient data: {len(results["tokens"])}')

# Save results
output_path = 'qwen72b_depth_probe_results.json'
with open(output_path, 'w') as f:
    json.dump(results, f, indent=2)
print(f'\nResults saved to {output_path}')

# Quick summary
print('\n=== Top 20 most depth-efficient tokens (lowest uniformity CV) ===')
sorted_tokens = sorted(results['tokens'].items(), key=lambda x: x[1]['uniformity_cv'])
for tid, data in sorted_tokens[:20]:
    print(f"  {data['token_string']:>15s}  CV={data['uniformity_cv']:.3f}  panic={data['panic_ratio']:.2f}  work={data['active_work']:.0f}  obs={data['observations']}")

print('\n=== Top 20 most depth-WASTEFUL tokens (highest panic ratio) ===')
sorted_panic = sorted(results['tokens'].items(), key=lambda x: x[1]['panic_ratio'], reverse=True)
for tid, data in sorted_panic[:20]:
    print(f"  {data['token_string']:>15s}  panic={data['panic_ratio']:.2f}  CV={data['uniformity_cv']:.3f}  work={data['active_work']:.0f}  obs={data['observations']}")

print('\n=== Summary statistics ===')
all_panic = [d['panic_ratio'] for d in results['tokens'].values()]
all_cv = [d['uniformity_cv'] for d in results['tokens'].values()]
all_work = [d['active_work'] for d in results['tokens'].values()]
print(f'Panic ratio:  mean={np.mean(all_panic):.3f}  std={np.std(all_panic):.3f}  min={np.min(all_panic):.3f}  max={np.max(all_panic):.3f}')
print(f'Uniformity CV: mean={np.mean(all_cv):.3f}  std={np.std(all_cv):.3f}  min={np.min(all_cv):.3f}  max={np.max(all_cv):.3f}')
print(f'Active work:  mean={np.mean(all_work):.0f}  std={np.std(all_work):.0f}  min={np.min(all_work):.0f}  max={np.max(all_work):.0f}')

# Remove hooks
for h in hooks:
    h.remove()

print('\nProbe complete.')
