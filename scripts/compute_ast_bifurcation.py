#!/usr/bin/env python3
"""Compute AST bifurcation / reversion metrics from run telemetry.

This uses the existing AST hash + node-count instrumentation already present in
telemetry.jsonl. It does not require solver text history.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def parse_run_arg(raw: str) -> tuple[str, Path]:
    if "=" in raw:
        label, path_str = raw.split("=", 1)
        return label.strip(), Path(path_str.strip())
    p = Path(raw.strip())
    return p.name, p


def format_fatal_cycles(rows: list[dict[str, Any]]) -> set[int]:
    cycles: set[int] = set()
    for row in rows:
        if row.get("event") in {"format_fatal", "altitude_fatal"}:
            cycle = row.get("cycle")
            if isinstance(cycle, int):
                cycles.add(cycle)
    return cycles


def classify_grind_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grind = [row for row in rows if row.get("cycle_type") == "grind"]
    fatal_cycles = format_fatal_cycles(rows)

    cycle_records: list[dict[str, Any]] = []
    seen_hash_first_cycle: dict[str, int] = {}
    last_bifurcation_cycle: int | None = None
    bifurcation_cycles: list[int] = []
    bifurcation_node_deltas: list[dict[str, int]] = []

    total_work = sum(1 for row in grind if row.get("work_event"))
    total_same = 0
    total_bif = 0
    total_rev = 0
    total_gap = 0
    hash_change_events = 0

    previous_grind: dict[str, Any] | None = None
    for row in grind:
        cycle = int(row.get("cycle"))
        ast_hash = row.get("solver_ast_structure_hash")
        node_count = row.get("solver_ast_node_count")

        classification: str | None = None
        reversion_target_cycle: int | None = None
        hash_delta: bool | None = None
        node_count_delta: int | None = None

        if previous_grind is not None:
            prev_cycle = int(previous_grind.get("cycle"))
            prev_hash = previous_grind.get("solver_ast_structure_hash")
            prev_nodes = previous_grind.get("solver_ast_node_count")
            intervening_fatals = any(prev_cycle < fc < cycle for fc in fatal_cycles)

            if intervening_fatals:
                classification = "gap"
                total_gap += 1
                hash_delta = None
                node_count_delta = None
            else:
                hash_delta = ast_hash != prev_hash
                if node_count is not None and prev_nodes is not None:
                    node_count_delta = int(node_count) - int(prev_nodes)
                if not hash_delta:
                    classification = "same_as_prev"
                    total_same += 1
                else:
                    hash_change_events += 1
                    if ast_hash in seen_hash_first_cycle:
                        classification = "reversion"
                        reversion_target_cycle = seen_hash_first_cycle[ast_hash]
                        total_rev += 1
                    else:
                        classification = "bifurcation"
                        total_bif += 1
                        bifurcation_cycles.append(cycle)
                        bifurcation_node_deltas.append(
                            {"cycle": cycle, "node_count_delta": int(node_count_delta or 0)}
                        )
                        last_bifurcation_cycle = cycle

        if ast_hash and ast_hash not in seen_hash_first_cycle:
            seen_hash_first_cycle[ast_hash] = cycle

        if previous_grind is None:
            cycles_since_last_bifurcation = None
        elif last_bifurcation_cycle is None:
            cycles_since_last_bifurcation = None
        elif classification == "bifurcation":
            cycles_since_last_bifurcation = 0
        else:
            cycles_since_last_bifurcation = cycle - last_bifurcation_cycle

        cycle_records.append({
            "cycle_number": cycle,
            "ast_hash": ast_hash,
            "ast_node_count": node_count,
            "hash_delta": hash_delta,
            "node_count_delta": node_count_delta,
            "classification": classification,
            "reversion_target_cycle": reversion_target_cycle,
            "cycles_since_last_bifurcation": cycles_since_last_bifurcation,
            "oracle_fixed": row.get("oracle_fixed"),
            "work_event": row.get("work_event"),
        })
        previous_grind = row

    inter_bif_intervals: list[int] = []
    if len(bifurcation_cycles) >= 2:
        inter_bif_intervals = [
            later - earlier for earlier, later in zip(bifurcation_cycles, bifurcation_cycles[1:])
        ]

    summary = {
        "total_grind_rows": len(grind),
        "total_w_t_events": total_work,
        "total_unique_ast_hashes": len(seen_hash_first_cycle),
        "total_bifurcations": total_bif,
        "total_reversions": total_rev,
        "total_same_as_prev": total_same,
        "total_gaps": total_gap,
        "bifurcation_density": round(len(seen_hash_first_cycle) / len(grind), 4) if grind else None,
        "bifurcation_to_tombstone_ratio": round(total_bif / total_work, 4) if total_work else None,
        "mean_inter_bifurcation_interval": round(statistics.mean(inter_bif_intervals), 4) if inter_bif_intervals else None,
        "reversion_rate": round(total_rev / hash_change_events, 4) if hash_change_events else None,
        "bifurcation_cycles_with_node_deltas": bifurcation_node_deltas,
        "format_fatal_cycles": sorted(fatal_cycles),
    }
    return cycle_records, summary


def run_analysis(label: str, run_dir: Path) -> dict[str, Any]:
    telemetry_path = run_dir / "telemetry.jsonl"
    rows = load_jsonl(telemetry_path)
    cycle_records, summary = classify_grind_rows(rows)
    return {
        "label": label,
        "run_dir": str(run_dir),
        "cycle_records": cycle_records,
        "summary": summary,
    }


def write_outputs(output_dir: Path, result: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    label = result["label"]
    (output_dir / f"{label}_ast_bifurcation_summary.json").write_text(
        json.dumps(result["summary"], indent=2),
        encoding="utf-8",
    )
    with (output_dir / f"{label}_ast_bifurcation_cycles.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for row in result["cycle_records"]:
            f.write(json.dumps(row) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute AST bifurcation filter metrics from telemetry.")
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        help="Run spec as label=PATH or just PATH. Repeat for multiple runs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional directory to write per-run JSON outputs.",
    )
    args = parser.parse_args()

    for raw in args.run:
        label, run_dir = parse_run_arg(raw)
        result = run_analysis(label, run_dir)
        if args.output_dir:
            write_outputs(args.output_dir, result)
        print(json.dumps({
            "label": result["label"],
            "run_dir": result["run_dir"],
            "summary": result["summary"],
        }))


if __name__ == "__main__":
    main()
