#!/usr/bin/env python3
"""Post-processing: compute PE_t (narrative/code decoupling ratio).

Inputs:
    telemetry.jsonl — cycle-level calorimeter data
    opinions_history.jsonl — per-cycle opinions text

Outputs:
    Prints per-cycle PE metrics to stdout as JSONL.
    Optionally writes to pe_metrics.jsonl.

PE_t = opinions_jaccard_distance / max(ast_structure_distance, epsilon)

High PE_t: narrative is moving but code is not (speculation).
Low PE_t: code is moving in step with narrative (grounded work).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EPSILON = 1e-6


def jaccard_distance(text_a: str, text_b: str) -> float:
    """Word-level Jaccard distance between two texts."""
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a and not words_b:
        return 0.0
    union = words_a | words_b
    if not union:
        return 0.0
    intersection = words_a & words_b
    return 1.0 - len(intersection) / len(union)


def ast_structure_distance(
    hash_changed: bool,
    node_delta: int,
    node_count: int,
) -> float:
    """AST structure distance proxy.

    Returns:
        1.0 if hash changed (structural rewrite) scaled by normalized node delta,
        0.0 if hash unchanged.
    """
    if not hash_changed:
        return 0.0
    # Normalize node delta by current node count to get a 0-1 scale
    if node_count > 0:
        return 1.0 + (node_delta / max(node_count, 1))
    return 1.0


def load_opinions_history(path: str) -> dict[int, str]:
    """Load opinions_history.jsonl into {cycle: opinions_text}."""
    history: dict[int, str] = {}
    p = Path(path)
    if not p.exists():
        return history
    for line in p.read_text(encoding="utf-8").strip().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        cycle = row.get("cycle")
        text = row.get("opinions_text", "")
        if cycle is not None:
            history[int(cycle)] = text
    return history


def load_telemetry(path: str) -> list[dict]:
    """Load telemetry.jsonl into list of dicts."""
    rows: list[dict] = []
    p = Path(path)
    if not p.exists():
        return rows
    for line in p.read_text(encoding="utf-8").strip().splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def compute_pe(
    telemetry_path: str,
    opinions_path: str,
) -> list[dict]:
    """Compute PE metrics for each grind cycle."""
    telemetry = load_telemetry(telemetry_path)
    opinions = load_opinions_history(opinions_path)

    results: list[dict] = []
    previous_opinions_text: str | None = None

    for row in telemetry:
        cycle = row.get("cycle")
        cycle_type = row.get("cycle_type", "")

        if cycle is None:
            continue

        # Get opinions text for this cycle
        opinions_text = opinions.get(int(cycle), "")

        # PE only meaningful for grind cycles with a predecessor
        if cycle_type != "grind":
            previous_opinions_text = opinions_text if opinions_text else previous_opinions_text
            continue

        if previous_opinions_text is None:
            previous_opinions_text = opinions_text
            continue

        # Compute opinions Jaccard distance
        oj_dist = jaccard_distance(previous_opinions_text, opinions_text)

        # Compute AST structure distance
        hash_changed = row.get("solver_ast_hash_changed", False)
        node_delta = row.get("solver_ast_node_delta", 0)
        node_count = row.get("solver_ast_node_count", 0)
        ast_dist = ast_structure_distance(hash_changed, node_delta, node_count)

        # PE ratio
        pe_ratio = oj_dist / max(ast_dist, EPSILON)

        results.append({
            "cycle": cycle,
            "opinions_jaccard_distance": round(oj_dist, 6),
            "ast_structure_distance": round(ast_dist, 6),
            "pe_ratio": round(pe_ratio, 6),
            "solver_ast_hash_changed": hash_changed,
            "solver_ast_node_delta": node_delta,
        })

        previous_opinions_text = opinions_text

    return results


def main():
    parser = argparse.ArgumentParser(description="Compute PE_t (narrative/code decoupling)")
    parser.add_argument("--telemetry", default="telemetry.jsonl",
                        help="Path to telemetry.jsonl")
    parser.add_argument("--opinions", default="opinions_history.jsonl",
                        help="Path to opinions_history.jsonl")
    parser.add_argument("--output", default=None,
                        help="Output file (default: stdout)")
    args = parser.parse_args()

    results = compute_pe(args.telemetry, args.opinions)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as f:
            for row in results:
                f.write(json.dumps(row) + "\n")
        print(f"Wrote {len(results)} PE records to {args.output}")
    else:
        for row in results:
            print(json.dumps(row))


if __name__ == "__main__":
    main()
