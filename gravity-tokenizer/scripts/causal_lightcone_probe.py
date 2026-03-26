"""
Causal Light-Cone Probe — Do connectives create directed attention geometry?

Tests whether backward-causal connectives (because, since, after) systematically
pull more attention from downstream positions (effect seeking cause), while
forward-causal connectives (so, before) pull more from upstream positions
(cause projecting effect).

All tested connectives are SINGLE TOKENS in the gravity vocabulary, so
sequence length is matched (Δposition = 0). RoPE confound is eliminated.

Measures Directional Attention Asymmetry:
  DAA = (Attention_from_right - Attention_from_left) / (Attention_from_right + Attention_from_left)

  DAA > 0: Token pulls more from downstream (backward-causal: effect seeks cause)
  DAA < 0: Token pulls more from upstream (forward-causal: cause projects effect)
  DAA ≈ 0: Symmetric (neutral connective)
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
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

import sentencepiece as spm

SCRIPT_DIR = os.path.dirname(__file__)
GOLF_ROOT = os.path.join(SCRIPT_DIR, "..", "parameter-golf")
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")


# ── Model (reused from spacetime_correlation_probe.py) ──

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

    def forward_with_attn(self, input_ids):
        """Forward pass capturing attention weights from all layers."""
        x = self.tok_emb(input_ids)
        x = F.rms_norm(x, (x.size(-1),))
        x0 = x.clone()

        skips = []
        for i in range(self.num_encoder_layers):
            x = self.blocks[i](x, x0, capture_attn=True)
            skips.append(x)

        for i in range(self.num_decoder_layers):
            if skips:
                x = x + self.skip_weights[i].to(dtype=x.dtype)[None, None, :] * skips.pop()
            x = self.blocks[self.num_encoder_layers + i](x, x0, capture_attn=True)

        all_attn = [block.attn.last_attn_weights for block in self.blocks]
        return all_attn


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


# ── Sentence templates ──
# Each template has: left context (cause/subject), CONNECTIVE slot, right context (effect/object)
# The connective sits between left and right, all at matched position.

TEMPLATES = [
    {
        "pattern": "The water {CONN} caused the damage",
        "left_word": "water",
        "right_word": "damage",
    },
    {
        "pattern": "The system {CONN} produced the result",
        "left_word": "system",
        "right_word": "result",
    },
    {
        "pattern": "The country {CONN} changed the policy",
        "left_word": "country",
        "right_word": "policy",
    },
    {
        "pattern": "The team {CONN} won the game",
        "left_word": "team",
        "right_word": "game",
    },
]

# ── Connective categories ──
CONNECTIVES = {
    # Backward-causal: effect seeks cause. "X because Y" means Y explains X.
    # The right side (after connective) provides the cause.
    "backward_causal": ["because", "since", "after", "when", "while", "whether", "until"],

    # Forward-causal: cause projects effect. "X so Y" means X leads to Y.
    # The left side (before connective) provides the cause.
    "forward_causal": ["so", "before"],

    # Symmetric/neutral: no directional bias
    "symmetric": ["still", "every", "both", "either", "such", "quite", "rather"],

    # Relational: structural but potentially directional
    "relational": ["however", "between", "without", "through", "during", "against"],
}


@torch.no_grad()
def measure_directional_attention(model, sp, connective, template, device):
    """
    Measure the Directional Attention Asymmetry for a connective in a template.

    Returns dict with:
      - attn_from_left: how much the connective attends to tokens LEFT of it
      - attn_from_right: how much the connective receives attention FROM tokens right of it
      - left_to_conn: attention mass from left context flowing INTO the connective
      - right_to_conn: attention mass from right context flowing INTO the connective
      - conn_to_left: attention mass from connective flowing to left context
      - conn_to_right: attention mass from connective flowing to right context
      - DAA: directional attention asymmetry
    """
    text = template["pattern"].replace("{CONN}", connective)
    left_word = template["left_word"]
    right_word = template["right_word"]

    targets = {"left": left_word, "right": right_word, "conn": connective}
    ids, pieces, pos = tokenize_and_locate(sp, text, targets)

    if "left" not in pos or "right" not in pos or "conn" not in pos:
        return None

    # Verify connective is single-token
    if len(pos["conn"]["tokens"]) != 1:
        return None

    # Reset rotary cache
    for block in model.blocks:
        block.attn.rotary._seq_len_cached = 0

    input_ids = torch.tensor([ids], dtype=torch.long, device=device)
    all_attn = model.forward_with_attn(input_ids)

    conn_pos = pos["conn"]["repr"]
    left_pos = pos["left"]["repr"]
    right_pos = pos["right"]["repr"]

    # Aggregate across all layers and heads
    # For each layer, get mean across heads
    left_to_conn_layers = []
    right_to_conn_layers = []
    conn_to_left_layers = []
    conn_to_right_layers = []

    for attn in all_attn:
        if attn is None:
            continue
        a = attn[0]  # [heads, seq, seq]

        # Attention FROM left word TO connective (left queries, conn is key)
        # But causal mask: left_pos < conn_pos, so left can't attend to conn
        # Instead: connective attends to left (conn queries, left is key)
        conn_to_left_layers.append(a[:, conn_pos, left_pos].mean().item())

        # Right word attends to connective (right queries, conn is key)
        # right_pos > conn_pos, so right CAN attend to conn
        right_to_conn_layers.append(a[:, right_pos, conn_pos].mean().item())

        # Connective attends to left (already captured above)
        # Right word attends to left (through connective or directly)

        # Also measure: how much does the CONNECTIVE attend leftward vs rightward?
        # Connective can only attend to positions <= conn_pos (causal)
        # So "conn attending right" is impossible.
        # But positions RIGHT of conn can attend to conn.

        # The key asymmetry for causal connectives:
        # "because": right tokens (the cause) should attend heavily to conn
        #            AND conn should attend heavily to left (the effect)
        # "so": left tokens feed conn, conn is attended by right tokens

        # Measure: total inbound attention to conn from right context
        # = sum of A[j, conn_pos] for j > conn_pos
        seq_len = a.shape[-1]
        if conn_pos + 1 < seq_len:
            right_inbound = a[:, conn_pos+1:, conn_pos].sum(dim=-1).mean().item()
        else:
            right_inbound = 0.0

        # Total inbound attention to conn from left context
        # = in causal attention, positions left of conn CAN'T attend to conn
        # Instead, measure conn's outbound attention to left
        if conn_pos > 0:
            left_outbound = a[:, conn_pos, :conn_pos].sum(dim=-1).mean().item()
        else:
            left_outbound = 0.0

    # Average across layers
    mean_conn_to_left = np.mean(conn_to_left_layers) if conn_to_left_layers else 0
    mean_right_to_conn = np.mean(right_to_conn_layers) if right_to_conn_layers else 0

    # DAA based on the physically meaningful flows:
    # right_to_conn = how much the right context (downstream) queries the connective
    # conn_to_left = how much the connective queries the left context (upstream)
    # High right_to_conn + high conn_to_left = backward bridge (effect seeking cause via conn)

    # For forward connective:
    # conn_to_left should be high (absorbing cause from left)
    # right_to_conn should be lower (right doesn't need to look back through conn)

    # Actually, let's measure ALL directional flows
    # In causal attention, information flows: keys → queries (past → present)
    # A[q, k] = how much position q attends to position k

    # Flow 1: conn ← left (conn attends to left, absorbing left context)
    # Flow 2: right ← conn (right attends to conn, absorbing conn state)
    # Flow 3: right ← left (right attends directly to left, bypassing conn)

    flow_conn_absorbs_left = mean_conn_to_left  # conn queries left
    flow_right_absorbs_conn = mean_right_to_conn  # right queries conn

    # The DAA: does the connective create an asymmetric bridge?
    # Backward causal (because): RIGHT needs to look at LEFT via CONN
    #   → high right_absorbs_conn (right looks through conn to understand cause)
    # Forward causal (so): LEFT feeds CONN feeds RIGHT naturally
    #   → high conn_absorbs_left (conn pulls from left to project forward)

    total = flow_right_absorbs_conn + flow_conn_absorbs_left
    if total > 0:
        # DAA > 0 means more right-to-conn flow (backward causal signature)
        # DAA < 0 means more conn-to-left flow (forward causal signature)
        daa = (flow_right_absorbs_conn - flow_conn_absorbs_left) / total
    else:
        daa = 0.0

    return {
        "connective": connective,
        "template": template["pattern"],
        "left_word": left_word,
        "right_word": right_word,
        "conn_pos": conn_pos,
        "left_pos": left_pos,
        "right_pos": right_pos,
        "conn_absorbs_left": float(flow_conn_absorbs_left),
        "right_absorbs_conn": float(flow_right_absorbs_conn),
        "daa": float(daa),
        "pieces": [p.replace("\u2581", "_") for p in pieces],
    }


@torch.no_grad()
def run_probe(device="cuda"):
    """Run the full causal light-cone probe."""

    # Find checkpoint
    ckpt_candidates = [
        os.path.join(GOLF_ROOT, "logs", "gravity_12L_seed137.int8.ptz"),
        os.path.join(GOLF_ROOT, "logs", "gravity_12L_seed42.int8.ptz"),
        os.path.join(GOLF_ROOT, "final_model.int8.ptz"),
    ]
    ckpt = None
    for c in ckpt_candidates:
        if os.path.exists(c):
            ckpt = c
            break
    if ckpt is None:
        print("ERROR: No checkpoint found")
        return

    tok_path = os.path.join(DATA_DIR, "tokenizers", "gravity_beta_1.0.model")
    print(f"Loading model from {ckpt}")
    print(f"Loading tokenizer from {tok_path}")

    model, sp = load_model(ckpt, tok_path, num_layers=12, device=device)
    print("Model loaded.\n")

    # First, verify which connectives are single-token
    print("=== VERIFYING SINGLE-TOKEN CONNECTIVES ===")
    valid_connectives = {}
    for category, words in CONNECTIVES.items():
        valid = []
        for w in words:
            pieces = sp.EncodeAsPieces(" " + w)
            if len(pieces) == 1:
                valid.append(w)
                print(f"  {w:15s} [{category}] -> single token")
            else:
                print(f"  {w:15s} [{category}] -> {len(pieces)} pieces (SKIPPED)")
        valid_connectives[category] = valid

    print(f"\nValid connectives: {sum(len(v) for v in valid_connectives.values())}")

    # Run the sweep
    print("\n=== RUNNING DIRECTIONAL ATTENTION SWEEP ===\n")

    all_results = []

    for category, words in valid_connectives.items():
        for word in words:
            word_results = []
            for template in TEMPLATES:
                result = measure_directional_attention(model, sp, word, template, device)
                if result is not None:
                    result["category"] = category
                    word_results.append(result)

            if word_results:
                # Average across templates
                mean_daa = np.mean([r["daa"] for r in word_results])
                mean_conn_left = np.mean([r["conn_absorbs_left"] for r in word_results])
                mean_right_conn = np.mean([r["right_absorbs_conn"] for r in word_results])

                summary = {
                    "connective": word,
                    "category": category,
                    "n_templates": len(word_results),
                    "mean_daa": float(mean_daa),
                    "mean_conn_absorbs_left": float(mean_conn_left),
                    "mean_right_absorbs_conn": float(mean_right_conn),
                    "per_template": word_results,
                }
                all_results.append(summary)

                arrow = ">>" if mean_daa > 0.05 else ("<<" if mean_daa < -0.05 else "--")
                print(f"  {word:15s} [{category:18s}] DAA={mean_daa:+.4f} {arrow}  "
                      f"L<-C={mean_conn_left:.4f}  R<-C={mean_right_conn:.4f}")

    # Save results
    out_path = os.path.join(DATA_DIR, "causal_lightcone_results.json")
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to {out_path}")

    # Print summary by category
    print("\n=== CATEGORY SUMMARY ===\n")
    for category in ["backward_causal", "forward_causal", "symmetric", "relational"]:
        cat_results = [r for r in all_results if r["category"] == category]
        if cat_results:
            daas = [r["mean_daa"] for r in cat_results]
            print(f"{category:20s}: n={len(cat_results)}, "
                  f"mean DAA={np.mean(daas):+.4f} (std={np.std(daas):.4f}), "
                  f"range=[{min(daas):+.4f}, {max(daas):+.4f}]")

    # Statistical test: do backward and forward categories differ?
    backward = [r["mean_daa"] for r in all_results if r["category"] == "backward_causal"]
    forward = [r["mean_daa"] for r in all_results if r["category"] == "forward_causal"]
    symmetric = [r["mean_daa"] for r in all_results if r["category"] == "symmetric"]

    if backward and forward:
        print(f"\nBackward causal mean DAA: {np.mean(backward):+.4f}")
        print(f"Forward causal mean DAA:  {np.mean(forward):+.4f}")
        print(f"Symmetric mean DAA:       {np.mean(symmetric):+.4f}")
        print(f"Backward - Forward delta: {np.mean(backward) - np.mean(forward):+.4f}")

    # Visualization
    if HAS_MPL and all_results:
        plot_results(all_results)

    return all_results


def plot_results(results):
    """Create the directional attention asymmetry chart."""

    # Color scheme
    bg_color = "#0a0a1a"
    colors = {
        "backward_causal": "#ff6b35",  # Orange
        "forward_causal": "#4ecdc4",   # Teal
        "symmetric": "#95a5a6",        # Gray
        "relational": "#a78bfa",       # Purple
    }
    labels = {
        "backward_causal": "Backward Causal",
        "forward_causal": "Forward Causal",
        "symmetric": "Symmetric",
        "relational": "Relational",
    }

    fig, ax = plt.subplots(1, 1, figsize=(14, 8), dpi=300)
    fig.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    # Sort by DAA
    results_sorted = sorted(results, key=lambda r: r["mean_daa"])

    y_positions = range(len(results_sorted))

    for i, r in enumerate(results_sorted):
        color = colors.get(r["category"], "#ffffff")
        ax.barh(i, r["mean_daa"], color=color, alpha=0.85, height=0.7,
                edgecolor=color, linewidth=0.5)

        # Label
        label_x = r["mean_daa"] + (0.005 if r["mean_daa"] >= 0 else -0.005)
        ha = "left" if r["mean_daa"] >= 0 else "right"
        ax.text(label_x, i, r["connective"], va="center", ha=ha,
                fontsize=11, fontweight="bold", color=color)

    # Zero line
    ax.axvline(x=0, color="#ffffff", linewidth=0.8, alpha=0.5, linestyle="--")

    # Labels
    ax.set_xlabel("Directional Attention Asymmetry (DAA)", fontsize=12, color="#ffffff")
    ax.set_title("Causal Light-Cones in a 12-Layer Transformer\n"
                 "Do connectives create directed attention geometry?",
                 fontsize=14, fontweight="bold", color="#ffffff", pad=20)

    # Annotations
    ax.text(0.02, 0.98, "\u2190 Forward (cause \u2192 effect)", transform=ax.transAxes,
            fontsize=10, color="#4ecdc4", va="top", ha="left", style="italic")
    ax.text(0.98, 0.98, "Backward (effect \u2190 cause) \u2192", transform=ax.transAxes,
            fontsize=10, color="#ff6b35", va="top", ha="right", style="italic")

    ax.set_yticks([])
    ax.tick_params(colors="#ffffff")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color("#333333")

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=colors[k], label=labels[k]) for k in colors]
    legend = ax.legend(handles=legend_elements, loc="lower right", fontsize=9,
                       facecolor="#1a1a2e", edgecolor="#333333", labelcolor="#ffffff")

    plt.tight_layout()
    out_path = os.path.join(DATA_DIR, "causal_lightcone.png")
    plt.savefig(out_path, dpi=300, facecolor=bg_color, bbox_inches="tight")
    plt.close()
    print(f"\nChart saved to {out_path}")


if __name__ == "__main__":
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    run_probe(device)
