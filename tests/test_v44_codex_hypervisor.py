"""Focused tests for V4.4.1 Codex hypervisor constraints."""

from __future__ import annotations

import importlib
import os


def load_module():
    os.environ.pop("AVALANCHE_ACTIVE", None)
    return importlib.import_module("hypervisor_v44_codex")


def test_anti_cache_rejects_hardcoded_known_cases():
    hv = load_module()
    solver = """
KNOWN_CASES = {
    (1, 2, 3, 4): (1, -2, 3, -4),
}

def transduce(arr):
    return list(KNOWN_CASES.get(tuple(arr), arr))
"""
    error = hv.anti_cache_error(solver)
    assert error is not None
    assert "Epistemic Fraud Detected" in error


def test_anti_cache_allows_small_literal_initializers():
    hv = load_module()
    solver = """
def transduce(arr):
    out = arr.copy()
    seed = [0] * len(arr)
    trio = (1, 2, 3)
    return out
"""
    assert hv.anti_cache_error(solver) is None


def test_generate_permutation_array_returns_distinct_values():
    hv = load_module()
    arr = hv.generate_permutation_array(hv.random.Random(7), min_len=7, max_len=7)
    assert len(arr) == 7
    assert sorted(arr) == [1, 2, 3, 4, 5, 6, 7]
    assert len(set(arr)) == 7
