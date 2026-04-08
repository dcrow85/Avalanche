"""Join predecessor entropy with coherence/phase data and test as Stage 2 separator."""
import json
import math
import statistics

from classification_compat import is_quiescent_classification, normalize_phase_space_snapshot

with open('C:/Avalanche/gravity-tokenizer/parameter-golf/logs/coherence_seed_1337/gravity_coherence_seed_1337_coherence_snapshot.json') as f:
    coh = json.load(f)
with open('C:/Avalanche/gravity-tokenizer/parameter-golf/logs/coherence_seed_1337/gravity_coherence_seed_1337_phase_space.json') as f:
    ps = normalize_phase_space_snapshot(json.load(f))
with open('C:/Avalanche/gravity-tokenizer/parameter-golf/logs/coherence_seed_1337/predecessor_entropy.json') as f:
    pe = json.load(f)

ps_rows = {r['token_id']: r for r in ps['rows']}
coh_rows = {r['token_id']: r for r in coh['rows']}
pe_rows = {r['token_id']: r for r in pe}

E_CRIT = 1.20

toks = []
for tid, psr in ps_rows.items():
    cr = coh_rows.get(tid)
    if not cr or not cr.get('is_dynamic'):
        continue
    per = pe_rows.get(tid, {})
    toks.append({
        'tid': tid,
        'readable': psr.get('readable', f'?{tid}'),
        'cls': psr.get('classification', '?'),
        'energy': cr['grad_energy_total'],
        'grad_max': cr['grad_magnitude_max'],
        'freq_corp': psr.get('corpus_frequency', 0),
        'freq_data': per.get('freq', 0),
        'pred_entropy': per.get('predecessor_entropy_bits', None),
        'eff_pred': per.get('effective_predecessors', None),
        'top1_pred': per.get('top1_predecessor_frac', None),
        'top3_pred': per.get('top3_predecessor_frac', None),
    })

eligible = [t for t in toks if t['energy'] >= E_CRIT and t['pred_entropy'] is not None]
graduates = [t for t in eligible if is_quiescent_classification(t['cls'])]
near_miss = [t for t in eligible if t['cls'] in ('IMMATURE', 'DEBRIS', 'MARGINAL', 'CRYSTAL')]

print(f'Eligible above floor with predecessor data: {len(eligible)}')
print(f'  graduates: {len(graduates)}')
print(f'  near-miss: {len(near_miss)}')

def stats(label, items, key):
    vals = [t[key] for t in items if t.get(key) is not None]
    if not vals:
        return
    print(f'  {label:15s} n={len(vals):3d}  min={min(vals):>9.3f}  med={statistics.median(vals):>9.3f}  max={max(vals):>9.3f}')

print('\n=== PREDECESSOR ENTROPY (bits) ===')
stats('Graduates', graduates, 'pred_entropy')
stats('Near-misses', near_miss, 'pred_entropy')

print('\n=== EFFECTIVE PREDECESSORS (perplexity of predecessor dist) ===')
stats('Graduates', graduates, 'eff_pred')
stats('Near-misses', near_miss, 'eff_pred')

print('\n=== TOP-1 PREDECESSOR FRACTION ===')
stats('Graduates', graduates, 'top1_pred')
stats('Near-misses', near_miss, 'top1_pred')

print('\n=== TOP-3 PREDECESSOR FRACTION ===')
stats('Graduates', graduates, 'top3_pred')
stats('Near-misses', near_miss, 'top3_pred')

print('\n=== ALL ELIGIBLE GRADUATES ===')
print(f'{"token":15s} {"freq":>10s} {"H_pred":>8s} {"eff_pr":>8s} {"top1":>6s} {"top3":>6s}')
for t in sorted(graduates, key=lambda x: -x['freq_data']):
    print(f"{t['readable']:15s} {t['freq_data']:>10d} {t['pred_entropy']:>8.2f} {t['eff_pred']:>8.1f} {t['top1_pred']:>6.3f} {t['top3_pred']:>6.3f}")

print('\n=== TOP-15 NEAR-MISSES BY HIGHEST PREDECESSOR ENTROPY ===')
print(f'{"token":15s} {"cls":10s} {"freq":>10s} {"H_pred":>8s} {"eff_pr":>8s} {"top1":>6s}')
for t in sorted(near_miss, key=lambda x: -x['pred_entropy'])[:15]:
    print(f"{t['readable']:15s} {t['cls']:10s} {t['freq_data']:>10d} {t['pred_entropy']:>8.2f} {t['eff_pred']:>8.1f} {t['top1_pred']:>6.3f}")

print('\n=== KEY TEST: er vs ed/ng/nd ===')
for name in ['er', 'ed', 'ng', 'nd', 'have', 'will', 'your']:
    for t in toks:
        if t['readable'] == name and t['pred_entropy'] is not None:
            print(f"  {t['readable']:8s} cls={t['cls']:10s} freq={t['freq_data']:>9d} H={t['pred_entropy']:>5.2f} eff={t['eff_pred']:>6.1f} top1={t['top1_pred']:.3f} top3={t['top3_pred']:.3f}")

print('\n=== PREDECESSOR ENTROPY AS PREDICTOR (lowest entropy first) ===')
ranked = sorted(eligible, key=lambda t: t['pred_entropy'])
n_g = len(graduates)
for n in [n_g, 2*n_g, 3*n_g, 5*n_g, 10*n_g]:
    if n > len(ranked):
        continue
    top = ranked[:n]
    hits = sum(1 for t in top if is_quiescent_classification(t['cls']))
    print(f'  Top-{n:>3d}: {hits}/{n_g} graduates  prec={hits/n*100:.1f}%  recall={hits/n_g*100:.1f}%')

print('\n=== TOP-1 PREDECESSOR FRACTION AS PREDICTOR ===')
ranked2 = sorted(eligible, key=lambda t: -t['top1_pred'])
for n in [n_g, 2*n_g, 3*n_g, 5*n_g, 10*n_g]:
    if n > len(ranked2):
        continue
    top = ranked2[:n]
    hits = sum(1 for t in top if is_quiescent_classification(t['cls']))
    print(f'  Top-{n:>3d}: {hits}/{n_g} graduates  prec={hits/n*100:.1f}%  recall={hits/n_g*100:.1f}%')

print('\n=== FREQUENCY-CONTROLLED PREDECESSOR ENTROPY ===')
print(f'  {"grad":15s} {"freq":>9s} {"H_g":>6s} {"H_nm_med":>9s} {"ratio":>6s}  {"matched_nm":40s}')
for grad in sorted(graduates, key=lambda t: t['freq_data']):
    matched = sorted(near_miss, key=lambda nm: abs(math.log(max(nm['freq_data'], 1)) - math.log(max(grad['freq_data'], 1))))[:5]
    h_nm = statistics.median([m['pred_entropy'] for m in matched])
    ratio = grad['pred_entropy'] / h_nm if h_nm > 0 else float('inf')
    nm_names = ', '.join(f"{m['readable']}" for m in matched[:3])
    print(f"  {grad['readable']:15s} {grad['freq_data']:>9d} {grad['pred_entropy']:>6.2f} {h_nm:>9.2f} {ratio:>6.2f}  [{nm_names}]")
