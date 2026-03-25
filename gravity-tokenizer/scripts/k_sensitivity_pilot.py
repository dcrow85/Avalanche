"""
K Sensitivity Pilot — Required pre-check before full scoring.

Scores a small subset of candidates (~100) at K = 5, 10, 20, 40 to determine
whether the downstream window parameter K affects leverage rankings.

If rankings are stable across K: K is a free parameter, use K=10 for speed.
If rankings shift: K reveals scale-dependent gravity types.

Usage:
    python scripts/k_sensitivity_pilot.py \
        --candidates data/candidates_filtered.jsonl \
        --output data/k_sensitivity_report.json \
        --reference-model gpt2 \
        --corpus-dir ./parameter-golf/data/datasets/fineweb10B_sp1024 \
        --base-tokenizer ./parameter-golf/data/tokenizers/fineweb_1024_bpe.model
"""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy import stats

from score_leverage import (
    compute_leverage_for_candidate,
    load_corpus_text,
    load_reference_model,
)


def rank_correlation(rankings_a, rankings_b):
    """Compute Spearman rank correlation between two ranking vectors."""
    if len(rankings_a) < 3:
        return 0.0
    rho, pvalue = stats.spearmanr(rankings_a, rankings_b)
    return float(rho)


def main():
    parser = argparse.ArgumentParser(description="K Sensitivity Pilot")
    parser.add_argument("--candidates", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    parser.add_argument("--reference-model", type=str, default="gpt2")
    parser.add_argument("--corpus-dir", type=str, required=True)
    parser.add_argument("--base-tokenizer", type=str, required=True)
    parser.add_argument("--n-candidates", type=int, default=100,
                        help="Number of candidates to test")
    parser.add_argument("--contexts-per-candidate", type=int, default=50,
                        help="Contexts per candidate (fewer than full scoring)")
    parser.add_argument("--device", type=str, default="cuda")
    args = parser.parse_args()

    K_VALUES = [5, 10, 20, 40]

    # Load model and corpus
    model, tokenizer = load_reference_model(args.reference_model, args.device)
    corpus_text = load_corpus_text(Path(args.corpus_dir), args.base_tokenizer)

    # Load candidates (sample evenly from frequency distribution)
    candidates = []
    with open(args.candidates, "r", encoding="utf-8") as f:
        for line in f:
            candidates.append(json.loads(line))

    # Sample candidates: take every Nth to get even distribution
    step = max(1, len(candidates) // args.n_candidates)
    pilot_candidates = candidates[::step][:args.n_candidates]
    print(f"Pilot: {len(pilot_candidates)} candidates at K={K_VALUES}")

    # Score at each K
    results_by_k = {}
    for K in K_VALUES:
        print(f"\n{'='*60}")
        print(f"Scoring at K={K}...")
        print(f"{'='*60}")

        scored = []
        for c in pilot_candidates:
            result = compute_leverage_for_candidate(
                model, tokenizer, c, corpus_text,
                K=K,
                n_contexts=args.contexts_per_candidate,
                early_exit_n=args.contexts_per_candidate,  # No early exit for pilot
                device=args.device,
            )
            scored.append(result)

        results_by_k[K] = scored

    # Compute rank correlations between all K pairs
    correlation_matrix = {}
    for K_a in K_VALUES:
        for K_b in K_VALUES:
            leverages_a = [r["ablation_leverage"] for r in results_by_k[K_a]]
            leverages_b = [r["ablation_leverage"] for r in results_by_k[K_b]]
            rho = rank_correlation(leverages_a, leverages_b)
            correlation_matrix[f"K{K_a}_vs_K{K_b}"] = rho

    # Identify candidates whose rank shifts dramatically with K
    rank_shifts = []
    for i, c in enumerate(pilot_candidates):
        ranks = {}
        for K in K_VALUES:
            leverages = [r["ablation_leverage"] for r in results_by_k[K]]
            sorted_indices = np.argsort(leverages)[::-1]
            rank = list(sorted_indices).index(i)
            ranks[K] = rank
        max_shift = max(ranks.values()) - min(ranks.values())
        rank_shifts.append({
            "candidate": c.get("readable", ""),
            "ranks": ranks,
            "max_shift": max_shift,
        })

    # Find scale-dependent candidates (big rank shifts)
    rank_shifts.sort(key=lambda x: -x["max_shift"])

    # Build report
    report = {
        "K_values_tested": K_VALUES,
        "n_candidates": len(pilot_candidates),
        "contexts_per_candidate": args.contexts_per_candidate,
        "rank_correlation_matrix": correlation_matrix,
        "recommendation": "",
        "top_rank_shifters": rank_shifts[:20],
        "leverage_summaries": {},
    }

    for K in K_VALUES:
        leverages = [r["ablation_leverage"] for r in results_by_k[K]]
        report["leverage_summaries"][f"K={K}"] = {
            "mean": float(np.mean(leverages)),
            "std": float(np.std(leverages)),
            "min": float(np.min(leverages)),
            "max": float(np.max(leverages)),
        }

    # Determine recommendation
    min_corr = min(
        correlation_matrix[f"K{a}_vs_K{b}"]
        for a in K_VALUES for b in K_VALUES if a != b
    )

    if min_corr > 0.85:
        report["recommendation"] = (
            f"Rankings are STABLE across K values (min rho={min_corr:.3f}). "
            f"K is a free parameter. Use K=10 for speed."
        )
    elif min_corr > 0.6:
        report["recommendation"] = (
            f"Rankings show MODERATE sensitivity to K (min rho={min_corr:.3f}). "
            f"Consider using K=10 as default but investigate scale-dependent "
            f"gravity types in the top rank shifters."
        )
    else:
        report["recommendation"] = (
            f"Rankings are UNSTABLE across K values (min rho={min_corr:.3f}). "
            f"K is a load-bearing parameter. Scale-dependent gravity types detected. "
            f"Consider separate vocabulary budgets for local vs discourse operators."
        )

    # Save report
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print("K SENSITIVITY PILOT REPORT")
    print(f"{'='*60}")
    print(f"\nRank correlations:")
    for K_a in K_VALUES:
        row = []
        for K_b in K_VALUES:
            rho = correlation_matrix[f"K{K_a}_vs_K{K_b}"]
            row.append(f"{rho:.3f}")
        print(f"  K={K_a:2d}: {' '.join(row)}")

    print(f"\nRecommendation: {report['recommendation']}")

    print(f"\nTop 10 rank shifters (scale-dependent gravity candidates):")
    for rs in rank_shifts[:10]:
        ranks_str = " ".join(f"K{k}:#{v}" for k, v in rs["ranks"].items())
        print(f"  shift={rs['max_shift']:3d}  {rs['candidate']!r}  [{ranks_str}]")

    print(f"\nFull report saved to: {output_path}")


if __name__ == "__main__":
    main()
