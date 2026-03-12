"""Focused tests for the raw V4.4.1 hypervisor path."""

from __future__ import annotations

import importlib
import os


def load_module():
    os.environ.pop("AVALANCHE_ACTIVE", None)
    return importlib.import_module("hypervisor_v44")


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


def test_generate_permutation_array_returns_distinct_values():
    hv = load_module()
    arr = hv.generate_permutation_array(hv.random.Random(11), min_len=8, max_len=8)
    assert len(arr) == 8
    assert sorted(arr) == [1, 2, 3, 4, 5, 6, 7, 8]
    assert len(set(arr)) == 8


def test_strip_leading_think_block_returns_json_payload():
    hv = load_module()
    payload = "<think>hidden chain</think>\n{\"ok\": true}"
    assert hv.strip_leading_think_block(payload) == "{\"ok\": true}"


def test_normalize_structured_output_text_strips_markdown_fences():
    hv = load_module()
    payload = "```json\n{\"ok\": true, \"value\": \"HAIKU_OK\"}\n```"
    assert hv.normalize_structured_output_text(payload) == "{\"ok\": true, \"value\": \"HAIKU_OK\"}"
