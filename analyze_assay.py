#!/usr/bin/env python3
"""
Post-hoc spectral analysis for the Three-Branch Actuator Assay (Experiment 04).

Loads assay_log.jsonl from each workspace, computes FFT on accept/reject series,
and produces a summary with cross-branch comparisons.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from pathlib import Path
from typing import Any

# Add parent dir for v43_metrics import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.pop("AVALANCHE_ACTIVE", None)

from v43_metrics import spectral_series_metrics


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_assay_log(workspace: str) -> list[dict]:
    path = os.path.join(workspace, "assay_log.jsonl")
    if not os.path.exists(path):
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def load_assay_config(workspace: str) -> dict:
    path = os.path.join(workspace, "assay_config.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Gate series extraction
# ---------------------------------------------------------------------------

def extract_gate_series(records: list[dict]) -> list[int]:
    """Extract binary gate series: 0=accepted, 1=rejected. Gated phase only."""
    series = []
    for r in records:
        if r.get("phase") != "gated":
            continue
        decision = r.get("gate_decision", "")
        if decision == "rejected":
            series.append(1)
        elif decision == "accepted":
            series.append(0)
        # Skip format_fail entries
    return series


def extract_e_ratio_series(records: list[dict]) -> list[float]:
    """Extract E_ratio time series from gated phase."""
    return [
        r.get("e_ratio", 0.0) for r in records
        if r.get("phase") == "gated" and "e_ratio" in r
    ]


def extract_oracle_series(records: list[dict]) -> list[float]:
    """Extract oracle score time series from gated phase."""
    return [
        r.get("oracle_score", 0.0) for r in records
        if r.get("phase") == "gated" and "oracle_score" in r
    ]


# ---------------------------------------------------------------------------
# Per-run analysis
# ---------------------------------------------------------------------------

def analyze_run(workspace: str) -> dict[str, Any]:
    """Analyze a single assay run."""
    config = load_assay_config(workspace)
    records = load_assay_log(workspace)
    gated = [r for r in records if r.get("phase") == "gated"]

    if not gated:
        return {
            "workspace": workspace,
            "branch": config.get("branch", "?"),
            "run_id": config.get("run_id", 0),
            "error": "No gated phase data",
        }

    gate_series = extract_gate_series(records)
    e_ratio_series = extract_e_ratio_series(records)
    oracle_series = extract_oracle_series(records)

    # Gate statistics
    total_gated = len(gated)
    rejected = sum(1 for r in gated if r.get("gate_decision") == "rejected")
    accepted = total_gated - rejected
    rejection_rate = rejected / total_gated if total_gated > 0 else 0.0

    # Spectral analysis on gate series
    gate_spectral = spectral_series_metrics(gate_series, "gate")

    # Spectral analysis on E_ratio series
    e_ratio_spectral = spectral_series_metrics(e_ratio_series, "e_ratio")

    # E_ratio distribution stats
    e_stats = {}
    if e_ratio_series:
        e_stats = {
            "e_ratio_mean": round(statistics.mean(e_ratio_series), 4),
            "e_ratio_median": round(statistics.median(e_ratio_series), 4),
            "e_ratio_stdev": round(statistics.stdev(e_ratio_series), 4) if len(e_ratio_series) > 1 else 0.0,
            "e_ratio_max": round(max(e_ratio_series), 4),
            "e_ratio_min": round(min(e_ratio_series), 4),
        }

    # Oracle stats
    o_stats = {}
    if oracle_series:
        o_stats = {
            "oracle_mean": round(statistics.mean(oracle_series), 4),
            "oracle_max": round(max(oracle_series), 4),
            "first_improvement_cycle": None,
        }
        for i, score in enumerate(oracle_series):
            if score > 0:
                o_stats["first_improvement_cycle"] = i + 1
                break

    # Token usage
    total_tokens = sum(r.get("tokens", 0) for r in gated)

    return {
        "workspace": workspace,
        "branch": config.get("branch", "?"),
        "run_id": config.get("run_id", 0),
        "config": config,
        "total_gated_cycles": total_gated,
        "accepted": accepted,
        "rejected": rejected,
        "rejection_rate": round(rejection_rate, 4),
        "total_tokens": total_tokens,
        **e_stats,
        **o_stats,
        **gate_spectral,
        **e_ratio_spectral,
    }


# ---------------------------------------------------------------------------
# Cross-branch comparison
# ---------------------------------------------------------------------------

def _mean_or_none(values: list[float]) -> float | None:
    return round(statistics.mean(values), 4) if values else None


def compare_branches(runs: list[dict]) -> dict[str, Any]:
    """Compare statistics across branches."""
    by_branch: dict[str, list[dict]] = {"A": [], "B": [], "C": []}
    for run in runs:
        branch = run.get("branch", "?")
        if branch in by_branch:
            by_branch[branch].append(run)

    comparison = {}
    for branch, branch_runs in by_branch.items():
        if not branch_runs:
            comparison[branch] = {"n_runs": 0}
            continue

        gate_betas = [r.get("gate_pink_beta", 0.0) for r in branch_runs if "gate_pink_beta" in r]
        e_ratio_betas = [r.get("e_ratio_pink_beta", 0.0) for r in branch_runs if "e_ratio_pink_beta" in r]
        rejection_rates = [r.get("rejection_rate", 0.0) for r in branch_runs]
        e_means = [r.get("e_ratio_mean", 0.0) for r in branch_runs if "e_ratio_mean" in r]
        oracle_means = [r.get("oracle_mean", 0.0) for r in branch_runs if "oracle_mean" in r]
        first_improvements = [
            r.get("first_improvement_cycle") for r in branch_runs
            if r.get("first_improvement_cycle") is not None
        ]

        comparison[branch] = {
            "n_runs": len(branch_runs),
            "gate_spectral_exponent_mean": _mean_or_none(gate_betas),
            "gate_spectral_exponent_values": [round(b, 4) for b in gate_betas],
            "e_ratio_spectral_exponent_mean": _mean_or_none(e_ratio_betas),
            "rejection_rate_mean": _mean_or_none(rejection_rates),
            "e_ratio_mean_of_means": _mean_or_none(e_means),
            "oracle_mean_of_means": _mean_or_none(oracle_means),
            "first_improvement_cycles": first_improvements,
        }

    # Key diagnostic: A vs C spectral comparison
    a_betas = [r.get("gate_pink_beta", 0.0) for r in by_branch.get("A", []) if "gate_pink_beta" in r]
    c_betas = [r.get("gate_pink_beta", 0.0) for r in by_branch.get("C", []) if "gate_pink_beta" in r]

    interpretation = "insufficient_data"
    if a_betas and c_betas:
        a_mean = statistics.mean(a_betas)
        c_mean = statistics.mean(c_betas)
        if abs(a_mean - 1.0) < 0.3 and abs(c_mean - 1.0) < 0.3:
            interpretation = "both_pink__signature_is_artifact"
        elif abs(a_mean - 1.0) < 0.3 and abs(c_mean) < 0.3:
            interpretation = "informed_pink_random_white__coupling_matters"
        elif abs(a_mean) < 0.3 and abs(c_mean) < 0.3:
            interpretation = "both_white__no_long_range_correlations"
        else:
            interpretation = f"ambiguous__A_beta={a_mean:.2f}_C_beta={c_mean:.2f}"

    comparison["ac_spectral_diagnosis"] = interpretation

    # A vs B: does rhetoric matter?
    b_runs = by_branch.get("B", [])
    a_runs = by_branch.get("A", [])
    if a_runs and b_runs:
        a_oracle = [r.get("oracle_mean", 0.0) for r in a_runs if "oracle_mean" in r]
        b_oracle = [r.get("oracle_mean", 0.0) for r in b_runs if "oracle_mean" in r]
        if a_oracle and b_oracle:
            comparison["ab_rhetoric_delta"] = {
                "a_oracle_mean": round(statistics.mean(a_oracle), 4),
                "b_oracle_mean": round(statistics.mean(b_oracle), 4),
                "delta": round(statistics.mean(b_oracle) - statistics.mean(a_oracle), 4),
                "interpretation": "rhetoric_effect" if abs(statistics.mean(b_oracle) - statistics.mean(a_oracle)) > 0.05 else "no_significant_effect",
            }

    return comparison


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def discover_workspaces(root: str) -> list[str]:
    """Find all branch-X-run-N directories under root."""
    workspaces = []
    root_path = Path(root)
    if not root_path.exists():
        return []
    for entry in sorted(root_path.iterdir()):
        if entry.is_dir() and entry.name.startswith("branch-"):
            workspaces.append(str(entry))
    return workspaces


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Three-Branch Actuator Assay results")
    parser.add_argument("--workspace-root", required=True,
                        help="Parent directory containing branch-X-run-N workspaces")
    parser.add_argument("--output", default=None,
                        help="Output path for assay_summary.json (default: workspace-root/assay_summary.json)")
    args = parser.parse_args()

    workspaces = discover_workspaces(args.workspace_root)
    if not workspaces:
        print(f"No assay workspaces found under {args.workspace_root}")
        sys.exit(1)

    print(f"Found {len(workspaces)} workspaces:")
    for ws in workspaces:
        print(f"  {ws}")

    # Analyze each run
    runs = []
    for ws in workspaces:
        print(f"\nAnalyzing {os.path.basename(ws)}...")
        result = analyze_run(ws)
        runs.append(result)

        if "error" in result:
            print(f"  ERROR: {result['error']}")
        else:
            print(f"  Branch {result['branch']}: "
                  f"{result['total_gated_cycles']} cycles, "
                  f"rejection_rate={result['rejection_rate']:.2f}, "
                  f"gate_beta={result.get('gate_pink_beta', '?')}, "
                  f"e_ratio_mean={result.get('e_ratio_mean', '?')}")

    # Cross-branch comparison
    print("\n--- Cross-Branch Comparison ---")
    comparison = compare_branches(runs)

    for branch in ["A", "B", "C"]:
        bc = comparison.get(branch, {})
        n = bc.get("n_runs", 0)
        if n == 0:
            print(f"  Branch {branch}: no data")
            continue
        print(f"  Branch {branch} (n={n}):")
        print(f"    Gate spectral exponent: {bc.get('gate_spectral_exponent_mean', '?')}")
        print(f"    E_ratio spectral exponent: {bc.get('e_ratio_spectral_exponent_mean', '?')}")
        print(f"    Rejection rate: {bc.get('rejection_rate_mean', '?')}")

    print(f"\n  A vs C diagnosis: {comparison.get('ac_spectral_diagnosis', '?')}")
    if "ab_rhetoric_delta" in comparison:
        ab = comparison["ab_rhetoric_delta"]
        print(f"  A vs B rhetoric: delta={ab['delta']:.4f} ({ab['interpretation']})")

    # Write summary
    output_path = args.output or os.path.join(args.workspace_root, "assay_summary.json")
    summary = {
        "runs": runs,
        "comparison": comparison,
        "timestamp": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nSummary written to {output_path}")


if __name__ == "__main__":
    main()
