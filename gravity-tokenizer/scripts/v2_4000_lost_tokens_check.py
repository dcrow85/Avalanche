"""
Check the tokens that were classifier-QUIESCENT at some snapshot of v2-4000
but are NOT in the step-4000 classifier-QUIESCENT set.

For each such token, report:
  - first classifier-QUIESCENT snapshot
  - last classifier-QUIESCENT snapshot
  - fixed state at step 4000 under the step-4000 thresholds
    (FIXED_QUIET / FIXED_MARGINAL / FIXED_CRYSTAL / FIXED_DEBRIS)

This answers: was the apparent boundary layer purely quantile-ranking drift
inside a stable quiet pool, or is there a real outward-motion remainder?
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


def fixed_bucket(pr, aw, p_thresh, w_thresh, w_floor):
    if pr > p_thresh:
        return "FIXED_DEBRIS"
    if aw < w_floor:
        return "FIXED_QUIET"
    if aw > w_thresh:
        return "FIXED_CRYSTAL"
    return "FIXED_MARGINAL"


def main():
    snaps = sorted(LOG_DIR.glob(PATTERN))
    steps = []
    runs = []
    for sp in snaps:
        step = int(sp.stem.rsplit("_", 1)[-1])
        steps.append(step)
        runs.append(load(sp))

    # Late thresholds from final snapshot
    final_th = runs[-1]["thresholds"]
    P = final_th["panic_threshold"]
    WT = final_th["work_threshold"]
    WF = final_th["work_floor"]

    # Classifier QUIESCENT per snapshot
    classifier_grad = []
    for ps in runs:
        classifier_grad.append(
            {r["piece"] for r in ps["rows"] if is_quiescent_classification(r.get("classification"))}
        )

    ever_grad = set()
    for g in classifier_grad:
        ever_grad |= g
    final_grad = classifier_grad[-1]

    lost = sorted(ever_grad - final_grad)
    print(f"Union classifier QUIESCENT across all 8 snapshots: {len(ever_grad)}")
    print(f"Step-4000 classifier QUIESCENT:                    {len(final_grad)}")
    print(f"Lost tokens (union \\ final):                 {len(lost)}")
    print()

    # Build per-token lookup of (pr, aw) at each snapshot
    def get_row(ps, piece):
        for r in ps["rows"]:
            if r.get("piece") == piece:
                return r
        return None

    # For each lost token, compute first/last classifier-QUIESCENT snapshot
    # and fixed bucket at step 4000
    print(f"{'token':<14}  {'first QUIET':>11}  {'last QUIET':>10}  "
          f"{'pr@4000':>8}  {'aw@4000':>12}  {'fixed@4000':<16}  {'cls@4000':<10}")
    print("-" * 95)

    # Count destinations
    from collections import Counter
    dest = Counter()

    rows = []
    for piece in lost:
        first_step = None
        last_step = None
        for i, g in enumerate(classifier_grad):
            if piece in g:
                if first_step is None:
                    first_step = steps[i]
                last_step = steps[i]
        final_row = get_row(runs[-1], piece)
        if final_row is None:
            bucket = "NOT_DYNAMIC"
            pr_f = 0.0
            aw_f = 0.0
            cls_f = "?"
        else:
            pr_f = final_row.get("panic_ratio", 0)
            aw_f = final_row.get("active_work", 0)
            bucket = fixed_bucket(pr_f, aw_f, P, WT, WF)
            cls_f = final_row.get("classification", "?")
        dest[bucket] += 1
        rows.append((piece, first_step, last_step, pr_f, aw_f, bucket, cls_f))

    # Sort by bucket then by token
    bucket_order = {"FIXED_QUIET": 0, "FIXED_MARGINAL": 1, "FIXED_CRYSTAL": 2, "FIXED_DEBRIS": 3, "NOT_DYNAMIC": 4}
    rows.sort(key=lambda r: (bucket_order.get(r[5], 99), r[0]))

    for piece, first, last, pr, aw, bucket, cls in rows:
        print(f"{piece!r:<14}  {first!s:>11}  {last!s:>10}  "
              f"{pr:>8.3f}  {aw:>12.0f}  {bucket:<16}  {cls:<10}")

    print()
    print(f"Destination histogram at step 4000 (where did the 'lost' tokens go?):")
    for b, n in sorted(dest.items(), key=lambda x: -x[1]):
        print(f"  {b:<16} {n:>5}")

    print()
    n_quiet = dest.get("FIXED_QUIET", 0)
    n_other = sum(n for b, n in dest.items() if b != "FIXED_QUIET")
    pct_quiet = n_quiet / max(len(lost), 1) * 100
    print(f"Still in FIXED_QUIET at step 4000: {n_quiet}/{len(lost)} ({pct_quiet:.0f}%)")
    print(f"Moved out of FIXED_QUIET:          {n_other}/{len(lost)} ({100-pct_quiet:.0f}%)")
    print()
    if n_other == 0:
        print("VERDICT: the entire boundary layer is quantile-ranking drift inside the")
        print("         fixed-quiet pool. No token that was ever classifier-QUIESCENT has left the")
        print("         raw-quiet region. Strongest form of the retraction is justified.")
    else:
        print(f"VERDICT: {n_quiet} lost tokens are still fixed-quiet (quantile drift),")
        print(f"         but {n_other} tokens DID leave the fixed-quiet region — genuine")
        print(f"         outward motion. Writeup should reflect a mixed boundary:")
        print(f"         some quantile drift, some real departure.")


if __name__ == "__main__":
    main()
