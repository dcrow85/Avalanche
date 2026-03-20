from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.compute_ast_bifurcation import classify_grind_rows, load_jsonl


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_classifies_same_bifurcation_and_reversion(tmp_path: Path) -> None:
    rows = [
        {"cycle": 1, "cycle_type": "grind", "solver_ast_structure_hash": "A", "solver_ast_node_count": 10, "work_event": False},
        {"cycle": 2, "cycle_type": "grind", "solver_ast_structure_hash": "A", "solver_ast_node_count": 10, "work_event": False},
        {"cycle": 3, "cycle_type": "grind", "solver_ast_structure_hash": "B", "solver_ast_node_count": 14, "work_event": True},
        {"cycle": 4, "cycle_type": "grind", "solver_ast_structure_hash": "A", "solver_ast_node_count": 10, "work_event": False},
    ]
    cycle_records, summary = classify_grind_rows(rows)
    assert cycle_records[1]["classification"] == "same_as_prev"
    assert cycle_records[2]["classification"] == "bifurcation"
    assert cycle_records[3]["classification"] == "reversion"
    assert cycle_records[3]["reversion_target_cycle"] == 1
    assert summary["total_bifurcations"] == 1
    assert summary["total_reversions"] == 1


def test_classifies_gap_when_format_fatal_between_grinds() -> None:
    rows = [
        {"cycle": 1, "cycle_type": "grind", "solver_ast_structure_hash": "A", "solver_ast_node_count": 10, "work_event": False},
        {"cycle": 2, "event": "format_fatal"},
        {"cycle": 3, "cycle_type": "grind", "solver_ast_structure_hash": "B", "solver_ast_node_count": 12, "work_event": False},
        {"cycle": 4, "cycle_type": "grind", "solver_ast_structure_hash": "C", "solver_ast_node_count": 20, "work_event": False},
    ]
    cycle_records, summary = classify_grind_rows(rows)
    assert cycle_records[1]["classification"] == "gap"
    assert cycle_records[2]["classification"] == "bifurcation"
    assert summary["total_gaps"] == 1
    assert summary["total_bifurcations"] == 1


def test_load_jsonl_ignores_bad_lines(tmp_path: Path) -> None:
    path = tmp_path / "telemetry.jsonl"
    path.write_text('{"cycle":1}\nnot-json\n{"cycle":2}\n', encoding="utf-8")
    rows = load_jsonl(path)
    assert len(rows) == 2
