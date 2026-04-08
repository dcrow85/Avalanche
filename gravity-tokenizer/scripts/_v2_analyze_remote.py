"""Analyze v2 coherence run on the pod. Load phase_space + coherence snapshot, count graduates."""
import json
import sys

from classification_compat import is_quiescent_classification, normalize_phase_space_snapshot

sys.stdout.reconfigure(encoding="utf-8")

PS = "logs/gravity_v2_coherence_seed_1337_phase_space.json"
SNAP = "logs/gravity_v2_coherence_seed_1337_coherence_snapshot.json"

ps = normalize_phase_space_snapshot(json.load(open(PS, encoding="utf-8")))
snap = json.load(open(SNAP, encoding="utf-8"))

print("thresholds:", json.dumps(ps["thresholds"], indent=1))
print()
print("class_counts:", ps["class_counts"])

rows = ps["rows"]
energy_map = {r["token_id"]: r["grad_energy_total"] for r in snap["rows"]}

grads = [r for r in rows if is_quiescent_classification(r.get("classification"))]
print()
print(f"=== GRADUATES: {len(grads)} ===")
for r in sorted(grads, key=lambda x: x.get("corpus_frequency", 0)):
    piece = r["piece"]
    freq = r["corpus_frequency"]
    lev = r["ablation_leverage"]
    panic = r["panic_ratio"]
    work = r["active_work"]
    e = energy_map.get(r["token_id"], 0.0)
    print(f"  {piece!r:18} freq={freq:>8}  lev={lev:.3f}  panic={panic:.3f}  work={work:.0f}  E={e:.2f}")

dyn = [r for r in rows if r.get("classification") not in (None, "STATIC")]
E_CRIT = 1.20
crossers = [r for r in dyn if energy_map.get(r["token_id"], 0.0) >= E_CRIT]

print()
print(f"Dynamic tokens:                 {len(dyn)}")
print(f"Crossed E_crit ({E_CRIT}):          {len(crossers)}")
print(f"Graduates:                      {len(grads)}")
if crossers:
    print(f"Conditional graduation rate:   {len(grads)/len(crossers)*100:.1f}%")
print(f"Unconditional grad rate:        {len(grads)/max(len(dyn),1)*100:.2f}%")

# Energy histogram by class
from collections import defaultdict
import statistics
by_class = defaultdict(list)
for r in dyn:
    by_class[r["classification"]].append(energy_map.get(r["token_id"], 0.0))
print()
print("Energy by classification:")
for c, es in sorted(by_class.items()):
    es = sorted(es)
    if es:
        med = statistics.median(es)
        print(f"  {c:10} n={len(es):4}  min={min(es):.4f}  median={med:.4f}  max={max(es):.4f}")
