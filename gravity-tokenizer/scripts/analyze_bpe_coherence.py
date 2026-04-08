"""
Analyze BPE coherence run and compare against gravity findings:
1. Stage 1: where is the volume floor for BPE?
2. Conditional graduation rate above the BPE floor
3. Type A/B/C distribution among BPE graduates
4. Parasitism check (top1_succ > 0.95)
5. Decision tree multi-feature analysis
"""
import json
import statistics

from classification_compat import is_quiescent_classification, normalize_phase_space_snapshot

BPE = 'C:/Avalanche/gravity-tokenizer/parameter-golf/logs/coherence_bpe_seed_1337'
GRAV = 'C:/Avalanche/gravity-tokenizer/parameter-golf/logs/coherence_seed_1337'


def load_run(prefix, vocab_label):
    coh = json.load(open(f'{prefix}/{vocab_label}_coherence_snapshot.json'))
    ps = normalize_phase_space_snapshot(json.load(open(f'{prefix}/{vocab_label}_phase_space.json')))
    return coh, ps


def build_token_table(coh, ps, bg):
    ps_rows = {r['token_id']: r for r in ps['rows']}
    coh_rows = {r['token_id']: r for r in coh['rows']}
    bg_rows = {r['token_id']: r for r in bg}
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
            'is_grad': is_quiescent_classification(psr.get('classification')),
            'is_static': psr.get('classification') == 'STATIC' or psr.get('is_static_core'),
            'energy': cr['grad_energy_total'],
            'grad_max': cr['grad_magnitude_max'],
            'updates': cr['update_count'],
            'freq_corp': psr.get('corpus_frequency', 0),
            'freq_data': bgr.get('freq', 0),
            'h_pred': bgr.get('predecessor_entropy_bits'),
            'h_succ': bgr.get('successor_entropy_bits'),
            'top1_pred': bgr.get('top1_predecessor_frac'),
            'top1_succ': bgr.get('top1_successor_frac'),
        })
    return toks


# Load both runs
print('=' * 70)
print('LOADING BPE')
print('=' * 70)
bpe_coh, bpe_ps = load_run(BPE, 'bpe_coherence_seed_1337')
bpe_bg = json.load(open(f'{BPE}/bpe_bigram_entropy.json'))
bpe_toks = build_token_table(bpe_coh, bpe_ps, bpe_bg)
print(f'BPE total dynamic tokens: {len(bpe_toks)}')
print(f'BPE class counts:')
for cls, n in sorted(bpe_ps['class_counts'].items(), key=lambda x: -x[1]):
    print(f'  {cls}: {n}')

print('\n' + '=' * 70)
print('LOADING GRAVITY (for comparison)')
print('=' * 70)
grav_coh, grav_ps = load_run(GRAV, 'gravity_coherence_seed_1337')
grav_bg = json.load(open(f'{GRAV}/bigram_entropy.json'))
grav_toks = build_token_table(grav_coh, grav_ps, grav_bg)
print(f'Gravity total dynamic tokens: {len(grav_toks)}')
print(f'Gravity class counts:')
for cls, n in sorted(grav_ps['class_counts'].items(), key=lambda x: -x[1]):
    print(f'  {cls}: {n}')


def analyze_stage1(label, toks):
    print(f'\n{"=" * 70}')
    print(f'STAGE 1 ANALYSIS: {label}')
    print('=' * 70)
    grads = [t for t in toks if t['is_grad']]
    print(f'  Total dynamic tokens: {len(toks)}')
    print(f'  Graduates: {len(grads)}')

    # Find lowest-energy graduate (volume floor)
    if grads:
        grad_energies = sorted([t['energy'] for t in grads])
        E_CRIT = grad_energies[0]
        print(f'  Lowest graduate energy (E_crit): {E_CRIT:.4f}')
        print(f'  Graduate energy range: {grad_energies[0]:.3f} - {grad_energies[-1]:.3f}')

        # Tokens above floor
        above = [t for t in toks if t['energy'] >= E_CRIT and not t['is_static']]
        below = [t for t in toks if t['energy'] < E_CRIT and not t['is_static']]
        print(f'  Tokens above floor (excluding STATIC): {len(above)}')
        print(f'  Tokens below floor: {len(below)}')
        below_grads = sum(1 for t in below if t['is_grad'])
        print(f'  Graduates below floor (should be 0): {below_grads}')

        # Conditional graduation rate
        above_grads = sum(1 for t in above if t['is_grad'])
        if above:
            rate = above_grads / len(above)
            print(f'  Conditional graduation rate above floor: {above_grads}/{len(above)} = {rate*100:.1f}%')
        return E_CRIT
    return None


bpe_floor = analyze_stage1('BPE', bpe_toks)
grav_floor = analyze_stage1('GRAVITY', grav_toks)


def analyze_stage2(label, toks, floor):
    print(f'\n{"=" * 70}')
    print(f'STAGE 2 ANALYSIS: {label}')
    print('=' * 70)
    eligible = [t for t in toks if t['energy'] >= floor and not t['is_static'] and t.get('h_pred') is not None]
    grads = [t for t in eligible if t['is_grad']]
    nm = [t for t in eligible if not t['is_grad']]
    print(f'  Eligible above floor: {len(eligible)}')
    print(f'  Graduates: {len(grads)}, Near-miss: {len(nm)}')
    print(f'  Conditional graduation rate: {len(grads)}/{len(eligible)} = {len(grads)/max(len(eligible),1)*100:.1f}%')

    # Type classification
    print(f'\n  Type distribution among graduates:')
    type_a = []  # predecessor-locked: high top1_pred
    type_b = []  # successor-locked: high top1_succ
    type_c = []  # extreme volume
    type_other = []
    for t in grads:
        if t['top1_pred'] >= 0.30 and t['h_pred'] < 4.0:
            type_a.append(t)
        elif t['top1_succ'] >= 0.55 and t['h_succ'] < 4.0:
            type_b.append(t)
        elif t['freq_data'] > 10_000_000:
            type_c.append(t)
        else:
            type_other.append(t)
    print(f'    Type A (predecessor-locked, top1_pred>=0.30, h_pred<4): {len(type_a)}')
    for t in type_a[:8]:
        print(f"      {t['readable']:15s} h_p={t['h_pred']:.2f} top1_p={t['top1_pred']:.3f}")
    print(f'    Type B (successor-locked, top1_succ>=0.55, h_succ<4): {len(type_b)}')
    for t in type_b[:8]:
        print(f"      {t['readable']:15s} h_s={t['h_succ']:.2f} top1_s={t['top1_succ']:.3f}")
    print(f'    Type C (extreme volume, freq>10M): {len(type_c)}')
    for t in type_c[:5]:
        print(f"      {t['readable']:15s} freq={t['freq_data']:>10d}")
    print(f'    Other / unclassified: {len(type_other)}')
    for t in type_other[:8]:
        print(f"      {t['readable']:15s} freq={t['freq_data']:>9d} h_p={t['h_pred']:.2f} top1_p={t['top1_pred']:.3f} h_s={t['h_succ']:.2f} top1_s={t['top1_succ']:.3f}")

    # Parasitism check
    parasites = [t for t in eligible if t['top1_succ'] is not None and t['top1_succ'] > 0.95]
    grad_parasites = sum(1 for t in parasites if t['is_grad'])
    print(f'\n  Subword parasitism (top1_succ > 0.95): {len(parasites)} tokens, {grad_parasites} graduate')
    for t in sorted(parasites, key=lambda x: -x['top1_succ'])[:10]:
        marker = '*GRAD*' if t['is_grad'] else t['cls']
        print(f"    {t['readable']:15s} top1_s={t['top1_succ']:.4f} {marker}")

    return eligible, grads, nm


bpe_elig, bpe_g, bpe_n = analyze_stage2('BPE', bpe_toks, bpe_floor)
grav_elig, grav_g, grav_n = analyze_stage2('GRAVITY', grav_toks, grav_floor)


print(f'\n{"=" * 70}')
print('SIDE-BY-SIDE COMPARISON')
print('=' * 70)
print(f'{"":15s} {"BPE":>15s} {"GRAVITY":>15s}')
print(f'{"Total dynamic":15s} {len(bpe_toks):>15d} {len(grav_toks):>15d}')
print(f'{"Total grads":15s} {sum(1 for t in bpe_toks if t["is_grad"]):>15d} {sum(1 for t in grav_toks if t["is_grad"]):>15d}')
print(f'{"E_crit":15s} {bpe_floor:>15.3f} {grav_floor:>15.3f}')
print(f'{"Eligible":15s} {len(bpe_elig):>15d} {len(grav_elig):>15d}')
print(f'{"Cond. rate":15s} {len(bpe_g)/max(len(bpe_elig),1)*100:>14.1f}% {len(grav_g)/max(len(grav_elig),1)*100:>14.1f}%')

# Parasitism count
bpe_parasites = sum(1 for t in bpe_elig if t.get('top1_succ', 0) and t['top1_succ'] > 0.95)
grav_parasites = sum(1 for t in grav_elig if t.get('top1_succ', 0) and t['top1_succ'] > 0.95)
print(f'{"Parasites":15s} {bpe_parasites:>15d} {grav_parasites:>15d}')

# Bigram anchoring distribution among ALL eligible tokens
def anchor_count(elig, side='pred', threshold=0.30):
    key = f'top1_{side}'
    return sum(1 for t in elig if t.get(key) and t[key] >= threshold)

print(f'\nBigram anchoring among eligible tokens:')
print(f'{"":25s} {"BPE":>10s} {"GRAVITY":>10s}')
print(f'{"top1_pred >= 0.30":25s} {anchor_count(bpe_elig, "pred", 0.30):>10d} {anchor_count(grav_elig, "pred", 0.30):>10d}')
print(f'{"top1_pred >= 0.50":25s} {anchor_count(bpe_elig, "pred", 0.50):>10d} {anchor_count(grav_elig, "pred", 0.50):>10d}')
print(f'{"top1_succ >= 0.55":25s} {anchor_count(bpe_elig, "succ", 0.55):>10d} {anchor_count(grav_elig, "succ", 0.55):>10d}')
print(f'{"top1_succ >= 0.95 (parasite)":25s} {bpe_parasites:>10d} {grav_parasites:>10d}')

# Show all BPE graduates with full profile
print('\n=== ALL BPE GRADUATES ===')
print(f'{"token":15s} {"cls":10s} {"freq":>10s} {"E":>8s} {"top1_p":>7s} {"top1_s":>7s} {"h_p":>5s} {"h_s":>5s}')
for t in sorted([t for t in bpe_toks if t['is_grad']], key=lambda x: -x['energy']):
    h_p = f"{t['h_pred']:.2f}" if t['h_pred'] is not None else 'N/A'
    h_s = f"{t['h_succ']:.2f}" if t['h_succ'] is not None else 'N/A'
    t1p = f"{t['top1_pred']:.3f}" if t['top1_pred'] is not None else 'N/A'
    t1s = f"{t['top1_succ']:.3f}" if t['top1_succ'] is not None else 'N/A'
    print(f"  {t['readable']:15s} {t['cls']:10s} {t['freq_data']:>10d} {t['energy']:>8.2f} {t1p:>7s} {t1s:>7s} {h_p:>5s} {h_s:>5s}")
