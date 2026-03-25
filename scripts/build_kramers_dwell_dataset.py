#!/usr/bin/env python3
"""Build predeclared dwell-barrier datasets for Kramers analysis.

This pass is intentionally separate from the event-local barrier dataset.
It uses fixed, theory-motivated dwell rules:

- dwell window begins at the previous kept transition cycle, or the earliest
  available grind cycle if there is no previous kept transition
- dwell window is capped at 12 grind cycles
- dwell window ends just before the current transition cycle

Two barriers are emitted:

- oracle_dwell_barrier:
    cumulative positive fixed-score gain + cumulative hamming mass
- structure_dwell_barrier:
    cumulative AST hash-change count + relative node-count standard deviation
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any


MAX_DWELL_CYCLES = 12


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


def latest_cycle_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[int, dict[str, Any]] = {}
    order: list[int] = []
    for row in rows:
        if "cycle" not in row:
            continue
        cycle = int(row["cycle"])
        if cycle not in latest:
            order.append(cycle)
        latest[cycle] = row
    return [latest[cycle] for cycle in order]


def canonical_grind_telemetry(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return latest_cycle_rows([
        row for row in rows
        if row.get("cycle_type") in (None, "grind") and "oracle_fixed" in row
    ])


def parse_bool_vector(value: Any) -> list[bool] | None:
    if isinstance(value, list) and all(isinstance(item, bool) for item in value):
        return list(value)
    return None


def hamming_mass(row: dict[str, Any]) -> float:
    try:
        value = row.get("hamming_distance")
        if value is None:
            return 0.0
        return max(0.0, float(value) / 12.0)
    except (TypeError, ValueError):
        return 0.0


def positive_score_gain(current: dict[str, Any], previous: dict[str, Any] | None) -> float:
    if previous is None:
        return 0.0
    try:
        now = float(current.get("oracle_fixed") or 0.0)
        before = float(previous.get("oracle_fixed") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, now - before)


def relative_node_std(rows: list[dict[str, Any]]) -> float:
    values: list[float] = []
    for row in rows:
        try:
            value = row.get("solver_ast_node_count")
            if value is None:
                continue
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    if len(values) < 2:
        return 0.0
    mean = statistics.fmean(values)
    if mean <= 0:
        return 0.0
    return statistics.pstdev(values) / mean


def mean_node_count(rows: list[dict[str, Any]]) -> float:
    values: list[float] = []
    for row in rows:
        try:
            value = row.get("solver_ast_node_count")
            if value is None:
                continue
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    if not values:
        return 0.0
    return statistics.fmean(values)


def vector_hold_lengths(canonical_rows: list[dict[str, Any]]) -> dict[int, int]:
    holds: dict[int, int] = {}
    vectors_by_cycle: list[tuple[int, list[bool] | None]] = [
        (int(row["cycle"]), parse_bool_vector(row.get("fixed_suite_vector")))
        for row in canonical_rows
    ]
    for index, (cycle, vector) in enumerate(vectors_by_cycle):
        if vector is None:
            holds[cycle] = 0
            continue
        hold = 1
        next_index = index + 1
        while next_index < len(vectors_by_cycle):
            _, next_vector = vectors_by_cycle[next_index]
            if next_vector != vector:
                break
            hold += 1
            next_index += 1
        holds[cycle] = hold
    return holds


def dwell_cycles_for_transition(
    *,
    transition_cycle: int,
    previous_transition_cycle: int | None,
    available_cycles: list[int],
) -> list[int]:
    if not available_cycles:
        return []
    earliest_cycle = available_cycles[0]
    lower_bound = earliest_cycle if previous_transition_cycle is None else previous_transition_cycle
    lower_bound = max(lower_bound, transition_cycle - MAX_DWELL_CYCLES)
    return [cycle for cycle in available_cycles if lower_bound <= cycle < transition_cycle]


def build_rows(
    *,
    label: str,
    filtered_candidates: list[dict[str, Any]],
    telemetry_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    canonical = canonical_grind_telemetry(telemetry_rows)
    telemetry_by_cycle = {int(row["cycle"]): row for row in canonical}
    available_cycles = [int(row["cycle"]) for row in canonical]
    hold_by_cycle = vector_hold_lengths(canonical)

    rows: list[dict[str, Any]] = []
    previous_transition_cycle: int | None = None

    for candidate in sorted(filtered_candidates, key=lambda row: int(row["cycle"])):
        cycle = int(candidate["cycle"])
        dwell_cycles = dwell_cycles_for_transition(
            transition_cycle=cycle,
            previous_transition_cycle=previous_transition_cycle,
            available_cycles=available_cycles,
        )
        dwell_rows = [telemetry_by_cycle[dwell_cycle] for dwell_cycle in dwell_cycles if dwell_cycle in telemetry_by_cycle]

        oracle_gain = 0.0
        oracle_hamming = 0.0
        ast_change_count = 0
        node_delta_mass = 0
        previous_row: dict[str, Any] | None = None
        for row in dwell_rows:
            oracle_gain += positive_score_gain(row, previous_row)
            oracle_hamming += hamming_mass(row)
            ast_change_count += 1 if row.get("solver_ast_hash_changed") else 0
            try:
                node_delta_mass += abs(int(row.get("solver_ast_node_delta") or 0))
            except (TypeError, ValueError):
                node_delta_mass += 0
            previous_row = row

        structure_variance = relative_node_std(dwell_rows)
        mean_nodes = mean_node_count(dwell_rows)
        oracle_barrier = oracle_gain + oracle_hamming
        structure_barrier = ast_change_count + structure_variance
        dwell_count = max(1, len(dwell_cycles))
        ast_change_density = ast_change_count / dwell_count
        node_delta_density = node_delta_mass / dwell_count
        node_delta_relative_density = (node_delta_density / mean_nodes) if mean_nodes > 0 else 0.0
        structure_barrier_normalized = ast_change_density + node_delta_relative_density + structure_variance

        current_telemetry = telemetry_by_cycle.get(cycle, {})
        waiting_time = None if previous_transition_cycle is None else cycle - previous_transition_cycle

        rows.append({
            "run_label": label,
            "cycle": cycle,
            "previous_transition_cycle": previous_transition_cycle,
            "waiting_time_since_previous_transition": waiting_time,
            "transition_category": candidate.get("category"),
            "transition_reason": candidate.get("kramers_reason"),
            "from_basins": candidate.get("from_basins"),
            "to_basins": candidate.get("to_basins"),
            "work_event": bool(current_telemetry.get("work_event")),
            "oracle_fixed": current_telemetry.get("oracle_fixed"),
            "oracle_combined": current_telemetry.get("oracle_combined"),
            "fixed_suite_vector": current_telemetry.get("fixed_suite_vector"),
            "current_vector_hold_length": hold_by_cycle.get(cycle, 0),
            "current_probe_g_distance": current_telemetry.get("probe_g_distance"),
            "dwell_cycles": dwell_cycles,
            "dwell_cycle_count": len(dwell_cycles),
            "oracle_dwell_positive_gain": round(oracle_gain, 6),
            "oracle_dwell_hamming_mass": round(oracle_hamming, 6),
            "oracle_dwell_barrier": round(oracle_barrier, 6),
            "structure_dwell_ast_change_count": ast_change_count,
            "structure_dwell_node_delta_mass": node_delta_mass,
            "structure_dwell_mean_node_count": round(mean_nodes, 6),
            "structure_dwell_relative_node_std": round(structure_variance, 6),
            "structure_dwell_barrier": round(structure_barrier, 6),
            "structure_dwell_ast_change_density": round(ast_change_density, 6),
            "structure_dwell_node_delta_density": round(node_delta_density, 6),
            "structure_dwell_node_delta_relative_density": round(node_delta_relative_density, 6),
            "structure_dwell_barrier_normalized": round(structure_barrier_normalized, 6),
        })
        previous_transition_cycle = cycle

    summary = {
        "run_label": label,
        "rows": len(rows),
        "max_dwell_cycles": MAX_DWELL_CYCLES,
        "rows_with_waiting_time": sum(1 for row in rows if row["waiting_time_since_previous_transition"] not in (None, 0)),
    }
    return rows, summary


def write_outputs(output_dir: Path, label: str, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / f"{label}_dwell_dataset.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    (output_dir / f"{label}_dwell_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build predeclared dwell-barrier Kramers dataset rows.")
    parser.add_argument("--label", required=True)
    parser.add_argument("--filtered-candidates", type=Path, required=True)
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    rows, summary = build_rows(
        label=args.label,
        filtered_candidates=load_jsonl(args.filtered_candidates),
        telemetry_rows=load_jsonl(args.telemetry),
    )
    write_outputs(args.output_dir, args.label, rows, summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
