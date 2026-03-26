"""
BERT (RoBERTa) Causal Light-Cone Control Experiment

Tests whether the directional attention asymmetry (DAA) observed in the
causal gravity tokenizer model is imposed by the causal mask or learned
from language structure.

Prediction: In a bidirectional model (no causal mask), backward-causal
connectives like "because" should flip to POSITIVE DAA (effect genuinely
seeks cause), forward-causal like "so" should remain negative or near zero,
and symmetric connectives should sit near zero.

If confirmed: the directional geometry is learned from language, not
imposed by the causal mask. The causal mask in GPT suppresses a genuine
sign flip that exists in the learned representations.
"""

import torch
import numpy as np
import json
import os
from collections import defaultdict

# ── Model setup ──────────────────────────────────────────────────────
from transformers import RobertaModel, RobertaTokenizer

print("Loading RoBERTa-base...")
tokenizer = RobertaTokenizer.from_pretrained('roberta-base')
model = RobertaModel.from_pretrained('roberta-base', output_attentions=True)
model.eval()
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = model.to(device)
print(f"RoBERTa-base loaded on {device}")

# ── Connective definitions ───────────────────────────────────────────
CONNECTIVES = {
    'backward_causal': ['because', 'since', 'after', 'when', 'while', 'whether', 'until'],
    'forward_causal': ['so', 'before'],
    'symmetric': ['still', 'every', 'both', 'either', 'such', 'quite', 'rather'],
    'relational': ['however', 'between', 'without', 'through', 'during', 'against'],
}

# ── Sentence templates ───────────────────────────────────────────────
# Structure: [left context] [CONN] [right context]
# The connective is inserted between a subject-clause and object-clause
TEMPLATES = [
    ("The water damage {CONN} the storm destroyed everything", "water", "storm"),
    ("The government acted {CONN} the crisis demanded action", "government", "crisis"),
    ("The students learned {CONN} the teacher explained clearly", "students", "teacher"),
    ("The company changed {CONN} the market shifted rapidly", "company", "market"),
]

def find_token_positions(input_ids, target_id):
    """Find all positions of target_id in input_ids."""
    positions = []
    for i, tid in enumerate(input_ids):
        if tid == target_id:
            positions.append(i)
    return positions

def measure_daa_roberta(sentence, conn_word, left_word, right_word):
    """
    Measure Directional Attention Asymmetry for a connective in RoBERTa.

    In a bidirectional model, attention flows BOTH directions.
    We measure:
    - conn_absorbs_left: how much the connective attends to the left context
    - right_absorbs_conn: how much the right context attends to the connective
    - conn_absorbs_right: how much the connective attends to the right context (NEW - not possible in causal)
    - left_absorbs_conn: how much the left context attends to the connective (NEW)

    DAA = (right_absorbs_conn - left_absorbs_conn) / (right_absorbs_conn + left_absorbs_conn)
    Positive DAA = right context attends MORE to connective (backward-seeking)
    Negative DAA = left context attends MORE to connective (forward-projecting)
    """
    inputs = tokenizer(sentence, return_tensors='pt').to(device)
    input_ids = inputs['input_ids'][0].tolist()

    # Find token positions
    conn_id = tokenizer.encode(f' {conn_word}', add_special_tokens=False)[0]
    left_id = tokenizer.encode(f' {left_word}', add_special_tokens=False)[0]
    right_id = tokenizer.encode(f' {right_word}', add_special_tokens=False)[0]

    conn_positions = find_token_positions(input_ids, conn_id)
    left_positions = find_token_positions(input_ids, left_id)
    right_positions = find_token_positions(input_ids, right_id)

    if not conn_positions or not left_positions or not right_positions:
        return None

    conn_pos = conn_positions[0]
    left_pos = left_positions[0]
    right_pos = right_positions[0]

    # Verify structural ordering: left < conn < right
    if not (left_pos < conn_pos < right_pos):
        return None

    with torch.no_grad():
        outputs = model(**inputs)
        # attentions: tuple of (batch, heads, seq, seq) per layer
        attentions = outputs.attentions

    # Average attention across all layers and heads
    # Shape: [seq_len, seq_len] where [i, j] = how much position i attends to position j
    all_attn = torch.stack(attentions)  # [n_layers, batch, heads, seq, seq]
    mean_attn = all_attn.mean(dim=(0, 1, 2))  # [seq, seq]
    attn = mean_attn.cpu().numpy()

    # Bidirectional measurements
    conn_absorbs_left = float(attn[conn_pos, left_pos])    # conn attending to left
    conn_absorbs_right = float(attn[conn_pos, right_pos])  # conn attending to right (NEW)
    right_absorbs_conn = float(attn[right_pos, conn_pos])  # right attending to conn
    left_absorbs_conn = float(attn[left_pos, conn_pos])    # left attending to conn (NEW)

    # Direct path (for comparison with causal model)
    right_to_left_direct = float(attn[right_pos, left_pos])
    left_to_right_direct = float(attn[left_pos, right_pos])

    # DAA: does the right context or left context attend more to the connective?
    total_inbound = right_absorbs_conn + left_absorbs_conn
    if total_inbound < 1e-10:
        daa = 0.0
    else:
        daa = (right_absorbs_conn - left_absorbs_conn) / total_inbound

    # Asymmetry of the connective's own attention: does it look left or right?
    conn_total = conn_absorbs_left + conn_absorbs_right
    if conn_total < 1e-10:
        conn_asymmetry = 0.0
    else:
        conn_asymmetry = (conn_absorbs_right - conn_absorbs_left) / conn_total

    return {
        'daa': daa,
        'conn_asymmetry': conn_asymmetry,
        'conn_absorbs_left': conn_absorbs_left,
        'conn_absorbs_right': conn_absorbs_right,
        'right_absorbs_conn': right_absorbs_conn,
        'left_absorbs_conn': left_absorbs_conn,
        'right_to_left_direct': right_to_left_direct,
        'left_to_right_direct': left_to_right_direct,
        'conn_pos': conn_pos,
        'left_pos': left_pos,
        'right_pos': right_pos,
    }


# ── Run the sweep ────────────────────────────────────────────────────
print("\n" + "="*80)
print("BERT CAUSAL LIGHT-CONE CONTROL EXPERIMENT")
print("="*80)

results = []
category_results = defaultdict(list)

for category, words in CONNECTIVES.items():
    for word in words:
        word_daas = []
        word_conn_asyms = []
        word_measurements = []

        for template_str, left_word, right_word in TEMPLATES:
            sentence = template_str.replace('{CONN}', word)
            measurement = measure_daa_roberta(sentence, word, left_word, right_word)

            if measurement is not None:
                word_daas.append(measurement['daa'])
                word_conn_asyms.append(measurement['conn_asymmetry'])
                word_measurements.append(measurement)

        if word_daas:
            mean_daa = np.mean(word_daas)
            mean_conn_asym = np.mean(word_conn_asyms)
            mean_right_to_conn = np.mean([m['right_absorbs_conn'] for m in word_measurements])
            mean_left_to_conn = np.mean([m['left_absorbs_conn'] for m in word_measurements])
            mean_conn_to_left = np.mean([m['conn_absorbs_left'] for m in word_measurements])
            mean_conn_to_right = np.mean([m['conn_absorbs_right'] for m in word_measurements])

            result = {
                'word': word,
                'category': category,
                'mean_daa': float(mean_daa),
                'mean_conn_asymmetry': float(mean_conn_asym),
                'mean_right_absorbs_conn': float(mean_right_to_conn),
                'mean_left_absorbs_conn': float(mean_left_to_conn),
                'mean_conn_absorbs_left': float(mean_conn_to_left),
                'mean_conn_absorbs_right': float(mean_conn_to_right),
                'n_templates': len(word_daas),
                'std_daa': float(np.std(word_daas)),
            }
            results.append(result)
            category_results[category].append(result)

# ── Print results ────────────────────────────────────────────────────
print(f"\n{'CONNECTIVE':15s} {'CATEGORY':20s} {'DAA':>8s} {'CONN_ASYM':>10s} {'L>conn':>8s} {'R>conn':>8s} {'conn>L':>8s} {'conn>R':>8s}")
print("-" * 95)

for r in sorted(results, key=lambda x: x['mean_daa'], reverse=True):
    print(f"{r['word']:15s} {r['category']:20s} {r['mean_daa']:+8.3f} {r['mean_conn_asymmetry']:+10.3f} "
          f"{r['mean_left_absorbs_conn']:8.4f} {r['mean_right_absorbs_conn']:8.4f} "
          f"{r['mean_conn_absorbs_left']:8.4f} {r['mean_conn_absorbs_right']:8.4f}")

print("\n" + "="*80)
print("CATEGORY SUMMARY")
print("="*80)
print(f"\n{'CATEGORY':20s} {'n':>3s} {'Mean DAA':>10s} {'Std':>8s} {'Range':>20s}")
print("-" * 65)

for category in ['backward_causal', 'forward_causal', 'symmetric', 'relational']:
    cat_daas = [r['mean_daa'] for r in category_results[category]]
    if cat_daas:
        print(f"{category:20s} {len(cat_daas):3d} {np.mean(cat_daas):+10.3f} {np.std(cat_daas):8.3f} "
              f"[{min(cat_daas):+.3f}, {max(cat_daas):+.3f}]")

# ── The critical comparison ──────────────────────────────────────────
print("\n" + "="*80)
print("CRITICAL COMPARISON: because vs so")
print("="*80)

because_result = next((r for r in results if r['word'] == 'because'), None)
so_result = next((r for r in results if r['word'] == 'so'), None)

if because_result and so_result:
    print(f"\n  because  DAA = {because_result['mean_daa']:+.3f}  (prediction: POSITIVE)")
    print(f"  so       DAA = {so_result['mean_daa']:+.3f}  (prediction: NEGATIVE or near zero)")
    print(f"  and      DAA = ", end="")
    and_result = next((r for r in results if r['word'] == 'both'), None)  # 'and' may not be single-token
    if and_result:
        print(f"{and_result['mean_daa']:+.3f}  (prediction: near ZERO)")
    else:
        print("N/A")

    sign_flipped = because_result['mean_daa'] > 0
    print(f"\n  SIGN FLIP FOR 'because': {'YES ✓' if sign_flipped else 'NO ✗'}")

    separation = because_result['mean_daa'] - so_result['mean_daa']
    print(f"  because - so separation: {separation:+.3f}")

    if sign_flipped:
        print("\n  *** THE CAUSAL MASK WAS SUPPRESSING A GENUINE SIGN FLIP ***")
        print("  *** Directional geometry is learned from language, not imposed by architecture ***")
    else:
        print("\n  The sign did not flip. The directional asymmetry may be weaker than predicted,")
        print("  or RoBERTa's bidirectional training may produce different routing patterns.")

# ── Gemini's full prediction check ───────────────────────────────────
print("\n" + "="*80)
print("GEMINI'S PREDICTIONS")
print("="*80)

backward_mean = np.mean([r['mean_daa'] for r in category_results['backward_causal']])
forward_mean = np.mean([r['mean_daa'] for r in category_results['forward_causal']])
symmetric_mean = np.mean([r['mean_daa'] for r in category_results['symmetric']])

print(f"\n  Prediction 1: backward_causal DAA > 0 (flips positive)")
print(f"  Result: {backward_mean:+.3f}  {'CONFIRMED ✓' if backward_mean > 0 else 'REJECTED ✗'}")

print(f"\n  Prediction 2: forward_causal DAA < 0 or near 0")
print(f"  Result: {forward_mean:+.3f}  {'CONFIRMED ✓' if forward_mean <= 0.05 else 'REJECTED ✗'}")

print(f"\n  Prediction 3: symmetric DAA ≈ 0")
print(f"  Result: {symmetric_mean:+.3f}  {'CONFIRMED ✓' if abs(symmetric_mean) < 0.1 else 'REJECTED ✗'}")

# ── Save results ─────────────────────────────────────────────────────
output_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'bert_lightcone_results.json')
output = {
    'model': 'roberta-base',
    'description': 'Bidirectional control for causal light-cone probe',
    'n_templates': len(TEMPLATES),
    'n_connectives': len(results),
    'results': results,
    'category_summary': {
        cat: {
            'mean_daa': float(np.mean([r['mean_daa'] for r in cat_results])),
            'std_daa': float(np.std([r['mean_daa'] for r in cat_results])),
            'n': len(cat_results),
        }
        for cat, cat_results in category_results.items()
    },
    'predictions': {
        'because_flips_positive': bool(because_result and because_result['mean_daa'] > 0),
        'so_stays_negative': bool(so_result and so_result['mean_daa'] <= 0.05),
        'backward_minus_forward': float(backward_mean - forward_mean),
    }
}

os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, 'w') as f:
    json.dump(output, f, indent=2)
print(f"\nResults saved to {output_path}")
