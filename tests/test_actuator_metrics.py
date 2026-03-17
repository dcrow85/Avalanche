"""Unit tests for actuator_metrics.py (Experiment 04)."""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from actuator_metrics import (
    EPSILON,
    _dead_end_diff,
    ast_branching_depth,
    delta_c_topological,
    e_ratio,
    epistemic_flux,
    evaluate_solver_fractional,
)


# ---------------------------------------------------------------------------
# delta_c_topological
# ---------------------------------------------------------------------------

def test_delta_c_flat_math():
    """Arithmetic-only code → low/negative ΔC (reward > penalty)."""
    code = "def f(x):\n    return x * 2 + 3 - 1\n"
    result = delta_c_topological(code)
    assert result < 1.0, f"Flat math should yield low ΔC, got {result}"


def test_delta_c_nested_branches():
    """Deeply nested if/for → high ΔC."""
    code = (
        "def f(arr):\n"
        "    for i in range(len(arr)):\n"
        "        for j in range(len(arr)):\n"
        "            if arr[i] > arr[j]:\n"
        "                if arr[i] - arr[j] > 5:\n"
        "                    pass\n"
    )
    result = delta_c_topological(code)
    assert result > 10.0, f"Nested branches should yield high ΔC, got {result}"


def test_delta_c_empty_string():
    """Empty code → 0.0."""
    assert delta_c_topological("") == 0.0


def test_delta_c_syntax_error():
    """Syntax error → 0.0 graceful fallback."""
    assert delta_c_topological("def f(:\n  broken") == 0.0


# ---------------------------------------------------------------------------
# epistemic_flux / _dead_end_diff
# ---------------------------------------------------------------------------

def _empty_dead_ends():
    return {"basins": [], "families": [], "locals": []}


def test_flux_no_change():
    """Identical dead-ends → 0.0 diff."""
    de = _empty_dead_ends()
    assert _dead_end_diff(de, de) == 0.0


def test_flux_add_local():
    """Adding a local costs 1."""
    prev = _empty_dead_ends()
    curr = {"basins": [], "families": [], "locals": [{"failing_hypothesis": "x"}]}
    assert _dead_end_diff(prev, curr) == 1.0


def test_flux_new_family():
    """Adding a family costs 5."""
    prev = _empty_dead_ends()
    curr = {
        "basins": [],
        "families": [{"id": "F1", "status": "ACTIVE", "claim": "test"}],
        "locals": [],
    }
    assert _dead_end_diff(prev, curr) == 5.0


def test_flux_family_supersede():
    """Superseding an existing family costs 5."""
    prev = {
        "basins": [],
        "families": [{"id": "F1", "status": "ACTIVE", "claim": "old"}],
        "locals": [],
    }
    curr = {
        "basins": [],
        "families": [{"id": "F1", "status": "SUPERSEDED", "claim": "old"}],
        "locals": [],
    }
    assert _dead_end_diff(prev, curr) == 5.0


def test_flux_basin_add():
    """Adding a basin costs 15."""
    prev = _empty_dead_ends()
    curr = {
        "basins": [{"id": "B1", "status": "ACTIVE", "claim": "test"}],
        "families": [],
        "locals": [],
    }
    assert _dead_end_diff(prev, curr) == 15.0


def test_flux_basin_supersede():
    """Superseding a basin costs 50."""
    prev = {
        "basins": [{"id": "B1", "status": "ACTIVE", "claim": "old"}],
        "families": [],
        "locals": [],
    }
    curr = {
        "basins": [{"id": "B1", "status": "SUPERSEDED", "claim": "old"}],
        "families": [],
        "locals": [],
    }
    assert _dead_end_diff(prev, curr) == 50.0


def test_flux_zero_oracle():
    """oracle_score=0 → flux=0 regardless of diff."""
    prev = _empty_dead_ends()
    curr = {
        "basins": [{"id": "B1", "status": "ACTIVE", "claim": "test"}],
        "families": [{"id": "F1", "status": "ACTIVE", "claim": "test"}],
        "locals": [{"failing_hypothesis": "x"}],
    }
    assert epistemic_flux(prev, curr, oracle_score=0.0) == 0.0


def test_flux_grounded_by_oracle():
    """Flux scales linearly with oracle_score."""
    prev = _empty_dead_ends()
    curr = {
        "basins": [],
        "families": [{"id": "F1", "status": "ACTIVE", "claim": "test"}],
        "locals": [],
    }
    # Raw diff = 5.0 (one new family)
    assert epistemic_flux(prev, curr, oracle_score=0.5) == 2.5
    assert epistemic_flux(prev, curr, oracle_score=1.0) == 5.0


# ---------------------------------------------------------------------------
# e_ratio
# ---------------------------------------------------------------------------

def test_e_ratio_high_bloat_low_work():
    """High ΔC, low flux → high ratio."""
    result = e_ratio(100.0, 0.5)
    assert result > 100.0


def test_e_ratio_low_bloat_high_work():
    """Low ΔC, high flux → low ratio."""
    result = e_ratio(2.0, 50.0)
    assert result < 0.1


def test_e_ratio_zero_flux():
    """Zero flux → divides by epsilon, not zero."""
    result = e_ratio(10.0, 0.0)
    assert result == 10.0 / EPSILON


# ---------------------------------------------------------------------------
# evaluate_solver_fractional
# ---------------------------------------------------------------------------

def _simple_law(arr):
    """Test law: negate every element."""
    return [-x for x in arr]


def test_evaluate_fractional_all_pass():
    """Perfect solver → score 1.0."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, dir=tempfile.gettempdir()
    ) as f:
        f.write("def transduce(arr):\n    return [-x for x in arr]\n")
        f.flush()
        path = f.name
    try:
        score, passed, total, failure = evaluate_solver_fractional(
            [[1, 2, 3], [4, 5, 6]], _simple_law, path
        )
        assert score == 1.0
        assert passed == 2
        assert total == 2
        assert failure == ""
    finally:
        os.unlink(path)


def test_evaluate_fractional_partial_pass():
    """Solver that only works on short arrays → partial score."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, dir=tempfile.gettempdir()
    ) as f:
        # Only negate if length <= 3
        f.write(
            "def transduce(arr):\n"
            "    if len(arr) <= 3:\n"
            "        return [-x for x in arr]\n"
            "    return arr\n"
        )
        f.flush()
        path = f.name
    try:
        cases = [[1, 2, 3], [4, 5, 6, 7], [8, 9]]
        score, passed, total, failure = evaluate_solver_fractional(
            cases, _simple_law, path
        )
        # Cases [1,2,3] and [8,9] pass (len<=3), [4,5,6,7] fails
        assert passed == 2
        assert total == 3
        assert abs(score - 2 / 3) < 0.01
        assert "Expected" in failure
    finally:
        os.unlink(path)


def test_evaluate_fractional_no_solver():
    """Missing solver file → score 0."""
    score, passed, total, failure = evaluate_solver_fractional(
        [[1, 2]], _simple_law, "/nonexistent/solver.py"
    )
    assert score == 0.0
    assert passed == 0
    assert "not found" in failure


def test_evaluate_fractional_crash():
    """Crashing solver → still runs remaining tests."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, dir=tempfile.gettempdir()
    ) as f:
        f.write(
            "def transduce(arr):\n"
            "    if len(arr) == 2:\n"
            "        raise ValueError('boom')\n"
            "    return [-x for x in arr]\n"
        )
        f.flush()
        path = f.name
    try:
        cases = [[1, 2], [3, 4, 5], [6, 7]]
        score, passed, total, failure = evaluate_solver_fractional(
            cases, _simple_law, path
        )
        # [1,2] crashes, [3,4,5] passes, [6,7] crashes
        assert passed == 1
        assert total == 3
        assert "Crash" in failure or "boom" in failure
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# ast_branching_depth
# ---------------------------------------------------------------------------

def test_ast_branching_depth_flat():
    """Flat code with no branches → 0."""
    code = "def f(x):\n    return x * 2 + 3\n"
    assert ast_branching_depth(code) == 0


def test_ast_branching_depth_nested():
    """Nested if/for → reports max depth of a branching node."""
    code = (
        "def f(arr):\n"
        "    for i in range(len(arr)):\n"
        "        if arr[i] > 0:\n"
        "            for j in range(i):\n"
        "                if arr[j] < arr[i]:\n"
        "                    pass\n"
    )
    result = ast_branching_depth(code)
    assert result >= 4, f"Expected depth >= 4 for deeply nested code, got {result}"


def test_ast_branching_depth_empty():
    """Empty string → 0."""
    assert ast_branching_depth("") == 0


def test_ast_branching_depth_syntax_error():
    """Syntax error → 0 graceful fallback."""
    assert ast_branching_depth("def f(:\n  broken") == 0
