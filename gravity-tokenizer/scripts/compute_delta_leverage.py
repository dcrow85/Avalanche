"""
Compute the Discrete Derivative of Leverage along the BPE merge tree.

For each scored candidate token T formed by merging children L + R:
    ΔLev(T) = Leverage(T) - Leverage(crystallization_parent)

where the crystallization parent is the child with the higher merge rank
(the more complex child — the last intermediate before T was formed).

If both children are leaf nodes (bytes/chars), ΔLev = absolute leverage.

This replaces static leverage with a differential measure: what we want
is not tokens with high gravity, but tokens where gravity SNAPS into
existence — Prigoginian bifurcation points in the merge tree.

Usage:
    python scripts/compute_delta_leverage.py \
        --model data/large_bpe.model \
        --scored data/candidates_scored.jsonl \
        --output data/candidates_scored_delta.jsonl

    # Then build vocabulary using delta-leverage:
    python scripts/build_vocabulary.py \
        --scored-candidates data/candidates_scored_delta.jsonl \
        --beta 0.3 \
        --output data/vocabularies/ \
        --use-delta-leverage
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np


def load_merge_tree(model_path: str) -> dict:
    """Reconstruct BPE merge tree from SentencePiece model proto."""
    from sentencepiece import sentencepiece_model_pb2 as sp_model

    proto = sp_model.ModelProto()
    with open(model_path, "rb") as f:
        proto.ParseFromString(f.read())

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

    byte_and_control_count = sum(
        1 for p in pieces.values() if p["type"] in ("byte", "control", "unknown")
    )
    for p in pieces.values():
        if p["type"] != "normal":
            p["rank"] = -1
        else:
            piece_str = p["piece"]
            if len(piece_str) == 1 or (len(piece_str) == 2 and piece_str[0] == "\u2581"):
                p["rank"] = -1
                p["type"] = "char"
            else:
                p["rank"] = p["index"] - byte_and_control_count

    merge_pieces = {k: v for k, v in pieces.items() if v["rank"] >= 0}

    for piece_str, pinfo in merge_pieces.items():
        best_split = None
        best_max_rank = float("inf")

        for split_pos in range(1, len(piece_str)):
            left_str = piece_str[:split_pos]
            right_str = piece_str[split_pos:]

            if left_str not in pieces or right_str not in pieces:
                continue

            left_rank = pieces[left_str]["rank"]
            right_rank = pieces[right_str]["rank"]

            if left_rank >= pinfo["rank"] and left_rank != -1:
                continue
            if right_rank >= pinfo["rank"] and right_rank != -1:
                continue

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

    n_resolved = sum(1 for p in merge_pieces.values() if p["left_child"] is not None)
    print(f"Merge tree: {n_resolved}/{len(merge_pieces)} resolved")

    return pieces


def compute_delta_leverage(
    pieces: dict,
    scored_by_piece: dict,
) -> dict:
    """
    Compute ΔLeverage for every scored candidate.

    For token T with children L, R:
      crystallization_parent = argmax(rank(L), rank(R))
                               (the more complex child)
      ΔLev(T) = Lev(T) - Lev(parent)

    If parent is a leaf (byte/char) or has no score: ΔLev = Lev(T).
    Returns dict: piece_string -> {delta_leverage, parent_piece, parent_leverage}
    """
    results = {}

    for piece_str, sc in scored_by_piece.items():
        lev = sc.get("ablation_leverage", 0.0)

        pinfo = pieces.get(piece_str)
        if pinfo is None or pinfo["left_child"] is None:
            # No merge tree entry or unresolved — delta = absolute
            results[piece_str] = {
                "delta_leverage": lev,
                "parent_piece": None,
                "parent_leverage": 0.0,
                "parent_readable": None,
            }
            continue

        left_str = pinfo["left_child"]
        right_str = pinfo["right_child"]

        left_info = pieces[left_str]
        right_info = pieces[right_str]

        # Crystallization parent = the child with higher merge rank
        # (more complex, last intermediate before this token)
        if left_info["rank"] > right_info["rank"]:
            parent_str = left_str
        elif right_info["rank"] > left_info["rank"]:
            parent_str = right_str
        else:
            # Both are leaves (rank -1) or same rank — use whichever is longer
            parent_str = left_str if len(left_str) >= len(right_str) else right_str

        parent_sc = scored_by_piece.get(parent_str)
        if parent_sc and parent_sc.get("ablation_leverage", 0.0) != 0.0:
            parent_lev = parent_sc["ablation_leverage"]
        else:
            parent_lev = 0.0

        parent_readable = parent_str.replace("\u2581", " ").strip()

        results[piece_str] = {
            "delta_leverage": lev - parent_lev,
            "parent_piece": parent_str,
            "parent_leverage": parent_lev,
            "parent_readable": parent_readable,
        }

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Compute discrete derivative of leverage along BPE merge tree"
    )
    parser.add_argument("--model", type=str, required=True,
                        help="SentencePiece BPE model (large_bpe.model)")
    parser.add_argument("--scored", type=str, required=True,
                        help="Scored candidates JSONL")
    parser.add_argument("--output", type=str, required=True,
                        help="Output enriched JSONL with delta_leverage fields")
    args = parser.parse_args()

    # Load merge tree
    print("Loading merge tree...")
    pieces = load_merge_tree(args.model)

    # Load scored candidates
    print("Loading scored candidates...")
    candidates = []
    scored_by_piece = {}
    with open(args.scored, "r", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            candidates.append(c)
            scored_by_piece[c["piece"]] = c
    print(f"  {len(candidates)} candidates loaded")

    # Compute delta-leverage
    print("Computing delta-leverage...")
    deltas = compute_delta_leverage(pieces, scored_by_piece)

    # Enrich candidates with delta fields
    for c in candidates:
        piece = c["piece"]
        d = deltas.get(piece)
        if d:
            c["delta_leverage"] = d["delta_leverage"]
            c["parent_piece"] = d["parent_piece"]
            c["parent_leverage"] = d["parent_leverage"]
            c["parent_readable"] = d["parent_readable"]
        else:
            c["delta_leverage"] = c.get("ablation_leverage", 0.0)
            c["parent_piece"] = None
            c["parent_leverage"] = 0.0
            c["parent_readable"] = None

    # Write output
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(candidates)} candidates to {out}")

    # Stats
    delta_vals = [c["delta_leverage"] for c in candidates if c["delta_leverage"] != 0.0]
    abs_vals = [c.get("ablation_leverage", 0.0) for c in candidates if c.get("ablation_leverage", 0.0) != 0.0]
    delta_arr = np.array(delta_vals)
    abs_arr = np.array(abs_vals)

    print(f"\nAbsolute leverage distribution ({len(abs_vals)} non-zero):")
    print(f"  mean={np.mean(abs_arr):.4f}  std={np.std(abs_arr):.4f}  "
          f"min={np.min(abs_arr):.4f}  max={np.max(abs_arr):.4f}")

    print(f"\nDelta-leverage distribution ({len(delta_vals)} non-zero):")
    print(f"  mean={np.mean(delta_arr):.4f}  std={np.std(delta_arr):.4f}  "
          f"min={np.min(delta_arr):.4f}  max={np.max(delta_arr):.4f}")
    print(f"  positive: {(delta_arr > 0).sum()}/{len(delta_arr)} "
          f"({100*(delta_arr > 0).sum()/len(delta_arr):.1f}%)")
    print(f"  negative: {(delta_arr < 0).sum()}/{len(delta_arr)} "
          f"({100*(delta_arr < 0).sum()/len(delta_arr):.1f}%)")

    # Rank correlation: does delta-leverage reorder the vocabulary?
    both = [(c.get("ablation_leverage", 0.0), c["delta_leverage"])
            for c in candidates if c.get("ablation_leverage", 0.0) != 0.0]
    if len(both) > 10:
        from scipy.stats import spearmanr
        abs_ranks, delta_ranks = zip(*both)
        rho, pval = spearmanr(abs_ranks, delta_ranks)
        print(f"\nSpearman correlation (absolute vs delta): rho={rho:.4f}, p={pval:.2e}")
        if rho < 0.85:
            print("  -> Substantial reordering. Delta-leverage selects a different vocabulary.")
        else:
            print("  -> High correlation. Delta and absolute largely agree.")

    # Show top 20 tokens that move most between rankings
    ranked_abs = sorted(candidates, key=lambda c: -c.get("ablation_leverage", 0.0))
    ranked_delta = sorted(candidates, key=lambda c: -c["delta_leverage"])

    abs_rank = {c["piece"]: i for i, c in enumerate(ranked_abs)}
    delta_rank = {c["piece"]: i for i, c in enumerate(ranked_delta)}

    # Biggest promotions (rank improves under delta)
    promotions = []
    for c in candidates:
        if c.get("ablation_leverage", 0.0) == 0.0:
            continue
        ar = abs_rank[c["piece"]]
        dr = delta_rank[c["piece"]]
        promotions.append((c, ar - dr))  # positive = promoted

    promotions.sort(key=lambda x: -x[1])

    print(f"\nTop 15 promotions (tokens that rise under delta-leverage):")
    for c, shift in promotions[:15]:
        readable = c.get("readable", c["piece"])
        parent = c.get("parent_readable", "?")
        print(f"  {readable!r}: abs_lev={c['ablation_leverage']:.3f}, "
              f"delta={c['delta_leverage']:.3f}, "
              f"parent={parent!r}, "
              f"rank shift +{shift}")

    print(f"\nTop 15 demotions (tokens that fall under delta-leverage):")
    for c, shift in promotions[-15:]:
        readable = c.get("readable", c["piece"])
        parent = c.get("parent_readable", "?")
        print(f"  {readable!r}: abs_lev={c['ablation_leverage']:.3f}, "
              f"delta={c['delta_leverage']:.3f}, "
              f"parent={parent!r}, "
              f"rank shift {shift}")


if __name__ == "__main__":
    main()
