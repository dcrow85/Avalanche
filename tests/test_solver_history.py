"""Tests for solver_history.jsonl logging in compression_assay."""

from __future__ import annotations

import ast
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_log_solver_history_grind_row(monkeypatch, tmp_path):
    import compression_assay as ca
    import hypervisor_v44 as hv

    monkeypatch.chdir(tmp_path)

    solver_text = (
        "def transduce(arr: list[int]) -> list[int]:\n"
        "    return [-x for x in arr]\n"
    )
    opinions_text = "Current theory: negate all elements."

    ca._log_solver_history(
        42,
        "grind",
        opinions_text,
        solver_text=solver_text,
        oracle_vector=[True, False, True],
    )

    history_path = tmp_path / ca.SOLVER_HISTORY_FILE
    rows = history_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1

    record = json.loads(rows[0])
    assert record["cycle"] == 42
    assert record["cycle_type"] == "grind"
    assert record["solver_text"] == solver_text
    assert record["oracle_vector"] == [True, False, True]
    assert record["opinions_text"] == opinions_text
    assert record["ast_hash"] == hv.solver_ast_structure_hash(solver_text)
    assert record["ast_node_count"] == hv.solver_ast_node_count(solver_text)
    ast.parse(record["solver_text"])


def test_log_solver_history_failure_row(monkeypatch, tmp_path):
    import compression_assay as ca

    monkeypatch.chdir(tmp_path)

    ca._log_solver_history(
        43,
        "grind",
        "Theory preserved after fatal format failure.",
        solver_text=None,
        oracle_vector=None,
        ast_hash=None,
        ast_node_count=None,
        parse_failure=True,
        failure_type="FORMAT_FATAL",
    )

    record = json.loads((tmp_path / ca.SOLVER_HISTORY_FILE).read_text(encoding="utf-8").splitlines()[0])
    assert record["cycle"] == 43
    assert record["cycle_type"] == "grind"
    assert record["solver_text"] is None
    assert record["ast_hash"] is None
    assert record["ast_node_count"] is None
    assert record["oracle_vector"] is None
    assert record["parse_failure"] is True
    assert record["failure_type"] == "FORMAT_FATAL"


def test_read_solver_text_or_none(monkeypatch, tmp_path):
    import compression_assay as ca
    import hypervisor_v44 as hv

    monkeypatch.chdir(tmp_path)
    assert ca._read_solver_text_or_none() is None

    hv.write_text(
        hv.SOLVER_FILE,
        "def transduce(arr: list[int]) -> list[int]:\n    return arr\n",
    )
    assert ca._read_solver_text_or_none() == (
        "def transduce(arr: list[int]) -> list[int]:\n    return arr"
    )
