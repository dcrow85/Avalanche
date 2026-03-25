"""
Warm-Start Embedding Fusion for Gravity Tokenizer.

The Semantic Gravity Tokenizer introduces "cold" tokens — new vocabulary entries
whose embeddings start random. This causes a ~2000-step thermodynamic plateau
where the model burns compute assembling the embedding geometry.

This script bypasses the plateau by initializing each gravity token's embedding
as the spatial mean of its BPE decomposition's pre-trained embeddings.

    embedding(partic) = mean(embedding(part), embedding(ic))

For tokens that map 1:1 between BPE and gravity, this is a direct copy.
For promoted tokens, it provides a warm start from the existing latent geometry.

Usage:
    python scripts/warm_start_embeddings.py \
        --bpe-model data/tokenizers/fineweb_1024_bpe.model \
        --gravity-model data/tokenizers/gravity_beta_0.3.model \
        --checkpoint parameter-golf/final_model.pt \
        --output data/warm_embeddings_beta_0.3.pt
"""
import argparse
import json
from pathlib import Path

import sentencepiece as spm
import torch


def build_warm_embeddings(
    bpe_path: str,
    gravity_path: str,
    checkpoint_path: str,
    output_path: str,
    verbose: bool = True,
):
    # Load tokenizers
    bpe = spm.SentencePieceProcessor(model_file=bpe_path)
    grav = spm.SentencePieceProcessor(model_file=gravity_path)

    assert bpe.vocab_size() == grav.vocab_size(), (
        f"Vocab size mismatch: BPE={bpe.vocab_size()}, gravity={grav.vocab_size()}"
    )
    vocab_size = bpe.vocab_size()

    # Load BPE model embeddings
    state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    bpe_embeddings = state["tok_emb.weight"].float()  # [vocab_size, d_model]
    d_model = bpe_embeddings.shape[1]

    if verbose:
        print(f"BPE embeddings: {bpe_embeddings.shape}")
        print(f"BPE vocab: {vocab_size}, d_model: {d_model}")

    # Build warm-started embedding matrix for gravity tokenizer
    warm_embeddings = torch.zeros(vocab_size, d_model)
    stats = {"direct_copy": 0, "mean_fusion": 0, "byte_fallback": 0, "components": []}

    for grav_id in range(vocab_size):
        grav_piece = grav.id_to_piece(grav_id)

        # Control tokens and byte tokens: check if same piece exists in BPE
        if grav.is_control(grav_id) or grav.is_byte(grav_id):
            # These should map 1:1 by ID (same structure in both tokenizers)
            warm_embeddings[grav_id] = bpe_embeddings[grav_id]
            stats["direct_copy"] += 1
            continue

        # For merge tokens: decode to text, re-encode with BPE, average embeddings
        text = grav.decode([grav_id])
        if not text.strip():
            # Empty decode — use random init (shouldn't happen for real tokens)
            warm_embeddings[grav_id] = bpe_embeddings[grav_id]
            stats["byte_fallback"] += 1
            continue

        bpe_ids = bpe.encode(text)
        if not bpe_ids:
            warm_embeddings[grav_id] = bpe_embeddings[grav_id]
            stats["byte_fallback"] += 1
            continue

        # Average BPE component embeddings
        component_embeddings = bpe_embeddings[bpe_ids]
        warm_embeddings[grav_id] = component_embeddings.mean(dim=0)

        n_components = len(bpe_ids)
        if n_components == 1:
            stats["direct_copy"] += 1
        else:
            stats["mean_fusion"] += 1
            if verbose and n_components >= 2:
                bpe_pieces = [bpe.id_to_piece(i) for i in bpe_ids]
                stats["components"].append(
                    (grav_piece, bpe_pieces, n_components)
                )

    # Convert to bfloat16 to match model dtype
    warm_embeddings = warm_embeddings.bfloat16()

    # Save
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(warm_embeddings, output_path)

    if verbose:
        print(f"\nStats:")
        print(f"  Direct copy (1:1 match): {stats['direct_copy']}")
        print(f"  Mean fusion (multi-component): {stats['mean_fusion']}")
        print(f"  Byte fallback: {stats['byte_fallback']}")
        print(f"\nSample fusions (gravity_piece -> BPE components):")
        for piece, components, n in sorted(stats["components"], key=lambda x: -x[2])[:25]:
            print(f"  {piece:20s} -> {components}")
        print(f"\nSaved warm embeddings to: {output_path}")
        print(f"  Shape: {warm_embeddings.shape}, dtype: {warm_embeddings.dtype}")

    return warm_embeddings, stats


def main():
    parser = argparse.ArgumentParser(description="Warm-start gravity embeddings")
    parser.add_argument("--bpe-model", required=True, help="BPE tokenizer model path")
    parser.add_argument("--gravity-model", required=True, help="Gravity tokenizer model path")
    parser.add_argument("--checkpoint", required=True, help="Trained BPE model checkpoint (.pt)")
    parser.add_argument("--output", required=True, help="Output warm embeddings path (.pt)")
    args = parser.parse_args()

    build_warm_embeddings(args.bpe_model, args.gravity_model, args.checkpoint, args.output)


if __name__ == "__main__":
    main()
