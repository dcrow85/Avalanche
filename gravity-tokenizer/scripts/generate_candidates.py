"""
Generate BPE candidate pool for gravity scoring.

Runs BPE merge algorithm on FineWeb corpus to produce 8000 merges (8256 total
vocabulary entries including 256 byte tokens). Outputs candidates.jsonl with
frequency and merge rank for each candidate.

Usage:
    python scripts/generate_candidates.py --data-dir ./parameter-golf/data/datasets/fineweb10B_sp1024 --output candidates.jsonl
"""

import argparse
import json
import struct
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from tqdm import tqdm


def load_shard_tokens(path: Path) -> np.ndarray:
    """Load tokens from a binary shard file (parameter-golf format)."""
    header = np.fromfile(path, dtype="<i4", count=256)
    if header.size != 256 or int(header[0]) != 20240520:
        raise ValueError(f"Bad shard header: {path}")
    num_tokens = int(header[2])
    header_bytes = 256 * np.dtype("<i4").itemsize
    tokens = np.fromfile(path, dtype="<u2", count=num_tokens, offset=header_bytes)
    return tokens


def decode_token_id(token_id: int, sp) -> bytes:
    """Decode a SentencePiece token ID to its byte representation."""
    if sp.is_byte(token_id):
        # Byte tokens: extract the byte value from <0xNN> format
        piece = sp.id_to_piece(token_id)
        hex_str = piece[3:-1]  # strip <0x and >
        return bytes([int(hex_str, 16)])
    elif sp.is_control(token_id) or sp.is_unknown(token_id):
        return b""
    else:
        piece = sp.id_to_piece(token_id)
        # SentencePiece uses \u2581 for space
        piece = piece.replace("\u2581", " ")
        return piece.encode("utf-8")


def run_bpe_on_bytes(byte_sequences: list[bytes], num_merges: int = 8000) -> list[dict]:
    """
    Run BPE merge algorithm on byte sequences.
    Returns a list of merge candidates with frequency and rank.
    """
    # Initialize: each byte is a separate token (represented as a tuple of one byte)
    print("Initializing byte sequences...")
    # Work with sequences of token tuples
    # Each "token" is a tuple of bytes that have been merged
    sequences = []
    for seq in tqdm(byte_sequences, desc="Converting to token sequences"):
        sequences.append(list(seq))  # list of individual bytes

    # Count initial bigram frequencies
    print("Counting initial bigram frequencies...")

    def count_bigrams(seqs):
        counts = Counter()
        for seq in seqs:
            for i in range(len(seq) - 1):
                counts[(seq[i], seq[i + 1])] += 1
        return counts

    bigram_counts = count_bigrams(sequences)

    candidates = []
    # Track the vocabulary: byte values 0-255 are the base
    # Each merge creates a new "token" which is the concatenation of two existing tokens
    token_to_bytes = {}
    for b in range(256):
        token_to_bytes[b] = bytes([b])

    next_token_id = 256

    for merge_idx in tqdm(range(num_merges), desc="Running BPE merges"):
        if not bigram_counts:
            print(f"No more bigrams to merge at step {merge_idx}")
            break

        # Find most frequent bigram
        best_pair = bigram_counts.most_common(1)[0]
        (left, right), freq = best_pair

        if freq < 2:
            print(f"Most frequent bigram has count {freq} at step {merge_idx}, stopping")
            break

        # Record this merge
        left_bytes = token_to_bytes.get(left, bytes([left]) if isinstance(left, int) and left < 256 else b"")
        right_bytes = token_to_bytes.get(right, bytes([right]) if isinstance(right, int) and right < 256 else b"")
        merged_bytes = left_bytes + right_bytes

        token_to_bytes[next_token_id] = merged_bytes

        try:
            token_string = merged_bytes.decode("utf-8", errors="replace")
        except Exception:
            token_string = repr(merged_bytes)

        candidates.append({
            "token_id": next_token_id,
            "token_bytes": list(merged_bytes),
            "token_string": token_string,
            "merge_rank": merge_idx + 1,
            "corpus_frequency": freq,
            "left_token": left,
            "right_token": right,
        })

        # Apply merge to all sequences
        new_token = next_token_id
        next_token_id += 1

        for seq_idx in range(len(sequences)):
            seq = sequences[seq_idx]
            new_seq = []
            i = 0
            while i < len(seq):
                if i < len(seq) - 1 and seq[i] == left and seq[i + 1] == right:
                    new_seq.append(new_token)
                    i += 2
                else:
                    new_seq.append(seq[i])
                    i += 1
            sequences[seq_idx] = new_seq

        # Recount bigrams (incremental would be faster, but this is simpler)
        # For production: use incremental update
        if (merge_idx + 1) % 100 == 0:
            bigram_counts = count_bigrams(sequences)
        else:
            # Incremental: remove old bigrams involving the pair, add new ones
            # This is an approximation; full recount every 100 steps
            bigram_counts = count_bigrams(sequences)

    return candidates


def main():
    parser = argparse.ArgumentParser(description="Generate BPE candidate pool for gravity scoring")
    parser.add_argument("--data-dir", type=str, required=True,
                        help="Directory containing fineweb training shards")
    parser.add_argument("--tokenizer", type=str, default=None,
                        help="Path to SentencePiece model (to decode existing tokens to bytes)")
    parser.add_argument("--output", type=str, default="candidates.jsonl",
                        help="Output JSONL file")
    parser.add_argument("--num-merges", type=int, default=8000,
                        help="Number of BPE merges to run")
    parser.add_argument("--max-shards", type=int, default=3,
                        help="Max training shards to use (for speed)")
    parser.add_argument("--max-bytes", type=int, default=100_000_000,
                        help="Max bytes to process (100MB default)")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    shard_files = sorted(data_dir.glob("fineweb_train_*.bin"))

    if not shard_files:
        print(f"No training shards found in {data_dir}")
        sys.exit(1)

    # Load shards and decode to raw bytes
    if args.tokenizer:
        import sentencepiece as spm
        sp = spm.SentencePieceProcessor(model_file=args.tokenizer)
        print(f"Using tokenizer: {args.tokenizer} (vocab size: {sp.vocab_size()})")

        all_bytes = bytearray()
        for shard_path in shard_files[:args.max_shards]:
            print(f"Loading shard: {shard_path.name}")
            token_ids = load_shard_tokens(shard_path)
            # Decode tokens back to bytes
            for tid in tqdm(token_ids[:5_000_000], desc="Decoding tokens"):
                all_bytes.extend(decode_token_id(int(tid), sp))
            if len(all_bytes) >= args.max_bytes:
                break

        print(f"Total bytes: {len(all_bytes):,}")
    else:
        # If no tokenizer, assume raw byte data or use the raw text
        print("No tokenizer specified. Reading raw data from docs if available.")
        sys.exit(1)

    # Split into chunks for BPE (treat each ~4KB block as a sequence)
    chunk_size = 4096
    byte_data = bytes(all_bytes[:args.max_bytes])
    chunks = [byte_data[i:i+chunk_size] for i in range(0, len(byte_data), chunk_size)]
    print(f"Split into {len(chunks)} chunks of ~{chunk_size} bytes")

    # Run BPE
    candidates = run_bpe_on_bytes(chunks, num_merges=args.num_merges)

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(candidates)} candidates to {output_path}")
    print(f"Top 20 by frequency:")
    for c in sorted(candidates, key=lambda x: -x["corpus_frequency"])[:20]:
        print(f"  rank={c['merge_rank']:4d}  freq={c['corpus_frequency']:10,}  {c['token_string']!r}")


if __name__ == "__main__":
    main()
