"""
Crystallization Curve Extractor — merge-chain leverage trajectories.

For each target token, walks the BPE merge tree (reconstructed from the
SentencePiece model proto) to extract leverage at every intermediate merge
step. Produces data for plotting leverage vs. merge step — the
"crystallization curve" that reveals where meaning snaps into existence.

Two modes:
  - Report mode (default, no GPU): uses existing scores, flags gaps
  - Score mode (--score-missing): fills gaps on-the-fly via score_leverage.py

Usage:
    python scripts/crystallization_curves.py \
        --model data/large_bpe.model \
        --scored data/candidates_scored.jsonl \
        --output data/crystallization_curves.json \
        --top-n 50

    python scripts/crystallization_curves.py \
        --model data/large_bpe.model \
        --scored data/candidates_scored.jsonl \
        --output data/crystallization_curves.json \
        --targets "the,every,under,contin,partic" \
        --score-missing \
        --reference-model gpt2 \
        --corpus-dir ./parameter-golf/data/datasets/fineweb10B_sp1024 \
        --base-tokenizer ./parameter-golf/data/tokenizers/fineweb_1024_bpe.model \
        --device cuda
"""

import argparse
import csv
import json
import sys
from pathlib import Path


def load_merge_tree(model_path: str) -> dict:
    """
    Reconstruct the BPE merge tree from a SentencePiece model proto.

    Returns a dict mapping piece string -> {piece, score, rank, type,
    left_child, right_child} for every piece in the model.
    """
    from sentencepiece import sentencepiece_model_pb2 as sp_model

    proto = sp_model.ModelProto()
    with open(model_path, "rb") as f:
        proto.ParseFromString(f.read())

    # Build piece lookup: piece_string -> (index, score, type)
    pieces = {}
    for idx, p in enumerate(proto.pieces):
        ptype = p.type
        type_name = {
            sp_model.ModelProto.SentencePiece.NORMAL: "normal",
            sp_model.ModelProto.SentencePiece.UNKNOWN: "unknown",
            sp_model.ModelProto.SentencePiece.CONTROL: "control",
            sp_model.ModelProto.SentencePiece.BYTE: "byte",
        }.get(ptype, "other")

        pieces[p.piece] = {
            "piece": p.piece,
            "index": idx,
            "score": p.score,
            "type": type_name,
            "left_child": None,
            "right_child": None,
        }

    # For BPE models, score is the negative merge rank.
    # Assign rank: byte/control/unknown get rank -1 (leaf nodes).
    # Normal pieces get rank from their index (approximation: index - offset).
    #
    # SentencePiece BPE puts single-character fallback pieces at the END of
    # the vocab (high indices) even though they're leaf-level building blocks.
    # We treat them as leaves (rank=-1) so merge tree resolution works.
    byte_and_control_count = sum(
        1 for p in pieces.values() if p["type"] in ("byte", "control", "unknown")
    )
    for p in pieces.values():
        if p["type"] != "normal":
            p["rank"] = -1
        else:
            raw_rank = p["index"] - byte_and_control_count
            # Single-character normal pieces are character-level fallbacks,
            # not real BPE merges. Treat as leaves.
            piece_str = p["piece"]
            if len(piece_str) == 1 or (len(piece_str) == 2 and piece_str[0] == "\u2581"):
                p["rank"] = -1
                p["type"] = "char"  # reclassify
            else:
                p["rank"] = raw_rank

    # Reconstruct parent pointers by trying all binary splits.
    # For BPE, the correct split is the one where the later-created child
    # has the lowest merge rank (i.e., the split that could have happened
    # earliest in the BPE merge sequence).
    merge_pieces = {k: v for k, v in pieces.items() if v["rank"] >= 0}
    normal_pieces = merge_pieces  # alias for clarity

    for piece_str, pinfo in normal_pieces.items():
        best_split = None
        best_max_rank = float("inf")

        for split_pos in range(1, len(piece_str)):
            left_str = piece_str[:split_pos]
            right_str = piece_str[split_pos:]

            if left_str not in pieces or right_str not in pieces:
                continue

            left_rank = pieces[left_str]["rank"]
            right_rank = pieces[right_str]["rank"]

            # Both children must exist before this piece was created.
            # Byte/control tokens (rank=-1) always exist.
            if left_rank >= pinfo["rank"] and left_rank != -1:
                continue
            if right_rank >= pinfo["rank"] and right_rank != -1:
                continue

            # Pick the split where the latest-created child has lowest rank.
            max_child_rank = max(
                left_rank if left_rank >= 0 else -1,
                right_rank if right_rank >= 0 else -1,
            )
            if max_child_rank < best_max_rank:
                best_max_rank = max_child_rank
                best_split = (left_str, right_str)

        if best_split:
            pinfo["left_child"] = best_split[0]
            pinfo["right_child"] = best_split[1]

    n_resolved = sum(1 for p in normal_pieces.values() if p["left_child"] is not None)
    n_total = len(normal_pieces)
    print(f"Merge tree: {n_resolved}/{n_total} normal pieces resolved "
          f"({n_total - n_resolved} unresolved)")

    return pieces


def walk_merge_chain(pieces: dict, target_piece: str) -> list[dict]:
    """
    Walk the merge tree for a target piece, collecting all intermediates
    from bytes up to the final token.

    Returns a list of dicts ordered by merge step (bytes first, target last):
    [{piece, rank, byte_length, merge_step}, ...]
    """
    if target_piece not in pieces:
        return []

    # Collect all intermediates via recursive descent
    visited = {}

    def _collect(piece_str):
        if piece_str in visited:
            return
        pinfo = pieces.get(piece_str)
        if pinfo is None:
            return
        visited[piece_str] = pinfo
        if pinfo["left_child"]:
            _collect(pinfo["left_child"])
        if pinfo["right_child"]:
            _collect(pinfo["right_child"])

    _collect(target_piece)

    # Sort by rank (bytes/control first with rank -1, then by merge order)
    chain = []
    for piece_str, pinfo in visited.items():
        readable = piece_str.replace("\u2581", " ").strip()
        chain.append({
            "piece": piece_str,
            "readable": readable,
            "rank": pinfo["rank"],
            "byte_length": len(piece_str.replace("\u2581", " ").encode("utf-8")),
            "type": pinfo["type"],
        })

    chain.sort(key=lambda x: (x["rank"] if x["rank"] >= 0 else -1))

    # Assign merge_step (0-indexed from first non-byte)
    for i, entry in enumerate(chain):
        entry["merge_step"] = i

    return chain


def load_scored_candidates(scored_path: str) -> dict:
    """Load scored candidates into a dict keyed by piece string."""
    scored = {}
    with open(scored_path, "r", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            scored[c["piece"]] = c
    print(f"Loaded {len(scored)} scored candidates")
    return scored


def join_leverage(chain: list[dict], scored: dict) -> list[dict]:
    """
    Join a merge chain with leverage scores from scored candidates.
    Marks entries as gaps if no score is available.
    """
    for entry in chain:
        sc = scored.get(entry["piece"])
        if sc and sc["ablation_leverage"] != 0.0:
            entry["leverage"] = sc["ablation_leverage"]
            entry["leverage_ci_low"] = sc.get("leverage_ci_low", 0.0)
            entry["leverage_ci_high"] = sc.get("leverage_ci_high", 0.0)
            entry["leverage_std"] = sc.get("leverage_std", 0.0)
            entry["n_contexts"] = sc.get("n_contexts_sampled", 0)
            entry["is_gap"] = False
        elif entry["type"] in ("byte", "char"):
            # Byte/char tokens have no leverage (they're the base units)
            entry["leverage"] = None
            entry["leverage_ci_low"] = None
            entry["leverage_ci_high"] = None
            entry["leverage_std"] = None
            entry["n_contexts"] = 0
            entry["is_gap"] = False
        else:
            entry["leverage"] = None
            entry["leverage_ci_low"] = None
            entry["leverage_ci_high"] = None
            entry["leverage_std"] = None
            entry["n_contexts"] = 0
            entry["is_gap"] = True

    return chain


def score_missing_intermediates(
    chains: dict[str, list[dict]],
    model_path: str,
    reference_model: str,
    corpus_dir: str,
    base_tokenizer: str,
    device: str,
    K: int,
    contexts_per_candidate: int,
    batch_size: int,
):
    """
    Score intermediates that are missing from candidates_scored.jsonl.
    Modifies chains in-place, filling in leverage values for gaps.
    """
    # Collect all unique gaps across all chains
    gaps = {}
    for target, chain in chains.items():
        for entry in chain:
            if entry["is_gap"]:
                gaps[entry["piece"]] = entry["readable"]

    if not gaps:
        print("No gaps to score.")
        return

    print(f"\nScoring {len(gaps)} missing intermediates...")

    # Import scoring infrastructure from score_leverage.py
    sys.path.insert(0, str(Path(__file__).parent))
    from score_leverage import (
        compute_leverage_batched,
        find_contexts,
        load_corpus_text,
        load_reference_model,
    )

    model, tokenizer = load_reference_model(reference_model, device)
    corpus_text = load_corpus_text(
        Path(corpus_dir), base_tokenizer, max_shards=2,
    )

    # Score each gap
    scored_gaps = {}
    for i, (piece_str, readable) in enumerate(gaps.items()):
        target = readable if readable else piece_str.replace("\u2581", " ").strip()
        if not target or len(target) < 2:
            scored_gaps[piece_str] = {
                "leverage": 0.0, "ci_low": 0.0, "ci_high": 0.0,
                "std": 0.0, "n_contexts": 0,
            }
            continue

        contexts = find_contexts(corpus_text, target, max_contexts=contexts_per_candidate)
        if len(contexts) < 5:
            print(f"  [{i+1}/{len(gaps)}] {target!r}: only {len(contexts)} contexts, skipping")
            scored_gaps[piece_str] = {
                "leverage": 0.0, "ci_low": 0.0, "ci_high": 0.0,
                "std": 0.0, "n_contexts": len(contexts),
            }
            continue

        leverages = compute_leverage_batched(
            model, tokenizer, contexts, target,
            K=K, device=device, batch_size=batch_size,
        )

        if leverages:
            import numpy as np
            arr = np.array(leverages)
            mean_lev = float(np.mean(arr))
            std_lev = float(np.std(arr))
            ci_half = 1.96 * std_lev / np.sqrt(len(arr))
            scored_gaps[piece_str] = {
                "leverage": mean_lev,
                "ci_low": mean_lev - ci_half,
                "ci_high": mean_lev + ci_half,
                "std": std_lev,
                "n_contexts": len(leverages),
            }
            print(f"  [{i+1}/{len(gaps)}] {target!r}: "
                  f"lev={mean_lev:.4f} +/- {ci_half:.4f} (n={len(leverages)})")
        else:
            scored_gaps[piece_str] = {
                "leverage": 0.0, "ci_low": 0.0, "ci_high": 0.0,
                "std": 0.0, "n_contexts": 0,
            }
            print(f"  [{i+1}/{len(gaps)}] {target!r}: no valid leverages")

    # Fill gaps back into chains
    for target, chain in chains.items():
        for entry in chain:
            if entry["is_gap"] and entry["piece"] in scored_gaps:
                sg = scored_gaps[entry["piece"]]
                entry["leverage"] = sg["leverage"]
                entry["leverage_ci_low"] = sg["ci_low"]
                entry["leverage_ci_high"] = sg["ci_high"]
                entry["leverage_std"] = sg["std"]
                entry["n_contexts"] = sg["n_contexts"]
                entry["is_gap"] = False
                entry["newly_scored"] = True


def select_targets(scored: dict, pieces: dict, top_n: int,
                   target_str: str | None) -> list[str]:
    """
    Select target pieces for crystallization analysis.

    If --targets is provided, use those. Otherwise, pick the top-N scored
    candidates by leverage that have at least 2 merge steps.
    """
    if target_str:
        targets = []
        for t in target_str.split(","):
            t = t.strip()
            # Try with and without SentencePiece prefix.
            # Prefer space-prefixed form (more common in scored data).
            candidates = [f"\u2581{t}", t, t.replace(" ", "\u2581")]
            for c in candidates:
                if c in pieces and pieces[c]["type"] == "normal":
                    targets.append(c)
                    break
            else:
                print(f"  WARNING: target {t!r} not found in model vocabulary")
        return targets

    # Select top-N by leverage, filtering for tokens with merge chains
    ranked = []
    for piece_str, sc in scored.items():
        if sc["ablation_leverage"] <= 0:
            continue
        if piece_str not in pieces:
            continue
        if pieces[piece_str]["type"] != "normal":
            continue
        ranked.append((piece_str, sc["ablation_leverage"]))

    ranked.sort(key=lambda x: -x[1])

    # Filter to tokens that have at least 2 merge steps (non-trivial chains)
    targets = []
    for piece_str, lev in ranked:
        chain = walk_merge_chain(pieces, piece_str)
        normal_steps = [e for e in chain if e["type"] == "normal"]
        if len(normal_steps) >= 2:
            targets.append(piece_str)
        if len(targets) >= top_n:
            break

    return targets


def write_outputs(chains: dict[str, list[dict]], output_path: str):
    """Write JSON and CSV output files."""
    # JSON output
    json_data = {}
    for target, chain in chains.items():
        readable = target.replace("\u2581", " ").strip()
        json_data[readable] = {
            "piece": target,
            "chain": [
                {
                    "piece": e["piece"],
                    "readable": e["readable"],
                    "merge_step": e["merge_step"],
                    "rank": e["rank"],
                    "byte_length": e["byte_length"],
                    "type": e["type"],
                    "leverage": e["leverage"],
                    "leverage_ci_low": e.get("leverage_ci_low"),
                    "leverage_ci_high": e.get("leverage_ci_high"),
                    "leverage_std": e.get("leverage_std"),
                    "n_contexts": e.get("n_contexts", 0),
                    "is_gap": e.get("is_gap", False),
                    "newly_scored": e.get("newly_scored", False),
                }
                for e in chain
            ],
        }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"\nJSON output: {out} ({len(json_data)} chains)")

    # CSV output (flat, for plotting)
    csv_path = out.with_suffix(".csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "target", "merge_step", "piece", "readable", "rank",
            "byte_length", "leverage", "leverage_ci_low", "leverage_ci_high",
            "is_gap",
        ])
        for target, chain in chains.items():
            target_readable = target.replace("\u2581", " ").strip()
            for e in chain:
                if e["type"] in ("byte", "char"):
                    continue  # Skip byte/char-level entries in CSV
                writer.writerow([
                    target_readable,
                    e["merge_step"],
                    e["piece"],
                    e["readable"],
                    e["rank"],
                    e["byte_length"],
                    e["leverage"] if e["leverage"] is not None else "",
                    e.get("leverage_ci_low", "") if e.get("leverage_ci_low") is not None else "",
                    e.get("leverage_ci_high", "") if e.get("leverage_ci_high") is not None else "",
                    e.get("is_gap", False),
                ])
    print(f"CSV output:  {csv_path}")


def print_chain_summary(target: str, chain: list[dict]):
    """Print a human-readable summary of a merge chain."""
    readable = target.replace("\u2581", " ").strip()
    normal_entries = [e for e in chain if e["type"] == "normal"]
    gap_count = sum(1 for e in normal_entries if e.get("is_gap", False))

    parts = []
    for e in normal_entries:
        lev_str = f"{e['leverage']:.3f}" if e["leverage"] is not None else "GAP"
        parts.append(f"{e['readable']}({lev_str})")

    chain_str = " -> ".join(parts)
    gap_str = f"  [{gap_count} gaps]" if gap_count else ""
    print(f"  {readable}: {chain_str}{gap_str}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract crystallization curves from BPE merge tree"
    )
    parser.add_argument("--model", type=str, required=True,
                        help="Path to SentencePiece BPE model (large_bpe.model)")
    parser.add_argument("--scored", type=str, required=True,
                        help="Path to candidates_scored.jsonl")
    parser.add_argument("--output", type=str, default="data/crystallization_curves.json",
                        help="Output JSON path (CSV generated alongside)")
    parser.add_argument("--top-n", type=int, default=50,
                        help="Number of top-leverage tokens to trace (default: 50)")
    parser.add_argument("--targets", type=str, default=None,
                        help="Comma-separated specific tokens to trace (overrides --top-n)")

    # Scoring options (for --score-missing)
    parser.add_argument("--score-missing", action="store_true",
                        help="Score missing intermediates on-the-fly (requires GPU)")
    parser.add_argument("--reference-model", type=str, default="gpt2",
                        help="HuggingFace model for scoring (default: gpt2)")
    parser.add_argument("--corpus-dir", type=str, default=None,
                        help="FineWeb corpus directory (for --score-missing)")
    parser.add_argument("--base-tokenizer", type=str, default=None,
                        help="Base SentencePiece model for corpus decoding")
    parser.add_argument("--device", type=str, default="cuda",
                        help="Device for scoring (default: cuda)")
    parser.add_argument("--K", type=int, default=10,
                        help="Downstream window for leverage (default: 10)")
    parser.add_argument("--contexts-per-candidate", type=int, default=100,
                        help="Contexts per candidate for scoring (default: 100)")
    parser.add_argument("--batch-size", type=int, default=32,
                        help="Batch size for scoring (default: 32)")
    args = parser.parse_args()

    # Validate scoring args
    if args.score_missing:
        if not args.corpus_dir:
            print("ERROR: --corpus-dir required when using --score-missing")
            sys.exit(1)
        if not args.base_tokenizer:
            print("ERROR: --base-tokenizer required when using --score-missing")
            sys.exit(1)

    # Step 1: Reconstruct merge tree
    print("Loading merge tree from SentencePiece model...")
    pieces = load_merge_tree(args.model)

    # Step 2: Load existing scores
    scored = load_scored_candidates(args.scored)

    # Step 3: Select targets
    print(f"\nSelecting targets...")
    targets = select_targets(scored, pieces, args.top_n, args.targets)
    print(f"Selected {len(targets)} targets")

    # Step 4: Walk merge chains and join with leverage
    print(f"\nExtracting merge chains...")
    chains = {}
    total_gaps = 0
    for target in targets:
        chain = walk_merge_chain(pieces, target)
        chain = join_leverage(chain, scored)
        chains[target] = chain
        gap_count = sum(1 for e in chain if e.get("is_gap", False))
        total_gaps += gap_count

    # Print summaries
    print(f"\nChain summaries ({total_gaps} total gaps):")
    for target, chain in chains.items():
        print_chain_summary(target, chain)

    # Step 5: Score missing intermediates
    if args.score_missing and total_gaps > 0:
        score_missing_intermediates(
            chains,
            model_path=args.model,
            reference_model=args.reference_model,
            corpus_dir=args.corpus_dir,
            base_tokenizer=args.base_tokenizer,
            device=args.device,
            K=args.K,
            contexts_per_candidate=args.contexts_per_candidate,
            batch_size=args.batch_size,
        )

        # Reprint summaries after scoring
        remaining_gaps = sum(
            1 for chain in chains.values()
            for e in chain if e.get("is_gap", False)
        )
        print(f"\nAfter scoring: {remaining_gaps} gaps remaining")
        for target, chain in chains.items():
            print_chain_summary(target, chain)

    elif total_gaps > 0 and not args.score_missing:
        print(f"\n  Hint: use --score-missing to fill {total_gaps} gaps on-the-fly")

    # Step 6: Write outputs
    write_outputs(chains, args.output)

    # Summary stats
    all_normal = [
        e for chain in chains.values() for e in chain if e["type"] == "normal"
    ]
    with_leverage = [e for e in all_normal if e["leverage"] is not None]
    print(f"\nSummary:")
    print(f"  Chains: {len(chains)}")
    print(f"  Total intermediates: {len(all_normal)}")
    print(f"  With leverage: {len(with_leverage)}")
    print(f"  Gaps: {len(all_normal) - len(with_leverage)}")

    # Compute delta-leverage stats across all chains
    if with_leverage:
        max_delta = 0.0
        max_delta_pair = ("", "")
        for target, chain in chains.items():
            normal = [e for e in chain if e["type"] == "normal" and e["leverage"] is not None]
            for i in range(1, len(normal)):
                delta = normal[i]["leverage"] - normal[i-1]["leverage"]
                if delta > max_delta:
                    max_delta = delta
                    max_delta_pair = (normal[i-1]["readable"], normal[i]["readable"])

        print(f"  Largest leverage jump: +{max_delta:.3f} "
              f"({max_delta_pair[0]!r} → {max_delta_pair[1]!r})")


if __name__ == "__main__":
    main()
