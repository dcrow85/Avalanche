"""
Vocabulary Construction — Select tokens using the two-dimensional score.

For a given beta value, computes:
    score(t) = freq_norm(t)^(1-beta) * leverage_norm(t)^beta

Both frequency and leverage are log-scaled before normalization.
Breadth was dropped: mean 2.57, std 0.15 across all candidates — no
discriminative power. The frozen-entanglement problem doesn't exist in
this candidate pool.

Selects top 765 candidates (+ 256 byte + 3 control = 1024 total vocabulary).
Outputs the graveyard list (high-leverage tokens that didn't make the cut).

Usage:
    python scripts/build_vocabulary.py \
        --scored-candidates data/candidates_scored.jsonl \
        --beta 0.3 \
        --output data/vocabularies/ \
        --vocab-size 1024
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np


def normalize_to_01(values: list[float]) -> list[float]:
    """Normalize values to [0, 1] range."""
    arr = np.array(values)
    vmin, vmax = arr.min(), arr.max()
    if vmax - vmin < 1e-10:
        return [0.5] * len(values)
    return ((arr - vmin) / (vmax - vmin)).tolist()


def compute_scores(candidates: list[dict], beta: float) -> list[dict]:
    """Compute two-dimensional scores for all candidates.

    Both frequency and leverage are log-scaled before normalization.
    The raw leverage distribution is compressed (mean ~0.58, std ~0.19) —
    log-scaling stretches it so the beta exponent has teeth.
    """
    freqs = [c.get("corpus_frequency", 0) for c in candidates]
    leverages = [c.get("ablation_leverage", 0.0) for c in candidates]

    # Log-scale leverage to stretch the compressed distribution
    lev_arr = np.array(leverages)
    lev_floor = max(lev_arr[lev_arr > 0].min() * 0.1, 1e-6) if np.any(lev_arr > 0) else 1e-6
    log_leverages = np.log(np.maximum(lev_arr, lev_floor)).tolist()

    # Log-scale frequency (spans orders of magnitude)
    freq_arr = np.array(freqs, dtype=float)
    log_freqs = np.log(np.maximum(freq_arr, 1.0)).tolist()

    # Normalize to [0, 1]
    freq_norm = normalize_to_01(log_freqs)
    lev_norm = normalize_to_01(log_leverages)

    for i, c in enumerate(candidates):
        fn = max(freq_norm[i], 1e-8)
        ln = max(lev_norm[i], 1e-8)

        c["score"] = (fn ** (1 - beta)) * (ln ** beta)
        c["freq_normalized"] = freq_norm[i]
        c["leverage_normalized"] = lev_norm[i]
        c["raw_leverage"] = leverages[i]
        c["raw_frequency"] = freqs[i]

    return candidates


def select_vocabulary(candidates: list[dict], n_merge_tokens: int = 768) -> tuple[list[dict], list[dict]]:
    """
    Select top n_merge_tokens by score.
    Returns (selected, graveyard).
    """
    sorted_candidates = sorted(candidates, key=lambda c: -c["score"])
    selected = sorted_candidates[:n_merge_tokens]
    rejected = sorted_candidates[n_merge_tokens:]

    # Graveyard: high leverage tokens that were rejected
    median_leverage = np.median([c.get("ablation_leverage", 0.0) for c in candidates])
    graveyard = [
        c for c in rejected
        if c.get("ablation_leverage", 0.0) > median_leverage
    ]

    return selected, graveyard


def categorize_tokens(tokens: list[dict]) -> dict:
    """Categorize tokens into functional groups."""
    categories = {
        "operators": [],        # not, if, but, or, and
        "morphological": [],    # un-, re-, -ing, -tion, -ly
        "function_words": [],   # the, a, of, to, in, for
        "content_fragments": [],  # common content word parts
        "punctuation": [],      # ., ,, !, ?
        "other": [],
    }

    operator_patterns = {"not", "if", "but", "or", "and", "nor", "yet", "so",
                         "because", "although", "however", "therefore", "unless",
                         "whether", "while", "since", "though", "whereas"}
    morphological_patterns = {"un", "re", "pre", "dis", "mis", "non", "over",
                              "ing", "tion", "ment", "ness", "able", "ible",
                              "ful", "less", "ous", "ive", "ly", "er", "est",
                              "ed", "es", "al", "ial", "ical"}
    function_words = {"the", "a", "an", "of", "to", "in", "for", "is", "on",
                      "that", "by", "this", "with", "from", "as", "are", "was",
                      "at", "be", "have", "it", "which", "had", "has", "will",
                      "can", "been", "would", "their", "its", "they", "you", "he",
                      "she", "we", "who", "what", "when", "where", "how"}

    for t in tokens:
        readable = t.get("readable", "").strip().lower()
        if readable in operator_patterns:
            categories["operators"].append(t)
        elif readable in morphological_patterns:
            categories["morphological"].append(t)
        elif readable in function_words:
            categories["function_words"].append(t)
        elif readable in ".,!?;:'\"-()[]{}":
            categories["punctuation"].append(t)
        elif readable:
            categories["content_fragments"].append(t)
        else:
            categories["other"].append(t)

    return categories


def main():
    parser = argparse.ArgumentParser(description="Vocabulary Construction")
    parser.add_argument("--scored-candidates", type=str, required=True)
    parser.add_argument("--beta", type=float, required=True)
    parser.add_argument("--gamma", type=float, default=0.0,
                        help="Deprecated, ignored. Kept for CLI compatibility.")
    parser.add_argument("--output", type=str, required=True,
                        help="Output directory for vocabulary files")
    parser.add_argument("--vocab-size", type=int, default=1024,
                        help="Total vocabulary size including 256 byte tokens")
    args = parser.parse_args()

    n_merge_tokens = args.vocab_size - 256 - 3  # Reserve 256 byte + 3 control tokens (<unk>, <s>, </s>)

    # Load scored candidates
    candidates = []
    with open(args.scored_candidates, "r", encoding="utf-8") as f:
        for line in f:
            candidates.append(json.loads(line))
    print(f"Loaded {len(candidates)} scored candidates")

    # Compute scores (two-dimensional: freq x leverage)
    candidates = compute_scores(candidates, args.beta)

    # Select vocabulary
    selected, graveyard = select_vocabulary(candidates, n_merge_tokens)

    print(f"\nVocabulary selection (beta={args.beta}):")
    print(f"  Selected: {len(selected)} tokens")
    print(f"  Graveyard: {len(graveyard)} high-leverage tokens rejected")

    # Categorize selected and graveyard
    sel_cats = categorize_tokens(selected)
    grave_cats = categorize_tokens(graveyard)

    print(f"\nSelected token categories:")
    for cat, tokens in sel_cats.items():
        if tokens:
            print(f"  {cat}: {len(tokens)}")
            for t in tokens[:5]:
                print(f"    {t['readable']!r} (lev={t.get('ablation_leverage', 0):.4f}, "
                      f"freq={t.get('corpus_frequency', 0):,})")

    print(f"\nGraveyard categories:")
    for cat, tokens in grave_cats.items():
        if tokens:
            print(f"  {cat}: {len(tokens)}")
            for t in sorted(tokens, key=lambda x: -x.get("ablation_leverage", 0))[:3]:
                print(f"    {t['readable']!r} (lev={t.get('ablation_leverage', 0):.4f}, "
                      f"freq={t.get('corpus_frequency', 0):,}, score={t.get('score', 0):.6f})")

    # Save outputs
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    tag = f"beta_{args.beta}"

    # Save vocabulary
    vocab_path = output_dir / f"vocabulary_{tag}.json"
    vocab_data = {
        "beta": args.beta,
        "vocab_size": args.vocab_size,
        "n_byte_tokens": 256,
        "n_merge_tokens": len(selected),
        "tokens": [
            {
                "piece": t.get("piece", ""),
                "readable": t.get("readable", ""),
                "token_bytes": t.get("token_bytes", []),
                "score": t["score"],
                "ablation_leverage": t.get("ablation_leverage", 0.0),
                "corpus_frequency": t.get("corpus_frequency", 0),
            }
            for t in selected
        ],
    }
    with open(vocab_path, "w", encoding="utf-8") as f:
        json.dump(vocab_data, f, indent=2, ensure_ascii=False)
    print(f"\nVocabulary saved to: {vocab_path}")

    # Save graveyard
    graveyard_path = output_dir / f"graveyard_{tag}.json"
    graveyard_data = {
        "beta": args.beta,
        "n_graveyard_tokens": len(graveyard),
        "tokens": [
            {
                "piece": t.get("piece", ""),
                "readable": t.get("readable", ""),
                "ablation_leverage": t.get("ablation_leverage", 0.0),
                "corpus_frequency": t.get("corpus_frequency", 0),
                "score": t["score"],
            }
            for t in sorted(graveyard, key=lambda x: -x.get("ablation_leverage", 0.0))
        ],
    }
    with open(graveyard_path, "w", encoding="utf-8") as f:
        json.dump(graveyard_data, f, indent=2, ensure_ascii=False)
    print(f"Graveyard saved to: {graveyard_path}")


if __name__ == "__main__":
    main()
