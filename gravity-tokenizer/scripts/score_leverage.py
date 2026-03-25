"""
Ablation Leverage Scorer — Core gravity measurement pipeline.

For each candidate token, measures the downstream loss increase when the token
is presented as its constituent bytes rather than as an atomic unit, using a
frozen reference model.

Implements:
- Batched forward passes for GPU efficiency (~5x faster than sequential)
- Configurable downstream window K with offset-based extraction
- Early-exit for low-leverage candidates
- Per-context leverage distribution for breadth computation
- GPT-2 vocabulary contamination calibration check

Usage:
    python scripts/score_leverage.py \
        --candidates data/candidates_filtered.jsonl \
        --output data/candidates_scored.jsonl \
        --reference-model gpt2 \
        --corpus-dir ./parameter-golf/data/datasets/fineweb10B_sp1024 \
        --base-tokenizer ./parameter-golf/data/tokenizers/fineweb_1024_bpe.model \
        --K 10 \
        --contexts-per-candidate 100 \
        --device cuda
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from tqdm import tqdm


def load_reference_model(model_name: str, device: str):
    """Load a frozen reference model for leverage scoring."""
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"Loading reference model: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16,
        trust_remote_code=True,
    ).to(device)
    model.eval()

    # Set padding token for batched inference
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        model.config.pad_token_id = tokenizer.eos_token_id

    # Freeze all parameters
    for param in model.parameters():
        param.requires_grad = False

    n_params = sum(p.numel() for p in model.parameters())
    print(f"  Parameters: {n_params:,}")
    print(f"  Vocab size: {tokenizer.vocab_size}")
    print(f"  Device: {device}")

    return model, tokenizer


def load_corpus_text(data_dir: Path, base_tokenizer_path: str,
                     max_shards: int = 2, max_tokens: int = 5_000_000) -> str:
    """Load and decode FineWeb corpus to raw text."""
    import sentencepiece as spm

    sp = spm.SentencePieceProcessor(model_file=base_tokenizer_path)
    shard_files = sorted(data_dir.glob("fineweb_train_*.bin"))[:max_shards]

    all_text = []
    for shard_path in shard_files:
        print(f"  Loading shard: {shard_path.name}")
        header = np.fromfile(shard_path, dtype="<i4", count=256)
        num_tokens = int(header[2])
        header_bytes = 256 * np.dtype("<i4").itemsize
        tokens = np.fromfile(shard_path, dtype="<u2", count=min(num_tokens, max_tokens),
                             offset=header_bytes)

        # Decode in chunks
        chunk_size = 100_000
        for i in range(0, len(tokens), chunk_size):
            chunk = tokens[i:i + chunk_size].tolist()
            all_text.append(sp.decode(chunk))

    text = " ".join(all_text)
    print(f"  Total corpus text: {len(text):,} characters")
    return text


def find_contexts(text: str, target_string: str, context_chars: int = 512,
                  max_contexts: int = 500) -> list[str]:
    """Find contexts in the corpus that contain the target string."""
    contexts = []
    start = 0
    while len(contexts) < max_contexts:
        idx = text.find(target_string, start)
        if idx == -1:
            break
        ctx_start = max(0, idx - context_chars // 2)
        ctx_end = min(len(text), idx + len(target_string) + context_chars // 2)
        ctx = text[ctx_start:ctx_end]
        contexts.append(ctx)
        start = idx + len(target_string)

    return contexts


def compute_leverage_batched(
    model,
    tokenizer,
    contexts: list[str],
    target_string: str,
    K: int = 10,
    device: str = "cuda",
    batch_size: int = 32,
) -> list[float]:
    """
    Compute ablation leverage for a batch of contexts using batched
    forward passes.

    Returns a list of per-context leverage values. Positive values mean
    shattering the target increases prediction loss (high structural gravity).
    """
    # Build intact/shattered text pairs
    intact_texts = []
    shattered_texts = []
    target_end_chars = []
    shattered_suffix_chars = []

    for ctx in contexts:
        target_start = ctx.find(target_string)
        if target_start == -1:
            continue
        target_end = target_start + len(target_string)
        shattered = (
            ctx[:target_start]
            + " ".join(target_string)
            + ctx[target_end:]
        )
        intact_texts.append(ctx)
        shattered_texts.append(shattered)
        target_end_chars.append(target_end)
        shattered_suffix_chars.append(target_start + len(" ".join(target_string)))

    if not intact_texts:
        return []

    leverages = []

    for b_start in range(0, len(intact_texts), batch_size):
        b_end = min(b_start + batch_size, len(intact_texts))
        b_intact = intact_texts[b_start:b_end]
        b_shattered = shattered_texts[b_start:b_end]
        b_target_ends = target_end_chars[b_start:b_end]
        b_shat_suffixes = shattered_suffix_chars[b_start:b_end]

        # Tokenize with padding and offset mapping
        try:
            intact_enc = tokenizer(
                b_intact, return_tensors="pt", padding=True,
                truncation=True, max_length=512, return_offsets_mapping=True,
            )
            shattered_enc = tokenizer(
                b_shattered, return_tensors="pt", padding=True,
                truncation=True, max_length=512, return_offsets_mapping=True,
            )
            has_offsets = True
        except Exception:
            intact_enc = tokenizer(
                b_intact, return_tensors="pt", padding=True,
                truncation=True, max_length=512,
            )
            shattered_enc = tokenizer(
                b_shattered, return_tensors="pt", padding=True,
                truncation=True, max_length=512,
            )
            has_offsets = False

        intact_ids = intact_enc["input_ids"].to(device)
        intact_mask = intact_enc["attention_mask"].to(device)
        shattered_ids = shattered_enc["input_ids"].to(device)
        shattered_mask = shattered_enc["attention_mask"].to(device)

        if has_offsets:
            intact_offsets = intact_enc["offset_mapping"]
            shattered_offsets = shattered_enc["offset_mapping"]

        # Batched forward passes
        with torch.inference_mode():
            intact_logits = model(intact_ids, attention_mask=intact_mask).logits
            shattered_logits = model(shattered_ids, attention_mask=shattered_mask).logits

        # Per-position loss (loss at index i predicts token at index i+1)
        intact_targets = intact_ids[:, 1:]
        intact_lp = F.log_softmax(intact_logits[:, :-1, :].float(), dim=-1)
        intact_losses = -intact_lp.gather(2, intact_targets.unsqueeze(-1)).squeeze(-1)

        shattered_targets = shattered_ids[:, 1:]
        shattered_lp = F.log_softmax(shattered_logits[:, :-1, :].float(), dim=-1)
        shattered_losses = -shattered_lp.gather(2, shattered_targets.unsqueeze(-1)).squeeze(-1)

        # Mask: only count loss where next token is real (not pad)
        intact_target_mask = intact_mask[:, 1:].float()
        shattered_target_mask = shattered_mask[:, 1:].float()

        # Extract per-item leverage
        for j in range(len(b_intact)):
            lev = None

            if has_offsets:
                i_off = intact_offsets[j]
                s_off = shattered_offsets[j]
                t_end = b_target_ends[j]
                s_suf = b_shat_suffixes[j]

                # Find downstream start in intact sequence
                ds_intact = None
                for t_idx in range(i_off.shape[0]):
                    if i_off[t_idx, 0].item() >= t_end:
                        ds_intact = t_idx
                        break

                ds_shattered = None
                for t_idx in range(s_off.shape[0]):
                    if s_off[t_idx, 0].item() >= s_suf:
                        ds_shattered = t_idx
                        break

                if ds_intact is not None and ds_shattered is not None:
                    # Loss index for predicting token at ds_start is ds_start-1
                    i_lo = max(0, ds_intact - 1)
                    i_hi = min(intact_losses.shape[1], i_lo + K)
                    s_lo = max(0, ds_shattered - 1)
                    s_hi = min(shattered_losses.shape[1], s_lo + K)

                    i_ds = intact_losses[j, i_lo:i_hi]
                    s_ds = shattered_losses[j, s_lo:s_hi]
                    i_ds_m = intact_target_mask[j, i_lo:i_hi]
                    s_ds_m = shattered_target_mask[j, s_lo:s_hi]

                    if i_ds_m.sum() > 0 and s_ds_m.sum() > 0:
                        i_mean = (i_ds * i_ds_m).sum() / i_ds_m.sum()
                        s_mean = (s_ds * s_ds_m).sum() / s_ds_m.sum()
                        lev = float(s_mean.item() - i_mean.item())

            if lev is None:
                # Fallback: masked overall mean
                i_m = intact_target_mask[j]
                s_m = shattered_target_mask[j]
                if i_m.sum() > 0 and s_m.sum() > 0:
                    i_mean = (intact_losses[j] * i_m).sum() / i_m.sum()
                    s_mean = (shattered_losses[j] * s_m).sum() / s_m.sum()
                    lev = float(s_mean.item() - i_mean.item())

            if lev is not None:
                leverages.append(lev)

    return leverages


def compute_leverage_for_context(
    model,
    tokenizer,
    context: str,
    target_string: str,
    K: int = 10,
    device: str = "cuda",
) -> float | None:
    """
    Compute ablation leverage for one context (non-batched fallback).

    Kept for compatibility with k_sensitivity_pilot.py.
    For production scoring, use compute_leverage_batched.
    """
    results = compute_leverage_batched(
        model, tokenizer, [context], target_string,
        K=K, device=device, batch_size=1,
    )
    return results[0] if results else None


def compute_leverage_for_candidate(
    model,
    tokenizer,
    candidate: dict,
    corpus_text: str,
    K: int = 10,
    n_contexts: int = 100,
    early_exit_n: int = 30,
    early_exit_threshold: float = 0.0,
    device: str = "cuda",
    batch_size: int = 32,
) -> dict:
    """
    Compute ablation leverage for a candidate token using batched scoring.

    Two-stage approach: score early_exit_n contexts first, then score
    the remainder if the candidate isn't clearly below threshold.
    """
    target = candidate["readable"]
    if not target or len(target) < 2:
        return {
            **candidate,
            "ablation_leverage": 0.0,
            "leverage_ci_low": 0.0,
            "leverage_ci_high": 0.0,
            "breadth": 0.0,
            "n_contexts_sampled": 0,
            "per_context_leverages": [],
        }

    # Find contexts containing this token
    contexts = find_contexts(corpus_text, target, max_contexts=n_contexts)

    if len(contexts) < 5:
        return {
            **candidate,
            "ablation_leverage": 0.0,
            "leverage_ci_low": 0.0,
            "leverage_ci_high": 0.0,
            "breadth": 0.0,
            "n_contexts_sampled": len(contexts),
            "per_context_leverages": [],
        }

    # Stage 1: Score first early_exit_n contexts
    stage1 = contexts[:early_exit_n]
    per_context_leverages = compute_leverage_batched(
        model, tokenizer, stage1, target,
        K=K, device=device, batch_size=batch_size,
    )

    # Early exit check
    do_stage2 = True
    if per_context_leverages:
        current_mean = np.mean(per_context_leverages)
        current_std = np.std(per_context_leverages) / np.sqrt(len(per_context_leverages))
        if current_mean + 2 * current_std < early_exit_threshold:
            do_stage2 = False

    # Stage 2: Score remaining contexts
    if do_stage2 and len(contexts) > early_exit_n:
        stage2 = contexts[early_exit_n:]
        stage2_leverages = compute_leverage_batched(
            model, tokenizer, stage2, target,
            K=K, device=device, batch_size=batch_size,
        )
        per_context_leverages.extend(stage2_leverages)

    if not per_context_leverages:
        return {
            **candidate,
            "ablation_leverage": 0.0,
            "leverage_ci_low": 0.0,
            "leverage_ci_high": 0.0,
            "breadth": 0.0,
            "n_contexts_sampled": 0,
            "per_context_leverages": [],
        }

    leverages = np.array(per_context_leverages)
    mean_lev = float(np.mean(leverages))
    std_lev = float(np.std(leverages))
    ci_half = 1.96 * std_lev / np.sqrt(len(leverages))

    # Breadth: entropy of the leverage distribution across contexts
    if len(leverages) > 5 and std_lev > 1e-8:
        n_bins = min(20, len(leverages) // 3)
        counts, _ = np.histogram(leverages, bins=max(n_bins, 2))
        probs = counts / counts.sum()
        probs = probs[probs > 0]
        breadth = float(-np.sum(probs * np.log(probs)))
    else:
        breadth = 0.0

    return {
        **candidate,
        "ablation_leverage": mean_lev,
        "leverage_ci_low": mean_lev - ci_half,
        "leverage_ci_high": mean_lev + ci_half,
        "breadth": breadth,
        "leverage_std": std_lev,
        "n_contexts_sampled": len(per_context_leverages),
        "per_context_leverages": [float(x) for x in per_context_leverages[:50]],
    }


def contamination_check(scored_candidates: list[dict], gpt2_tokenizer) -> dict:
    """
    Check for reference model contamination.

    Computes correlation between leverage scores and whether a candidate
    is in GPT-2's vocabulary. If significant correlation, the scores
    may be contaminated by GPT-2's tokenizer boundaries.
    """
    gpt2_vocab = set()
    for token_id in range(gpt2_tokenizer.vocab_size):
        try:
            token_str = gpt2_tokenizer.decode([token_id])
            gpt2_vocab.add(token_str.strip())
        except Exception:
            pass

    leverages = []
    in_gpt2 = []

    for c in scored_candidates:
        if c["ablation_leverage"] != 0.0:
            leverages.append(c["ablation_leverage"])
            readable = c.get("readable", "")
            in_gpt2.append(1.0 if readable in gpt2_vocab else 0.0)

    if len(leverages) < 10:
        return {"r_value": 0.0, "n_samples": len(leverages), "warning": "Too few samples"}

    leverages = np.array(leverages)
    in_gpt2 = np.array(in_gpt2)

    # Pearson correlation
    if np.std(leverages) < 1e-10 or np.std(in_gpt2) < 1e-10:
        r = 0.0
    else:
        r = float(np.corrcoef(leverages, in_gpt2)[0, 1])

    result = {
        "r_value": r,
        "n_samples": len(leverages),
        "pct_in_gpt2": float(np.mean(in_gpt2)),
        "mean_leverage_in_gpt2": float(np.mean(leverages[in_gpt2 > 0.5])) if np.sum(in_gpt2 > 0.5) > 0 else 0.0,
        "mean_leverage_not_in_gpt2": float(np.mean(leverages[in_gpt2 < 0.5])) if np.sum(in_gpt2 < 0.5) > 0 else 0.0,
    }

    if abs(r) > 0.3:
        result["warning"] = f"CONTAMINATION DETECTED: r={r:.3f}. Consider switching to byte-level reference model."
    else:
        result["status"] = f"Clean: r={r:.3f}. No significant contamination detected."

    return result


def main():
    parser = argparse.ArgumentParser(description="Ablation Leverage Scorer")
    parser.add_argument("--candidates", type=str, required=True,
                        help="Path to candidates JSONL file")
    parser.add_argument("--output", type=str, required=True,
                        help="Output scored candidates JSONL file")
    parser.add_argument("--reference-model", type=str, default="gpt2",
                        help="HuggingFace model name for reference model")
    parser.add_argument("--corpus-dir", type=str, required=True,
                        help="Directory containing FineWeb training shards")
    parser.add_argument("--base-tokenizer", type=str, required=True,
                        help="Path to base SentencePiece model")
    parser.add_argument("--K", type=int, default=10,
                        help="Downstream window size for leverage measurement")
    parser.add_argument("--contexts-per-candidate", type=int, default=100,
                        help="Number of contexts to sample per candidate")
    parser.add_argument("--early-exit-n", type=int, default=30,
                        help="Contexts before early-exit check")
    parser.add_argument("--batch-size", type=int, default=32,
                        help="Batch size for forward passes")
    parser.add_argument("--device", type=str, default="cuda",
                        help="Device to run on")
    parser.add_argument("--max-candidates", type=int, default=0,
                        help="Max candidates to score (0=all)")
    parser.add_argument("--run-contamination-check", action="store_true",
                        help="Run GPT-2 vocabulary contamination check")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from checkpoint file if it exists")
    args = parser.parse_args()

    # Load reference model
    model, tokenizer = load_reference_model(args.reference_model, args.device)

    # Load corpus text
    print("\nLoading corpus...")
    corpus_text = load_corpus_text(
        Path(args.corpus_dir),
        args.base_tokenizer,
        max_shards=2,
    )

    # Load candidates
    print("\nLoading candidates...")
    candidates = []
    with open(args.candidates, "r", encoding="utf-8") as f:
        for line in f:
            candidates.append(json.loads(line))
    print(f"  Loaded {len(candidates)} candidates")

    if args.max_candidates > 0:
        candidates = candidates[:args.max_candidates]
        print(f"  Truncated to {len(candidates)} candidates")

    # Resume from checkpoint if requested
    scored = []
    start_idx = 0
    if args.resume:
        checkpoint_path = args.output + ".checkpoint"
        if Path(checkpoint_path).exists():
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                for line in f:
                    scored.append(json.loads(line))
            start_idx = len(scored)
            print(f"\n  Resuming from checkpoint: {start_idx} already scored, "
                  f"{len(candidates) - start_idx} remaining")

    # Score candidates
    remaining = len(candidates) - start_idx
    print(f"\nScoring {remaining} candidates (K={args.K}, "
          f"contexts={args.contexts_per_candidate}, batch={args.batch_size})...")

    for i, candidate in enumerate(tqdm(candidates[start_idx:], desc="Scoring",
                                       initial=start_idx, total=len(candidates))):
        result = compute_leverage_for_candidate(
            model, tokenizer, candidate, corpus_text,
            K=args.K,
            n_contexts=args.contexts_per_candidate,
            early_exit_n=args.early_exit_n,
            device=args.device,
            batch_size=args.batch_size,
        )
        scored.append(result)

        # Periodic checkpoint
        if len(scored) % 100 == 0:
            with open(args.output + ".checkpoint", "w", encoding="utf-8") as f:
                for s in scored:
                    f.write(json.dumps(s, ensure_ascii=False) + "\n")

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for s in scored:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(scored)} scored candidates to {output_path}")

    # Run contamination check
    if args.run_contamination_check:
        print("\nRunning GPT-2 vocabulary contamination check...")
        contam = contamination_check(scored, tokenizer)
        print(f"  Contamination check results:")
        for k, v in contam.items():
            print(f"    {k}: {v}")

        # Save contamination report
        contam_path = output_path.with_suffix(".contamination.json")
        with open(contam_path, "w") as f:
            json.dump(contam, f, indent=2)
        print(f"  Saved to: {contam_path}")

    # Summary
    valid = [s for s in scored if s["ablation_leverage"] != 0.0]
    if valid:
        leverages = [s["ablation_leverage"] for s in valid]
        print(f"\nSummary ({len(valid)} valid candidates):")
        print(f"  Mean leverage: {np.mean(leverages):.6f}")
        print(f"  Median leverage: {np.median(leverages):.6f}")
        print(f"  Std leverage: {np.std(leverages):.6f}")

        print(f"\nTop 20 by leverage:")
        for s in sorted(valid, key=lambda x: -x["ablation_leverage"])[:20]:
            print(f"  lev={s['ablation_leverage']:.6f}  breadth={s['breadth']:.3f}  "
                  f"n={s['n_contexts_sampled']}  {s['readable']!r}")

        print(f"\nBottom 20 by leverage:")
        for s in sorted(valid, key=lambda x: x["ablation_leverage"])[:20]:
            print(f"  lev={s['ablation_leverage']:.6f}  breadth={s['breadth']:.3f}  "
                  f"n={s['n_contexts_sampled']}  {s['readable']!r}")


if __name__ == "__main__":
    main()
