"""
Adversarial-rule search.

Generate many sparse F_2 polynomial rules with mixed-degree monomial sets and
asymmetric variable choices, then SELECT the ones with the lowest max
alignment against the library primitives. This produces adversarial rules
that are demonstrably near-random against the whole library, rather than
hand-designed and hoping for the best.

Campaign-1 local-functional restriction is load-bearing here: the
non-symmetry local-functional screen is the best agreement with the 1024
affine linear functions of the 9 neighborhood bits, not an unrestricted
all-Boolean family.

Each candidate is a polynomial:

    r(b) = c_0 ^ XOR over a few sampled monomials of degrees 1..4

with monomials sampled uniformly from the multilinear monomials over the 9
bits. The rule must:
  * be balanced (256 ± 32 ones out of 512), to avoid trivially-symmetric
    sparse rules,
  * score < 0.60 on every symmetry primitive,
  * score < 0.62 on the best affine linear functional,
  * not duplicate a previously accepted exact rule fingerprint.

Final selection also favors diversity in (degree, monomial_count) signatures.
This script writes an intermediate adversarial_selection.json for the
canonical manifest assembler; it does not emit the frozen manifest artifact.
"""

import numpy as np
import json
import hashlib
from pathlib import Path
from build_manifest import (
    ALL_BITS, N_CONFIGS, build_library_primitives,
    alignment_with_primitive, best_affine_linear_alignment,
    rule_fingerprint, life_rule, parity_rule, f2_rank,
)

BASE_DIR = Path(__file__).resolve().parent
SELECTION_PATH = BASE_DIR / "adversarial_selection.json"


def random_polynomial_rule(rng, n_monomials_range=(4, 9), max_degree=4):
    """Generate a random F_2 polynomial as a rule vector and return
    (rule, description)."""
    n_mon = rng.integers(n_monomials_range[0], n_monomials_range[1] + 1)
    constant = int(rng.integers(0, 2))
    monomials = []
    for _ in range(n_mon):
        deg = int(rng.integers(1, max_degree + 1))
        vars_ = sorted(rng.choice(9, size=deg, replace=False).tolist())
        monomials.append(tuple(vars_))
    # Dedupe (XOR cancellation).
    seen = {}
    for m in monomials:
        seen[m] = seen.get(m, 0) + 1
    monomials = [m for m, c in seen.items() if c % 2 == 1]
    if not monomials and constant == 0:
        return None, None
    r = np.full(N_CONFIGS, constant, dtype=np.int8)
    for m in monomials:
        prod = np.ones(N_CONFIGS, dtype=np.int8)
        for v in m:
            prod &= ALL_BITS[:, v]
        r ^= prod
    desc = {
        "constant": constant,
        "monomials": [list(m) for m in monomials],
        "degree": max((len(m) for m in monomials), default=0),
        "n_monomials": len(monomials),
    }
    return r, desc


def score_rule(rule, primitives):
    scores = {p: alignment_with_primitive(rule, primitives[p]) for p in primitives}
    best_lin, best_lin_coeffs = best_affine_linear_alignment(rule)
    scores["best_affine_linear"] = best_lin
    return scores, best_lin_coeffs


def main():
    primitives = build_library_primitives()

    rng = np.random.default_rng(seed=20260408_1)

    # Search parameters.
    N_TRIALS = 4000
    BALANCE_TOL = 32           # |weight - 256| <= 32
    SYM_THRESHOLD = 0.60       # max symmetry-primitive alignment
    LIN_THRESHOLD = 0.62       # max linear-functional alignment

    accepted = []  # list of (rule, desc, scores)
    fingerprints = set()

    for trial in range(N_TRIALS):
        rule, desc = random_polynomial_rule(rng)
        if rule is None:
            continue
        weight = int(rule.sum())
        if abs(weight - 256) > BALANCE_TOL:
            continue
        scores, lin_coeffs = score_rule(rule, primitives)
        max_sym = max(
            scores["C4_rotation"],
            scores["Z2_horizontal"],
            scores["D4_dihedral"],
            scores["color_inversion"],
            scores["outer_totalistic"],
        )
        if max_sym > SYM_THRESHOLD:
            continue
        if scores["best_affine_linear"] > LIN_THRESHOLD:
            continue
        fp = rule_fingerprint(rule)
        if fp in fingerprints:
            continue
        fingerprints.add(fp)
        accepted.append((rule, desc, scores, lin_coeffs, weight, fp))

    print(f"Accepted {len(accepted)} candidates out of {N_TRIALS} trials.")

    # Score by max alignment, ascending. Take diverse-degree picks: try to
    # include rules with different degrees and different monomial counts.
    accepted.sort(key=lambda x: max(x[2].values()))

    selected = []
    seen_signature = set()
    for rule, desc, scores, lin_coeffs, weight, fp in accepted:
        # Diversity signature: (degree, n_monomials).
        sig = (desc["degree"], desc["n_monomials"])
        if sig in seen_signature:
            continue
        seen_signature.add(sig)
        selected.append((rule, desc, scores, lin_coeffs, weight, fp))
        if len(selected) >= 5:
            break

    if len(selected) < 5:
        # Fall back: fill with the next-best regardless of signature.
        for entry in accepted:
            if entry not in selected:
                selected.append(entry)
            if len(selected) >= 5:
                break

    print()
    print("Selected adversarial rules:")
    print(f"{'name':35s}  {'wt':>4s}  {'C4':>6s} {'Z2h':>6s} {'D4':>6s} "
          f"{'CInv':>6s} {'OT':>6s} {'Lin':>6s}  desc")
    for i, (rule, desc, scores, lin_coeffs, weight, fp) in enumerate(selected, 1):
        name = f"ADV{i}_d{desc['degree']}_m{desc['n_monomials']}"
        print(
            f"{name:35s}  {weight:4d}  "
            f"{scores['C4_rotation']:.3f}  "
            f"{scores['Z2_horizontal']:.3f}  "
            f"{scores['D4_dihedral']:.3f}  "
            f"{scores['color_inversion']:.3f}  "
            f"{scores['outer_totalistic']:.3f}  "
            f"{scores['best_affine_linear']:.3f}  "
            f"const={desc['constant']} mon={desc['monomials']}"
        )

    # Save selection to a small intermediate file for the canonical manifest
    # assembler to ingest.
    out = []
    for i, (rule, desc, scores, lin_coeffs, weight, fp) in enumerate(selected, 1):
        out.append({
            "name": f"ADV{i}_d{desc['degree']}_m{desc['n_monomials']}",
            "constant": desc["constant"],
            "monomials": desc["monomials"],
            "degree": desc["degree"],
            "n_monomials": desc["n_monomials"],
            "weight": weight,
            "fingerprint_sha256_16": fp,
            "alignment": scores,
            "best_affine_linear_coeffs": lin_coeffs,
        })
    with open(SELECTION_PATH, "w") as f:
        json.dump(out, f, indent=2)

    print()
    print(f"Saved selection to {SELECTION_PATH}")


if __name__ == "__main__":
    main()
