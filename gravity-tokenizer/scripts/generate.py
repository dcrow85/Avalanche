"""
Generate text from a trained Gravity Tokenizer model.
Loads the int8+zlib checkpoint, dequantizes, and runs autoregressive generation.

Usage:
    python scripts/generate.py --prompt "The meaning of"
    python scripts/generate.py --interactive
"""

import argparse
import io
import math
import os
import sys
import zlib

import torch
import torch.nn.functional as F
from torch import Tensor, nn

import sentencepiece as spm

GOLF_ROOT = os.path.join(os.path.dirname(__file__), "..", "parameter-golf")


# ── Model (matched exactly to train_gpt_win.py checkpoint format) ──

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
        self.proj._zero_init = True
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

        # Manual attention (no flash attention needed for single-sequence inference)
        scale = 1.0 / math.sqrt(self.head_dim)
        if self.num_kv_heads < self.num_heads:
            reps = self.num_heads // self.num_kv_heads
            k = k.repeat_interleave(reps, dim=1)
            v = v.repeat_interleave(reps, dim=1)
        attn = (q @ k.transpose(-2, -1)) * scale
        mask = torch.triu(torch.ones(seqlen, seqlen, device=x.device, dtype=torch.bool), diagonal=1)
        attn = attn.masked_fill(mask[None, None], float('-inf'))
        attn = F.softmax(attn, dim=-1, dtype=torch.float32).to(x.dtype)
        y = (attn @ v).transpose(1, 2).contiguous().reshape(bsz, seqlen, dim)
        return self.proj(y)

class MLP(nn.Module):
    def __init__(self, dim, mlp_mult):
        super().__init__()
        self.fc = CastedLinear(dim, mlp_mult * dim, bias=False)
        self.proj = CastedLinear(mlp_mult * dim, dim, bias=False)
        self.proj._zero_init = True
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

    def forward_logits(self, input_ids):
        x = self.tok_emb(input_ids)
        x = F.rms_norm(x, (x.size(-1),))
        x0 = x
        skips = []
        for i in range(self.num_encoder_layers):
            x = self.blocks[i](x, x0)
            skips.append(x)
        for i in range(self.num_decoder_layers):
            if skips:
                x = x + self.skip_weights[i].to(dtype=x.dtype)[None, None, :] * skips.pop()
            x = self.blocks[self.num_encoder_layers + i](x, x0)
        x = self.final_norm(x)
        if self.tie_embeddings:
            logits_proj = F.linear(x, self.tok_emb.weight)
        else:
            logits_proj = self.lm_head(x)
        return self.logit_softcap * torch.tanh(logits_proj / self.logit_softcap)


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


@torch.no_grad()
def generate(model, tokenizer, prompt, max_tokens=150, temperature=0.7, top_k=50, device="cuda"):
    token_ids = tokenizer.encode(prompt)
    tokens = torch.tensor([token_ids], dtype=torch.long, device=device)
    generated = []

    for _ in range(max_tokens):
        input_tokens = tokens[:, -2048:]
        logits = model.forward_logits(input_tokens)
        next_logits = logits[:, -1, :].float()

        if temperature > 0:
            next_logits = next_logits / temperature
            if top_k > 0:
                v, _ = torch.topk(next_logits, min(top_k, next_logits.size(-1)))
                next_logits[next_logits < v[:, [-1]]] = float('-inf')
            probs = F.softmax(next_logits, dim=-1)
            next_token = torch.multinomial(probs, num_samples=1)
        else:
            next_token = next_logits.argmax(dim=-1, keepdim=True)

        tokens = torch.cat([tokens, next_token], dim=1)

    return tokenizer.decode(tokens[0].tolist())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", type=str, default="The meaning of")
    parser.add_argument("--checkpoint", type=str,
                        default=os.path.join(GOLF_ROOT, "final_model.int8.ptz"))
    parser.add_argument("--tokenizer", type=str,
                        default=os.path.join(os.path.dirname(__file__), "..", "data", "tokenizers", "gravity_beta_1.0.model"))
    parser.add_argument("--max-tokens", type=int, default=150)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument("--device", type=str, default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--interactive", action="store_true")
    # Model config — 13L to match this checkpoint
    parser.add_argument("--d-model", type=int, default=384)
    parser.add_argument("--num-layers", type=int, default=13)
    parser.add_argument("--num-heads", type=int, default=6)
    parser.add_argument("--num-kv-heads", type=int, default=2)
    parser.add_argument("--mlp-mult", type=int, default=3)
    parser.add_argument("--vocab-size", type=int, default=1024)
    parser.add_argument("--logit-softcap", type=float, default=30.0)
    parser.add_argument("--rope-base", type=float, default=10000.0)
    parser.add_argument("--qk-gain-init", type=float, default=1.5)
    args = parser.parse_args()

    print(f"Loading tokenizer: {args.tokenizer}")
    sp = spm.SentencePieceProcessor(model_file=args.tokenizer)
    print(f"  Vocab size: {sp.vocab_size()}")

    print(f"\nBuilding model: {args.d_model}d x {args.num_layers}L")
    model = GPT(
        vocab_size=args.vocab_size, num_layers=args.num_layers,
        model_dim=args.d_model, num_heads=args.num_heads,
        num_kv_heads=args.num_kv_heads, mlp_mult=args.mlp_mult,
        tie_embeddings=True, logit_softcap=args.logit_softcap,
        rope_base=args.rope_base, qk_gain_init=args.qk_gain_init,
    )

    print(f"Loading checkpoint: {args.checkpoint}")
    with open(args.checkpoint, "rb") as f:
        quant_blob = f.read()
    quant_state = torch.load(io.BytesIO(zlib.decompress(quant_blob)),
                             map_location="cpu", weights_only=True)
    state_dict = dequantize_state_dict_int8(quant_state)
    model.load_state_dict(state_dict, strict=False)
    model = model.to(args.device).eval()
    print(f"  Parameters: {sum(p.numel() for p in model.parameters()):,}")
    print(f"  Device: {args.device}")

    if args.interactive:
        print("\n--- Interactive mode (type 'quit' to exit) ---\n")
        while True:
            try:
                prompt = input(">>> ")
            except (EOFError, KeyboardInterrupt):
                break
            if prompt.strip().lower() in ("quit", "exit", "q"):
                break
            if not prompt.strip():
                continue
            output = generate(model, sp, prompt, max_tokens=args.max_tokens,
                              temperature=args.temperature, top_k=args.top_k,
                              device=args.device)
            print(f"\n{output}\n")
    else:
        print(f"\nPrompt: {args.prompt}")
        print(f"Temperature: {args.temperature}, Top-k: {args.top_k}")
        print("\n--- Generated text ---\n")
        output = generate(model, sp, args.prompt, max_tokens=args.max_tokens,
                          temperature=args.temperature, top_k=args.top_k,
                          device=args.device)
        # SentencePiece uses ▁ for spaces — replace for display
        clean = output.replace('\u2581', ' ').strip()
        sys.stdout.buffer.write((clean + '\n').encode('utf-8', errors='replace'))

if __name__ == "__main__":
    main()
