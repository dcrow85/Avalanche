#!/usr/bin/env python3
"""Reconstruct a best-effort sidecar snapshot from exact-history artifacts.

This is intentionally honest about its limitations: it recreates the
workspace-facing surfaces at a target cycle, but it cannot replay the exact
provider context window unless that context was separately logged.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import hypervisor_v44 as hv
from v44_epistemics import blank_state, merge_state, render_dead_ends_md, save_state


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _latest_cycle_row(rows: list[dict[str, Any]], cycle: int) -> dict[str, Any]:
    exact = [row for row in rows if int(row.get("cycle", -1)) == cycle]
    if not exact:
        raise ValueError(f"No row found for cycle {cycle}")
    return exact[-1]


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def reconstruct_snapshot(source_run: Path, cycle: int, output_dir: Path) -> dict[str, Any]:
    opinions_rows = _load_jsonl(source_run / "opinions_history.jsonl")
    solver_rows = _load_jsonl(source_run / "solver_history.jsonl")
    dead_rows = _load_jsonl(source_run / "dead_ends_history.jsonl")
    telemetry_rows = _load_jsonl(source_run / "telemetry.jsonl")

    opinions_row = _latest_cycle_row(opinions_rows, cycle)
    solver_row = _latest_cycle_row(solver_rows, cycle)
    dead_row = _latest_cycle_row(dead_rows, cycle)
    telemetry_row = _latest_cycle_row(telemetry_rows, cycle)

    output_dir.mkdir(parents=True, exist_ok=True)

    opinions_text = str(opinions_row.get("opinions_text", "") or "")
    solver_text = str(solver_row.get("solver_text", "") or "")
    dead_ends = dead_row.get("dead_ends", {})
    if not isinstance(dead_ends, dict):
        raise ValueError(f"dead_ends history row at cycle {cycle} did not contain a JSON object")

    _write_text(output_dir / hv.OPINIONS_FILE, opinions_text)
    _write_text(output_dir / hv.SOLVER_FILE, solver_text.rstrip() + ("\n" if solver_text else ""))
    (output_dir / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(dead_ends, indent=2), encoding="utf-8")
    _write_text(output_dir / hv.DEAD_ENDS_FILE, render_dead_ends_md(dead_ends))
    reconstructed_state = merge_state(blank_state(), dead_ends, cycle=cycle)
    save_state(str(output_dir / hv.DEAD_END_STATE_FILE), reconstructed_state)

    copied_optional: list[str] = []
    for name in (hv.GOAL_FILE, hv.DATA_FILE):
        src = source_run / name
        if src.exists():
            _write_text(output_dir / name, src.read_text(encoding="utf-8"))
            copied_optional.append(name)

    note = (
        "# Reconstructed Context Sidecar\n\n"
        f"Source run: {source_run}\n"
        f"Target cycle: {cycle}\n\n"
        "This snapshot reconstructs the workspace-facing surfaces from exact-history logs:\n"
        "- opinions.md from opinions_history.jsonl\n"
        "- solver.py from solver_history.jsonl\n"
        "- dead-ends.json from dead_ends_history.jsonl\n\n"
        "It does not recreate the exact provider prompt window at that cycle unless the full prompt "
        "assembly was separately logged. Treat this as a reconstructed-context sidecar, not a perfect replay.\n"
    )
    _write_text(output_dir / "RECONSTRUCTION_NOTE.md", note)

    metadata = {
        "source_run": str(source_run),
        "target_cycle": cycle,
        "reconstruction_type": "reconstructed_context_sidecar",
        "copied_optional_files": copied_optional,
        "opinions_history_row": opinions_row,
        "solver_history_row": solver_row,
        "dead_ends_history_row": dead_row,
        "telemetry_row": telemetry_row,
        "limitations": [
            "Exact provider prompt assembly at the target cycle was not reconstructed.",
            "dead-end-state.json registry/history was rebuilt from the active dead-ends surface.",
            "data.json and goal.md were copied from the source run directory, not reconstructed per cycle.",
        ],
    }
    (output_dir / "reconstruction_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconstruct a best-effort sidecar snapshot from exact-history artifacts.")
    parser.add_argument("--source-run", required=True, help="Path to the source run directory")
    parser.add_argument("--cycle", type=int, required=True, help="Target cycle to reconstruct")
    parser.add_argument("--output-dir", required=True, help="Directory to write the reconstructed snapshot")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metadata = reconstruct_snapshot(Path(args.source_run), args.cycle, Path(args.output_dir))
    print(json.dumps({
        "output_dir": args.output_dir,
        "target_cycle": args.cycle,
        "graveyard_hash": metadata["dead_ends_history_row"].get("dead_ends_hash"),
        "probe_g_distance": metadata["telemetry_row"].get("probe_g_distance"),
        "reconstruction_type": metadata["reconstruction_type"],
    }, indent=2))


if __name__ == "__main__":
    main()
