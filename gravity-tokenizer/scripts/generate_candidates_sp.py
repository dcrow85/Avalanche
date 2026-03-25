"""
Generate BPE candidate pool using SentencePiece.

Trains a larger SentencePiece BPE model (8256 tokens) on FineWeb raw text
to discover the full set of candidate merges. Then exports all non-byte
tokens as the candidate pool for gravity scoring.

This is much faster than running BPE from scratch in Python.

Usage:
    python scripts/generate_candidates_sp.py \
        --tokenizer ./parameter-golf/data/tokenizers/fineweb_1024_bpe.model \
        --data-dir ./parameter-golf/data/datasets/fineweb10B_sp1024 \
        --output data/candidates.jsonl \
        --vocab-size 8256
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import sentencepiece as spm
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


def decode_shard_to_text(shard_path: Path, sp: spm.SentencePieceProcessor,
                         max_tokens: int = 10_000_000) -> str:
    """Decode a tokenized shard back to raw text using SentencePiece."""
    token_ids = load_shard_tokens(shard_path)
    token_ids = token_ids[:max_tokens]

    # Decode in chunks to avoid memory issues
    chunk_size = 100_000
    text_parts = []
    for i in range(0, len(token_ids), chunk_size):
        chunk = token_ids[i:i + chunk_size].tolist()
        text_parts.append(sp.decode(chunk))

    return "".join(text_parts)


def train_large_bpe(text_file: Path, vocab_size: int, output_prefix: str) -> str:
    """Train a SentencePiece BPE model with a large vocabulary."""
    model_path = f"{output_prefix}.model"

    spm.SentencePieceTrainer.train(
        input=str(text_file),
        model_prefix=output_prefix,
        vocab_size=vocab_size,
        model_type="bpe",
        character_coverage=1.0,
        byte_fallback=True,
        normalization_rule_name="identity",
        max_sentence_length=16384,
        num_threads=8,
        train_extremely_large_corpus=False,
    )

    return model_path


def extract_candidates(sp_large: spm.SentencePieceProcessor,
                       sp_base: spm.SentencePieceProcessor,
                       raw_text: str) -> list[dict]:
    """Extract non-byte tokens from the large BPE model as candidates."""
    candidates = []

    # Get all tokens from the large model
    for i in range(sp_large.vocab_size()):
        if sp_large.is_byte(i) or sp_large.is_control(i) or sp_large.is_unknown(i):
            continue

        piece = sp_large.id_to_piece(i)
        score = sp_large.get_score(i)

        # Decode to readable string
        readable = piece.replace("\u2581", " ")

        # Get the raw bytes
        try:
            raw_bytes = readable.encode("utf-8")
        except Exception:
            raw_bytes = piece.encode("utf-8", errors="replace")

        # Check if this token is in the base (1024) vocabulary
        in_base_vocab = False
        for j in range(sp_base.vocab_size()):
            if not sp_base.is_byte(j) and not sp_base.is_control(j):
                if sp_base.id_to_piece(j) == piece:
                    in_base_vocab = True
                    break

        candidates.append({
            "token_id_in_large": i,
            "piece": piece,
            "readable": readable.strip(),
            "token_bytes": list(raw_bytes),
            "byte_length": len(raw_bytes),
            "sp_score": float(score),
            "in_base_vocab": in_base_vocab,
            "merge_rank": i - 259 if i >= 260 else -1,  # Approximate rank
        })

    return candidates


def count_frequencies(candidates: list[dict], raw_text: str) -> list[dict]:
    """Count how often each candidate's string appears in the raw text."""
    print("Counting candidate frequencies in corpus...")
    for c in tqdm(candidates):
        readable = c["readable"]
        if readable:
            c["corpus_frequency"] = raw_text.count(readable)
        else:
            c["corpus_frequency"] = 0
    return candidates


def main():
    parser = argparse.ArgumentParser(
        description="Generate BPE candidate pool using SentencePiece"
    )
    parser.add_argument("--tokenizer", type=str, required=True,
                        help="Path to base SentencePiece model (1024 vocab)")
    parser.add_argument("--data-dir", type=str, required=True,
                        help="Directory containing fineweb training shards")
    parser.add_argument("--output", type=str, default="data/candidates.jsonl",
                        help="Output JSONL file")
    parser.add_argument("--vocab-size", type=int, default=8256,
                        help="Target vocabulary size for extended BPE (default: 8256 = 256 bytes + 8000 merges)")
    parser.add_argument("--max-shards", type=int, default=3,
                        help="Max training shards to decode (for speed)")
    parser.add_argument("--max-tokens-per-shard", type=int, default=10_000_000,
                        help="Max tokens to decode per shard")
    args = parser.parse_args()

    # Load base tokenizer
    sp_base = spm.SentencePieceProcessor(model_file=args.tokenizer)
    print(f"Base tokenizer: {args.tokenizer} (vocab: {sp_base.vocab_size()})")

    # Decode shards to raw text
    data_dir = Path(args.data_dir)
    shard_files = sorted(data_dir.glob("fineweb_train_*.bin"))[:args.max_shards]

    if not shard_files:
        print(f"No training shards found in {data_dir}")
        sys.exit(1)

    print(f"\nDecoding {len(shard_files)} shards to raw text...")
    raw_text_parts = []
    for shard_path in shard_files:
        print(f"  Decoding: {shard_path.name}")
        text = decode_shard_to_text(shard_path, sp_base, args.max_tokens_per_shard)
        raw_text_parts.append(text)
        print(f"    -> {len(text):,} characters")

    raw_text = "\n".join(raw_text_parts)
    print(f"Total raw text: {len(raw_text):,} characters")

    # Write raw text to temp file for SentencePiece training
    # Split into lines of max ~4000 chars (SP max_sentence_length is 16384)
    # Split on sentence boundaries where possible, fall back to whitespace
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        line_count = 0
        for part in raw_text_parts:
            # Split on newlines first, then on periods for long segments
            segments = part.split("\n")
            for seg in segments:
                if len(seg) <= 4000:
                    if seg.strip():
                        f.write(seg.strip() + "\n")
                        line_count += 1
                else:
                    # Split long segments on ". " boundaries
                    sentences = seg.split(". ")
                    current_line = ""
                    for sent in sentences:
                        if len(current_line) + len(sent) + 2 > 4000:
                            if current_line.strip():
                                f.write(current_line.strip() + "\n")
                                line_count += 1
                            current_line = sent + ". "
                        else:
                            current_line += sent + ". "
                    if current_line.strip():
                        f.write(current_line.strip() + "\n")
                        line_count += 1
        text_file = Path(f.name)
    print(f"Raw text written to: {text_file} ({line_count:,} lines)")

    # Train large BPE model
    output_dir = Path(args.output).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    model_prefix = str(output_dir / "large_bpe")

    print(f"\nTraining SentencePiece BPE with vocab_size={args.vocab_size}...")
    model_path = train_large_bpe(text_file, args.vocab_size, model_prefix)
    print(f"Model saved to: {model_path}")

    # Load large model and extract candidates
    sp_large = spm.SentencePieceProcessor(model_file=model_path)
    print(f"Large model vocab size: {sp_large.vocab_size()}")

    candidates = extract_candidates(sp_large, sp_base, raw_text)
    print(f"Extracted {len(candidates)} candidates")

    # Count frequencies
    candidates = count_frequencies(candidates, raw_text)

    # Sort by frequency
    candidates.sort(key=lambda x: -x["corpus_frequency"])

    # Write output
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(candidates)} candidates to {output_path}")

    # Summary stats
    in_base = sum(1 for c in candidates if c["in_base_vocab"])
    new_tokens = sum(1 for c in candidates if not c["in_base_vocab"])
    print(f"  In base vocab (1024): {in_base}")
    print(f"  New candidates: {new_tokens}")
    print(f"\nTop 30 candidates by frequency:")
    for c in candidates[:30]:
        base_marker = "*" if c["in_base_vocab"] else " "
        print(f"  {base_marker} freq={c['corpus_frequency']:>10,}  "
              f"bytes={c['byte_length']}  {c['readable']!r}")

    # Clean up
    text_file.unlink(missing_ok=True)
    print("\nDone.")


if __name__ == "__main__":
    main()
