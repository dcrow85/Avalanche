"""
Spacetime Correlation Probe — Do lensing and depth efficiency unify?

Sweeps across crystal tokens in the gravity vocabulary, measuring:
  X-axis: Lensing strength (attention deflection when token is inserted)
  Y-axis: Depth efficiency (1.0 / persistence ratio, higher = more uniform)

If they correlate tightly (r > 0.7), the horizontal (attention routing) and
vertical (layer depth) effects are mechanically coupled — the vocabulary
defines a unified spacetime geometry.

Uses a fixed sentence template with a gap for token insertion:
  Base: "The system produced the result"
  Insert: "The system {TOKEN} produced the result"
"""

import io
import math
import os
import sys
import zlib
import json
import time

import torch
import torch.nn.functional as F
from torch import Tensor, nn
import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

import sentencepiece as spm

SCRIPT_DIR = os.path.dirname(__file__)
GOLF_ROOT = os.path.join(SCRIPT_DIR, "..", "parameter-golf")
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")


# ── Model (unified: captures both attention AND velocity) ──

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
        self.last_attn_weights = None

    def forward(self, x, capture_attn=False):
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

        if capture_attn:
            scale = 1.0 / math.sqrt(self.head_dim)
            attn = (q @ k.transpose(-2, -1)) * scale
            mask = torch.triu(torch.ones(seqlen, seqlen, device=x.device, dtype=torch.bool), diagonal=1)
            attn = attn.masked_fill(mask[None, None], float("-inf"))
            attn_weights = F.softmax(attn, dim=-1, dtype=torch.float32)
            self.last_attn_weights = attn_weights.detach().cpu()
            y = (attn_weights.to(x.dtype) @ v).transpose(1, 2).contiguous().reshape(bsz, seqlen, dim)
        else:
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

    def forward(self, x, x0, capture_attn=False):
        mix = self.resid_mix.to(dtype=x.dtype)
        x = mix[0][None, None, :] * x + mix[1][None, None, :] * x0
        x = x + self.attn_scale.to(dtype=x.dtype)[None, None, :] * self.attn(self.attn_norm(x), capture_attn=capture_attn)
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

    def forward_unified(self, input_ids):
        """
        Forward pass capturing BOTH attention weights AND residual velocities.
        Returns (logits, all_attn, velocity_map).
        """
        x = self.tok_emb(input_ids)
        x = F.rms_norm(x, (x.size(-1),))
        x0 = x.clone()

        velocities = []
        skips = []

        for i in range(self.num_encoder_layers):
            x_before = x.clone()
            x = self.blocks[i](x, x0, capture_attn=True)
            delta = x - x_before
            velocities.append(delta[0].norm(dim=-1).detach().cpu())
            skips.append(x)

        for i in range(self.num_decoder_layers):
            x_before = x.clone()
            if skips:
                x = x + self.skip_weights[i].to(dtype=x.dtype)[None, None, :] * skips.pop()
            x = self.blocks[self.num_encoder_layers + i](x, x0, capture_attn=True)
            delta = x - x_before
            velocities.append(delta[0].norm(dim=-1).detach().cpu())

        x = self.final_norm(x)
        if self.tie_embeddings:
            logits = F.linear(x, self.tok_emb.weight)
        else:
            logits = self.lm_head(x)
        logits = self.logit_softcap * torch.tanh(logits / self.logit_softcap)

        all_attn = [block.attn.last_attn_weights for block in self.blocks]
        velocity_map = torch.stack(velocities)

        return logits, all_attn, velocity_map


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


def tokenize_and_locate(sp, text, target_tokens):
    """Tokenize text and find positions of target words."""
    ids = sp.encode(text)
    pieces = [sp.id_to_piece(i) for i in ids]

    reconstructed = ""
    token_char_spans = []
    for idx, piece in enumerate(pieces):
        display = piece.replace("\u2581", " ")
        if piece.startswith("<0x") and piece.endswith(">"):
            try:
                byte_val = int(piece[3:-1], 16)
                display = bytes([byte_val]).decode("utf-8", errors="replace")
            except:
                display = "?"
        start = len(reconstructed)
        reconstructed += display
        end = len(reconstructed)
        token_char_spans.append((start, end))

    positions = {}
    for name, surface in target_tokens.items():
        for search in [" " + surface, surface]:
            char_idx = reconstructed.find(search)
            if char_idx >= 0:
                char_start = char_idx
                char_end = char_idx + len(search)
                tok_start = None
                tok_end = None
                for tidx, (cs, ce) in enumerate(token_char_spans):
                    if cs < char_end and ce > char_start:
                        if tok_start is None:
                            tok_start = tidx
                        tok_end = tidx + 1
                if tok_start is not None:
                    positions[name] = {
                        "span": (tok_start, tok_end),
                        "repr": tok_end - 1,
                        "tokens": pieces[tok_start:tok_end],
                    }
                break

    return ids, pieces, positions


@torch.no_grad()
def sweep_token(model, sp, token_surface, base_text, subject, obj, device):
    """
    Measure both lensing and depth efficiency for a single inserted token.

    Returns dict with lensing_strength, depth_efficiency, or None if the
    token can't be located after insertion.
    """
    # Base sentence (no insertion)
    base_targets = {"subject": subject, "object": obj}
    base_ids, base_pieces, base_pos = tokenize_and_locate(sp, base_text, base_targets)

    if "subject" not in base_pos or "object" not in base_pos:
        return None

    # Reset rotary
    for block in model.blocks:
        block.attn.rotary._seq_len_cached = 0

    base_input = torch.tensor([base_ids], dtype=torch.long, device=device)
    _, base_attn, _ = model.forward_unified(base_input)

    base_subj = base_pos["subject"]["repr"]
    base_obj = base_pos["object"]["repr"]

    # Direct attention in base
    base_direct_per_layer = []
    for attn in base_attn:
        if attn is not None:
            base_direct_per_layer.append(attn[0, :, base_obj, base_subj].mean().item())
    base_direct = np.mean(base_direct_per_layer) if base_direct_per_layer else 0

    # Inserted sentence
    # Insert the token surface form between subject and the verb
    # Template: "The {subject} {TOKEN} produced the {object}"
    inserted_text = base_text.replace(
        subject + " ",
        subject + " " + token_surface + " ",
        1
    )

    ins_targets = {"subject": subject, "object": obj, "lens": token_surface}
    ins_ids, ins_pieces, ins_pos = tokenize_and_locate(sp, inserted_text, ins_targets)

    if "subject" not in ins_pos or "object" not in ins_pos or "lens" not in ins_pos:
        return None

    for block in model.blocks:
        block.attn.rotary._seq_len_cached = 0

    ins_input = torch.tensor([ins_ids], dtype=torch.long, device=device)
    _, ins_attn, ins_vel = model.forward_unified(ins_input)

    ins_subj = ins_pos["subject"]["repr"]
    ins_obj = ins_pos["object"]["repr"]
    ins_lens = ins_pos["lens"]["repr"]

    # --- LENSING: measure direct attention deflection ---
    ins_direct_per_layer = []
    obj_to_lens_per_layer = []
    lens_to_subj_per_layer = []

    for attn in ins_attn:
        if attn is not None:
            a = attn[0]  # [heads, seq, seq]
            ins_direct_per_layer.append(a[:, ins_obj, ins_subj].mean().item())
            obj_to_lens_per_layer.append(a[:, ins_obj, ins_lens].mean().item())
            lens_to_subj_per_layer.append(a[:, ins_lens, ins_subj].mean().item())

    ins_direct = np.mean(ins_direct_per_layer) if ins_direct_per_layer else 0
    obj_to_lens = np.mean(obj_to_lens_per_layer) if obj_to_lens_per_layer else 0
    lens_to_subj = np.mean(lens_to_subj_per_layer) if lens_to_subj_per_layer else 0

    # Lensing strength: how much did the direct path collapse?
    if base_direct > 0:
        deflection = (base_direct - ins_direct) / base_direct
    else:
        deflection = 0

    # Also compute the indirect path strength
    indirect_strength = obj_to_lens + lens_to_subj

    # --- DEPTH EFFICIENCY: measure persistence ratio of the inserted token ---
    # vel shape: [n_layers, seq_len]
    n_layers = ins_vel.shape[0]

    # Get velocity profile for the lens token position
    lens_vel = ins_vel[:, ins_lens].numpy()

    # Early layers (0-3), late layers (8 to n-2, excluding final)
    early_vel = lens_vel[:4].mean()
    late_vel = lens_vel[8:-1].mean() if n_layers > 9 else lens_vel[8:].mean()

    if early_vel > 0:
        persistence_ratio = late_vel / early_vel
        depth_efficiency = 1.0 / persistence_ratio if persistence_ratio > 0 else 0
    else:
        persistence_ratio = 0
        depth_efficiency = 0

    # Panic ratio (L11 / L5)
    if n_layers > 11 and lens_vel[5] > 0:
        panic_ratio = lens_vel[-1] / lens_vel[5]
    else:
        panic_ratio = 0

    return {
        "token": token_surface,
        "pieces": ins_pos["lens"]["tokens"],
        "is_single_token": len(ins_pos["lens"]["tokens"]) == 1,
        "base_direct": float(base_direct),
        "ins_direct": float(ins_direct),
        "deflection": float(deflection),
        "obj_to_lens": float(obj_to_lens),
        "lens_to_subj": float(lens_to_subj),
        "indirect_strength": float(indirect_strength),
        "early_vel": float(early_vel),
        "late_vel": float(late_vel),
        "persistence_ratio": float(persistence_ratio),
        "depth_efficiency": float(depth_efficiency),
        "panic_ratio": float(panic_ratio),
        "velocity_profile": lens_vel.tolist(),
    }


@torch.no_grad()
def run_sweep(model, sp, device="cuda"):
    """
    Sweep across crystal tokens, measuring lensing + depth efficiency.
    Uses multiple sentence templates to average across contexts.
    """
    # Load leverage scores
    scored_path = os.path.join(DATA_DIR, "candidates_scored.jsonl")
    leverage_map = {}
    token_list = []

    with open(scored_path, "r", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            readable = c.get("readable", "")
            lev = c.get("ablation_leverage", 0)
            if lev > 0 and readable:
                leverage_map[readable] = lev
                # Only sweep tokens that exist in the gravity vocabulary
                # (they'll tokenize as single tokens)
                token_list.append((readable, lev))

    # Sort by leverage descending
    token_list.sort(key=lambda x: -x[1])
    print("Total scored tokens: %d" % len(token_list))

    # Sentence templates: {subject} ___GAP___ {verb phrase} {object}
    templates = [
        {
            "text": "The system produced the result",
            "subject": "system",
            "object": "result",
        },
        {
            "text": "The water caused the damage",
            "subject": "water",
            "object": "damage",
        },
        {
            "text": "The country changed the policy",
            "subject": "country",
            "object": "policy",
        },
    ]

    results = []
    skipped = 0
    t0 = time.time()

    # Sweep top tokens by leverage (most interesting) plus a sample of lower ones
    # Top 100 + every 10th from the rest
    sweep_tokens = token_list[:100]
    sweep_tokens += token_list[100::10]
    print("Sweeping %d tokens across %d templates..." % (len(sweep_tokens), len(templates)))

    for idx, (token_surface, leverage) in enumerate(sweep_tokens):
        if idx % 25 == 0:
            elapsed = time.time() - t0
            rate = idx / max(elapsed, 0.01)
            print("  [%d/%d] %.1f tok/s  (%.0fs elapsed)" % (
                idx, len(sweep_tokens), rate, elapsed))

        # Clean up surface form for insertion
        surface = token_surface.strip()
        if not surface or len(surface) > 20:
            skipped += 1
            continue

        # Average across templates
        template_results = []
        for tmpl in templates:
            r = sweep_token(model, sp, surface, tmpl["text"],
                           tmpl["subject"], tmpl["object"], device)
            if r is not None:
                template_results.append(r)

        if not template_results:
            skipped += 1
            continue

        # Average the metrics across templates
        avg = {
            "token": token_surface,
            "leverage": leverage,
            "is_single_token": any(r["is_single_token"] for r in template_results),
            "n_templates": len(template_results),
            "deflection": np.mean([r["deflection"] for r in template_results]),
            "indirect_strength": np.mean([r["indirect_strength"] for r in template_results]),
            "depth_efficiency": np.mean([r["depth_efficiency"] for r in template_results]),
            "persistence_ratio": np.mean([r["persistence_ratio"] for r in template_results]),
            "panic_ratio": np.mean([r["panic_ratio"] for r in template_results]),
            "early_vel": np.mean([r["early_vel"] for r in template_results]),
            "late_vel": np.mean([r["late_vel"] for r in template_results]),
        }
        results.append(avg)

    elapsed = time.time() - t0
    print("\nSweep complete: %d tokens measured, %d skipped, %.1fs" % (
        len(results), skipped, elapsed))

    return results


def plot_correlation(results, output_dir=None):
    """Generate the spacetime correlation scatter plot."""
    if not HAS_MPL:
        print("matplotlib not available")
        return

    if output_dir is None:
        output_dir = DATA_DIR

    eva_colors = [
        (0.02, 0.02, 0.08),
        (0.08, 0.02, 0.20),
        (0.20, 0.02, 0.40),
        (0.50, 0.05, 0.30),
        (0.85, 0.15, 0.10),
        (1.00, 0.40, 0.00),
        (1.00, 0.75, 0.00),
        (1.00, 1.00, 0.85),
    ]
    eva_cmap = LinearSegmentedColormap.from_list("eva", eva_colors, N=256)

    # Filter to tokens with valid data
    valid = [r for r in results if r["deflection"] != 0 and r["depth_efficiency"] != 0]

    if len(valid) < 5:
        print("Not enough valid data points for correlation: %d" % len(valid))
        return

    deflections = np.array([r["deflection"] for r in valid])
    depth_effs = np.array([r["depth_efficiency"] for r in valid])
    leverages = np.array([r["leverage"] for r in valid])
    tokens = [r["token"] for r in valid]
    single = np.array([r["is_single_token"] for r in valid])

    # Pearson correlation
    corr = np.corrcoef(deflections, depth_effs)[0, 1]
    print("\n=== SPACETIME CORRELATION ===")
    print("Pearson r(deflection, depth_efficiency) = %.4f  (n=%d)" % (corr, len(valid)))

    # Also check leverage correlations
    corr_lev_def = np.corrcoef(leverages, deflections)[0, 1]
    corr_lev_dep = np.corrcoef(leverages, depth_effs)[0, 1]
    print("Pearson r(leverage, deflection) = %.4f" % corr_lev_def)
    print("Pearson r(leverage, depth_efficiency) = %.4f" % corr_lev_dep)

    # === MAIN SCATTER: Deflection vs Depth Efficiency ===
    fig, ax = plt.subplots(figsize=(12, 10), dpi=300)
    fig.patch.set_facecolor("#0a0a14")
    ax.set_facecolor("#0a0a14")

    # Color by leverage, size by leverage
    scatter = ax.scatter(
        deflections, depth_effs,
        c=leverages, cmap=eva_cmap,
        s=leverages * 80 + 10,
        alpha=0.7, edgecolors="#ffffff22", linewidth=0.5,
    )

    # Label notable tokens (top 15 by leverage, top 5 by deflection, top 5 by depth_eff)
    labeled = set()
    # Top by leverage
    top_lev = sorted(range(len(valid)), key=lambda i: -leverages[i])[:12]
    # Top by deflection
    top_def = sorted(range(len(valid)), key=lambda i: -abs(deflections[i]))[:5]
    # Top by depth efficiency
    top_dep = sorted(range(len(valid)), key=lambda i: -depth_effs[i])[:5]

    for i in set(top_lev + top_def + top_dep):
        if i not in labeled:
            ax.annotate(
                tokens[i].strip(),
                (deflections[i], depth_effs[i]),
                xytext=(5, 5), textcoords="offset points",
                fontsize=7, color="#ff8800", fontfamily="monospace",
                alpha=0.9,
            )
            labeled.add(i)

    # Colorbar
    cbar = plt.colorbar(scatter, ax=ax, pad=0.02, fraction=0.03)
    cbar.set_label("Ablation Leverage", color="#cccccc", fontsize=10)
    cbar.ax.yaxis.set_tick_params(color="#cccccc")
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="#cccccc")

    # Correlation annotation
    ax.text(0.98, 0.02, "Pearson r = %.3f  (n=%d)" % (corr, len(valid)),
           transform=ax.transAxes, ha="right", va="bottom",
           fontsize=12, color="#ff8800", fontfamily="monospace",
           fontweight="bold",
           bbox=dict(boxstyle="round,pad=0.3", facecolor="#1a1a2e", edgecolor="#ff880044"))

    ax.set_xlabel("Lensing Strength (attention deflection)", color="#cccccc", fontsize=12)
    ax.set_ylabel("Depth Efficiency (1 / persistence ratio)", color="#cccccc", fontsize=12)
    ax.set_title("Spacetime Correlation: Do Lensing and Depth Efficiency Unify?\n"
                 "Each point is a gravity token inserted between subject and object",
                 color="#e0e0e0", fontsize=13, fontfamily="monospace", pad=15)
    ax.tick_params(colors="#666666")
    ax.grid(True, alpha=0.1, color="#ffffff")
    for spine in ax.spines.values():
        spine.set_color("#333333")

    plt.tight_layout()
    fig.savefig(os.path.join(output_dir, "spacetime_correlation.png"), dpi=300,
               bbox_inches="tight", facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()
    print("Saved: spacetime_correlation.png")

    # === TRIPLE SCATTER: leverage vs deflection, leverage vs depth, deflection vs depth ===
    fig, axes = plt.subplots(1, 3, figsize=(20, 7), dpi=300)
    fig.patch.set_facecolor("#0a0a14")

    pairs = [
        (leverages, deflections, "Ablation Leverage", "Lensing Strength", corr_lev_def),
        (leverages, depth_effs, "Ablation Leverage", "Depth Efficiency", corr_lev_dep),
        (deflections, depth_effs, "Lensing Strength", "Depth Efficiency", corr),
    ]

    for ax, (xdata, ydata, xlabel, ylabel, r) in zip(axes, pairs):
        ax.set_facecolor("#0a0a14")
        ax.scatter(xdata, ydata, c=leverages, cmap=eva_cmap,
                  s=30, alpha=0.6, edgecolors="#ffffff22", linewidth=0.3)
        ax.set_xlabel(xlabel, color="#cccccc", fontsize=10)
        ax.set_ylabel(ylabel, color="#cccccc", fontsize=10)
        ax.set_title("r = %.3f" % r, color="#ff8800", fontsize=11, fontfamily="monospace")
        ax.tick_params(colors="#666666")
        ax.grid(True, alpha=0.1, color="#ffffff")
        for spine in ax.spines.values():
            spine.set_color("#333333")

    fig.suptitle("Three Axes of Token Mass: Leverage, Lensing, and Depth",
                 color="#e0e0e0", fontsize=14, fontfamily="monospace", y=1.02)
    plt.tight_layout()
    fig.savefig(os.path.join(output_dir, "spacetime_triple.png"), dpi=300,
               bbox_inches="tight", facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()
    print("Saved: spacetime_triple.png")


if __name__ == "__main__":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, errors="replace")

    device = "cuda" if torch.cuda.is_available() else "cpu"

    checkpoint = os.path.join(GOLF_ROOT, "logs", "gravity_12L_seed137.int8.ptz")
    if not os.path.exists(checkpoint):
        checkpoint = os.path.join(GOLF_ROOT, "final_model.int8.ptz")
        num_layers = 13
        print("WARNING: Using 13L smoke test checkpoint")
    else:
        num_layers = 12

    tokenizer = os.path.join(DATA_DIR, "tokenizers", "gravity_beta_1.0.model")

    print("Loading model (%dL)..." % num_layers)
    model, sp = load_model(checkpoint, tokenizer, num_layers=num_layers, device=device)
    print("Model loaded. Parameters: %s" % "{:,}".format(sum(p.numel() for p in model.parameters())))
    print("Device: %s\n" % device)

    results = run_sweep(model, sp, device)

    # Save raw results
    output_path = os.path.join(DATA_DIR, "spacetime_correlation_results.json")
    clean = json.loads(json.dumps(results, default=lambda x: float(x) if isinstance(x, (np.floating, np.integer)) else x))
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)
    print("Results saved to: %s" % output_path)

    if HAS_MPL:
        plot_correlation(results)
    else:
        print("Install matplotlib for visualizations")
