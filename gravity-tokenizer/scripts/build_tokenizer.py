"""
Build SentencePiece Unigram tokenizer from a gravity-selected vocabulary.

Takes a vocabulary JSON file (from build_vocabulary.py) and constructs a
SentencePiece model that uses exactly those tokens.

Uses the SentencePiece model proto format to inject a pre-specified vocabulary
into a Unigram model, bypassing the normal EM training process.

Usage:
    python scripts/build_tokenizer.py \
        --vocabulary data/vocabularies/vocabulary_beta_0.3_gamma_0.0.json \
        --output data/tokenizers/gravity_beta_0.3.model \
        --corpus-sample data/corpus_sample.txt
"""

import argparse
import json
import math
import tempfile
from pathlib import Path


def build_unigram_tokenizer(vocab_data: dict, corpus_sample_path: str,
                            output_path: str):
    """
    Build a SentencePiece Unigram tokenizer with a pre-specified vocabulary.

    Strategy: Train a SentencePiece Unigram model with the desired vocab_size,
    then replace its vocabulary with our gravity-selected tokens.
    """
    import sentencepiece as spm

    vocab_size = vocab_data["vocab_size"]
    tokens = vocab_data["tokens"]

    # First, train a dummy Unigram model on the corpus to get proper model structure
    with tempfile.NamedTemporaryFile(suffix=".model", delete=False) as f:
        model_prefix = f.name.replace(".model", "")

    print(f"Training base Unigram model (vocab_size={vocab_size})...")
    spm.SentencePieceTrainer.train(
        input=corpus_sample_path,
        model_prefix=model_prefix,
        vocab_size=vocab_size,
        model_type="unigram",
        character_coverage=1.0,
        byte_fallback=True,
        normalization_rule_name="identity",
        max_sentence_length=16384,
        num_threads=8,
    )

    # Now load the model proto and replace the vocabulary
    from sentencepiece import sentencepiece_model_pb2 as sp_model

    model_proto = sp_model.ModelProto()
    with open(f"{model_prefix}.model", "rb") as f:
        model_proto.ParseFromString(f.read())

    # Clear existing pieces and rebuild with our vocabulary
    # Keep the first few control tokens
    control_pieces = []
    for piece in model_proto.pieces:
        if piece.type in (sp_model.ModelProto.SentencePiece.CONTROL,
                          sp_model.ModelProto.SentencePiece.UNKNOWN):
            control_pieces.append(piece)

    # Clear all pieces
    del model_proto.pieces[:]

    # Re-add control tokens
    for piece in control_pieces:
        new_piece = model_proto.pieces.add()
        new_piece.CopyFrom(piece)

    # Add byte tokens (256 of them)
    for byte_val in range(256):
        piece = model_proto.pieces.add()
        piece.piece = f"<0x{byte_val:02X}>"
        piece.score = 0.0
        piece.type = sp_model.ModelProto.SentencePiece.BYTE

    # Add gravity-selected tokens
    for i, token in enumerate(tokens):
        piece = model_proto.pieces.add()
        piece.piece = token.get("piece", token.get("readable", ""))
        # Score in Unigram model is log probability — use negative log frequency as proxy
        freq = token.get("corpus_frequency", 1)
        piece.score = -math.log(max(freq, 1))
        piece.type = sp_model.ModelProto.SentencePiece.NORMAL

    # Validate total piece count matches expected vocab_size
    total_pieces = len(model_proto.pieces)
    if total_pieces != vocab_size:
        print(f"  WARNING: total pieces ({total_pieces}) != vocab_size ({vocab_size})")
        print(f"    control={len(control_pieces)}, bytes=256, merges={len(tokens)}")
        print(f"    Expected merges: {vocab_size - 256 - len(control_pieces)}")

    # Save the modified model
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(model_proto.SerializeToString())

    print(f"Tokenizer saved to: {output_path}")
    print(f"  Control tokens: {len(control_pieces)}")
    print(f"  Byte tokens: 256")
    print(f"  Merge tokens: {len(tokens)}")
    print(f"  Total: {len(model_proto.pieces)}")

    # Verify
    sp_test = spm.SentencePieceProcessor(model_file=output_path)
    print(f"\nVerification:")
    print(f"  Loaded vocab size: {sp_test.vocab_size()}")

    test_text = "The quick brown fox jumps over the lazy dog."
    encoded = sp_test.encode(test_text)
    decoded = sp_test.decode(encoded)
    print(f"  Test encode: {test_text!r}")
    print(f"    -> {len(encoded)} tokens: {encoded[:20]}...")
    print(f"    -> decoded: {ascii(decoded)}")

    # Measure average token length on a longer text
    test_long = test_text * 100
    encoded_long = sp_test.encode(test_long)
    avg_bytes_per_token = len(test_long.encode("utf-8")) / len(encoded_long)
    print(f"  Avg bytes/token: {avg_bytes_per_token:.2f}")

    return output_path


def main():
    parser = argparse.ArgumentParser(description="Build gravity tokenizer")
    parser.add_argument("--vocabulary", type=str, required=True,
                        help="Vocabulary JSON file from build_vocabulary.py")
    parser.add_argument("--output", type=str, required=True,
                        help="Output SentencePiece model path")
    parser.add_argument("--corpus-sample", type=str, required=True,
                        help="Path to corpus text sample for Unigram training")
    args = parser.parse_args()

    # Load vocabulary
    with open(args.vocabulary, "r", encoding="utf-8") as f:
        vocab_data = json.load(f)

    print(f"Vocabulary: {args.vocabulary}")
    print(f"  Beta: {vocab_data['beta']}")
    print(f"  Vocab size: {vocab_data['vocab_size']}")
    print(f"  Merge tokens: {vocab_data['n_merge_tokens']}")

    build_unigram_tokenizer(vocab_data, args.corpus_sample, args.output)


if __name__ == "__main__":
    main()
