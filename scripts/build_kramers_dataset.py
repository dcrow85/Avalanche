#!/usr/bin/env python3
"""Build a first-pass Kramers dataset from filtered macrostate candidates.

This script joins:

- filtered macrostate candidates
- canonical telemetry rows
- PE_t-v2 cycle classifications

and emits:

- raw observables (waiting time, hamming directionality, vector hold length,
  temperature proxy, PE classification)
- provisional coefficient mapping and barrier proxy

The provisional coefficients are explicitly marked as such. They are useful for
inspection and plotting, but not yet a settled derivation.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


COUPLING_COEFFICIENTS = {
    "genuine_coupled_advance": 1.0,
    "bow_shock_advance": 0.8,
    "silent_structural_work": 0.65,
    "graveyard_only_shift": 0.5,
    "mixed_transition": 0.3,
    "code_narrative_without_graveyard": 0.25,
    "code_only_wobble": 0.2,
    "pattern_eater": 0.1,
    "administrative_or_stasis": 0.05,
}


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


def parse_bool_vector(value: Any) -> list[bool] | None:
    if isinstance(value, list) and all(isinstance(item, bool) for item in value):
        return list(value)
    return None


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


def canonical_hash_changes(canonical_dead_rows: list[dict[str, Any]]) -> set[int]:
    changed: set[int] = set()
    previous_hash: str | None = None
    for row in canonical_dead_rows:
        cycle = int(row["cycle"])
        current_hash = row.get("dead_ends_hash")
        if previous_hash is not None and current_hash != previous_hash:
            changed.add(cycle)
        previous_hash = current_hash
    return changed


def temperature_proxy(
    cycle: int,
    telemetry_by_cycle: dict[int, dict[str, Any]],
    hash_change_cycles: set[int],
    *,
    radius: int = 2,
) -> dict[str, Any]:
    cycles = [c for c in range(cycle - radius, cycle + radius + 1) if c in telemetry_by_cycle]
    total_tokens = 0
    for c in cycles:
        value = telemetry_by_cycle[c].get("total_tokens")
        try:
            total_tokens += int(value or 0)
        except (TypeError, ValueError):
            total_tokens += 0
    denom = sum(1 for c in cycles if c in hash_change_cycles)
    denom = max(denom, 1)
    return {
        "window_cycles": cycles,
        "window_total_tokens": total_tokens,
        "window_hash_changes": denom,
        "tokens_per_hash_change": total_tokens / denom,
    }


def directionality_fraction(row: dict[str, Any]) -> float:
    value = row.get("hamming_distance")
    try:
        if value is None:
            return 0.0
        return max(0.0, min(1.0, float(value) / 12.0))
    except (TypeError, ValueError):
        return 0.0


def persistence_fraction(hold_length: int, *, stable_target: int = 5) -> float:
    if hold_length <= 0:
        return 0.0
    return max(0.0, min(1.0, hold_length / stable_target))


def coupling_fraction(classification: str) -> float:
    return COUPLING_COEFFICIENTS.get(classification, 0.2)


def build_rows(
    *,
    label: str,
    filtered_candidates: list[dict[str, Any]],
    telemetry_rows: list[dict[str, Any]],
    dead_rows: list[dict[str, Any]],
    pe_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    canonical_telemetry = latest_cycle_rows([
        row for row in telemetry_rows
        if row.get("cycle_type") in (None, "grind") and "oracle_fixed" in row
    ])
    canonical_dead = latest_cycle_rows([
        row for row in dead_rows
        if row.get("cycle_type") in (None, "grind") and "cycle" in row
    ])
    telemetry_by_cycle = {int(row["cycle"]): row for row in canonical_telemetry}
    pe_by_cycle = {int(row["cycle"]): row for row in pe_rows}
    hold_by_cycle = vector_hold_lengths(canonical_telemetry)
    hash_change_cycles = canonical_hash_changes(canonical_dead)

    rows: list[dict[str, Any]] = []
    previous_transition_cycle: int | None = None
    infinite_barriers = 0

    for candidate in sorted(filtered_candidates, key=lambda row: int(row["cycle"])):
        cycle = int(candidate["cycle"])
        telemetry = telemetry_by_cycle.get(cycle, {})
        pe = pe_by_cycle.get(cycle, {})

        hold_length = hold_by_cycle.get(cycle, 0)
        coupling = coupling_fraction(str(pe.get("classification") or "mixed_transition"))
        direction = directionality_fraction(candidate)
        persistence = persistence_fraction(hold_length)
        anchoring = 1.0 if candidate.get("hash_changed") else 0.0
        product = coupling * direction * persistence * anchoring
        barrier = None
        if product > 0:
            barrier = -math.log(product)
        else:
            infinite_barriers += 1

        temp = temperature_proxy(cycle, telemetry_by_cycle, hash_change_cycles)
        waiting_time = None if previous_transition_cycle is None else cycle - previous_transition_cycle

        rows.append({
            "run_label": label,
            "cycle": cycle,
            "previous_cycle": candidate.get("previous_cycle"),
            "waiting_time_since_previous_transition": waiting_time,
            "transition_category": candidate.get("category"),
            "transition_reason": candidate.get("kramers_reason"),
            "from_basins": candidate.get("from_basins"),
            "to_basins": candidate.get("to_basins"),
            "oracle_fixed": telemetry.get("oracle_fixed"),
            "oracle_combined": telemetry.get("oracle_combined"),
            "fixed_suite_vector": telemetry.get("fixed_suite_vector"),
            "hamming_distance": candidate.get("hamming_distance"),
            "vector_hold_length": hold_length,
            "stable_vector_5": hold_length >= 5,
            "probe_g_distance": telemetry.get("probe_g_distance"),
            "work_event": bool(telemetry.get("work_event")),
            "total_tokens_cycle": telemetry.get("total_tokens"),
            "temperature_window_cycles": temp["window_cycles"],
            "temperature_window_total_tokens": temp["window_total_tokens"],
            "temperature_window_hash_changes": temp["window_hash_changes"],
            "temperature_tokens_per_hash_change": round(temp["tokens_per_hash_change"], 6),
            "pe_classification": pe.get("classification"),
            "pe_narrative_drift": pe.get("narrative_drift"),
            "pe_code_drift": pe.get("code_drift"),
            "pe_graveyard_drift": pe.get("graveyard_drift"),
            "provisional_coupling_coeff": round(coupling, 6),
            "provisional_directionality_coeff": round(direction, 6),
            "provisional_persistence_coeff": round(persistence, 6),
            "provisional_anchoring_coeff": round(anchoring, 6),
            "provisional_barrier_log_term": round(barrier, 6) if barrier is not None else None,
            "provisional_barrier_is_infinite": barrier is None,
        })
        previous_transition_cycle = cycle

    summary = {
        "run_label": label,
        "rows": len(rows),
        "infinite_barrier_rows": infinite_barriers,
        "finite_barrier_rows": len(rows) - infinite_barriers,
        "pe_class_counts": _count_by(rows, "pe_classification"),
        "transition_reason_counts": _count_by(rows, "transition_reason"),
    }
    return rows, summary


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key))
        counts[value] = counts.get(value, 0) + 1
    return counts


def write_outputs(output_dir: Path, label: str, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / f"{label}_kramers_dataset.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    (output_dir / f"{label}_kramers_dataset_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build first-pass Kramers dataset rows.")
    parser.add_argument("--label", required=True)
    parser.add_argument("--filtered-candidates", type=Path, required=True)
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--dead-ends", type=Path, required=True)
    parser.add_argument("--pe-steps", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    rows, summary = build_rows(
        label=args.label,
        filtered_candidates=load_jsonl(args.filtered_candidates),
        telemetry_rows=load_jsonl(args.telemetry),
        dead_rows=load_jsonl(args.dead_ends),
        pe_rows=load_jsonl(args.pe_steps),
    )
    write_outputs(args.output_dir, args.label, rows, summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
