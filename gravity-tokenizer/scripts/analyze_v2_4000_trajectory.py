"""
Analyze the v2-4000 time-evolution probe trajectory.

This script reports the moving classifier's QUIESCENT slice over time:
  1. stable quiet core size
  2. union size of tokens ever classified QUIESCENT
  3. swap rate per interval between consecutive QUIESCENT sets

Important caveat:
  the moving classifier uses per-snapshot quantile thresholds, so this script is
  useful for ranking drift and slice turnover, not for absolute "graduation"
  claims. Use the fixed-threshold replay alongside it for raw-metric stability.
"""
import json
import sys
from pathlib import Path

from classification_compat import is_quiescent_classification, normalize_phase_space_snapshot

sys.stdout.reconfigure(encoding="utf-8")

LOG_DIR = Path("C:/Avalanche/gravity-tokenizer/parameter-golf/logs/coherence_v2_seed_1337")
PATTERN = "gravity_v2_4000_coherence_seed_1337_phase_space_step_*.json"
REF = LOG_DIR / "gravity_v2_coherence_seed_1337_phase_space.json"


def load_full_snapshot(path: Path) -> dict:
    """Return the full phase_space snapshot for rank-trace analysis."""
    return normalize_phase_space_snapshot(json.loads(path.read_text(encoding="utf-8")))


def panic_ranks_at_step(ps: dict) -> dict[str, int]:
    """Return {piece: 1-indexed rank} sorted by panic_ratio descending.
    Only over dynamic (non-static) tokens.
    """
    dyn = [r for r in ps["rows"] if r.get("classification") not in (None, "STATIC")]
    dyn.sort(key=lambda r: -r.get("panic_ratio", 0))
    return {r["piece"]: i + 1 for i, r in enumerate(dyn)}


def work_ranks_at_step(ps: dict) -> dict[str, int]:
    dyn = [r for r in ps["rows"] if r.get("classification") not in (None, "STATIC")]
    dyn.sort(key=lambda r: -r.get("active_work", 0))
    return {r["piece"]: i + 1 for i, r in enumerate(dyn)}


def main():
    snaps = sorted(LOG_DIR.glob(PATTERN))
    if not snaps:
        print("No snapshots found yet.")
        return

    print(f"Analyzing {len(snaps)} snapshot(s) from v2-4000 probe")
    print()

    # Per-snapshot data
    steps = []
    quiet_sets = []
    panic_thresh = []
    work_thresh = []
    panic_ranks_per_step = []
    work_ranks_per_step = []
    for sp in snaps:
        step = int(sp.stem.rsplit("_", 1)[-1])
        full = load_full_snapshot(sp)
        quiet = {r["piece"] for r in full["rows"] if is_quiescent_classification(r.get("classification"))}
        th = full.get("thresholds", {})
        steps.append(step)
        quiet_sets.append(quiet)
        panic_thresh.append(th.get("panic_threshold", 0))
        work_thresh.append(th.get("work_threshold", 0))
        panic_ranks_per_step.append(panic_ranks_at_step(full))
        work_ranks_per_step.append(work_ranks_at_step(full))

    # Three traces
    print(f"{'step':>6} {'QUIET':>5} {'core':>5} {'union':>5} {'swap':>5}  {'core/union':>10}  {'panic':>7} {'work':>9}")
    print("-" * 78)
    union = set()
    core = None
    prev_quiet = None
    for i, step in enumerate(steps):
        g = quiet_sets[i]
        union |= g
        if core is None:
            core = set(g)
        else:
            core &= g
        if prev_quiet is None:
            swap = 0
        else:
            joined = g - prev_quiet
            left = prev_quiet - g
            swap = len(joined) + len(left)
        ratio = len(core) / len(union) if union else 0
        print(f"{step:>6} {len(g):>5} {len(core):>5} {len(union):>5} {swap:>5}  {ratio:>9.3f}  "
              f"{panic_thresh[i]:>7.3f} {work_thresh[i]:>9.0f}")
        prev_quiet = g

    # Reference
    if REF.exists():
        ref = normalize_phase_space_snapshot(json.loads(REF.read_text(encoding="utf-8")))
        cc = ref["class_counts"]
        th = ref.get("thresholds", {})
        print(f"{'2903':>6} {cc.get('QUIESCENT',0):>5} {'-':>5} {'-':>5} {'-':>5}  {'-':>10}  "
              f"{th.get('panic_threshold',0):>7.3f} {th.get('work_threshold',0):>9.0f}  <-- v2-2903 final")

    # Detail: tokens that moved between last two snapshots
    if len(quiet_sets) >= 2:
        prev = quiet_sets[-2]
        curr = quiet_sets[-1]
        joined = sorted(curr - prev)
        left = sorted(prev - curr)
        print()
        print(f"Last interval ({steps[-2]} -> {steps[-1]}):")
        print(f"  joined: {joined}")
        print(f"  left:   {left}")

    # Stable core token list
    if core:
        print()
        print(f"Stable quiet core ({len(core)} tokens QUIESCENT in all {len(steps)} snapshots):")
        print(f"  {sorted(core)}")

    # Boundary layer (in union but not in core)
    boundary = union - (core or set())
    if boundary:
        print()
        print(f"Boundary layer ({len(boundary)} tokens ever QUIESCENT but not always):")
        print(f"  {sorted(boundary)}")

    # ----------------------------------------------------------------------
    # Trace 1: Jaccard overlap between consecutive QUIESCENT sets
    # ----------------------------------------------------------------------
    print()
    print("Jaccard overlap between consecutive QUIESCENT sets:")
    print(f"  {'interval':>14}  {'|A|':>4} {'|B|':>4} {'|A∩B|':>6} {'|A∪B|':>6}  {'jaccard':>8}")
    for i in range(1, len(quiet_sets)):
        A = quiet_sets[i-1]
        B = quiet_sets[i]
        inter = A & B
        union_ab = A | B
        jac = len(inter) / len(union_ab) if union_ab else 0
        print(f"  {steps[i-1]:>5}->{steps[i]:<6}  {len(A):>4} {len(B):>4} {len(inter):>6} {len(union_ab):>6}  {jac:>8.3f}")

    # ----------------------------------------------------------------------
    # Trace 2: dwell time per token across snapshots
    # First snapshot, last snapshot, total occurrences
    # ----------------------------------------------------------------------
    union = set()
    for g in quiet_sets:
        union |= g
    dwell = {}
    for piece in union:
        firsts = [i for i, g in enumerate(quiet_sets) if piece in g]
        lasts = firsts
        dwell[piece] = {
            "first": steps[firsts[0]] if firsts else None,
            "last": steps[lasts[-1]] if lasts else None,
            "count": len(firsts),
            "total_possible": len(quiet_sets),
            "indices": firsts,
        }

    # Histogram of dwell counts
    from collections import Counter
    dwell_hist = Counter(d["count"] for d in dwell.values())
    print()
    print("Dwell-time histogram (how many snapshots each token spends in QUIESCENT):")
    print(f"  {'snapshots in QUIET':>20} {'#tokens':>10}")
    for k in sorted(dwell_hist.keys(), reverse=True):
        n = dwell_hist[k]
        marker = "  <-- stable core" if k == len(quiet_sets) else ""
        marker += "  <-- single-snapshot tourists" if k == 1 else ""
        print(f"  {k:>20} {n:>10}{marker}")

    # Identify tourists (single-snapshot only) explicitly
    tourists = sorted([p for p, d in dwell.items() if d["count"] == 1])
    if tourists:
        print(f"  Tourists (1-snapshot dwell): {tourists}")

    # ----------------------------------------------------------------------
    # Trace 3: raw rank traces for boundary tokens on panic and work
    # For each token in the union, show its panic rank in each snapshot
    # ----------------------------------------------------------------------
    core_tokens = sorted(set.intersection(*quiet_sets) if quiet_sets else set())
    boundary_tokens = sorted(union - set(core_tokens))

    print()
    print("Raw panic_ratio rank trajectories (rank 1 = most panicky; higher ranks are quieter):")
    print(f"{'token':<14}  " + "  ".join(f"s{s:>5}" for s in steps))
    print(f"{'-' * 14}  " + "  ".join("-" * 6 for _ in steps))
    print("STABLE CORE (should stay toward the quiet end of the rank list):")
    for piece in core_tokens:
        ranks = [panic_ranks_per_step[i].get(piece, "-") for i in range(len(steps))]
        print(f"  {piece!r:<12}  " + "  ".join(f"{r:>6}" if r != "-" else f"{'-':>6}" for r in ranks))
    print("BOUNDARY (rank should hover near the moving cut):")
    for piece in boundary_tokens:
        ranks = [panic_ranks_per_step[i].get(piece, "-") for i in range(len(steps))]
        in_grad = ["Q" if piece in quiet_sets[i] else "." for i in range(len(steps))]
        print(f"  {piece!r:<12}  " + "  ".join(f"{r:>5}{m}" if r != "-" else f"{'-':>6}" for r, m in zip(ranks, in_grad)))

    # Observed turnover summary
    print()
    print("=" * 78)
    print("Observed turnover summary")
    print("=" * 78)
    if len(steps) >= 2:
        recent_quiet_counts = [len(g) for g in quiet_sets[-3:]]
        print(f"  Recent QUIESCENT counts: {recent_quiet_counts}")
        recent_swaps = []
        for i in range(max(1, len(quiet_sets) - 3), len(quiet_sets)):
            j = (quiet_sets[i] - quiet_sets[i-1]) | (quiet_sets[i-1] - quiet_sets[i])
            recent_swaps.append(len(j))
        print(f"  Recent swap counts: {recent_swaps}")
        recent_jaccards = []
        for i in range(max(1, len(quiet_sets) - 3), len(quiet_sets)):
            prev = quiet_sets[i - 1]
            curr = quiet_sets[i]
            recent_jaccards.append(len(prev & curr) / len(prev | curr) if (prev | curr) else 0.0)
        print(f"  Recent Jaccards: {[round(j, 3) for j in recent_jaccards]}")
        print("  Read this alongside the fixed-threshold replay:")
        print("    this script shows movement within the moving classifier slice,")
        print("    not absolute entry into or exit from raw quietness.")


if __name__ == "__main__":
    main()
