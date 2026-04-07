"""
Compute byte-level top1 successor fraction per merge candidate.

For each candidate substring s, scan the source corpus (decoded back to raw text
from BPE shards) and count which BYTE most often immediately follows each
occurrence of s. Output: per-candidate {n_occurrences, top1_successor_byte,
top1_successor_frac}.

This is the model-free parasitism filter for Gravity Tokenizer v2. A candidate
with top1_successor_frac > THRESHOLD is a hostage pointer (e.g. 'produ' -> 'c'),
not a semantic unit, and v2 vetoes it before leverage scoring.

Usage:
    python scripts/compute_candidate_successor_stats.py \
        --candidates data/candidates_scored.jsonl \
        --bpe-model parameter-golf/data/tokenizers/fineweb_1024_bpe.model \
        --shard-dir parameter-golf/data/datasets/fineweb10B_sp1024 \
        --num-shards 3 \
        --output data/candidates_successor_stats.jsonl
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import sentencepiece as spm
import ahocorasick

SHARD_MAGIC = 20240520
HEADER_INTS = 256


def load_shard_tokens(path: Path) -> np.ndarray:
    header = np.fromfile(path, dtype="<i4", count=256)
    if header.size != 256 or int(header[0]) != SHARD_MAGIC:
        raise ValueError(f"Bad shard header: {path}")
    num_tokens = int(header[2])
    return np.fromfile(path, dtype="<u2", count=num_tokens, offset=HEADER_INTS * 4)


def decode_shard_to_text(shard_path: Path, sp: spm.SentencePieceProcessor,
                         chunk_size: int = 200_000) -> str:
    """Decode a tokenized shard back to a Unicode text string."""
    token_ids = load_shard_tokens(shard_path)
    parts = []
    for i in range(0, len(token_ids), chunk_size):
        chunk = token_ids[i:i + chunk_size].tolist()
        parts.append(sp.decode(chunk))
    return "".join(parts)


def candidate_to_pattern(piece: str) -> str:
    """Decode a SentencePiece piece to its raw text representation.
    SentencePiece uses U+2581 (LOWER ONE EIGHTH BLOCK) as a leading-space marker.

    Returns a Unicode string. For ASCII patterns (the vast majority of gravity
    candidates), Unicode-char-level scanning is identical to byte-level. For
    the handful of non-ASCII patterns (smart quotes, em-dash), char-level is a
    cleaner unit than splitting them at byte boundaries.
    """
    return piece.replace("\u2581", " ")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--bpe-model", required=True)
    parser.add_argument("--shard-dir", required=True)
    parser.add_argument("--num-shards", type=int, default=3)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    # Load candidates
    candidates = []
    with open(args.candidates, encoding="utf-8") as f:
        for line in f:
            candidates.append(json.loads(line))
    print(f"Loaded {len(candidates)} candidates")

    # Build pattern->candidate index
    # Multiple candidates with the same byte pattern are unlikely but possible;
    # group them and emit one stats record per unique pattern.
    pattern_to_indices = defaultdict(list)
    for i, c in enumerate(candidates):
        pat = candidate_to_pattern(c["piece"])
        if not pat:
            continue
        pattern_to_indices[pat].append(i)
    print(f"Unique byte patterns: {len(pattern_to_indices)}")

    # Build Aho-Corasick automaton over byte patterns.
    # pyahocorasick supports bytes patterns via add_word with bytes objects when
    # the Automaton is created with key_type=ahocorasick.KEY_SEQUENCE; but the
    # simpler path is STORE_ANY + bytes. Verify by smoke test.
    A = ahocorasick.Automaton()
    pattern_id_for = {}
    for pid, pat in enumerate(pattern_to_indices.keys()):
        A.add_word(pat, (pid, pat))
        pattern_id_for[pat] = pid
    A.make_automaton()
    print(f"Automaton built ({A.kind})")

    # Counters per pattern: (occurrences, Counter of next byte)
    occ_count = [0] * len(pattern_to_indices)
    next_byte = [Counter() for _ in range(len(pattern_to_indices))]

    sp = spm.SentencePieceProcessor(model_file=args.bpe_model)

    shard_dir = Path(args.shard_dir)
    train_shards = sorted(shard_dir.glob("fineweb_train_*.bin"))[: args.num_shards]
    if not train_shards:
        raise SystemExit("No train shards found")
    print(f"Scanning {len(train_shards)} shard(s)")

    total_chars_scanned = 0
    for sp_path in train_shards:
        print(f"  Decoding {sp_path.name} ...", flush=True)
        text = decode_shard_to_text(sp_path, sp)
        total_chars_scanned += len(text)
        print(f"    {len(text):,} chars; running Aho-Corasick ...", flush=True)

        n_text = len(text)
        match_count = 0
        # iter yields (end_index, value) where end_index is the index of the LAST
        # matching char (inclusive). next position is end_index + 1.
        for end_index, (pid, pat) in A.iter(text):
            occ_count[pid] += 1
            nxt_pos = end_index + 1
            if nxt_pos < n_text:
                next_byte[pid][text[nxt_pos]] += 1
            match_count += 1
        print(f"    {match_count:,} matches", flush=True)

    print(f"\nTotal chars scanned: {total_chars_scanned:,}")

    # Emit per-candidate stats
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_written = 0
    with open(out_path, "w", encoding="utf-8") as out:
        for pat, idxs in pattern_to_indices.items():
            pid = pattern_id_for[pat]
            n_occ = occ_count[pid]
            ctr = next_byte[pid]
            n_with_succ = sum(ctr.values())
            if n_with_succ > 0:
                top_char, top_count = ctr.most_common(1)[0]
                top1_frac = top_count / n_with_succ
                top3 = ctr.most_common(3)
                top3_frac = sum(c for _, c in top3) / n_with_succ
            else:
                top_char, top_count = None, 0
                top1_frac = 0.0
                top3_frac = 0.0
            for idx in idxs:
                c = candidates[idx]
                rec = {
                    "piece": c["piece"],
                    "readable": c.get("readable", ""),
                    "corpus_frequency": c.get("corpus_frequency", 0),
                    "ablation_leverage": c.get("ablation_leverage", 0.0),
                    "byte_occurrences": n_occ,
                    "byte_with_successor": n_with_succ,
                    "top1_successor_char": top_char,
                    "top1_successor_frac": top1_frac,
                    "top3_successor_frac": top3_frac,
                }
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_written += 1
    print(f"Wrote {n_written} records to {out_path}")


if __name__ == "__main__":
    main()
