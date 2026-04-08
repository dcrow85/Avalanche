"""
Fixed-rank replay for v2-4000 trajectory.

The classifier's panic/work thresholds drift across snapshots because they're
quantile-based on per-snapshot population statistics. To separate real raw
movement from threshold drift, we replay the QUIESCENT slice selection using
rank-based criteria that are inherently bar-drift invariant.

For each snapshot, we compute:
  - Top-N tokens by lowest panic_ratio (quietest on the chaos dimension)
  - Top-N tokens by highest active_work (most worked on)
  - Top-N tokens by combined (panic_rank + work_rank) — closest analog to the
    classifier's joint criterion, but rank-based instead of threshold-based

We track how stable each rank-based slice is across snapshots, and compare it
to the classifier's QUIESCENT slice. If the rank-based core is much more stable
than the classifier's core, the back-half churn is largely classifier drift. If
equally unstable, it's real raw reorganization.
"""
import json
import sys
from pathlib import Path

from classification_compat import is_quiescent_classification, normalize_phase_space_snapshot

sys.stdout.reconfigure(encoding="utf-8")

LOG_DIR = Path("C:/Avalanche/gravity-tokenizer/parameter-golf/logs/coherence_v2_seed_1337")
PATTERN = "gravity_v2_4000_coherence_seed_1337_phase_space_step_*.json"

# Number of tokens to take in the fixed-N rank replay.
# 29 = the count v2-2903 settled at; 30 = the value v2-4000 reached at step 3000-3500;
# 31 = v2-4000 final.
N_REPLAY = 29


def load(path):
    return normalize_phase_space_snapshot(json.loads(path.read_text(encoding="utf-8")))


def main():
    snaps = sorted(LOG_DIR.glob(PATTERN))
    print(f"Loaded {len(snaps)} snapshots")
    print()

    # Per-snapshot: build dynamic-token list with panic, work, and the classifier's class
    steps = []
    classifier_grad = []         # set of pieces in classifier's QUIESCENT class
    rank_panic_top = []          # set of pieces in top-N by lowest panic_ratio
    rank_work_top = []           # set of pieces in top-N by highest active_work
    rank_combined_top = []       # set of pieces in top-N by combined panic+work rank
    panic_rank_per_snap = []     # {piece: rank}
    work_rank_per_snap = []
    combined_rank_per_snap = []

    for sp in snaps:
        step = int(sp.stem.rsplit("_", 1)[-1])
        ps = load(sp)
        rows = [r for r in ps["rows"]
                if r.get("classification") not in (None, "STATIC")]

        # rank by panic_ratio ASCENDING (lowest panic = most stable)
        rows_panic = sorted(rows, key=lambda r: r.get("panic_ratio", 0))
        panic_rank = {r["piece"]: i + 1 for i, r in enumerate(rows_panic)}

        # rank by active_work DESCENDING (highest work = most productive)
        rows_work = sorted(rows, key=lambda r: -r.get("active_work", 0))
        work_rank = {r["piece"]: i + 1 for i, r in enumerate(rows_work)}

        # combined: sum of panic_rank + work_rank, lower is better
        combined = {p: panic_rank[p] + work_rank[p] for p in panic_rank}
        rows_combined = sorted(rows, key=lambda r: combined[r["piece"]])
        combined_rank = {r["piece"]: i + 1 for i, r in enumerate(rows_combined)}

        # Top-N sets
        top_panic = {r["piece"] for r in rows_panic[:N_REPLAY]}
        top_work = {r["piece"] for r in rows_work[:N_REPLAY]}
        top_combined = {r["piece"] for r in rows_combined[:N_REPLAY]}

        # Classifier's QUIESCENT set
        grad = {r["piece"] for r in ps["rows"] if is_quiescent_classification(r.get("classification"))}

        steps.append(step)
        classifier_grad.append(grad)
        rank_panic_top.append(top_panic)
        rank_work_top.append(top_work)
        rank_combined_top.append(top_combined)
        panic_rank_per_snap.append(panic_rank)
        work_rank_per_snap.append(work_rank)
        combined_rank_per_snap.append(combined_rank)

    def trace_stats(label, sets):
        union = set()
        for s in sets:
            union |= s
        core = set(sets[0])
        for s in sets[1:]:
            core &= s
        # swap rate
        swaps = []
        for i in range(1, len(sets)):
            sw = len((sets[i] - sets[i-1]) | (sets[i-1] - sets[i]))
            swaps.append(sw)
        # consecutive jaccards
        jaccards = []
        for i in range(1, len(sets)):
            inter = sets[i] & sets[i-1]
            uni = sets[i] | sets[i-1]
            jaccards.append(len(inter) / len(uni) if uni else 0)
        return {
            "label": label,
            "core_size": len(core),
            "union_size": len(union),
            "swap_rates": swaps,
            "jaccards": jaccards,
            "core": sorted(core),
        }

    cls_stats = trace_stats("classifier QUIESCENT", classifier_grad)
    panic_stats = trace_stats(f"top-{N_REPLAY} by panic rank", rank_panic_top)
    work_stats = trace_stats(f"top-{N_REPLAY} by work rank", rank_work_top)
    combined_stats = trace_stats(f"top-{N_REPLAY} by combined rank", rank_combined_top)

    print(f"{'metric':<32} {'core':>5} {'union':>6}  {'mean swap':>10} {'mean jaccard':>13}")
    print("-" * 78)
    for s in [cls_stats, panic_stats, work_stats, combined_stats]:
        msw = sum(s["swap_rates"]) / max(len(s["swap_rates"]), 1)
        mj = sum(s["jaccards"]) / max(len(s["jaccards"]), 1)
        print(f"{s['label']:<32} {s['core_size']:>5} {s['union_size']:>6}  {msw:>10.2f} {mj:>13.3f}")

    print()
    print("Per-interval swap rates:")
    print(f"{'metric':<32}  " + "  ".join(f"{steps[i-1]}->{steps[i]}" for i in range(1, len(steps))))
    for s in [cls_stats, panic_stats, work_stats, combined_stats]:
        print(f"{s['label']:<32}  " + "  ".join(f"{sw:>9}" for sw in s["swap_rates"]))

    print()
    print("Per-interval Jaccards:")
    print(f"{'metric':<32}  " + "  ".join(f"{steps[i-1]}->{steps[i]}" for i in range(1, len(steps))))
    for s in [cls_stats, panic_stats, work_stats, combined_stats]:
        print(f"{s['label']:<32}  " + "  ".join(f"{j:>9.3f}" for j in s["jaccards"]))

    print()
    print(f"=== Stable core sets (tokens in set across ALL {len(snaps)} snapshots) ===")
    print(f"Classifier QUIESCENT core ({len(cls_stats['core'])}):")
    print(f"  {cls_stats['core']}")
    print(f"Top-{N_REPLAY} by panic-rank core ({len(panic_stats['core'])}):")
    print(f"  {panic_stats['core']}")
    print(f"Top-{N_REPLAY} by work-rank core ({len(work_stats['core'])}):")
    print(f"  {work_stats['core']}")
    print(f"Top-{N_REPLAY} by combined-rank core ({len(combined_stats['core'])}):")
    print(f"  {combined_stats['core']}")

    # Cross-check: how much do the rank-based and classifier sets overlap?
    print()
    print("Overlap between classifier QUIESCENT and combined-rank top-N (per snapshot):")
    print(f"{'step':>6} {'cls_QUIET':>9} {'comb_topN':>10} {'intersection':>13} {'jaccard':>8}")
    for i, step in enumerate(steps):
        a = classifier_grad[i]
        b = rank_combined_top[i]
        inter = a & b
        union = a | b
        jac = len(inter) / len(union) if union else 0
        print(f"{step:>6} {len(a):>9} {len(b):>10} {len(inter):>13} {jac:>8.3f}")

    # Final read: is the rank-based core MORE stable than the classifier core?
    print()
    print("=" * 78)
    print("Verdict")
    print("=" * 78)
    cls_core_size = cls_stats['core_size']
    cmb_core_size = combined_stats['core_size']
    cls_swap_mean = sum(cls_stats['swap_rates']) / len(cls_stats['swap_rates'])
    cmb_swap_mean = sum(combined_stats['swap_rates']) / len(combined_stats['swap_rates'])
    print(f"Classifier QUIESCENT core: {cls_core_size} tokens stable across all 8 snapshots, mean swap={cls_swap_mean:.1f}")
    print(f"Combined-rank top-{N_REPLAY} core: {cmb_core_size} tokens stable across all 8 snapshots, mean swap={cmb_swap_mean:.1f}")
    diff = cmb_core_size - cls_core_size
    if cmb_core_size > cls_core_size:
        print(f"  -> Rank-based core is LARGER by {diff} tokens.")
        print(f"  -> Some classifier-QUIESCENT churn is bar-drift artifact: tokens that are stable in raw rank")
        print(f"     but flip in/out of the classifier set due to threshold drift.")
    elif cmb_core_size < cls_core_size:
        print(f"  -> Rank-based core is SMALLER by {-diff} tokens.")
        print(f"  -> The classifier's class definition is more permissive than top-N rank in some snapshots.")
    else:
        print(f"  -> Rank-based and classifier cores are the same size: churn is likely real.")

    if cmb_swap_mean < cls_swap_mean:
        print(f"  -> Rank-based mean swap ({cmb_swap_mean:.1f}) < classifier mean swap ({cls_swap_mean:.1f}).")
        print(f"  -> Confirms some classifier churn is threshold drift, not raw movement.")
    elif cmb_swap_mean > cls_swap_mean:
        print(f"  -> Rank-based mean swap > classifier mean swap.")
        print(f"  -> The classifier is actually MORE stable than rank-based — unexpected.")
    else:
        print(f"  -> Same swap rates: churn is the same regardless of bar definition.")


if __name__ == "__main__":
    main()
