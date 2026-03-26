"""
Time Dilation Probe — Does processing depth correlate with token gravity?

Hypothesis: High-gravity tokens require more layers to resolve. The model
"spends more time" on them. In a transformer, "time" is layer depth.

The "velocity" of a token at layer l is the magnitude of its residual update:
    v_l = ||x_after_layer - x_before_layer||_2

Falsifiable signature:
- Low-gravity byte-gas (th, in) should freeze early (v_l → 0 by layer 3-4)
- High-gravity semantic crystals should remain active through all 12 layers
- The velocity profile correlates with ablation leverage scores

This is the transformer equivalent of gravitational time dilation:
near massive tokens, the residual stream evolves more — local time runs faster.
"""

import io
import math
import os
import sys
import zlib
import json

import torch
import torch.nn.functional as F
from torch import Tensor, nn
import numpy as np

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

import sentencepiece as spm

SCRIPT_DIR = os.path.dirname(__file__)
GOLF_ROOT = os.path.join(SCRIPT_DIR, "..", "parameter-golf")
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")


# ── Model (identical to lensing probe) ──

class CastedLinear(nn.Linear):
    def __init__(self, in_f, out_f, bias=False):
        super().__init__(in_f, out_f, bias=bias)
    def forward(self, x):
        return F.linear(x, self.weight.to(x.dtype),
                        self.bias.to(x.dtype) if self.bias is not None else None)

class RMSNorm(nn.Module):
    def forward(self, x):
        return F.rms_norm(x, (x.size(-1),))

class Rotary(nn.Module):
    def __init__(self, dim, base=10000.0):
        super().__init__()
        self.inv_freq = nn.Parameter(
            1.0 / (base ** (torch.arange(0, dim, 2).float() / dim)),
            requires_grad=False)
        self._seq_len_cached = 0
        self._cos_cached = None
        self._sin_cached = None

    def forward(self, seq_len, device, dtype):
        if seq_len > self._seq_len_cached:
            self._seq_len_cached = seq_len
            t = torch.arange(seq_len, device=device, dtype=self.inv_freq.dtype)
            freqs = torch.outer(t, self.inv_freq.to(device))
            self._cos_cached = freqs.cos()[None, None, :, :]
            self._sin_cached = freqs.sin()[None, None, :, :]
        return self._cos_cached.to(dtype=dtype), self._sin_cached.to(dtype=dtype)

def apply_rotary_emb(x, cos, sin):
    half = x.size(-1) // 2
    x1, x2 = x[..., :half], x[..., half:]
    return torch.cat((x1 * cos + x2 * sin, x1 * (-sin) + x2 * cos), dim=-1)

class CausalSelfAttention(nn.Module):
    def __init__(self, dim, num_heads, num_kv_heads, rope_base, qk_gain_init):
        super().__init__()
        self.num_heads = num_heads
        self.num_kv_heads = num_kv_heads
        self.head_dim = dim // num_heads
        kv_dim = num_kv_heads * self.head_dim
        self.c_q = CastedLinear(dim, dim, bias=False)
        self.c_k = CastedLinear(dim, kv_dim, bias=False)
        self.c_v = CastedLinear(dim, kv_dim, bias=False)
        self.proj = CastedLinear(dim, dim, bias=False)
        self.q_gain = nn.Parameter(torch.full((num_heads,), qk_gain_init, dtype=torch.float32))
        self.rotary = Rotary(self.head_dim, base=rope_base)

    def forward(self, x):
        bsz, seqlen, dim = x.shape
        q = self.c_q(x).reshape(bsz, seqlen, self.num_heads, self.head_dim).transpose(1, 2)
        k = self.c_k(x).reshape(bsz, seqlen, self.num_kv_heads, self.head_dim).transpose(1, 2)
        v = self.c_v(x).reshape(bsz, seqlen, self.num_kv_heads, self.head_dim).transpose(1, 2)
        q = F.rms_norm(q, (q.size(-1),))
        k = F.rms_norm(k, (k.size(-1),))
        cos, sin = self.rotary(seqlen, x.device, q.dtype)
        q = apply_rotary_emb(q, cos, sin)
        k = apply_rotary_emb(k, cos, sin)
        q = q * self.q_gain.to(dtype=q.dtype)[None, :, None, None]

        if self.num_kv_heads < self.num_heads:
            reps = self.num_heads // self.num_kv_heads
            k = k.repeat_interleave(reps, dim=1)
            v = v.repeat_interleave(reps, dim=1)

        y = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        y = y.transpose(1, 2).contiguous().reshape(bsz, seqlen, dim)
        return self.proj(y)

class MLP(nn.Module):
    def __init__(self, dim, mlp_mult):
        super().__init__()
        self.fc = CastedLinear(dim, mlp_mult * dim, bias=False)
        self.proj = CastedLinear(mlp_mult * dim, dim, bias=False)
    def forward(self, x):
        return self.proj(torch.relu(self.fc(x)).square())

class Block(nn.Module):
    def __init__(self, dim, num_heads, num_kv_heads, mlp_mult, rope_base, qk_gain_init):
        super().__init__()
        self.attn_norm = RMSNorm()
        self.mlp_norm = RMSNorm()
        self.attn = CausalSelfAttention(dim, num_heads, num_kv_heads, rope_base, qk_gain_init)
        self.mlp = MLP(dim, mlp_mult)
        self.attn_scale = nn.Parameter(torch.ones(dim, dtype=torch.float32))
        self.mlp_scale = nn.Parameter(torch.ones(dim, dtype=torch.float32))
        self.resid_mix = nn.Parameter(torch.stack((torch.ones(dim), torch.zeros(dim))).float())

    def forward(self, x, x0):
        mix = self.resid_mix.to(dtype=x.dtype)
        x = mix[0][None, None, :] * x + mix[1][None, None, :] * x0
        x = x + self.attn_scale.to(dtype=x.dtype)[None, None, :] * self.attn(self.attn_norm(x))
        x = x + self.mlp_scale.to(dtype=x.dtype)[None, None, :] * self.mlp(self.mlp_norm(x))
        return x

class GPT(nn.Module):
    def __init__(self, vocab_size, num_layers, model_dim, num_heads, num_kv_heads,
                 mlp_mult, tie_embeddings, logit_softcap, rope_base, qk_gain_init):
        super().__init__()
        self.tie_embeddings = tie_embeddings
        self.logit_softcap = logit_softcap
        self.tok_emb = nn.Embedding(vocab_size, model_dim)
        self.num_encoder_layers = num_layers // 2
        self.num_decoder_layers = num_layers - self.num_encoder_layers
        self.num_skip_weights = min(self.num_encoder_layers, self.num_decoder_layers)
        self.skip_weights = nn.Parameter(torch.ones(self.num_skip_weights, model_dim, dtype=torch.float32))
        self.blocks = nn.ModuleList([
            Block(model_dim, num_heads, num_kv_heads, mlp_mult, rope_base, qk_gain_init)
            for _ in range(num_layers)
        ])
        self.final_norm = RMSNorm()
        self.lm_head = None if tie_embeddings else CastedLinear(model_dim, vocab_size, bias=False)

    def forward_with_velocity(self, input_ids):
        """
        Forward pass that captures per-token residual velocity at each layer.

        Velocity = ||x_after_layer - x_before_layer||_2 per token position.
        This measures how much the residual stream changes at each layer —
        the "local time" experienced by each token.
        """
        x = self.tok_emb(input_ids)
        x = F.rms_norm(x, (x.size(-1),))
        x0 = x.clone()

        velocities = []  # [num_layers, seq_len]
        attn_velocities = []  # attention-only contribution
        mlp_velocities = []  # MLP-only contribution

        skips = []

        # Encoder layers
        for i in range(self.num_encoder_layers):
            x_before = x.clone()
            x = self.blocks[i](x, x0)

            # Per-token velocity: L2 norm of residual update
            delta = x - x_before  # [1, seq_len, dim]
            vel = delta[0].norm(dim=-1)  # [seq_len]
            velocities.append(vel.detach().cpu())

            skips.append(x)

        # Decoder layers (with skip connections)
        for i in range(self.num_decoder_layers):
            x_before = x.clone()

            if skips:
                x = x + self.skip_weights[i].to(dtype=x.dtype)[None, None, :] * skips.pop()

            x = self.blocks[self.num_encoder_layers + i](x, x0)

            # Velocity includes the skip connection contribution
            delta = x - x_before
            vel = delta[0].norm(dim=-1)
            velocities.append(vel.detach().cpu())

        x = self.final_norm(x)
        if self.tie_embeddings:
            logits = F.linear(x, self.tok_emb.weight)
        else:
            logits = self.lm_head(x)
        logits = self.logit_softcap * torch.tanh(logits / self.logit_softcap)

        # Stack: [num_layers, seq_len]
        velocity_map = torch.stack(velocities)
        return logits, velocity_map

    def forward_with_decomposed_velocity(self, input_ids):
        """
        Forward pass that decomposes velocity into attention and MLP contributions.
        Slower (extra forward passes per block) but reveals which mechanism drives activity.
        """
        x = self.tok_emb(input_ids)
        x = F.rms_norm(x, (x.size(-1),))
        x0 = x.clone()

        total_vel = []
        attn_vel = []
        mlp_vel = []

        skips = []

        for layer_idx in range(len(self.blocks)):
            block = self.blocks[layer_idx]

            # Handle skip connections for decoder layers
            if layer_idx >= self.num_encoder_layers:
                dec_idx = layer_idx - self.num_encoder_layers
                if dec_idx < len(skips):
                    skip_val = skips[-(dec_idx + 1)]  # pop from end
                    x = x + self.skip_weights[dec_idx].to(dtype=x.dtype)[None, None, :] * skip_val

            x_in = x.clone()

            # Apply resid_mix
            mix = block.resid_mix.to(dtype=x.dtype)
            x_mixed = mix[0][None, None, :] * x + mix[1][None, None, :] * x0

            # Attention contribution
            attn_out = block.attn_scale.to(dtype=x.dtype)[None, None, :] * block.attn(block.attn_norm(x_mixed))

            # MLP contribution
            x_after_attn = x_mixed + attn_out
            mlp_out = block.mlp_scale.to(dtype=x.dtype)[None, None, :] * block.mlp(block.mlp_norm(x_after_attn))

            # Full output
            x = x_after_attn + mlp_out

            # Store encoder outputs for skip connections
            if layer_idx < self.num_encoder_layers:
                skips.append(x)

            # Velocities
            total_delta = x - x_in
            total_vel.append(total_delta[0].norm(dim=-1).detach().cpu())
            attn_vel.append(attn_out[0].norm(dim=-1).detach().cpu())
            mlp_vel.append(mlp_out[0].norm(dim=-1).detach().cpu())

        return (torch.stack(total_vel),
                torch.stack(attn_vel),
                torch.stack(mlp_vel))


def dequantize_state_dict_int8(obj):
    out = {}
    qmeta = obj.get("qmeta", {})
    for name, q in obj["quantized"].items():
        dtype = getattr(torch, obj["dtypes"][name])
        s = obj["scales"][name]
        if qmeta.get(name, {}).get("scheme") == "per_row" or s.ndim > 0:
            s = s.to(dtype=torch.float32)
            out[name] = (q.float() * s.view(q.shape[0], *([1] * (q.ndim - 1)))).to(dtype=dtype).contiguous()
        else:
            out[name] = (q.float() * float(s.item())).to(dtype=dtype).contiguous()
    for name, t in obj["passthrough"].items():
        out_t = t.detach().to("cpu").contiguous()
        orig_dtype = obj.get("passthrough_orig_dtypes", {}).get(name)
        if isinstance(orig_dtype, str):
            out_t = out_t.to(dtype=getattr(torch, orig_dtype)).contiguous()
        out[name] = out_t
    return out


def load_model(checkpoint_path, tokenizer_path, num_layers=12, device="cuda"):
    sp = spm.SentencePieceProcessor(model_file=tokenizer_path)
    model = GPT(
        vocab_size=1024, num_layers=num_layers, model_dim=384,
        num_heads=6, num_kv_heads=2, mlp_mult=3,
        tie_embeddings=True, logit_softcap=30.0,
        rope_base=10000.0, qk_gain_init=1.5,
    )
    with open(checkpoint_path, "rb") as f:
        quant_blob = f.read()
    quant_state = torch.load(io.BytesIO(zlib.decompress(quant_blob)),
                             map_location="cpu", weights_only=True)
    state_dict = dequantize_state_dict_int8(quant_state)
    model.load_state_dict(state_dict, strict=False)
    model = model.to(device).eval()
    return model, sp


def load_leverage_scores():
    """Load ablation leverage scores for token labeling."""
    scored_path = os.path.join(DATA_DIR, "candidates_scored.jsonl")
    leverage_map = {}
    if os.path.exists(scored_path):
        with open(scored_path, "r", encoding="utf-8") as f:
            for line in f:
                c = json.loads(line)
                if c.get("ablation_leverage", 0) != 0:
                    leverage_map[c["readable"]] = c["ablation_leverage"]
    return leverage_map


@torch.no_grad()
def run_time_dilation_probe(model, sp, device="cuda"):
    """
    Run the time dilation experiment on multiple sentences.
    Measures per-token residual velocity across all 12 layers.
    """
    leverage_map = load_leverage_scores()
    print(f"Loaded {len(leverage_map)} leverage scores\n")

    # Test sentences designed to mix high-gravity crystals with byte-gas
    sentences = [
        "The water because caused the damage to the building",
        "Every country should understand the importance of education",
        "The government announced a new policy for economic development",
        "Children can help if they first understand the problem",
    ]

    all_results = []

    for sent in sentences:
        print(f"\n{'='*70}")
        print(f"Sentence: {sent!r}")
        print(f"{'='*70}")

        ids = sp.encode(sent)
        pieces = [sp.id_to_piece(i) for i in ids]

        # Classify each token
        token_info = []
        for idx, (tid, piece) in enumerate(zip(ids, pieces)):
            is_byte = tid < 256 or (piece.startswith('<0x') and piece.endswith('>'))

            # Look up leverage
            readable = piece.replace('\u2581', ' ').strip()
            lev = leverage_map.get(readable, leverage_map.get(piece, None))

            # Also try without space prefix
            if lev is None and piece.startswith('\u2581'):
                lev = leverage_map.get(piece[1:], None)

            token_info.append({
                'idx': idx,
                'id': tid,
                'piece': piece,
                'readable': readable,
                'is_byte': is_byte,
                'leverage': lev,
            })

            lev_str = f"  lev={lev:.3f}" if lev is not None else "  lev=?"
            byte_str = " [BYTE]" if is_byte else ""
            print(f"  [{idx:2d}] {piece:15s} (id={tid:4d}){byte_str}{lev_str}")

        # Reset rotary caches
        for block in model.blocks:
            block.attn.rotary._seq_len_cached = 0

        input_ids = torch.tensor([ids], dtype=torch.long, device=device)
        logits, velocity_map = model.forward_with_velocity(input_ids)

        # velocity_map: [num_layers, seq_len]
        print(f"\nVelocity map shape: {velocity_map.shape}")
        print(f"  (layers={velocity_map.shape[0]}, tokens={velocity_map.shape[1]})")

        # Print velocity table
        print(f"\n{'Token':>15s}", end="")
        for l in range(velocity_map.shape[0]):
            print(f"  L{l:02d}", end="")
        print(f"  {'Mean':>6s}  {'Lev':>6s}")
        print("-" * (15 + velocity_map.shape[0] * 6 + 16))

        for idx, info in enumerate(token_info):
            piece_display = info['piece'].replace('\u2581', '_')
            if len(piece_display) > 14:
                piece_display = piece_display[:14]
            print(f"{piece_display:>15s}", end="")
            for l in range(velocity_map.shape[0]):
                v = velocity_map[l, idx].item()
                print(f" {v:5.2f}", end="")
            mean_v = velocity_map[:, idx].mean().item()
            lev_str = f"{info['leverage']:.3f}" if info['leverage'] is not None else "  ?  "
            print(f"  {mean_v:6.3f}  {lev_str}")

        # Compute summary statistics
        byte_mask = torch.tensor([t['is_byte'] for t in token_info])
        crystal_mask = ~byte_mask

        if byte_mask.any():
            byte_vel = velocity_map[:, byte_mask].mean(dim=1)
            print(f"\nMean byte-gas velocity per layer:    {['%.3f' % v for v in byte_vel.tolist()]}")
        if crystal_mask.any():
            crystal_vel = velocity_map[:, crystal_mask].mean(dim=1)
            print(f"Mean crystal velocity per layer:      {['%.3f' % v for v in crystal_vel.tolist()]}")

        # Late-layer ratio: do crystals stay active longer?
        if byte_mask.any() and crystal_mask.any():
            late_layers = velocity_map[8:, :]  # layers 8-11
            early_layers = velocity_map[:4, :]  # layers 0-3

            byte_late = late_layers[:, byte_mask].mean().item()
            byte_early = early_layers[:, byte_mask].mean().item()
            crystal_late = late_layers[:, crystal_mask].mean().item()
            crystal_early = early_layers[:, crystal_mask].mean().item()

            byte_ratio = byte_late / max(byte_early, 1e-8)
            crystal_ratio = crystal_late / max(crystal_early, 1e-8)

            print(f"\nPersistence ratio (late/early velocity):")
            print(f"  Byte-gas:  {byte_ratio:.3f}  (early={byte_early:.3f}, late={byte_late:.3f})")
            print(f"  Crystals:  {crystal_ratio:.3f}  (early={crystal_early:.3f}, late={crystal_late:.3f})")

            if crystal_ratio > byte_ratio:
                print(f"\n  ** TIME DILATION DETECTED ** Crystals persist {crystal_ratio/max(byte_ratio, 1e-8):.1f}x longer than byte-gas")

        # Correlation between leverage and mean velocity (for tokens with known leverage)
        leverages = []
        mean_vels = []
        for idx, info in enumerate(token_info):
            if info['leverage'] is not None:
                leverages.append(info['leverage'])
                mean_vels.append(velocity_map[:, idx].mean().item())

        if len(leverages) >= 3:
            corr = np.corrcoef(leverages, mean_vels)[0, 1]
            print(f"\nLeverage-velocity correlation (Pearson): {corr:.3f}  (n={len(leverages)})")

        all_results.append({
            'sentence': sent,
            'token_info': token_info,
            'velocity_map': velocity_map.tolist(),
        })

    # Save results
    output_path = os.path.join(DATA_DIR, "time_dilation_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n\nResults saved to: {output_path}")

    return all_results


def plot_time_dilation(results, output_dir=None):
    """Generate the time dilation heatmap visualization."""
    if not HAS_MPL:
        print("matplotlib not available, skipping plot")
        return

    if output_dir is None:
        output_dir = DATA_DIR

    # Evangelion-inspired color scheme
    eva_colors = [
        (0.02, 0.02, 0.08),    # near-black void
        (0.08, 0.02, 0.20),    # deep purple
        (0.20, 0.02, 0.40),    # purple
        (0.50, 0.05, 0.30),    # magenta
        (0.85, 0.15, 0.10),    # red
        (1.00, 0.40, 0.00),    # orange
        (1.00, 0.75, 0.00),    # gold
        (1.00, 1.00, 0.85),    # white-hot
    ]
    eva_cmap = LinearSegmentedColormap.from_list("eva_heat", eva_colors, N=256)

    for res_idx, result in enumerate(results):
        token_info = result['token_info']
        vel_map = np.array(result['velocity_map'])  # [layers, tokens]
        sent = result['sentence']

        n_layers, n_tokens = vel_map.shape

        fig, ax = plt.subplots(figsize=(max(n_tokens * 0.9, 10), 8), dpi=200)
        fig.patch.set_facecolor('#0a0a14')
        ax.set_facecolor('#0a0a14')

        im = ax.imshow(vel_map, aspect='auto', cmap=eva_cmap,
                       interpolation='nearest', origin='lower')

        # Token labels on x-axis
        labels = []
        colors = []
        for info in token_info:
            piece = info['piece'].replace('\u2581', ' ')
            if info['is_byte']:
                labels.append(piece)
                colors.append('#4444aa')  # dim blue for bytes
            else:
                lev = info.get('leverage')
                labels.append(piece)
                if lev is not None and lev > 0.5:
                    colors.append('#ff4400')  # hot red for high gravity
                elif lev is not None and lev > 0.2:
                    colors.append('#ff8800')  # orange for medium
                else:
                    colors.append('#aaaaaa')  # grey for low/unknown

        ax.set_xticks(range(n_tokens))
        ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=9, fontfamily='monospace')
        for tick_label, color in zip(ax.get_xticklabels(), colors):
            tick_label.set_color(color)

        # Layer labels on y-axis
        layer_labels = [f'L{i}' for i in range(n_layers)]
        # Mark encoder/decoder boundary
        n_enc = n_layers // 2
        for i in range(n_layers):
            if i < n_enc:
                layer_labels[i] = f'E{i}'
            else:
                layer_labels[i] = f'D{i - n_enc}'

        ax.set_yticks(range(n_layers))
        ax.set_yticklabels(layer_labels, fontsize=10, fontfamily='monospace', color='#cccccc')

        # Add leverage annotations on top
        for idx, info in enumerate(token_info):
            lev = info.get('leverage')
            if lev is not None:
                ax.text(idx, n_layers + 0.3, f'{lev:.2f}',
                       ha='center', va='bottom', fontsize=7,
                       color='#ff8800', fontfamily='monospace')

        ax.text(n_tokens / 2, n_layers + 1.0, 'Ablation Leverage',
               ha='center', va='bottom', fontsize=9, color='#ff8800',
               fontfamily='monospace', fontstyle='italic')

        # Colorbar
        cbar = plt.colorbar(im, ax=ax, pad=0.02, fraction=0.03)
        cbar.set_label('Residual Velocity ||dx||', color='#cccccc', fontsize=10)
        cbar.ax.yaxis.set_tick_params(color='#cccccc')
        plt.setp(plt.getp(cbar.ax.axes, 'yticklabels'), color='#cccccc')

        ax.set_xlabel('Token Position', color='#cccccc', fontsize=11, labelpad=10)
        ax.set_ylabel('Layer Depth', color='#cccccc', fontsize=11)
        ax.set_title('Time Dilation in the Residual Stream\n'
                     'High-gravity tokens stay active longer — local time runs faster near mass',
                     color='#e0e0e0', fontsize=13, pad=25, fontfamily='monospace')

        # Add encoder/decoder boundary line
        ax.axhline(y=n_enc - 0.5, color='#ffffff', linewidth=0.5, linestyle='--', alpha=0.3)
        ax.text(-0.5, n_enc - 0.5, 'skip', ha='right', va='center',
               fontsize=7, color='#666666', fontstyle='italic')

        ax.tick_params(colors='#666666')
        for spine in ax.spines.values():
            spine.set_color('#333333')

        plt.tight_layout()

        output_path = os.path.join(output_dir, f'time_dilation_s{res_idx}.png')
        fig.savefig(output_path, dpi=200, bbox_inches='tight',
                   facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        print(f"Saved: {output_path}")


if __name__ == "__main__":
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, errors='replace')

    device = "cuda" if torch.cuda.is_available() else "cpu"

    # Default to fully trained 12L seed 137 checkpoint
    checkpoint = os.path.join(GOLF_ROOT, "logs", "gravity_12L_seed137.int8.ptz")
    if not os.path.exists(checkpoint):
        checkpoint = os.path.join(GOLF_ROOT, "final_model.int8.ptz")
        num_layers = 13
        print("WARNING: Using 13L smoke test checkpoint")
    else:
        num_layers = 12

    tokenizer = os.path.join(DATA_DIR, "tokenizers", "gravity_beta_1.0.model")

    print(f"Loading model ({num_layers}L)...")
    model, sp = load_model(checkpoint, tokenizer, num_layers=num_layers, device=device)
    print(f"Model loaded. Parameters: {sum(p.numel() for p in model.parameters()):,}")
    print(f"Device: {device}\n")

    results = run_time_dilation_probe(model, sp, device)

    if HAS_MPL:
        plot_time_dilation(results)
    else:
        print("\nInstall matplotlib for visualizations: pip install matplotlib")
