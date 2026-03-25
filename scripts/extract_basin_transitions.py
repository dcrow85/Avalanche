#!/usr/bin/env python3
"""Extract canonical graveyard transition candidates from mirrored run history.

This script is intentionally narrower than a full Kramers fit. It does the
local hygiene step first:

- collapse retries to the last grind row per cycle
- compare graveyard state cycle-to-cycle
- emit candidate structural transitions with enough evidence columns to filter
  true macrostate moves from local/admin churn
"""
from __future__ import annotations

import argparse
import json
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


def parse_run_arg(raw: str) -> tuple[str, Path]:
    if "=" in raw:
        label, path_str = raw.split("=", 1)
        return label.strip(), Path(path_str.strip())
    path = Path(raw.strip())
    return path.parent.name if path.name.startswith("run-") else path.name, path


def active_entries(dead_ends: dict[str, Any], key: str) -> list[dict[str, Any]]:
    active = [
        entry for entry in (dead_ends or {}).get(key, [])
        if entry.get("status") == "ACTIVE"
    ]
    active.sort(key=lambda item: item.get("id", ""))
    return active


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def entry_map(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(entry.get("id")): entry for entry in entries}


def basin_signature(dead_ends: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": basin.get("id"),
            "claim": basin.get("claim"),
            "cited_families": list(basin.get("cited_families", []) or []),
        }
        for basin in active_entries(dead_ends, "basins")
    ]


def diff_maps(
    previous: dict[str, dict[str, Any]],
    current: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str], list[str]]:
    previous_ids = set(previous)
    current_ids = set(current)
    added = sorted(current_ids - previous_ids)
    removed = sorted(previous_ids - current_ids)
    changed = sorted(
        entry_id for entry_id in previous_ids & current_ids
        if canonical_json(previous[entry_id]) != canonical_json(current[entry_id])
    )
    return added, removed, changed


def classify_transition(
    *,
    basin_added: list[str],
    basin_removed: list[str],
    basin_changed: list[str],
    family_added: list[str],
    family_removed: list[str],
    family_changed: list[str],
    local_added: list[str],
    local_removed: list[str],
    local_changed: list[str],
    work_event: bool,
) -> str:
    if basin_added or basin_removed:
        return "basin_id_transition"
    if basin_changed:
        return "basin_content_transition"
    if family_added or family_removed or family_changed or local_added or local_removed or local_changed:
        return "family_or_local_only"
    if work_event:
        return "work_event_without_structural_diff"
    return "no_structural_change"


def extract_run(run_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    telemetry_rows = latest_cycle_rows([
        row for row in load_jsonl(run_dir / "telemetry.jsonl")
        if row.get("cycle_type") in (None, "grind") and "oracle_fixed" in row
    ])
    dead_rows = latest_cycle_rows([
        row for row in load_jsonl(run_dir / "dead_ends_history.jsonl")
        if row.get("cycle_type") in (None, "grind") and "cycle" in row
    ])
    opinions_rows = latest_cycle_rows([
        row for row in load_jsonl(run_dir / "opinions_history.jsonl")
        if row.get("cycle_type") in (None, "grind") and "cycle" in row
    ])

    telemetry_by_cycle = {int(row["cycle"]): row for row in telemetry_rows}
    dead_by_cycle = {int(row["cycle"]): row for row in dead_rows}
    opinions_by_cycle = {int(row["cycle"]): row for row in opinions_rows}

    cycles = sorted(set(telemetry_by_cycle) & set(dead_by_cycle))
    transitions: list[dict[str, Any]] = []
    summary_counts: dict[str, int] = {}

    previous_cycle: int | None = None
    for cycle in cycles:
        if previous_cycle is None:
            previous_cycle = cycle
            continue

        previous_dead = dead_by_cycle[previous_cycle].get("dead_ends") or {}
        current_dead = dead_by_cycle[cycle].get("dead_ends") or {}
        previous_tel = telemetry_by_cycle[previous_cycle]
        current_tel = telemetry_by_cycle[cycle]
        current_op = opinions_by_cycle.get(cycle, {})

        previous_basins = entry_map(active_entries(previous_dead, "basins"))
        current_basins = entry_map(active_entries(current_dead, "basins"))
        previous_families = entry_map(active_entries(previous_dead, "families"))
        current_families = entry_map(active_entries(current_dead, "families"))
        previous_locals = entry_map(active_entries(previous_dead, "locals"))
        current_locals = entry_map(active_entries(current_dead, "locals"))

        basin_added, basin_removed, basin_changed = diff_maps(previous_basins, current_basins)
        family_added, family_removed, family_changed = diff_maps(previous_families, current_families)
        local_added, local_removed, local_changed = diff_maps(previous_locals, current_locals)

        hash_changed = dead_by_cycle[cycle].get("dead_ends_hash") != dead_by_cycle[previous_cycle].get("dead_ends_hash")
        category = classify_transition(
            basin_added=basin_added,
            basin_removed=basin_removed,
            basin_changed=basin_changed,
            family_added=family_added,
            family_removed=family_removed,
            family_changed=family_changed,
            local_added=local_added,
            local_removed=local_removed,
            local_changed=local_changed,
            work_event=bool(current_tel.get("work_event")),
        )
        summary_counts[category] = summary_counts.get(category, 0) + 1

        transitions.append({
            "cycle": cycle,
            "previous_cycle": previous_cycle,
            "category": category,
            "hash_changed": hash_changed,
            "work_event": bool(current_tel.get("work_event")),
            "oracle_fixed": current_tel.get("oracle_fixed"),
            "oracle_fixed_prev": previous_tel.get("oracle_fixed"),
            "oracle_combined": current_tel.get("oracle_combined"),
            "hamming_distance": current_tel.get("hamming_distance"),
            "probe_g_distance": current_tel.get("probe_g_distance"),
            "solver_ast_hash_changed": bool(current_tel.get("solver_ast_hash_changed")),
            "from_hash": dead_by_cycle[previous_cycle].get("dead_ends_hash"),
            "to_hash": dead_by_cycle[cycle].get("dead_ends_hash"),
            "from_basins": basin_signature(previous_dead),
            "to_basins": basin_signature(current_dead),
            "basin_added": basin_added,
            "basin_removed": basin_removed,
            "basin_changed": basin_changed,
            "family_added": family_added,
            "family_removed": family_removed,
            "family_changed": family_changed,
            "local_added": local_added,
            "local_removed": local_removed,
            "local_changed": local_changed,
            "opinions_text_hash": current_op.get("opinions_text_hash"),
        })
        previous_cycle = cycle

    summary = {
        "run_dir": str(run_dir),
        "total_cycles": len(cycles),
        "total_steps": max(0, len(cycles) - 1),
        "category_counts": summary_counts,
        "hash_changed_steps": sum(1 for row in transitions if row["hash_changed"]),
        "work_event_steps": sum(1 for row in transitions if row["work_event"]),
        "candidate_macrostate_steps": sum(
            1 for row in transitions
            if row["category"] in {"basin_id_transition", "basin_content_transition"}
        ),
    }
    return transitions, summary


def write_outputs(output_dir: Path, label: str, transitions: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{label}_transition_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    with (output_dir / f"{label}_transition_candidates.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in transitions:
            handle.write(json.dumps(row) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract canonical graveyard transition candidates.")
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
        help="Optional output directory for per-run JSON artifacts.",
    )
    args = parser.parse_args()

    for raw in args.run:
        label, run_dir = parse_run_arg(raw)
        transitions, summary = extract_run(run_dir)
        if args.output_dir:
            write_outputs(args.output_dir, label, transitions, summary)
        print(json.dumps({
            "label": label,
            "run_dir": str(run_dir),
            "summary": summary,
        }))


if __name__ == "__main__":
    main()
