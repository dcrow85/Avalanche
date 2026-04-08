"""
Assemble the final v0.2.2 hidden-rule manifest:

  - 5 library-aligned rules (Conway Life, HighLife, Day & Night, Seeds, Parity)
  - 5 adversarial rules (selected by search in search_adversarial.py)
  - 5 random rules (sampled with a versioned seed)

Each rule is recorded with:
  - stratum
  - construction recipe (so it can be regenerated bit-for-bit)
  - SHA-256 fingerprint of the 512-bit rule vector
  - alignment score against every library primitive
  - best affine linear functional approximation (fraction + coefficients)

Campaign-1 local-functional restriction is explicit here: manifest screening
uses the 1024 affine linear functions of the 9 neighborhood bits as the
local-functional family.

This script is the sole canonical manifest emitter for Campaign 1 of the Fast
Bench. Other scripts may verify ranks or search candidates, but they must not
overwrite the frozen campaign1_manifest.json artifact.
"""

import json
import numpy as np
from pathlib import Path
from build_manifest import (
    ALL_BITS, N_CONFIGS, build_library_primitives,
    alignment_with_primitive, best_affine_linear_alignment,
    rule_fingerprint, life_rule, parity_rule, f2_rank,
)

BASE_DIR = Path(__file__).resolve().parent
ADV_SELECTION_PATH = BASE_DIR / "adversarial_selection.json"
OUT_PATH = BASE_DIR / "campaign1_manifest.json"


def polynomial_rule_from_recipe(constant, monomials):
    r = np.full(N_CONFIGS, constant, dtype=np.int8)
    for m in monomials:
        prod = np.ones(N_CONFIGS, dtype=np.int8)
        for v in m:
            prod &= ALL_BITS[:, v]
        r ^= prod
    return r


def main():
    primitives = build_library_primitives()

    # Verify ranks once more.
    target_ranks = {
        "C4_rotation": 372,
        "Z2_horizontal": 224,
        "D4_dihedral": 410,
        "color_inversion": 256,
        "outer_totalistic": 494,
    }
    rank_report = {}
    for name, (C, _) in primitives.items():
        rank = f2_rank(C)
        rank_report[name] = {
            "rows": int(C.shape[0]),
            "rank": rank,
            "target": target_ranks[name],
            "match": rank == target_ranks[name],
        }
        assert rank == target_ranks[name], f"{name}: {rank} != {target_ranks[name]}"

    # ---------------- aligned stratum ----------------
    aligned_recipes = [
        {
            "name": "Conway_Life",
            "kind": "life_like",
            "B": [3], "S": [2, 3],
            "rule": life_rule({3}, {2, 3}),
        },
        {
            "name": "HighLife",
            "kind": "life_like",
            "B": [3, 6], "S": [2, 3],
            "rule": life_rule({3, 6}, {2, 3}),
        },
        {
            "name": "Day_and_Night",
            "kind": "life_like",
            "B": [3, 6, 7, 8], "S": [3, 4, 6, 7, 8],
            "rule": life_rule({3, 6, 7, 8}, {3, 4, 6, 7, 8}),
        },
        {
            "name": "Seeds",
            "kind": "life_like",
            "B": [2], "S": [],
            "rule": life_rule({2}, set()),
        },
        {
            "name": "Parity_9bit",
            "kind": "linear_functional",
            "L": [1, 1, 1, 1, 1, 1, 1, 1, 1],
            "constant": 0,
            "rule": parity_rule(),
        },
    ]

    # ---------------- adversarial stratum (from search) ----------------
    with open(ADV_SELECTION_PATH) as f:
        adv_selection = json.load(f)
    adversarial_recipes = []
    for entry in adv_selection:
        rule = polynomial_rule_from_recipe(entry["constant"], entry["monomials"])
        adversarial_recipes.append({
            "name": entry["name"],
            "kind": "f2_polynomial",
            "constant": entry["constant"],
            "monomials": entry["monomials"],
            "degree": entry["degree"],
            "n_monomials": entry["n_monomials"],
            "rule": rule,
        })

    # ---------------- random stratum ----------------
    SEED_RANDOM_STRATUM = 20260408
    rng = np.random.default_rng(seed=SEED_RANDOM_STRATUM)
    random_recipes = []
    for k in range(5):
        rule = rng.integers(0, 2, size=N_CONFIGS, dtype=np.int8)
        random_recipes.append({
            "name": f"RND{k+1}",
            "kind": "uniform_random",
            "seed_master": SEED_RANDOM_STRATUM,
            "draw_index": k,
            "rule": rule,
        })

    # ---------------- score everything ----------------
    rules_records = []
    for stratum, recipes in [
        ("aligned", aligned_recipes),
        ("adversarial", adversarial_recipes),
        ("random", random_recipes),
    ]:
        for entry in recipes:
            rule = entry.pop("rule")
            scores = {p: alignment_with_primitive(rule, primitives[p]) for p in primitives}
            best_lin, best_lin_coeffs = best_affine_linear_alignment(rule)
            scores["best_affine_linear"] = best_lin
            record = {
                "stratum": stratum,
                **entry,
                "weight": int(rule.sum()),
                "fingerprint_sha256_16": rule_fingerprint(rule),
                "alignment": scores,
                "best_affine_linear_coeffs": best_lin_coeffs,
            }
            rules_records.append(record)

    # ---------------- random alignment baseline ----------------
    rng_bl = np.random.default_rng(seed=999)
    n_baseline = 200
    baseline_scores = {p: [] for p in primitives}
    baseline_lin = []
    for _ in range(n_baseline):
        r = rng_bl.integers(0, 2, size=N_CONFIGS, dtype=np.int8)
        for p in primitives:
            baseline_scores[p].append(alignment_with_primitive(r, primitives[p]))
        baseline_lin.append(best_affine_linear_alignment(r)[0])
    baseline = {
        "n_samples": n_baseline,
        "seed": 999,
        "by_primitive": {
            p: {
                "mean": float(np.mean(baseline_scores[p])),
                "std": float(np.std(baseline_scores[p])),
                "max": float(np.max(baseline_scores[p])),
                "p99": float(np.quantile(baseline_scores[p], 0.99)),
            }
            for p in primitives
        },
        "best_affine_linear": {
            "mean": float(np.mean(baseline_lin)),
            "std": float(np.std(baseline_lin)),
            "max": float(np.max(baseline_lin)),
            "p99": float(np.quantile(baseline_lin, 0.99)),
        },
    }

    # ---------------- adversariality verdict ----------------
    # Adversarial rule passes iff every primitive alignment is within
    # baseline_p99 (or below) AND best linear within its baseline_p99.
    verdict = []
    for rec in rules_records:
        if rec["stratum"] != "adversarial":
            continue
        ok = True
        details = {}
        for p in primitives:
            score = rec["alignment"][p]
            p99 = baseline["by_primitive"][p]["p99"]
            details[p] = {"score": score, "baseline_p99": p99, "pass": score <= p99 + 0.02}
            if not details[p]["pass"]:
                ok = False
        lin_score = rec["alignment"]["best_affine_linear"]
        lin_p99 = baseline["best_affine_linear"]["p99"]
        details["best_affine_linear"] = {
            "score": lin_score, "baseline_p99": lin_p99,
            "pass": lin_score <= lin_p99 + 0.02,
        }
        if not details["best_affine_linear"]["pass"]:
            ok = False
        verdict.append({
            "name": rec["name"],
            "passes_adversariality_check": ok,
            "primitive_details": details,
        })

    # ---------------- write manifest ----------------
    manifest = {
        "spec_version": "v0.2.2",
        "manifest_version": "campaign-1.0",
        "generated_for": "Generative Closure Fast Bench, first throughput campaign",
        "campaign1_local_functional_library": {
            "kind": "affine_linear",
            "n_functions": 1024,
            "description": "Campaign 1 restricts local-functional primitives to affine linear functions of the 9 neighborhood bits, including constant.",
        },
        "canonical_emitter": {
            "script": "assemble_manifest.py",
            "policy": "single canonical manifest-emission path for campaign-1.0",
        },
        "indexing_convention": {
            "grid": "3x3 row-major",
            "positions": {
                "0": "(0,0) top-left",  "1": "(0,1) top-mid",   "2": "(0,2) top-right",
                "3": "(1,0) mid-left",  "4": "(1,1) center",    "5": "(1,2) mid-right",
                "6": "(2,0) bot-left",  "7": "(2,1) bot-mid",   "8": "(2,2) bot-right",
            },
            "config_encoding": "n in [0,512); bit at position k = (n >> (8-k)) & 1",
            "rule_semantics": "r[n] is the next state of the center cell (position 4)",
        },
        "library_primitive_ranks": rank_report,
        "random_alignment_baseline": baseline,
        "adversariality_verdict": verdict,
        "rules": rules_records,
    }

    out_path = OUT_PATH
    with open(out_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Verdict summary print.
    print("=" * 70)
    print("Adversariality verdict (vs baseline 99th percentile + 0.02 tolerance)")
    print("=" * 70)
    all_pass = True
    for v in verdict:
        status = "PASS" if v["passes_adversariality_check"] else "FAIL"
        print(f"  {v['name']:35s}  {status}")
        if not v["passes_adversariality_check"]:
            all_pass = False
            for p, d in v["primitive_details"].items():
                if not d["pass"]:
                    print(f"      {p}: score={d['score']:.3f} > p99={d['baseline_p99']:.3f}")
    print()
    print("ALL ADVERSARIAL RULES PASS" if all_pass else "SOME ADVERSARIAL RULES FAIL")
    print()
    print(f"Manifest written to {out_path}")


if __name__ == "__main__":
    main()
