"""Metrics for the Three-Branch Actuator Assay (Experiment 04).

ΔC (Topological Action): AST branching penalized by depth², algebraic ops rewarded.
Flux (Epistemic Work): Structural diff of dead-end JSON, grounded by oracle score.
E_ratio: ΔC / Flux. High = complexity without useful work.
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import signal
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# AST depth-weighted analysis
# ---------------------------------------------------------------------------

BRANCHING_NODES = (
    ast.If, ast.For, ast.While, ast.IfExp,
    ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp, ast.BoolOp,
)
ALGEBRAIC_NODES = (ast.BinOp, ast.UnaryOp, ast.Subscript, ast.Compare)


def _walk_with_depth(node: ast.AST, depth: int = 0):
    """Yield (node, depth) for every AST node via recursive traversal."""
    yield node, depth
    for child in ast.iter_child_nodes(node):
        yield from _walk_with_depth(child, depth + 1)


def delta_c_topological(solver_code: str) -> float:
    """Topological Action: branching penalty (depth²) minus algebraic reward.

    High value = bloated, deeply nested logic (epicycles).
    Low/negative value = flat, dense math.
    """
    try:
        tree = ast.parse(solver_code or "")
    except SyntaxError:
        return 0.0

    penalty = 0.0
    reward = 0.0
    for node, depth in _walk_with_depth(tree):
        if isinstance(node, BRANCHING_NODES):
            penalty += depth ** 2
        if isinstance(node, ALGEBRAIC_NODES):
            reward += 1.0
    return penalty - reward


# ---------------------------------------------------------------------------
# Epistemic Flux — structural diff of dead-end hierarchy
# ---------------------------------------------------------------------------

FLUX_COSTS: dict[str, float] = {
    "local_add": 1,
    "local_remove": 1,
    "family_add": 5,
    "family_remove": 5,
    "family_supersede": 5,
    "basin_add": 15,
    "basin_remove": 15,
    "basin_supersede": 50,
}


def _items_by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("id", "")): item for item in items if item.get("id")}


def _dead_end_diff(
    previous: dict[str, list[dict[str, Any]]],
    current: dict[str, list[dict[str, Any]]],
) -> float:
    """Compute structural diff cost between two dead-end states."""
    cost = 0.0

    # Locals: diff by count (no stable IDs)
    prev_local_count = len(previous.get("locals", []))
    curr_local_count = len(current.get("locals", []))
    added = max(0, curr_local_count - prev_local_count)
    removed = max(0, prev_local_count - curr_local_count)
    cost += added * FLUX_COSTS["local_add"] + removed * FLUX_COSTS["local_remove"]

    # Families: diff by ID
    prev_fam = _items_by_id(previous.get("families", []))
    curr_fam = _items_by_id(current.get("families", []))
    cost += len(set(curr_fam) - set(prev_fam)) * FLUX_COSTS["family_add"]
    cost += len(set(prev_fam) - set(curr_fam)) * FLUX_COSTS["family_remove"]
    for fid in set(prev_fam) & set(curr_fam):
        if (prev_fam[fid].get("status", "ACTIVE") == "ACTIVE"
                and curr_fam[fid].get("status", "ACTIVE") == "SUPERSEDED"):
            cost += FLUX_COSTS["family_supersede"]

    # Basins: diff by ID
    prev_bas = _items_by_id(previous.get("basins", []))
    curr_bas = _items_by_id(current.get("basins", []))
    cost += len(set(curr_bas) - set(prev_bas)) * FLUX_COSTS["basin_add"]
    cost += len(set(prev_bas) - set(curr_bas)) * FLUX_COSTS["basin_remove"]
    for bid in set(prev_bas) & set(curr_bas):
        if (prev_bas[bid].get("status", "ACTIVE") == "ACTIVE"
                and curr_bas[bid].get("status", "ACTIVE") == "SUPERSEDED"):
            cost += FLUX_COSTS["basin_supersede"]

    return cost


def epistemic_flux(
    previous_dead_ends: dict[str, list[dict[str, Any]]],
    current_dead_ends: dict[str, list[dict[str, Any]]],
    oracle_score: float,
) -> float:
    """Epistemic Work = structural_diff_cost × oracle_grounding_coefficient.

    oracle_score is fractional (passed_tests / total_tests).
    Zero oracle score → zero flux (ungrounded speculation).
    """
    return _dead_end_diff(previous_dead_ends, current_dead_ends) * oracle_score


# ---------------------------------------------------------------------------
# E_ratio
# ---------------------------------------------------------------------------

EPSILON = 1e-6


def e_ratio(delta_c: float, flux_value: float) -> float:
    """E_ratio = ΔC / max(Flux, ε). High = complexity without useful work."""
    return delta_c / max(flux_value, EPSILON)


# ---------------------------------------------------------------------------
# Fractional oracle evaluation
# ---------------------------------------------------------------------------

SOLVER_TIMEOUT_SECONDS = 5.0


class _SolverTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise _SolverTimeout()


def evaluate_solver_fractional(
    test_cases: list[list[int]],
    hidden_law_fn,
    solver_path: str,
) -> tuple[float, int, int, str]:
    """Run all test cases (no short-circuit) and return fractional score.

    Returns:
        (score, passed_count, total_count, first_failure_report)
    """
    # Load solver module
    module_name = f"_assay_solver_{os.getpid()}_{datetime.now(timezone.utc).timestamp()}"
    if not os.path.exists(solver_path):
        return 0.0, 0, len(test_cases), "solver.py not found"

    spec = importlib.util.spec_from_file_location(module_name, solver_path)
    if spec is None or spec.loader is None:
        return 0.0, 0, len(test_cases), "Unable to load solver module"

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        return 0.0, 0, len(test_cases), f"Import crash: {exc}"

    transduce = getattr(module, "transduce", None)
    if not callable(transduce):
        return 0.0, 0, len(test_cases), "No transduce function"

    passed = 0
    first_failure = ""
    use_alarm = os.name != "nt"

    for arr in test_cases:
        expected = hidden_law_fn(arr)
        try:
            if use_alarm:
                prev = signal.signal(signal.SIGALRM, _alarm_handler)
                signal.setitimer(signal.ITIMER_REAL, SOLVER_TIMEOUT_SECONDS)
                try:
                    result = transduce(arr.copy())
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0.0)
                    signal.signal(signal.SIGALRM, prev)
            else:
                result = transduce(arr.copy())
        except _SolverTimeout:
            if not first_failure:
                first_failure = f"Timeout on {arr}"
            continue
        except Exception as exc:
            if not first_failure:
                first_failure = f"Crash on {arr}: {exc}"
            continue

        if isinstance(result, list) and result == expected:
            passed += 1
        elif not first_failure:
            first_failure = f"Input: {arr}, Expected: {expected}, Got: {result}"

    total = len(test_cases)
    score = passed / total if total > 0 else 0.0
    return score, passed, total, first_failure
