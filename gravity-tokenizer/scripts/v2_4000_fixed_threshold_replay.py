"""
Fixed-threshold replay for v2-4000 trajectory.

Takes the LATE (step 4000) panic_threshold, work_threshold, and work_floor
values, then applies those same absolute thresholds to every snapshot.

Classifier polarity (from velocity.py):
  QUIESCENT = panic < panic_threshold AND active_work < work_FLOOR
              (stabilized AND no longer doing heavy update work — "in the library")
  CRYSTAL   = panic < panic_threshold AND active_work > work_threshold
              (stable AND still actively useful — "active crystallized")
  DEBRIS    = panic > panic_threshold AND active_work outside [work_floor, work_threshold]
  MARGINAL  = everything else

So QUIESCENT tokens have LOW work, not high work. The fixed-threshold replay must
preserve this polarity.

Design note: raw active_work grows ~50x from step 500 to step 4000 as the EMA
accumulator fills. Using the step-4000 work_floor absolutely on early snapshots
means: at step 500 almost every dynamic token has active_work < work_floor_final
(because work_floor_final is much larger than any step-500 work value), so
"QUIET-by-late-bar" would over-classify early.

The correct question is: of the tokens that eventually become classifier-QUIESCENT
at step 4000, did their raw metrics cross the LATE bar from above or below,
and when? That tells us whether the classifier's apparent stability of the
11-token core is reflecting stable raw values or just drifting quantiles.
"""
import json
import sys
from pathlib import Path

from classification_compat import is_quiescent_classification, normalize_phase_space_snapshot

sys.stdout.reconfigure(encoding="utf-8")

LOG_DIR = Path("C:/Avalanche/gravity-tokenizer/parameter-golf/logs/coherence_v2_seed_1337")
PATTERN = "gravity_v2_4000_coherence_seed_1337_phase_space_step_*.json"


def load(path):
    return normalize_phase_space_snapshot(json.loads(path.read_text(encoding="utf-8")))


def main():
    snaps = sorted(LOG_DIR.glob(PATTERN))
    if not snaps:
        print("No snapshots found.")
        return

    # Load all snapshots
    steps = []
    runs = []
    for sp in snaps:
        step = int(sp.stem.rsplit("_", 1)[-1])
        ps = load(sp)
        steps.append(step)
        runs.append(ps)

    # Take LATE (final) thresholds from the last snapshot
    final = runs[-1]
    final_th = final["thresholds"]
    LATE_PANIC = final_th["panic_threshold"]
    LATE_WORK = final_th["work_threshold"]
    LATE_WORK_FLOOR = final_th["work_floor"]

    print(f"Late bar (from step {steps[-1]}):")
    print(f"  panic_threshold   = {LATE_PANIC:.4f}")
    print(f"  work_threshold    = {LATE_WORK:.4f}")
    print(f"  work_floor        = {LATE_WORK_FLOOR:.4f}")
    print()

    # For each snapshot, apply the step-4000 thresholds with correct polarity:
    #   QUIET   = panic < LATE_PANIC AND active_work < LATE_WORK_FLOOR
    #   CRYSTAL = panic < LATE_PANIC AND active_work > LATE_WORK
    #   DEBRIS  = panic > LATE_PANIC
    #   MARG    = panic < LATE_PANIC AND LATE_WORK_FLOOR <= active_work <= LATE_WORK
    classifier_grad = []
    fixed_grad = []
    fixed_crystal = []
    fixed_marginal = []
    fixed_debris = []
    for ps in runs:
        rows = [r for r in ps["rows"] if r.get("classification") not in (None, "STATIC")]
        cg = {r["piece"] for r in rows if is_quiescent_classification(r.get("classification"))}
        fg = set()
        fc = set()
        fm = set()
        fd = set()
        for r in rows:
            pr = r.get("panic_ratio", 0)
            aw = r.get("active_work", 0)
            if pr > LATE_PANIC:
                fd.add(r["piece"])
            elif aw < LATE_WORK_FLOOR:
                fg.add(r["piece"])
            elif aw > LATE_WORK:
                fc.add(r["piece"])
            else:
                fm.add(r["piece"])
        classifier_grad.append(cg)
        fixed_grad.append(fg)
        fixed_crystal.append(fc)
        fixed_marginal.append(fm)
        fixed_debris.append(fd)

    print(f"{'step':>6} {'CLS_QUIET':>9} {'FIX_QUIET':>9} {'FIX_CRY':>8} {'FIX_MAR':>8} {'FIX_DEB':>8}  {'own_panic':>10} {'own_work':>10}")
    print("-" * 90)
    for i, step in enumerate(steps):
        th = runs[i]["thresholds"]
        print(f"{step:>6} {len(classifier_grad[i]):>9} {len(fixed_grad[i]):>9} "
              f"{len(fixed_crystal[i]):>8} {len(fixed_marginal[i]):>8} {len(fixed_debris[i]):>8}  "
              f"{th.get('panic_threshold', 0):>10.3f} {th.get('work_threshold', 0):>10.0f}")

    # Stability analysis on each trace
    def trace_stats(name, sets):
        union = set()
        core = None
        swaps = []
        jaccards = []
        for i, s in enumerate(sets):
            union |= s
            if core is None:
                core = set(s)
            else:
                core &= s
            if i > 0:
                prev = sets[i - 1]
                swap = len((prev - s) | (s - prev))
                swaps.append(swap)
                jac = len(prev & s) / len(prev | s) if (prev | s) else 0
                jaccards.append(jac)
        mean_swap = sum(swaps) / len(swaps) if swaps else 0
        mean_jac = sum(jaccards) / len(jaccards) if jaccards else 0
        return {
            "name": name,
            "core_size": len(core) if core is not None else 0,
            "union_size": len(union),
            "mean_swap": mean_swap,
            "mean_jaccard": mean_jac,
            "swaps": swaps,
            "jaccards": jaccards,
            "core": sorted(core) if core is not None else [],
        }

    cls_stats = trace_stats("classifier QUIESCENT", classifier_grad)
    fix_stats = trace_stats("fixed-bar QUIET (late)", fixed_grad)

    print()
    print(f"{'trace':<28} {'core':>5} {'union':>6}  {'mean swap':>10} {'mean jacc':>10}")
    print("-" * 78)
    for s in [cls_stats, fix_stats]:
        print(f"{s['name']:<28} {s['core_size']:>5} {s['union_size']:>6}  "
              f"{s['mean_swap']:>10.2f} {s['mean_jaccard']:>10.3f}")

    print()
    print("Per-interval swap rates:")
    print(f"{'trace':<28} " + "  ".join(f"{steps[i-1]}->{steps[i]}" for i in range(1, len(steps))))
    for s in [cls_stats, fix_stats]:
        print(f"{s['name']:<28}  " + "  ".join(f"{sw:>9}" for sw in s["swaps"]))

    print()
    print("Per-interval Jaccards:")
    for s in [cls_stats, fix_stats]:
        print(f"{s['name']:<28}  " + "  ".join(f"{j:>9.3f}" for j in s["jaccards"]))

    # ------------------------------------------------------------------------
    # Overlap between classifier-QUIESCENT set and fixed-bar-QUIET set per snapshot
    # ------------------------------------------------------------------------
    print()
    print("Overlap between classifier QUIESCENT and fixed-bar FIXED_QUIET per snapshot:")
    print(f"{'step':>6} {'cls':>5} {'fix':>5} {'shared':>7} {'cls_only':>10} {'fix_only':>10} {'jaccard':>8}")
    for i, step in enumerate(steps):
        cg = classifier_grad[i]
        fg = fixed_grad[i]
        inter = cg & fg
        union = cg | fg
        jac = len(inter) / len(union) if union else 0
        print(f"{step:>6} {len(cg):>5} {len(fg):>5} {len(inter):>7} {len(cg - fg):>10} {len(fg - cg):>10} {jac:>8.3f}")

    # ------------------------------------------------------------------------
    # For the final step-4000 classifier-QUIESCENT tokens: what do they look like
    # under the fixed late bar at each snapshot?
    # ------------------------------------------------------------------------
    print()
    print("=" * 78)
    print(f"History of the step-4000 classifier-QUIESCENT tokens under the FIXED late bar")
    print("=" * 78)
    print(f"{'token':<14}  " + "  ".join(f"s{s:>5}" for s in steps))
    for piece in sorted(classifier_grad[-1]):
        marks = []
        for i in range(len(steps)):
            if piece in fixed_grad[i]:
                marks.append(" G")     # fixed QUIET
            elif piece in fixed_crystal[i]:
                marks.append(" C")     # fixed CRYSTAL
            elif piece in fixed_marginal[i]:
                marks.append(" M")     # fixed MARGINAL
            elif piece in fixed_debris[i]:
                marks.append(" D")     # fixed DEBRIS
            else:
                marks.append(" .")
        print(f"  {piece!r:<12}  " + "  ".join(f"{m:>6}" for m in marks))

    print()
    print(f"Legend: G=fixed-bar QUIET, C=CRYSTAL, M=MARGINAL, D=DEBRIS (by step-4000 thresholds)")

    # ------------------------------------------------------------------------
    # What about the 11-token classifier stable core?
    # ------------------------------------------------------------------------
    stable_core = set.intersection(*classifier_grad)
    print()
    print("=" * 78)
    print(f"Stable-core tokens ({len(stable_core)}) under FIXED late bar:")
    print("=" * 78)
    print(f"{'token':<14}  " + "  ".join(f"s{s:>5}" for s in steps))
    for piece in sorted(stable_core):
        marks = []
        for i in range(len(steps)):
            if piece in fixed_grad[i]:
                marks.append("G")
            elif piece in fixed_crystal[i]:
                marks.append("C")
            elif piece in fixed_marginal[i]:
                marks.append("M")
            elif piece in fixed_debris[i]:
                marks.append("D")
            else:
                marks.append(".")
        print(f"  {piece!r:<12}  " + "  ".join(f"{m:>6}" for m in marks))

    # ------------------------------------------------------------------------
    # Tokens that would be fixed-bar QUIET continuously — these are the raw quiet pool
    # ------------------------------------------------------------------------
    always_fix_grad = set.intersection(*fixed_grad) if fixed_grad else set()
    print()
    print(f"Tokens classified FIXED-BAR QUIET in every snapshot: {len(always_fix_grad)}")
    if always_fix_grad:
        print(f"  {sorted(always_fix_grad)}")

    # Drift verdict
    print()
    print("=" * 78)
    print("Drift verdict")
    print("=" * 78)
    cls_core = set.intersection(*classifier_grad)
    overlap_core = cls_core & always_fix_grad
    print(f"Classifier stable core: {len(cls_core)} tokens")
    print(f"Fixed-bar quiet pool:   {len(always_fix_grad)} tokens")
    print(f"Intersection:           {len(overlap_core)} tokens")
    if len(cls_core) > 0 and len(overlap_core) / len(cls_core) > 0.7:
        print(f"  -> >70% of classifier stable core is ALSO fixed-bar quiet.")
        print(f"     The 11-token backbone is a REAL raw-metric-stable population.")
    elif len(overlap_core) == 0:
        print(f"  -> Zero overlap. The classifier's stable core is NOT reflecting stable raw metrics.")
        print(f"     The stability is an artifact of how the drifting bar interacts with drifting metrics.")
    else:
        print(f"  -> Partial overlap ({len(overlap_core)}/{len(cls_core)}). Mixed signal.")


if __name__ == "__main__":
    main()
