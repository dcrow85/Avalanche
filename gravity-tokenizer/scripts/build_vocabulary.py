"""
Vocabulary Construction — Select tokens using the two-dimensional score.

For a given beta value, computes:
    score(t) = freq_norm(t)^(1-beta) * leverage_norm(t)^beta

Both frequency and leverage are log-scaled before normalization.

GRAVITY TOKENIZER v2 (April 7, 2026): Two prefilters are applied BEFORE scoring.
The merge pool is restricted to candidates that satisfy both:

    1. Volume floor: corpus_frequency >= 2903
       Below this threshold, no token in the seed-1337 coherence run crossed the
       integrated-gradient-energy floor (E_crit ~ 1.20). Empirically derived from
       parameter-golf/logs/coherence_seed_1337.

    2. Parasitism veto: NOT (top1_successor_frac > 0.95 AND top1_char.isalpha())
       Tokens whose dominant continuation is a word-internal letter (e.g.
       'produ' -> 'c') are hostage pointers; gravity scoring misreads syntactic
       dependence as semantic leverage. The boundary-aware gate (isalpha) avoids
       false-flagging whole words whose top successor is a space.

Both filters apply only when --gravity-v2 is set, and they require a candidate
successor-stats file from scripts/compute_candidate_successor_stats.py.

Selects top 765 candidates (+ 256 byte + 3 control = 1024 total vocabulary).
Outputs the graveyard list (high-leverage tokens that didn't make the cut).

Usage:
    # Legacy v1 (no filters)
    python scripts/build_vocabulary.py \
        --scored-candidates data/candidates_scored.jsonl \
        --beta 0.3 \
        --output data/vocabularies/ \
        --vocab-size 1024

    # v2
    python scripts/build_vocabulary.py \
        --scored-candidates data/candidates_scored.jsonl \
        --successor-stats data/candidates_successor_stats.jsonl \
        --gravity-v2 \
        --beta 1.0 \
        --output data/vocabularies/ \
        --vocab-size 1024
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np


# Gravity Tokenizer v2 filter constants (April 7, 2026)
V2_VOLUME_FLOOR = 2903           # corpus_frequency floor; data-derived from seed_1337
V2_PARASITISM_THRESHOLD = 0.95   # top1 successor fraction veto threshold


def is_v2_parasite(top1_char: str | None, top1_frac: float) -> bool:
    """Boundary-aware parasitism rule.

    A candidate is a parasite if its dominant byte successor is a *word-internal*
    character (operationalized as isalpha()) and that successor accounts for
    >95% of occurrences. Whole words whose dominant successor is space or
    punctuation are NOT parasites — that's a complete-unit signal.
    """
    if top1_char is None:
        return False
    return top1_frac > V2_PARASITISM_THRESHOLD and top1_char.isalpha()


def apply_v2_filters(
    candidates: list[dict],
    successor_stats: dict[str, dict],
) -> tuple[list[dict], dict]:
    """Apply v2 prefilters to the merge candidate pool.

    Returns (eligible_candidates, audit) where audit is a dict of counts and
    rejected lists for the report.

    Rules:
      - in_base_vocab tokens are always retained (they're SP base bytes, not merges)
      - other candidates must pass volume floor AND not be a parasite
    """
    eligible = []
    rejected_below_floor = []
    rejected_parasite = []

    for c in candidates:
        if c.get("in_base_vocab", False):
            eligible.append(c)
            continue

        if c.get("corpus_frequency", 0) < V2_VOLUME_FLOOR:
            rejected_below_floor.append(c)
            continue

        s = successor_stats.get(c["piece"])
        top1_char = s.get("top1_successor_char") if s else None
        top1_frac = s.get("top1_successor_frac", 0.0) if s else 0.0
        if is_v2_parasite(top1_char, top1_frac):
            rj = dict(c)
            rj["top1_successor_char"] = top1_char
            rj["top1_successor_frac"] = top1_frac
            rejected_parasite.append(rj)
            continue

        # Annotate survivors with successor stats for downstream introspection
        c2 = dict(c)
        c2["top1_successor_char"] = top1_char
        c2["top1_successor_frac"] = top1_frac
        eligible.append(c2)

    audit = {
        "n_input": len(candidates),
        "n_eligible": len(eligible),
        "n_rejected_below_floor": len(rejected_below_floor),
        "n_rejected_parasite": len(rejected_parasite),
        "rejected_parasites": [
            {
                "piece": r["piece"],
                "readable": r.get("readable", ""),
                "corpus_frequency": r.get("corpus_frequency", 0),
                "ablation_leverage": r.get("ablation_leverage", 0.0),
                "top1_successor_char": r.get("top1_successor_char"),
                "top1_successor_frac": r.get("top1_successor_frac", 0.0),
            }
            for r in sorted(rejected_parasite, key=lambda x: -x.get("top1_successor_frac", 0.0))
        ],
        "volume_floor": V2_VOLUME_FLOOR,
        "parasitism_threshold": V2_PARASITISM_THRESHOLD,
    }
    return eligible, audit


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
    parser.add_argument("--gravity-v2", action="store_true",
                        help="Apply Gravity Tokenizer v2 prefilters: volume floor + parasitism veto")
    parser.add_argument("--successor-stats", type=str, default=None,
                        help="Path to successor stats file (required with --gravity-v2)")
    parser.add_argument("--with-space", action="store_true",
                        help="Replace the lowest-scoring merge token with a bare \u2581 "
                             "(SentencePiece space plumbing). Required for the SP encoder to "
                             "produce clean round-trip decoding. This is the 'space token fix' "
                             "from the v1 investigation.")
    args = parser.parse_args()

    if args.gravity_v2 and not args.successor_stats:
        parser.error("--gravity-v2 requires --successor-stats")

    n_merge_tokens = args.vocab_size - 256 - 3  # Reserve 256 byte + 3 control tokens (<unk>, <s>, </s>)

    # Load scored candidates
    candidates = []
    with open(args.scored_candidates, "r", encoding="utf-8") as f:
        for line in f:
            candidates.append(json.loads(line))
    print(f"Loaded {len(candidates)} scored candidates")

    audit = None
    if args.gravity_v2:
        # Load successor stats and apply v2 prefilters
        successor_stats = {}
        with open(args.successor_stats, "r", encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                successor_stats[r["piece"]] = r
        print(f"Loaded successor stats for {len(successor_stats)} candidates")

        candidates, audit = apply_v2_filters(candidates, successor_stats)
        print(f"\n=== Gravity v2 prefilter pass ===")
        print(f"  input candidates:           {audit['n_input']}")
        print(f"  rejected (below floor {V2_VOLUME_FLOOR}): {audit['n_rejected_below_floor']}")
        print(f"  rejected (parasite > {V2_PARASITISM_THRESHOLD}):     {audit['n_rejected_parasite']}")
        print(f"  eligible after filters:     {audit['n_eligible']}")
        print(f"  slot budget:                {n_merge_tokens}")
        print(f"  oversubscription:           {audit['n_eligible'] / n_merge_tokens:.2f}x")
        print(f"\n  Top vetoed parasites:")
        for r in audit["rejected_parasites"][:10]:
            print(f"    {r['piece']!r:18} top1={r['top1_successor_char']!r} "
                  f"frac={r['top1_successor_frac']:.4f} freq={r['corpus_frequency']}")

    # Compute scores (two-dimensional: freq x leverage) over the (filtered) pool
    candidates = compute_scores(candidates, args.beta)

    # Select vocabulary
    selected, graveyard = select_vocabulary(candidates, n_merge_tokens)

    print(f"\nVocabulary selection (beta={args.beta}):")
    print(f"  Selected: {len(selected)} tokens")
    print(f"  Graveyard: {len(graveyard)} high-leverage tokens rejected")

    if args.with_space:
        # Space token fix: replace lowest-scoring merge with bare U+2581.
        # Without this, the SP encoder cannot emit a standalone space token and
        # round-trip decoding of retokenized corpora leaks literal \u2581
        # characters into the training text. Same fix applied to v1's
        # vocabulary_beta_1.0_with_space.json.
        selected.sort(key=lambda c: c.get("score", 0))
        dropped = selected[0]
        selected = selected[1:]
        space_token = {
            "piece": "\u2581",
            "readable": "SPACE",
            "token_bytes": [0xe2, 0x96, 0x81],
            "ablation_leverage": 0.0,
            "score": 1.0,
            "corpus_frequency": 3315,  # historical; matches v1 for provenance
            "static_core": True,
            "note": "Plumbing token. Replaces 3-byte fallback for word boundaries.",
        }
        selected.append(space_token)
        # Re-sort by score descending to preserve the original ordering convention
        selected.sort(key=lambda c: -c.get("score", 0))
        print(f"\n[space token fix] replaced lowest-score merge "
              f"{dropped.get('piece')!r} (score={dropped.get('score', 0):.4f}) "
              f"with bare \u2581")

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

    tag = f"v2_beta_{args.beta}" if args.gravity_v2 else f"beta_{args.beta}"
    if args.with_space:
        tag = f"{tag}_with_space"

    # Save vocabulary
    vocab_path = output_dir / f"vocabulary_{tag}.json"
    vocab_data = {
        "beta": args.beta,
        "vocab_size": args.vocab_size,
        "n_byte_tokens": 256,
        "n_merge_tokens": len(selected),
        "gravity_v2": bool(args.gravity_v2),
        "v2_audit": (
            {
                "volume_floor": V2_VOLUME_FLOOR,
                "parasitism_threshold": V2_PARASITISM_THRESHOLD,
                "n_input_candidates": audit["n_input"],
                "n_rejected_below_floor": audit["n_rejected_below_floor"],
                "n_rejected_parasite": audit["n_rejected_parasite"],
                "n_eligible_after_filters": audit["n_eligible"],
                "rejected_parasites": audit["rejected_parasites"],
            }
            if audit is not None
            else None
        ),
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
