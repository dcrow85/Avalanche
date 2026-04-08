"""Test successor entropy as the Stage 2 mechanism, especially for ed vs er."""
import json
import math
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
    toks.append({
        'tid': tid,
        'readable': psr.get('readable', f'?{tid}'),
        'cls': psr.get('classification', '?'),
        'energy': cr['grad_energy_total'],
        'freq': bgr.get('freq', 0),
        'h_pred': bgr.get('predecessor_entropy_bits'),
        'h_succ': bgr.get('successor_entropy_bits'),
        'top1_pred': bgr.get('top1_predecessor_frac'),
        'top1_succ': bgr.get('top1_successor_frac'),
        'top3_pred': bgr.get('top3_predecessor_frac'),
        'top3_succ': bgr.get('top3_successor_frac'),
    })

eligible = [t for t in toks if t['energy'] >= E_CRIT and t['h_succ'] is not None]
graduates = [t for t in eligible if is_quiescent_classification(t['cls'])]
near_miss = [t for t in eligible if t['cls'] in ('IMMATURE','DEBRIS','MARGINAL','CRYSTAL')]

print(f'Eligible above floor: {len(eligible)}')
print(f'  graduates: {len(graduates)}')
print(f'  near-miss: {len(near_miss)}')

def stats(label, items, key):
    vals = [t[key] for t in items if t.get(key) is not None]
    if not vals:
        return
    print(f'  {label:15s} n={len(vals):3d}  min={min(vals):>9.3f}  med={statistics.median(vals):>9.3f}  max={max(vals):>9.3f}')

print('\n=== SUCCESSOR ENTROPY (bits) ===')
stats('Graduates', graduates, 'h_succ')
stats('Near-misses', near_miss, 'h_succ')

print('\n=== TOP-1 SUCCESSOR FRACTION ===')
stats('Graduates', graduates, 'top1_succ')
stats('Near-misses', near_miss, 'top1_succ')

print('\n=== TOP-3 SUCCESSOR FRACTION ===')
stats('Graduates', graduates, 'top3_succ')
stats('Near-misses', near_miss, 'top3_succ')

print('\n=== KEY TEST: er vs ed (ubiquitous suffixes) ===')
for name in ['er', 'ed', 'ng', 'nd', 'have', 'will', 'your', 'ck', 'nal']:
    for t in toks:
        if t['readable'] == name and t.get('h_succ') is not None:
            print(f"  {t['readable']:8s} cls={t['cls']:10s} freq={t['freq']:>9d}  H_pred={t['h_pred']:>5.2f} top1_p={t['top1_pred']:.3f}  |  H_succ={t['h_succ']:>5.2f} top1_s={t['top1_succ']:.3f} top3_s={t['top3_succ']:.3f}")

print('\n=== ALL ELIGIBLE GRADUATES (both directions) ===')
print(f'{"token":15s} {"freq":>10s}  {"H_pred":>7s} {"top1_p":>7s}  {"H_succ":>7s} {"top1_s":>7s}')
for t in sorted(graduates, key=lambda x: -x['freq']):
    print(f"{t['readable']:15s} {t['freq']:>10d}  {t['h_pred']:>7.2f} {t['top1_pred']:>7.3f}  {t['h_succ']:>7.2f} {t['top1_succ']:>7.3f}")

# Combined predictability score: low successor entropy + low predecessor entropy
print('\n=== COMBINED ENTROPY (predecessor + successor) ===')
for t in eligible:
    t['h_combined'] = t['h_pred'] + t['h_succ']
stats('Graduates', graduates, 'h_combined')
stats('Near-misses', near_miss, 'h_combined')

# Top-1 frac combined
for t in eligible:
    t['top1_combined'] = t['top1_pred'] + t['top1_succ']
print('\n=== COMBINED TOP-1 FRACTION (predecessor + successor) ===')
stats('Graduates', graduates, 'top1_combined')
stats('Near-misses', near_miss, 'top1_combined')

print('\n=== SUCCESSOR ENTROPY AS PREDICTOR (lowest first) ===')
ranked = sorted(eligible, key=lambda t: t['h_succ'])
n_g = len(graduates)
for n in [n_g, 2*n_g, 3*n_g, 5*n_g, 10*n_g]:
    if n > len(ranked):
        continue
    top = ranked[:n]
    hits = sum(1 for t in top if is_quiescent_classification(t['cls']))
    print(f'  Top-{n:>3d}: {hits}/{n_g}  prec={hits/n*100:.1f}%  recall={hits/n_g*100:.1f}%')

print('\n=== TOP-1 SUCCESSOR FRACTION AS PREDICTOR (highest first) ===')
ranked2 = sorted(eligible, key=lambda t: -t['top1_succ'])
for n in [n_g, 2*n_g, 3*n_g, 5*n_g, 10*n_g]:
    if n > len(ranked2):
        continue
    top = ranked2[:n]
    hits = sum(1 for t in top if is_quiescent_classification(t['cls']))
    print(f'  Top-{n:>3d}: {hits}/{n_g}  prec={hits/n*100:.1f}%  recall={hits/n_g*100:.1f}%')

print('\n=== COMBINED H (lowest sum first) ===')
ranked3 = sorted(eligible, key=lambda t: t['h_combined'])
for n in [n_g, 2*n_g, 3*n_g, 5*n_g, 10*n_g]:
    if n > len(ranked3):
        continue
    top = ranked3[:n]
    hits = sum(1 for t in top if is_quiescent_classification(t['cls']))
    print(f'  Top-{n:>3d}: {hits}/{n_g}  prec={hits/n*100:.1f}%  recall={hits/n_g*100:.1f}%')

print('\n=== COMBINED TOP-1 (highest first) ===')
ranked4 = sorted(eligible, key=lambda t: -t['top1_combined'])
for n in [n_g, 2*n_g, 3*n_g, 5*n_g, 10*n_g]:
    if n > len(ranked4):
        continue
    top = ranked4[:n]
    hits = sum(1 for t in top if is_quiescent_classification(t['cls']))
    print(f'  Top-{n:>3d}: {hits}/{n_g}  prec={hits/n*100:.1f}%  recall={hits/n_g*100:.1f}%')

# Frequency-controlled successor entropy comparison
import math as m
print('\n=== FREQUENCY-CONTROLLED SUCCESSOR ENTROPY ===')
print(f'  {"grad":15s} {"freq":>9s} {"H_succ":>7s} {"H_nm_med":>9s} {"ratio":>6s}')
for grad in sorted(graduates, key=lambda t: t['freq']):
    matched = sorted(near_miss, key=lambda nm: abs(m.log(max(nm['freq'], 1)) - m.log(max(grad['freq'], 1))))[:5]
    h_nm = statistics.median([n['h_succ'] for n in matched])
    ratio = grad['h_succ'] / h_nm if h_nm > 0 else float('inf')
    print(f"  {grad['readable']:15s} {grad['freq']:>9d} {grad['h_succ']:>7.2f} {h_nm:>9.2f} {ratio:>6.2f}")
