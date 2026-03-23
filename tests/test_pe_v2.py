from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.compute_pe_v2 import build_step_rows, classify_steps, latest_cycle_rows


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_build_step_rows_computes_graveyard_drift() -> None:
    telemetry = [
        {"cycle": 1, "cycle_type": "grind", "oracle_fixed": 0.1, "solver_ast_hash_changed": False, "solver_ast_node_delta": 0, "solver_ast_node_count": 10},
        {"cycle": 2, "cycle_type": "grind", "oracle_fixed": 0.2, "solver_ast_hash_changed": False, "solver_ast_node_delta": 0, "solver_ast_node_count": 10},
    ]
    opinions = [
        {"cycle": 1, "cycle_type": "grind", "opinions_text": "alpha beta"},
        {"cycle": 2, "cycle_type": "grind", "opinions_text": "alpha gamma"},
    ]
    dead = [
        {"cycle": 1, "cycle_type": "grind", "dead_ends_hash": "A"},
        {"cycle": 2, "cycle_type": "grind", "dead_ends_hash": "B"},
    ]
    steps = build_step_rows(telemetry, opinions, dead)
    assert len(steps) == 1
    assert steps[0]["graveyard_drift"] is True
    assert steps[0]["narrative_drift"] > 0


def test_latest_cycle_rows_keeps_last_retry_for_cycle() -> None:
    rows = [
        {"cycle": 1, "oracle_fixed": 0.1},
        {"cycle": 1, "oracle_fixed": 0.2},
        {"cycle": 2, "oracle_fixed": 0.3},
    ]
    collapsed = latest_cycle_rows(rows)
    assert collapsed == [
        {"cycle": 1, "oracle_fixed": 0.2},
        {"cycle": 2, "oracle_fixed": 0.3},
    ]


def test_classifies_pattern_eater() -> None:
    steps = [{
        "cycle": 2,
        "narrative_drift": 0.8,
        "code_drift": 0.0,
        "graveyard_drift": False,
    }]
    classified, summary = classify_steps(steps, narrative_threshold=0.5, code_threshold=1.0)
    assert classified[0]["classification"] == "pattern_eater"
    assert summary["class_counts"]["pattern_eater"] == 1


def test_classifies_bow_shock_advance() -> None:
    steps = [{
        "cycle": 3,
        "narrative_drift": 0.7,
        "code_drift": 0.0,
        "graveyard_drift": True,
    }]
    classified, _ = classify_steps(steps, narrative_threshold=0.5, code_threshold=1.0)
    assert classified[0]["classification"] == "bow_shock_advance"


def test_classifies_genuine_coupled_advance() -> None:
    steps = [{
        "cycle": 4,
        "narrative_drift": 0.7,
        "code_drift": 1.3,
        "graveyard_drift": True,
    }]
    classified, _ = classify_steps(steps, narrative_threshold=0.5, code_threshold=1.0)
    assert classified[0]["classification"] == "genuine_coupled_advance"


def test_classifies_silent_structural_work() -> None:
    steps = [{
        "cycle": 5,
        "narrative_drift": 0.1,
        "code_drift": 1.4,
        "graveyard_drift": True,
    }]
    classified, _ = classify_steps(steps, narrative_threshold=0.5, code_threshold=1.0)
    assert classified[0]["classification"] == "silent_structural_work"


def test_classifies_administrative_or_stasis() -> None:
    steps = [{
        "cycle": 6,
        "narrative_drift": 0.1,
        "code_drift": 0.0,
        "graveyard_drift": False,
    }]
    classified, _ = classify_steps(steps, narrative_threshold=0.5, code_threshold=1.0)
    assert classified[0]["classification"] == "administrative_or_stasis"


def test_emits_fallback_classes_for_uncovered_combinations() -> None:
    steps = [
        {"cycle": 7, "narrative_drift": 0.8, "code_drift": 1.4, "graveyard_drift": False},
        {"cycle": 8, "narrative_drift": 0.1, "code_drift": 0.0, "graveyard_drift": True},
        {"cycle": 9, "narrative_drift": 0.1, "code_drift": 1.4, "graveyard_drift": False},
    ]
    classified, _ = classify_steps(steps, narrative_threshold=0.5, code_threshold=1.0)
    labels = [row["classification"] for row in classified]
    assert labels == [
        "code_narrative_without_graveyard",
        "graveyard_only_shift",
        "code_only_wobble",
    ]


def test_auto_thresholds_use_positive_medians() -> None:
    steps = [
        {"cycle": 2, "narrative_drift": 0.0, "code_drift": 0.0, "graveyard_drift": False},
        {"cycle": 3, "narrative_drift": 0.6, "code_drift": 0.0, "graveyard_drift": False},
        {"cycle": 4, "narrative_drift": 0.8, "code_drift": 2.0, "graveyard_drift": True},
    ]
    _, summary = classify_steps(steps)
    assert summary["narrative_threshold"] == 0.6
    assert summary["code_threshold"] == 2.0
