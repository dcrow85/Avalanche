"""Unit tests for V4.7.1 Sharp Calorimeter components."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compression_assay import _hamming_distance, _log_opinions_history
from v44_epistemics import detect_work_event


# ---------------------------------------------------------------------------
# Hamming distance
# ---------------------------------------------------------------------------

class TestHammingDistance:
    def test_identical_vectors(self):
        assert _hamming_distance([True, True, False], [True, True, False]) == 0

    def test_all_different(self):
        assert _hamming_distance([True, False, True], [False, True, False]) == 3

    def test_single_flip(self):
        assert _hamming_distance(
            [True, True, True, True, False],
            [True, True, False, True, False],
        ) == 1

    def test_empty_vectors(self):
        assert _hamming_distance([], []) == 0

    def test_mismatched_lengths_raises(self):
        import pytest
        with pytest.raises(ValueError):
            _hamming_distance([True], [True, False])


# ---------------------------------------------------------------------------
# Work event detection
# ---------------------------------------------------------------------------

def _empty():
    return {"basins": [], "families": [], "locals": []}


class TestDetectWorkEvent:
    def test_no_change(self):
        de = _empty()
        assert not detect_work_event(de, de)

    def test_new_family(self):
        prev = _empty()
        curr = {"basins": [], "families": [{"id": "F1", "status": "ACTIVE", "claim": "test"}], "locals": []}
        assert detect_work_event(prev, curr)

    def test_new_basin(self):
        prev = _empty()
        curr = {"basins": [{"id": "B1", "status": "ACTIVE", "claim": "test"}], "families": [], "locals": []}
        assert detect_work_event(prev, curr)

    def test_family_superseded(self):
        prev = {"basins": [], "families": [{"id": "F1", "status": "ACTIVE", "claim": "old"}], "locals": []}
        curr = {"basins": [], "families": [{"id": "F1", "status": "SUPERSEDED", "claim": "old"}], "locals": []}
        assert detect_work_event(prev, curr)

    def test_basin_superseded(self):
        prev = {"basins": [{"id": "B1", "status": "ACTIVE", "claim": "old"}], "families": [], "locals": []}
        curr = {"basins": [{"id": "B1", "status": "SUPERSEDED", "claim": "old"}], "families": [], "locals": []}
        assert detect_work_event(prev, curr)

    def test_local_only_change_not_work_event(self):
        prev = _empty()
        curr = {"basins": [], "families": [], "locals": [{"failing_hypothesis": "x"}]}
        assert not detect_work_event(prev, curr)

    def test_family_claim_change_without_id_change_not_event(self):
        prev = {"basins": [], "families": [{"id": "F1", "status": "ACTIVE", "claim": "old"}], "locals": []}
        curr = {"basins": [], "families": [{"id": "F1", "status": "ACTIVE", "claim": "new"}], "locals": []}
        assert not detect_work_event(prev, curr)


# ---------------------------------------------------------------------------
# AST structure metrics
# ---------------------------------------------------------------------------

class TestASTStructureMetrics:
    def test_node_count_simple(self):
        from hypervisor_v44 import solver_ast_node_count
        code = "def f(x):\n    return x + 1\n"
        count = solver_ast_node_count(code)
        assert count > 0

    def test_node_count_empty(self):
        from hypervisor_v44 import solver_ast_node_count
        assert solver_ast_node_count("") == 1  # Module node

    def test_node_count_syntax_error(self):
        from hypervisor_v44 import solver_ast_node_count
        assert solver_ast_node_count("def f(:\n broken") == 0

    def test_structure_hash_stable(self):
        from hypervisor_v44 import solver_ast_structure_hash
        code = "def f(x):\n    return x + 1\n"
        h1 = solver_ast_structure_hash(code)
        h2 = solver_ast_structure_hash(code)
        assert h1 == h2
        assert len(h1) == 8

    def test_structure_hash_invariant_to_var_names(self):
        from hypervisor_v44 import solver_ast_structure_hash
        code_a = "def f(x):\n    return x + 1\n"
        code_b = "def g(y):\n    return y + 1\n"
        # Same structure, different names — should produce same hash
        assert solver_ast_structure_hash(code_a) == solver_ast_structure_hash(code_b)

    def test_structure_hash_different_for_different_structure(self):
        from hypervisor_v44 import solver_ast_structure_hash
        code_a = "def f(x):\n    return x + 1\n"
        code_b = "def f(x):\n    if x > 0:\n        return x\n    return -x\n"
        assert solver_ast_structure_hash(code_a) != solver_ast_structure_hash(code_b)

    def test_structure_hash_syntax_error(self):
        from hypervisor_v44 import solver_ast_structure_hash
        assert solver_ast_structure_hash("def f(:\n broken") == ""

    def test_structure_hash_empty(self):
        from hypervisor_v44 import solver_ast_structure_hash
        h = solver_ast_structure_hash("")
        assert isinstance(h, str)


# ---------------------------------------------------------------------------
# PE post-processing
# ---------------------------------------------------------------------------

class TestPEComputation:
    def test_jaccard_identical(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        from compute_pe import jaccard_distance
        assert jaccard_distance("hello world", "hello world") == 0.0

    def test_jaccard_disjoint(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        from compute_pe import jaccard_distance
        assert jaccard_distance("hello world", "foo bar") == 1.0

    def test_jaccard_partial_overlap(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        from compute_pe import jaccard_distance
        d = jaccard_distance("hello world foo", "hello world bar")
        assert 0.0 < d < 1.0

    def test_ast_structure_distance_no_change(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        from compute_pe import ast_structure_distance
        assert ast_structure_distance(False, 0, 50) == 0.0

    def test_ast_structure_distance_hash_changed(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        from compute_pe import ast_structure_distance
        d = ast_structure_distance(True, 5, 50)
        assert d > 0.0
