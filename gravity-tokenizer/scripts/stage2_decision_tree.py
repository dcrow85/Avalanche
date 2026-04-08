"""
Stage 2 multi-feature classifier test.

Train a shallow decision tree on the eligible-above-floor token population
using non-circular features (no panic_ratio, no active_work):
- frequency (corpus-derived)
- predecessor entropy + top1_pred (corpus bigrams)
- successor entropy + top1_succ (corpus bigrams)
- gradient max (coherence instrument)
- integrated gradient energy (coherence instrument)

Target: graduate vs not.

Uses leave-one-out cross-validation since N is tiny (~125 eligible, 7 graduates).
Also tests Gemini's Goldilocks band hypothesis: graduates have
0.15 < top1_pred OR top1_succ < 0.95.
"""
import json
import statistics

from classification_compat import is_quiescent_classification, normalize_phase_space_snapshot

with open('C:/Avalanche/gravity-tokenizer/parameter-golf/logs/coherence_seed_1337/gravity_coherence_seed_1337_coherence_snapshot.json') as f:
    coh = json.load(f)
with open('C:/Avalanche/gravity-tokenizer/parameter-golf/logs/coherence_seed_1337/gravity_coherence_seed_1337_phase_space.json') as f:
    ps = normalize_phase_space_snapshot(json.load(f))
with open('C:/Avalanche/gravity-tokenizer/parameter-golf/logs/coherence_seed_1337/bigram_entropy.json') as f:
    bg = json.load(f)

ps_rows = {r['token_id']: r for r in ps['rows']}
coh_rows = {r['token_id']: r for r in coh['rows']}
bg_rows = {r['token_id']: r for r in bg}

E_CRIT = 1.20

toks = []
for tid, psr in ps_rows.items():
    cr = coh_rows.get(tid)
    if not cr or not cr.get('is_dynamic'):
        continue
    bgr = bg_rows.get(tid, {})
    if cr['grad_energy_total'] < E_CRIT:
        continue
    if bgr.get('successor_entropy_bits') is None:
        continue
    is_grad = is_quiescent_classification(psr.get('classification'))
    toks.append({
        'tid': tid,
        'readable': psr['readable'],
        'cls': psr['classification'],
        'is_grad': is_grad,
        'energy': cr['grad_energy_total'],
        'grad_max': cr['grad_magnitude_max'],
        'freq': bgr['freq'],
        'h_pred': bgr['predecessor_entropy_bits'],
        'h_succ': bgr['successor_entropy_bits'],
        'top1_pred': bgr['top1_predecessor_frac'],
        'top1_succ': bgr['top1_successor_frac'],
    })

graduates = [t for t in toks if t['is_grad']]
near_miss = [t for t in toks if not t['is_grad']]
print(f'Eligible above floor: {len(toks)}')
print(f'  graduates: {len(graduates)}')
print(f'  near-miss: {len(near_miss)}')

# === Test 1: Goldilocks band hypothesis ===
print('\n=== TEST 1: Goldilocks band [0.15, 0.95] OR rule ===')
def goldilocks(t, lo=0.15, hi=0.95):
    return (lo < t['top1_pred'] < hi) or (lo < t['top1_succ'] < hi)

g_pass = sum(1 for t in graduates if goldilocks(t))
nm_pass = sum(1 for t in near_miss if goldilocks(t))
print(f'  Graduates passing Goldilocks: {g_pass}/{len(graduates)} ({g_pass/len(graduates)*100:.0f}%)')
print(f'  Near-miss passing Goldilocks: {nm_pass}/{len(near_miss)} ({nm_pass/len(near_miss)*100:.0f}%)')

# Try different bands
print('\n  Sweep over Goldilocks bands:')
for lo, hi in [(0.10, 0.99), (0.15, 0.95), (0.20, 0.90), (0.25, 0.85), (0.30, 0.80), (0.35, 0.75), (0.40, 0.70)]:
    g_p = sum(1 for t in graduates if (lo < t['top1_pred'] < hi) or (lo < t['top1_succ'] < hi))
    nm_p = sum(1 for t in near_miss if (lo < t['top1_pred'] < hi) or (lo < t['top1_succ'] < hi))
    if g_p + nm_p == 0:
        continue
    precision = g_p / (g_p + nm_p)
    recall = g_p / len(graduates)
    print(f'  [{lo:.2f}, {hi:.2f}]: g_pass={g_p}/{len(graduates)} nm_pass={nm_p}/{len(near_miss)}  precision={precision*100:.1f}%  recall={recall*100:.1f}%')

# === Test 2: Roche Limit / Subword Parasitism ===
print('\n=== TEST 2: Subword Parasitism (top1_succ > 0.95) ===')
parasites = [t for t in toks if t['top1_succ'] > 0.95]
print(f'  Tokens with top1_succ > 0.95: {len(parasites)}')
for t in sorted(parasites, key=lambda x: -x['top1_succ'])[:15]:
    print(f"    {t['readable']:15s} cls={t['cls']:10s} top1_succ={t['top1_succ']:.4f} top1_pred={t['top1_pred']:.3f} freq={t['freq']:>8d}")
g_parasites = sum(1 for t in parasites if t['is_grad'])
print(f'  Graduates among parasites: {g_parasites}/{len(parasites)}')

# Check higher thresholds
for thresh in [0.99, 0.95, 0.90, 0.80]:
    p = [t for t in toks if t['top1_succ'] > thresh]
    gp = sum(1 for t in p if t['is_grad'])
    print(f'  top1_succ > {thresh}: {len(p)} tokens, {gp} graduate')

# Also check predecessor side
print('\n  Checking predecessor parasitism (top1_pred > 0.95):')
for thresh in [0.99, 0.95, 0.90]:
    p = [t for t in toks if t['top1_pred'] > thresh]
    gp = sum(1 for t in p if t['is_grad'])
    print(f'    top1_pred > {thresh}: {len(p)} tokens, {gp} graduate')

# === Test 3: Manual decision tree (build by hand to handle small N) ===
print('\n=== TEST 3: Hand-built decision tree ===')
# Rule: graduate iff
#   energy >= E_CRIT (already filtered)
#   AND ( (top1_pred >= 0.30) OR (top1_succ >= 0.45) )
# These thresholds are derived from inspection of the graduate distribution

print('\n  Sweep over rule thresholds: top1_pred >= TP OR top1_succ >= TS')
best = None
for tp in [0.20, 0.25, 0.30, 0.34, 0.40, 0.44]:
    for ts in [0.40, 0.45, 0.49, 0.55, 0.60, 0.65]:
        def rule(t):
            return t['top1_pred'] >= tp or t['top1_succ'] >= ts
        g_p = sum(1 for t in graduates if rule(t))
        nm_p = sum(1 for t in near_miss if rule(t))
        if g_p == 0:
            continue
        precision = g_p / (g_p + nm_p)
        recall = g_p / len(graduates)
        f1 = 2 * precision * recall / (precision + recall) if (precision+recall) > 0 else 0
        if best is None or f1 > best[0]:
            best = (f1, tp, ts, g_p, nm_p, precision, recall)

if best:
    f1, tp, ts, g_p, nm_p, precision, recall = best
    print(f'  Best rule: top1_pred >= {tp} OR top1_succ >= {ts}')
    print(f'  Captures: {g_p}/{len(graduates)} graduates (recall {recall*100:.0f}%)')
    print(f'  False positives: {nm_p}/{len(near_miss)} near-misses')
    print(f'  Precision: {precision*100:.1f}%, F1={f1:.3f}')

# Show which graduates pass / fail the best rule
if best:
    _, tp, ts, *_ = best
    print(f'\n  Per-graduate breakdown for rule (tp={tp}, ts={ts}):')
    for t in sorted(graduates, key=lambda x: -x['freq']):
        passes = t['top1_pred'] >= tp or t['top1_succ'] >= ts
        why = []
        if t['top1_pred'] >= tp:
            why.append(f"top1_pred={t['top1_pred']:.3f}")
        if t['top1_succ'] >= ts:
            why.append(f"top1_succ={t['top1_succ']:.3f}")
        print(f"  {t['readable']:15s} pass={passes}  {' '.join(why)}")

# === Test 4: Show the failing near-misses (false positives) ===
if best:
    _, tp, ts, *_ = best
    print('\n  False positive near-misses (would be predicted GRADUATE but aren\'t):')
    fps = [t for t in near_miss if t['top1_pred'] >= tp or t['top1_succ'] >= ts]
    print(f'  Total false positives: {len(fps)}')
    for t in sorted(fps, key=lambda x: -max(x['top1_pred'], x['top1_succ']))[:15]:
        print(f"    {t['readable']:15s} cls={t['cls']:10s} top1_p={t['top1_pred']:.3f} top1_s={t['top1_succ']:.3f} freq={t['freq']:>8d}")

# === Test 5: Add Goldilocks ceiling: 0.15 <= top1 <= 0.95 ===
print('\n=== TEST 5: Best rule WITH Goldilocks ceiling (top1 < 0.95) ===')
def rule_goldilocks(t, tp, ts):
    pred_anchor = (tp <= t['top1_pred'] <= 0.95)
    succ_anchor = (ts <= t['top1_succ'] <= 0.95)
    return pred_anchor or succ_anchor

best2 = None
for tp in [0.20, 0.25, 0.30, 0.34, 0.40, 0.44]:
    for ts in [0.40, 0.45, 0.49, 0.55, 0.60, 0.65]:
        g_p = sum(1 for t in graduates if rule_goldilocks(t, tp, ts))
        nm_p = sum(1 for t in near_miss if rule_goldilocks(t, tp, ts))
        if g_p == 0:
            continue
        precision = g_p / (g_p + nm_p)
        recall = g_p / len(graduates)
        f1 = 2 * precision * recall / (precision + recall) if (precision+recall) > 0 else 0
        if best2 is None or f1 > best2[0]:
            best2 = (f1, tp, ts, g_p, nm_p, precision, recall)

if best2:
    f1, tp, ts, g_p, nm_p, precision, recall = best2
    print(f'  Best Goldilocks rule: ({tp} <= top1_pred <= 0.95) OR ({ts} <= top1_succ <= 0.95)')
    print(f'  Captures: {g_p}/{len(graduates)} graduates (recall {recall*100:.0f}%)')
    print(f'  False positives: {nm_p}/{len(near_miss)} near-misses')
    print(f'  Precision: {precision*100:.1f}%, F1={f1:.3f}')
