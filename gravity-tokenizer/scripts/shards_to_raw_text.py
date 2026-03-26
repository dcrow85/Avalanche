"""
Decode Parameter Golf binary shards back to raw UTF-8 text for JIT tokenization.

This is the Phase 1 bridge from the static pretokenized pipeline to the dynamic
raw-text training path. Each output shard preserves the original train/val split
and basename, but writes decoded text instead of uint16 token ids.

Examples:
    python scripts/shards_to_raw_text.py ^
        --input-dir ./parameter-golf/data/datasets/fineweb_gravity_beta_1.0 ^
        --tokenizer ./parameter-golf/data/tokenizers/gravity_beta_1.0.model ^
        --output-dir ./parameter-golf/data/raw_text/fineweb_gravity_beta_1.0 ^
        --compress gzip
"""

from __future__ import annotations

import argparse
import gzip
from pathlib import Path

import numpy as np
import sentencepiece as spm


SHARD_MAGIC = 20240520
HEADER_INTS = 256


def load_shard_tokens(path: Path) -> np.ndarray:
    header = np.fromfile(path, dtype="<i4", count=HEADER_INTS)
    if header.size != HEADER_INTS or int(header[0]) != SHARD_MAGIC:
        raise ValueError(f"Bad shard header: {path}")
    num_tokens = int(header[2])
    header_bytes = HEADER_INTS * np.dtype("<i4").itemsize
    return np.fromfile(path, dtype="<u2", count=num_tokens, offset=header_bytes)


def decode_shard_to_text(shard_path: Path, sp: spm.SentencePieceProcessor) -> str:
    token_ids = load_shard_tokens(shard_path)
    chunk_size = 100_000
    text_parts = []
    for i in range(0, len(token_ids), chunk_size):
        text_parts.append(sp.decode(token_ids[i : i + chunk_size].tolist()))
    return "".join(text_parts)


def output_path_for(path: Path, output_dir: Path, compress: str) -> Path:
    base = path.stem
    if compress == "none":
        return output_dir / f"{base}.txt"
    if compress == "gzip":
        return output_dir / f"{base}.txt.gz"
    if compress == "zstd":
        return output_dir / f"{base}.txt.zst"
    raise ValueError(f"Unsupported compression mode: {compress}")


def write_text(path: Path, text: str, compress: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compress == "none":
        path.write_text(text, encoding="utf-8")
        return
    if compress == "gzip":
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write(text)
        return
    if compress == "zstd":
        try:
            import zstandard as zstd
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Compression mode 'zstd' requires the optional 'zstandard' package."
            ) from exc
        cctx = zstd.ZstdCompressor(level=3)
        with open(path, "wb") as f:
            f.write(cctx.compress(text.encode("utf-8")))
        return
    raise ValueError(f"Unsupported compression mode: {compress}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Decode binary FineWeb shards back to raw text")
    parser.add_argument("--input-dir", required=True, help="Directory containing fineweb_train_*.bin / fineweb_val_*.bin")
    parser.add_argument("--tokenizer", required=True, help="SentencePiece model used to decode the binary shards")
    parser.add_argument("--output-dir", required=True, help="Destination directory for raw text shards")
    parser.add_argument("--compress", default="gzip", choices=("none", "gzip", "zstd"))
    parser.add_argument("--max-train-shards", type=int, default=0, help="Optional cap on train shards to export")
    parser.add_argument("--max-val-shards", type=int, default=0, help="Optional cap on val shards to export")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    sp = spm.SentencePieceProcessor(model_file=args.tokenizer)

    train_shards = sorted(input_dir.glob("fineweb_train_*.bin"))
    val_shards = sorted(input_dir.glob("fineweb_val_*.bin"))
    if args.max_train_shards > 0:
        train_shards = train_shards[: args.max_train_shards]
    if args.max_val_shards > 0:
        val_shards = val_shards[: args.max_val_shards]

    if not train_shards and not val_shards:
        raise FileNotFoundError(f"No FineWeb shard files found in {input_dir}")

    print(f"Decoding {len(train_shards)} train shards and {len(val_shards)} val shards")
    print(f"Output directory: {output_dir}")
    print(f"Compression: {args.compress}")

    for shard_path in train_shards + val_shards:
        text = decode_shard_to_text(shard_path, sp)
        output_path = output_path_for(shard_path, output_dir, args.compress)
        write_text(output_path, text, args.compress)
        print(f"{shard_path.name} -> {output_path.name} ({len(text.encode('utf-8')):,} bytes utf-8)")


if __name__ == "__main__":
    main()
