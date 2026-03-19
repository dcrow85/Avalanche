"""Focused tests for the raw V4.4.1 hypervisor path."""

from __future__ import annotations

import importlib
import json
import os
import urllib.request


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


def test_format_cycle_prompt_applies_prompt_budget(monkeypatch, tmp_path):
    hv = load_module()
    monkeypatch.chdir(tmp_path)
    (tmp_path / hv.GOAL_FILE).write_text("Find the hidden law.", encoding="utf-8")
    big_data = [
        {"input": list(range(1, 13)), "expected": list(range(12, 0, -1))}
        for _ in range(4)
    ]
    (tmp_path / hv.DATA_FILE).write_text(json.dumps(big_data, indent=2), encoding="utf-8")
    (tmp_path / hv.OPINIONS_FILE).write_text(("very long theory " * 200).strip(), encoding="utf-8")
    dead_ends = {
        "basins": [
            {"id": "B1", "status": "ACTIVE", "claim": "main basin", "cited_families": ["F1", "F2"]},
        ],
        "families": [
            {"id": "F1", "status": "ACTIVE", "claim": "family one", "falsifying_arrays": [[1, 2], [3, 4]]},
            {"id": "F2", "status": "ACTIVE", "claim": "family two", "falsifying_arrays": [[5, 6], [7, 8]]},
            {"id": "F3", "status": "SUPERSEDED", "claim": "old family", "falsifying_arrays": [[9, 10], [11, 12]]},
        ],
        "locals": [
            {"failing_hypothesis": f"local {i}", "falsifying_array": [i, i + 1, i + 2]}
            for i in range(6)
        ],
    }
    (tmp_path / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(dead_ends, indent=2), encoding="utf-8")

    full_prompt = hv.format_cycle_prompt(1, 20, "grind", hv.blank_state())[-1]["content"]
    trimmed_prompt = hv.format_cycle_prompt(
        1,
        20,
        "grind",
        hv.blank_state(),
        max_graveyard_entries=3,
        prompt_budget_tokens=900,
    )[-1]["content"]

    assert len(trimmed_prompt) < len(full_prompt)
    assert "old family" not in trimmed_prompt
    assert "local 0" not in trimmed_prompt
    assert "...[truncated for context budget]..." in trimmed_prompt


def test_format_cycle_prompt_negative_space_altitude_instruction(monkeypatch, tmp_path):
    hv = load_module()
    monkeypatch.chdir(tmp_path)
    (tmp_path / hv.GOAL_FILE).write_text("Find the hidden law.", encoding="utf-8")
    (tmp_path / hv.DATA_FILE).write_text("[]", encoding="utf-8")
    (tmp_path / hv.OPINIONS_FILE).write_text("Current theory.", encoding="utf-8")
    (tmp_path / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(hv.blank_dead_ends(), indent=2), encoding="utf-8")

    prompt = hv.format_cycle_prompt(
        10,
        200,
        "grind",
        hv.blank_state(),
        altitude_mode="negative-space",
    )[-1]["content"]

    assert "ALTITUDE SURVEY (NEGATIVE SPACE)" in prompt
    assert "Do not describe what failed." in prompt
    assert "what remains untested" in prompt


def test_invoke_openai_uses_max_completion_tokens_for_openai_gpt5(monkeypatch):
    hv = load_module()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            payload = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "opinions_md": "ok",
                                    "solver_py": "def transduce(arr):\n    return arr\n",
                                    "dead_ends": {"basins": [], "families": [], "locals": []},
                                }
                            )
                        }
                    }
                ],
                "usage": {},
            }
            return json.dumps(payload).encode("utf-8")

    def fake_urlopen(request, timeout=300):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    hv.invoke_openai(
        [{"role": "user", "content": "ping"}],
        "gpt-5.4-mini",
        "https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        max_tokens=123,
    )

    body = captured["body"]
    assert body["max_completion_tokens"] == 123
    assert "max_tokens" not in body


def test_invoke_openai_uses_max_tokens_for_non_openai_or_non_gpt5(monkeypatch):
    hv = load_module()
    monkeypatch.setenv("HAIMAKER_KEY", "test-key")
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            payload = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "opinions_md": "ok",
                                    "solver_py": "def transduce(arr):\n    return arr\n",
                                    "dead_ends": {"basins": [], "families": [], "locals": []},
                                }
                            )
                        }
                    }
                ],
                "usage": {},
            }
            return json.dumps(payload).encode("utf-8")

    def fake_urlopen(request, timeout=300):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    hv.invoke_openai(
        [{"role": "user", "content": "ping"}],
        "anthropic/claude-haiku-4-5",
        "https://api.haimaker.ai/v1",
        api_key_env="HAIMAKER_KEY",
        max_tokens=456,
    )

    body = captured["body"]
    assert body["max_tokens"] == 456
    assert "max_completion_tokens" not in body
