"""
Generative Closure Fast Bench v0.2.2 — primitive-library analysis helpers
and sanity reporting.

Indexing convention for the 3x3 Moore neighborhood:

    pos:  0 1 2
          3 4 5
          6 7 8

A configuration n in [0, 512) decodes to bits b[0..8] via:
    b[k] = (n >> (8 - k)) & 1
so position 0 is the most-significant bit.

A rule is a vector r in F_2^512 where r[n] is the next-state output bit for
configuration n. The cell whose next state is being computed is the center
cell (position 4).

Library primitives (per spec v0.2.2 §4):

    1. Atomic coordinate families (rank = subset size)
    2. Symmetry families:
        - C_4 rotation                         (target rank 372)
        - Z_2 horizontal reflection            (target rank 224)
        - D_4 full dihedral                    (target rank 410)
        - color inversion (complement-symm.)   (target rank 256)
        - outer-totalistic reduction           (target rank 494)
    3. Local functional families for Campaign 1: ALL affine linear functions of the 9
        neighborhood bits (1024 of them, including constant). The library
        is aligned with rule r if r matches some affine linear L on every
        configuration.

A rule's alignment with a primitive is the fraction of constraint rows it
satisfies (predicted bit matches target bit). A random rule scores ~0.5 on
homogeneous symmetry primitives. An adversarial rule is one that scores at
or near random on EVERY library primitive while still being structurally
generated (not random).
This module is the shared analysis library for manifest construction. It may
print rank/alignment sanity tables, but it must not emit the canonical
campaign1_manifest.json artifact; that frozen manifest is assembled only by
assemble_manifest.py.
"""

import numpy as np
import hashlib

# ----------------------------------------------------------------------------
# Cell indexing utilities
# ----------------------------------------------------------------------------

N_CELLS = 9
N_CONFIGS = 1 << N_CELLS  # 512


def config_bits(n):
    """Return [b0..b8] for configuration index n. Position 0 is the MSB."""
    return np.array([(n >> (8 - k)) & 1 for k in range(9)], dtype=np.int8)


def bits_to_config(bits):
    """Inverse of config_bits."""
    n = 0
    for k in range(9):
        n |= int(bits[k]) << (8 - k)
    return n


# Precompute all configurations as a (512, 9) int8 array.
ALL_BITS = np.array([config_bits(n) for n in range(N_CONFIGS)], dtype=np.int8)


# ----------------------------------------------------------------------------
# Cell-permutation -> configuration permutation
# ----------------------------------------------------------------------------

def apply_cell_perm_to_bits(bits, sigma):
    """
    sigma is a length-9 list where sigma[p] is the new position that cell p
    moves TO. So if the original cell at position p has bit b, the new
    configuration has bit b at position sigma[p].
    """
    new_bits = np.zeros(9, dtype=np.int8)
    for p in range(9):
        new_bits[sigma[p]] = bits[p]
    return new_bits


def config_perm_from_cell_perm(sigma):
    """Return a length-512 permutation pi such that pi[n] = index of the
    configuration obtained by moving cell at position p to position sigma[p]."""
    pi = np.zeros(N_CONFIGS, dtype=np.int32)
    for n in range(N_CONFIGS):
        new_bits = apply_cell_perm_to_bits(ALL_BITS[n], sigma)
        pi[n] = bits_to_config(new_bits)
    return pi


# Cell permutations for the spatial symmetries (3x3 grid):
#
#   Indexing:  (row, col) -> position = row*3 + col
#   So:        0 1 2
#              3 4 5
#              6 7 8
#
# Rotations: 90deg CW maps (r, c) -> (c, 2 - r).
# Reflections: horizontal flips columns 0<->2, vertical flips rows 0<->2.

def make_rotation_cw():
    sigma = [0] * 9
    for p in range(9):
        r, c = divmod(p, 3)
        new_r, new_c = c, 2 - r
        sigma[p] = new_r * 3 + new_c
    return sigma


SIGMA_ROT_CW = make_rotation_cw()              # 90deg CW
SIGMA_ROT_180 = [SIGMA_ROT_CW[SIGMA_ROT_CW[p]] for p in range(9)]
SIGMA_ROT_CCW = [SIGMA_ROT_CW[SIGMA_ROT_180[p]] for p in range(9)]

SIGMA_HORIZ = [0] * 9
SIGMA_VERT = [0] * 9
SIGMA_DIAG_MAIN = [0] * 9   # transpose: (r, c) -> (c, r)
SIGMA_DIAG_ANTI = [0] * 9   # anti-transpose: (r, c) -> (2-c, 2-r)

for p in range(9):
    r, c = divmod(p, 3)
    SIGMA_HORIZ[p] = r * 3 + (2 - c)
    SIGMA_VERT[p] = (2 - r) * 3 + c
    SIGMA_DIAG_MAIN[p] = c * 3 + r
    SIGMA_DIAG_ANTI[p] = (2 - c) * 3 + (2 - r)


# ----------------------------------------------------------------------------
# F_2 linear algebra: rank by Gaussian elimination
# ----------------------------------------------------------------------------

def f2_rank(M):
    """Rank of an int8 / bool matrix over F_2."""
    A = np.array(M, dtype=np.uint8) % 2
    A = A.copy()
    rows, cols = A.shape
    rank = 0
    pivot_row = 0
    for c in range(cols):
        # Find a row with a 1 in column c at or below pivot_row.
        pivot = -1
        for r in range(pivot_row, rows):
            if A[r, c] == 1:
                pivot = r
                break
        if pivot == -1:
            continue
        if pivot != pivot_row:
            A[[pivot_row, pivot]] = A[[pivot, pivot_row]]
        for r in range(rows):
            if r != pivot_row and A[r, c] == 1:
                A[r] ^= A[pivot_row]
        pivot_row += 1
        rank += 1
        if pivot_row == rows:
            break
    return rank


# ----------------------------------------------------------------------------
# Building primitive constraint matrices
# ----------------------------------------------------------------------------

def symmetry_constraints(group_perms):
    """
    Given a list of cell permutations (sigma) generating a group, return
    a constraint matrix C (rows are e_n + e_pi(n)) and target vector y (zero)
    for the constraint set "rule is invariant under all group elements".

    We deliberately overgenerate (one constraint per (config, generator) pair),
    then dedupe and reduce. The final RANK is what matters.
    """
    rows = []
    for sigma in group_perms:
        pi = config_perm_from_cell_perm(sigma)
        for n in range(N_CONFIGS):
            m = pi[n]
            if m == n:
                continue
            row = np.zeros(N_CONFIGS, dtype=np.int8)
            row[n] = 1
            row[m] = 1
            rows.append(row)
    if not rows:
        return np.zeros((0, N_CONFIGS), dtype=np.int8), np.zeros(0, dtype=np.int8)
    C = np.array(rows, dtype=np.int8)
    y = np.zeros(C.shape[0], dtype=np.int8)
    return C, y


def color_inversion_constraints():
    """Constraint: r[n] + r[~n] = 1 for all n. Rows are e_n + e_{~n}, RHS 1."""
    rows = []
    seen = set()
    for n in range(N_CONFIGS):
        m = n ^ 0x1FF  # flip all 9 bits
        key = tuple(sorted([n, m]))
        if key in seen:
            continue
        seen.add(key)
        row = np.zeros(N_CONFIGS, dtype=np.int8)
        row[n] = 1
        row[m] = 1
        rows.append(row)
    C = np.array(rows, dtype=np.int8)
    y = np.ones(C.shape[0], dtype=np.int8)
    return C, y


def outer_totalistic_constraints():
    """
    Constraint: r is determined by (center_bit, neighbor_live_count).
    For each equivalence class of >= 2 configurations, add equality rows
    among them all (relative to a representative).
    """
    classes = {}
    for n in range(N_CONFIGS):
        bits = ALL_BITS[n]
        center = int(bits[4])
        neighbor_count = int(bits.sum() - bits[4])
        key = (center, neighbor_count)
        classes.setdefault(key, []).append(n)
    rows = []
    for key, members in classes.items():
        if len(members) < 2:
            continue
        rep = members[0]
        for m in members[1:]:
            row = np.zeros(N_CONFIGS, dtype=np.int8)
            row[rep] = 1
            row[m] = 1
            rows.append(row)
    C = np.array(rows, dtype=np.int8)
    y = np.zeros(C.shape[0], dtype=np.int8)
    return C, y


# ----------------------------------------------------------------------------
# Library primitive set
# ----------------------------------------------------------------------------

def build_library_primitives():
    primitives = {}

    # C_4 rotation: generated by 90deg CW.
    C, y = symmetry_constraints([SIGMA_ROT_CW, SIGMA_ROT_180, SIGMA_ROT_CCW])
    primitives["C4_rotation"] = (C, y)

    # Z_2 horizontal reflection.
    C, y = symmetry_constraints([SIGMA_HORIZ])
    primitives["Z2_horizontal"] = (C, y)

    # D_4 dihedral: rotations + reflections.
    C, y = symmetry_constraints([
        SIGMA_ROT_CW, SIGMA_ROT_180, SIGMA_ROT_CCW,
        SIGMA_HORIZ, SIGMA_VERT, SIGMA_DIAG_MAIN, SIGMA_DIAG_ANTI,
    ])
    primitives["D4_dihedral"] = (C, y)

    # Color inversion (complement symmetry).
    C, y = color_inversion_constraints()
    primitives["color_inversion"] = (C, y)

    # Outer-totalistic.
    C, y = outer_totalistic_constraints()
    primitives["outer_totalistic"] = (C, y)

    return primitives


# ----------------------------------------------------------------------------
# Defining specific rules as F_2^512 vectors
# ----------------------------------------------------------------------------

def life_rule(birth_set, survive_set):
    """Generic Life-like rule. r[n] = 1 iff next state of center is alive."""
    r = np.zeros(N_CONFIGS, dtype=np.int8)
    for n in range(N_CONFIGS):
        bits = ALL_BITS[n]
        center = int(bits[4])
        neighbor_count = int(bits.sum() - bits[4])
        if center == 1 and neighbor_count in survive_set:
            r[n] = 1
        elif center == 0 and neighbor_count in birth_set:
            r[n] = 1
    return r


def parity_rule():
    """r[n] = parity of all 9 bits. Linear, fully symmetric."""
    return ALL_BITS.sum(axis=1).astype(np.int8) & 1


# Adversarial rule candidates ------------------------------------------------
#
# Each is constructed from a specific generating principle that we believe is
# orthogonal to the library. We will VERIFY orthogonality below.

def adv_quadratic_asymmetric():
    """A1: r = n0*n1 ^ n2*n5 ^ n3*n7 ^ n8."""
    r = np.zeros(N_CONFIGS, dtype=np.int8)
    for n in range(N_CONFIGS):
        b = ALL_BITS[n]
        r[n] = (b[0] & b[1]) ^ (b[2] & b[5]) ^ (b[3] & b[7]) ^ b[8]
    return r


def adv_threshold_asymmetric():
    """A2: r = 1 iff (n0 + n1 + n4 + n5 + n8) >= 3, on the L-shaped subset."""
    r = np.zeros(N_CONFIGS, dtype=np.int8)
    subset = [0, 1, 4, 5, 8]
    for n in range(N_CONFIGS):
        b = ALL_BITS[n]
        r[n] = 1 if sum(int(b[i]) for i in subset) >= 3 else 0
    return r


def adv_cubic_three_triangles():
    """A3: r = n0*n1*n4 ^ n2*n5*n8 ^ n3*n6*n7. Three asymmetric triangles."""
    r = np.zeros(N_CONFIGS, dtype=np.int8)
    for n in range(N_CONFIGS):
        b = ALL_BITS[n]
        r[n] = (b[0] & b[1] & b[4]) ^ (b[2] & b[5] & b[8]) ^ (b[3] & b[6] & b[7])
    return r


def adv_threshold_subset_4():
    """A4: r = 1 iff (n0 + n2 + n4 + n5) >= 2, on a 4-element asymmetric subset."""
    r = np.zeros(N_CONFIGS, dtype=np.int8)
    subset = [0, 2, 4, 5]
    for n in range(N_CONFIGS):
        b = ALL_BITS[n]
        r[n] = 1 if sum(int(b[i]) for i in subset) >= 2 else 0
    return r


def adv_majority_chain():
    """A5: r = MAJ(MAJ(n0,n1,n2), MAJ(n3,n4,n5), n8). Depth-2 majority circuit
    over the top row, the middle row, and the bottom-right corner. Asymmetric
    because n8 is singled out."""
    def maj3(a, b, c):
        return 1 if (int(a) + int(b) + int(c)) >= 2 else 0
    r = np.zeros(N_CONFIGS, dtype=np.int8)
    for n in range(N_CONFIGS):
        b = ALL_BITS[n]
        top = maj3(b[0], b[1], b[2])
        mid = maj3(b[3], b[4], b[5])
        r[n] = maj3(top, mid, int(b[8]))
    return r


# ----------------------------------------------------------------------------
# Alignment computation
# ----------------------------------------------------------------------------

def alignment_with_primitive(rule, primitive):
    """Fraction of primitive constraint rows satisfied by rule."""
    C, y = primitive
    if C.shape[0] == 0:
        return 1.0
    Cr = (C @ rule.astype(np.int32)) % 2
    matches = (Cr == y).sum()
    return float(matches) / C.shape[0]


def best_affine_linear_alignment(rule):
    """
    Maximum agreement fraction over all 1024 affine linear functions
    L(b) = a0*b0 ^ ... ^ a8*b8 ^ c. Returns (best_fraction, best_coeffs).
    """
    rule_int = rule.astype(np.int32)
    best_frac = 0.0
    best_coeffs = None
    # Iterate over all 2^9 linear coefficient choices and 2 constants.
    for mask in range(512):
        coeffs = np.array([(mask >> (8 - k)) & 1 for k in range(9)], dtype=np.int32)
        L = (ALL_BITS.astype(np.int32) @ coeffs) & 1  # length 512
        for c in (0, 1):
            Lc = L ^ c
            agree = (Lc == rule_int).sum()
            frac = float(agree) / N_CONFIGS
            if frac > best_frac:
                best_frac = frac
                best_coeffs = (coeffs.tolist(), c)
    return best_frac, best_coeffs


def rule_fingerprint(rule):
    """Short SHA-256 prefix of the rule vector for manifest identification."""
    h = hashlib.sha256(rule.tobytes()).hexdigest()
    return h[:16]


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    primitives = build_library_primitives()

    # First: verify ranks against the spec.
    print("=" * 70)
    print("Library primitive ranks (target values from spec v0.2.2 §4.2)")
    print("=" * 70)
    targets = {
        "C4_rotation": 372,
        "Z2_horizontal": 224,
        "D4_dihedral": 410,
        "color_inversion": 256,
        "outer_totalistic": 494,
    }
    rank_report = {}
    for name, (C, y) in primitives.items():
        rank = f2_rank(C)
        target = targets[name]
        ok = "OK" if rank == target else "MISMATCH"
        print(f"  {name:20s}  rows={C.shape[0]:6d}  rank={rank:4d}  target={target:4d}  [{ok}]")
        rank_report[name] = {"rank": rank, "target": target, "match": rank == target}

    # Define sanity-check rule sets.
    aligned_rules = {
        "Conway_Life":     life_rule({3}, {2, 3}),
        "HighLife":        life_rule({3, 6}, {2, 3}),
        "Day_and_Night":   life_rule({3, 6, 7, 8}, {3, 4, 6, 7, 8}),
        "Seeds":           life_rule({2}, set()),
        "Parity_9bit":     parity_rule(),
    }

    # These are legacy hand-designed nonlinear candidates kept only as a
    # contrast surface for sanity reporting. They are not the canonical
    # campaign-1 adversarial stratum, which is search-selected and assembled
    # by assemble_manifest.py.
    legacy_candidate_rules = {
        "ADV1_quadratic_asymmetric":   adv_quadratic_asymmetric(),
        "ADV2_threshold_L_shape":      adv_threshold_asymmetric(),
        "ADV3_cubic_three_triangles":  adv_cubic_three_triangles(),
        "ADV4_threshold_4subset":      adv_threshold_subset_4(),
        "ADV5_majority_chain":         adv_majority_chain(),
    }

    rng = np.random.default_rng(seed=20260408)
    random_rules = {}
    for k in range(5):
        random_rules[f"RND{k+1}"] = rng.integers(0, 2, size=N_CONFIGS, dtype=np.int8)

    all_rules = [
        ("aligned", aligned_rules),
        ("legacy_candidates", legacy_candidate_rules),
        ("random", random_rules),
    ]

    # Compute alignments.
    print()
    print("=" * 70)
    print("Alignment scores: fraction of constraint rows each rule satisfies")
    print("(random ~ 0.50; aligned = 1.00; adversarial target <= 0.60)")
    print("=" * 70)
    print(f"{'rule':35s}  {'C4':>6s} {'Z2h':>6s} {'D4':>6s} {'CInv':>6s} {'OT':>6s} {'Lin':>6s}")

    manifest_rules = []

    for stratum, rules in all_rules:
        print(f"\n--- {stratum} ---")
        for rname, r in rules.items():
            scores = {
                pname: alignment_with_primitive(r, prim)
                for pname, prim in primitives.items()
            }
            best_lin_frac, best_lin_coeffs = best_affine_linear_alignment(r)
            print(
                f"{rname:35s}  "
                f"{scores['C4_rotation']:.3f}  "
                f"{scores['Z2_horizontal']:.3f}  "
                f"{scores['D4_dihedral']:.3f}  "
                f"{scores['color_inversion']:.3f}  "
                f"{scores['outer_totalistic']:.3f}  "
                f"{best_lin_frac:.3f}"
            )
            manifest_rules.append({
                "stratum": stratum,
                "name": rname,
                "fingerprint_sha256_16": rule_fingerprint(r),
                "alignment": {
                    "C4_rotation": scores["C4_rotation"],
                    "Z2_horizontal": scores["Z2_horizontal"],
                    "D4_dihedral": scores["D4_dihedral"],
                    "color_inversion": scores["color_inversion"],
                    "outer_totalistic": scores["outer_totalistic"],
                    "best_affine_linear": best_lin_frac,
                },
                "best_affine_linear_coeffs": best_lin_coeffs,
                "weight": int(r.sum()),
            })

    # Pure-random baseline distribution sanity check.
    print()
    print("=" * 70)
    print("Sanity: distribution of alignment scores under uniform random rules")
    print("=" * 70)
    random_samples = 200
    random_scores = {pname: [] for pname in primitives}
    random_lin = []
    rng2 = np.random.default_rng(seed=999)
    for _ in range(random_samples):
        r = rng2.integers(0, 2, size=N_CONFIGS, dtype=np.int8)
        for pname, prim in primitives.items():
            random_scores[pname].append(alignment_with_primitive(r, prim))
        random_lin.append(best_affine_linear_alignment(r)[0])
    for pname in primitives:
        arr = np.array(random_scores[pname])
        print(f"  {pname:20s}  mean={arr.mean():.3f}  std={arr.std():.3f}  "
              f"max={arr.max():.3f}")
    arr = np.array(random_lin)
    print(f"  {'best_affine_linear':20s}  mean={arr.mean():.3f}  "
          f"std={arr.std():.3f}  max={arr.max():.3f}")

    print()
    print("No manifest emitted.")
    print("build_manifest.py is a sanity/report tool only.")
    print("The canonical campaign1_manifest.json artifact is emitted solely by assemble_manifest.py.")


if __name__ == "__main__":
    main()
