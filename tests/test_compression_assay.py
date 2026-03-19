#!/usr/bin/env python3
"""Unit tests for compression_assay.py — V4.7 dataclasses and logic."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compression_assay import (
    AltitudeState,
    CompressionPassState,
    GradientState,
    ALTITUDE_SURVEY_MIN_GRAVEYARD_ENTRIES,
    _compression_target_len,
    _cycle_usage_aliases,
    _effective_graveyard_entry_cap,
    _max_rendered_slot_len,
    _load_status_progress,
    _write_terminal_marker,
    extract_altitude_map,
    request_altitude_map,
    _render_opinions_from_slots,
    _check_alt_rule_duplication,
    _validate_compression_slots,
)


# ---------------------------------------------------------------------------
# GradientState tests
# ---------------------------------------------------------------------------

class TestGradientStateLinear:
    def test_initial_window(self):
        g = GradientState(initial_prompt_budget=1200, floor=400, decay="linear", total_cycles=100)
        assert g.current_prompt_budget == 1200

    def test_tick_shrinks(self):
        g = GradientState(initial_prompt_budget=1200, floor=400, decay="linear", total_cycles=100)
        g.tick()
        assert g.current_prompt_budget < 1200

    def test_reaches_floor(self):
        g = GradientState(initial_prompt_budget=1200, floor=400, decay="linear", total_cycles=100)
        for _ in range(200):
            g.tick()
        assert g.current_prompt_budget == 400

    def test_midpoint(self):
        g = GradientState(initial_prompt_budget=1200, floor=400, decay="linear", total_cycles=100)
        for _ in range(50):
            g.tick()
        # At 50% progress: 1200 - 800 * 0.5 = 800
        assert g.current_prompt_budget == 800

    def test_monotonically_decreasing(self):
        g = GradientState(initial_prompt_budget=1200, floor=400, decay="linear", total_cycles=100)
        windows = [g.current_prompt_budget]
        for _ in range(100):
            g.tick()
            windows.append(g.current_prompt_budget)
        for i in range(len(windows) - 1):
            assert windows[i] >= windows[i + 1]


class TestGradientStateLog:
    def test_reaches_floor(self):
        g = GradientState(initial_prompt_budget=1200, floor=400, decay="log", total_cycles=100)
        for _ in range(100):
            g.tick()
        assert g.current_prompt_budget == 400

    def test_drops_faster_initially(self):
        g_lin = GradientState(initial_prompt_budget=1200, floor=400, decay="linear", total_cycles=100)
        g_log = GradientState(initial_prompt_budget=1200, floor=400, decay="log", total_cycles=100)
        for _ in range(10):
            g_lin.tick()
            g_log.tick()
        # Log decay drops faster initially
        assert g_log.current_prompt_budget < g_lin.current_prompt_budget

    def test_monotonically_decreasing(self):
        g = GradientState(initial_prompt_budget=1200, floor=400, decay="log", total_cycles=100)
        windows = [g.current_prompt_budget]
        for _ in range(100):
            g.tick()
            windows.append(g.current_prompt_budget)
        for i in range(len(windows) - 1):
            assert windows[i] >= windows[i + 1]


class TestGradientStateStepped:
    def test_holds_then_drops(self):
        g = GradientState(initial_prompt_budget=1200, floor=400, decay="stepped", total_cycles=100)
        # First 24 cycles should be at initial
        for _ in range(24):
            g.tick()
        assert g.current_prompt_budget == 1200
        # Cycle 25 should drop
        g.tick()
        assert g.current_prompt_budget < 1200

    def test_reaches_floor(self):
        g = GradientState(initial_prompt_budget=1200, floor=400, decay="stepped", total_cycles=100)
        for _ in range(100):
            g.tick()
        assert g.current_prompt_budget == 400


class TestGradientBudgets:
    def test_prompt_budget_equals_current(self):
        g = GradientState(initial_prompt_budget=1200, floor=400, decay="linear", total_cycles=100)
        assert g.prompt_budget == 1200  # initial, before any tick
        assert g.output_budget == 1200  # fixed, never shrinks

    def test_prompt_budget_at_floor(self):
        g = GradientState(initial_prompt_budget=1200, floor=400, decay="linear", total_cycles=100)
        for _ in range(200):
            g.tick()
        assert g.prompt_budget == 400  # floor
        assert g.output_budget == 1200  # fixed, unchanged

    def test_output_budget_never_changes(self):
        g = GradientState(initial_prompt_budget=1200, floor=400, decay="linear", total_cycles=100)
        for _ in range(100):
            g.tick()
            assert g.output_budget == 1200


class TestGraveyardThinning:
    def test_max_entries_at_full_window(self):
        g = GradientState(initial_prompt_budget=1200, floor=400, decay="linear", total_cycles=100)
        # 1200 * 0.15 = 180 / 80 = 2 -> clamped to 3
        # Actually: 180 // 80 = 2, max(3, 2) = 3
        assert g.max_graveyard_entries >= 3

    def test_max_entries_decreases(self):
        g = GradientState(initial_prompt_budget=1200, floor=400, decay="linear", total_cycles=100)
        initial = g.max_graveyard_entries
        for _ in range(100):
            g.tick()
        final = g.max_graveyard_entries
        assert final <= initial

    def test_minimum_3_entries(self):
        g = GradientState(initial_prompt_budget=1200, floor=400, decay="linear", total_cycles=100)
        for _ in range(200):
            g.tick()
        assert g.max_graveyard_entries >= 3


# ---------------------------------------------------------------------------
# CompressionPassState tests
# ---------------------------------------------------------------------------

class TestCompressionPass:
    def test_no_trigger_initially(self):
        p = CompressionPassState(stagnation_window=3)
        assert not p.should_trigger()

    def test_no_trigger_insufficient_stall(self):
        p = CompressionPassState(stagnation_window=3)
        p.record(0.5, cycle=1)
        p.record(0.5, cycle=2)
        # Only 1 stall cycle (second record is not improvement), need 3
        assert not p.should_trigger()

    def test_triggers_after_stagnation_window(self):
        p = CompressionPassState(stagnation_window=3)
        p.record(0.5, cycle=1)   # best = 0.5, stall = 0
        p.record(0.5, cycle=2)   # no improvement, stall = 1
        p.record(0.5, cycle=3)   # stall = 2
        p.record(0.4, cycle=4)   # stall = 3 (worse score)
        assert p.should_trigger()

    def test_no_trigger_if_improving(self):
        p = CompressionPassState(stagnation_window=3)
        p.record(0.5, cycle=1)
        p.record(0.5, cycle=2)
        p.record(0.6, cycle=3)   # improvement resets stall
        assert not p.should_trigger()
        assert p.stall_count == 0

    def test_improvement_resets_stall(self):
        p = CompressionPassState(stagnation_window=3)
        p.record(0.5, cycle=1)
        p.record(0.4, cycle=2)   # stall = 1
        p.record(0.4, cycle=3)   # stall = 2
        p.record(0.6, cycle=4)   # improvement! stall = 0
        p.record(0.5, cycle=5)   # stall = 1
        assert not p.should_trigger()
        assert p.stall_count == 1
        assert p.best_oracle_fixed == 0.6
        assert p.best_oracle_cycle == 4

    def test_reset_after_trigger(self):
        p = CompressionPassState(stagnation_window=3)
        p.record(0.5, cycle=1)
        p.record(0.5, cycle=2)
        p.record(0.5, cycle=3)
        p.record(0.5, cycle=4)
        assert p.should_trigger()
        p.mark_triggered()
        assert not p.should_trigger()
        assert p.triggered_count == 1
        assert p.stall_count == 0
        # best_oracle_fixed is NOT reset — cumulative
        assert p.best_oracle_fixed == 0.5

    def test_max_passes_cap(self):
        p = CompressionPassState(stagnation_window=2, max_passes=2)
        # Trigger pass 1
        p.record(0.5, cycle=1)
        p.record(0.5, cycle=2)
        p.record(0.5, cycle=3)
        assert p.should_trigger()
        p.mark_triggered()
        # Trigger pass 2
        p.record(0.5, cycle=4)
        p.record(0.5, cycle=5)
        assert p.should_trigger()
        p.mark_triggered()
        # Pass 3 should NOT trigger — capped
        p.record(0.5, cycle=6)
        p.record(0.5, cycle=7)
        assert not p.should_trigger()
        assert p.triggered_count == 2

    def test_tracks_best_oracle(self):
        p = CompressionPassState(stagnation_window=5)
        p.record(0.12, cycle=1)
        p.record(0.24, cycle=5)
        p.record(0.18, cycle=10)
        assert p.best_oracle_fixed == 0.24
        assert p.best_oracle_cycle == 5

    def test_target_compression_stored(self):
        p = CompressionPassState(target_compression=0.75)
        assert p.target_compression == 0.75

    def test_first_score_always_becomes_best(self):
        p = CompressionPassState(stagnation_window=5)
        assert p.best_oracle_fixed is None
        assert p.best_oracle_cycle == 0
        p.record(0.0, cycle=1)
        assert p.best_oracle_fixed == 0.0
        assert p.best_oracle_cycle == 1
        assert p.stall_count == 0

    def test_first_zero_score_then_stall(self):
        p = CompressionPassState(stagnation_window=3)
        p.record(0.0, cycle=1)   # first score, becomes best
        p.record(0.0, cycle=2)   # equal, stall = 1
        p.record(0.0, cycle=3)   # stall = 2
        p.record(0.0, cycle=4)   # stall = 3
        assert p.should_trigger()
        assert p.best_oracle_cycle == 1  # not 0


# ---------------------------------------------------------------------------
# AltitudeState tests
# ---------------------------------------------------------------------------

class TestAltitude:
    def test_fires_at_frequency(self):
        a = AltitudeState(frequency=10)
        assert not a.should_fire(0)
        assert not a.should_fire(5)
        assert a.should_fire(10)
        assert a.should_fire(20)

    def test_does_not_fire_at_zero(self):
        a = AltitudeState(frequency=10)
        assert not a.should_fire(0)

    def test_rotates_altitudes(self):
        a = AltitudeState(frequency=5, prompt_style="rotating")
        assert a.next_altitude() == "low"
        assert a.next_altitude() == "medium"
        assert a.next_altitude() == "high"
        assert a.next_altitude() == "low"  # wraps

    def test_survey_mode_always_returns_survey(self):
        a = AltitudeState(frequency=5, prompt_style="survey")
        assert a.next_altitude() == "survey"
        assert a.next_altitude() == "survey"
        assert a.next_altitude() == "survey"

    def test_negative_space_mode_always_returns_negative_space(self):
        a = AltitudeState(frequency=5, prompt_style="negative-space")
        assert a.next_altitude() == "negative-space"
        assert a.next_altitude() == "negative-space"

    def test_default_prompt_style_is_survey(self):
        a = AltitudeState()
        assert a.prompt_style == "survey"
        assert a.next_altitude() == "survey"

    def test_custom_frequency(self):
        a = AltitudeState(frequency=3)
        assert a.should_fire(3)
        assert not a.should_fire(4)
        assert a.should_fire(6)


class TestAltitudeSurveyGraveyardCap:
    def test_survey_mode_raises_graveyard_cap(self):
        assert _effective_graveyard_entry_cap(3, "survey") == ALTITUDE_SURVEY_MIN_GRAVEYARD_ENTRIES

    def test_negative_space_mode_raises_graveyard_cap(self):
        assert _effective_graveyard_entry_cap(3, "negative-space") == ALTITUDE_SURVEY_MIN_GRAVEYARD_ENTRIES

    def test_non_survey_mode_keeps_original_cap(self):
        assert _effective_graveyard_entry_cap(3, "low") == 3
        assert _effective_graveyard_entry_cap(5, None) == 5


# ---------------------------------------------------------------------------
# extract_altitude_map tests
# ---------------------------------------------------------------------------

class TestExtractAltitudeMap:
    def test_extracts_section(self):
        payload = {"opinions_md": "Some text\n## Altitude Map\nLine 1\nLine 2\n## Other"}
        result = extract_altitude_map(payload)
        assert "Altitude Map" in result
        assert "Line 1" in result
        assert "Line 2" in result
        assert "Other" not in result

    def test_fallback_short_opinions(self):
        payload = {"opinions_md": "Short theory text"}
        result = extract_altitude_map(payload)
        assert result == "Short theory text"

    def test_empty_payload(self):
        result = extract_altitude_map({})
        assert result == ""

    def test_caps_length(self):
        long_text = "x" * 5000
        payload = {"opinions_md": f"## Altitude Map\n{long_text}"}
        result = extract_altitude_map(payload)
        assert len(result) <= 1200


def test_request_altitude_map_uses_direct_json_object_path(monkeypatch):
    import compression_assay as ca

    captured: dict[str, object] = {}

    def fake_format_cycle_prompt(*args, **kwargs):
        captured["prompt_budget_tokens"] = kwargs.get("prompt_budget_tokens")
        return [
            {"role": "system", "content": "unused"},
            {"role": "user", "content": "survey prompt"},
        ]

    def fake_invoke_openai(messages, model, api_base, **kwargs):
        captured["messages"] = messages
        captured["response_format_override"] = kwargs.get("response_format_override")
        return {"altitude_map": "Map body"}

    monkeypatch.setattr(ca.hv, "format_cycle_prompt", fake_format_cycle_prompt)
    monkeypatch.setattr(ca.hv, "invoke_openai", fake_invoke_openai)

    args = argparse.Namespace(
        max_cycles=20,
        model="anthropic/claude-haiku-4-5",
        api_base="https://api.haimaker.ai/v1",
        api_key_env="HAIMAKER_KEY",
    )
    gradient = GradientState(initial_prompt_budget=1200, floor=400, decay="linear", total_cycles=100)

    result = request_altitude_map(
        cycle=10,
        args=args,
        gradient=gradient,
        current_state={},
        altitude_mode="low",
        previous_map="",
    )

    assert result == {"map": "Map body", "opinions_md": ""}
    assert captured["prompt_budget_tokens"] == gradient.prompt_budget
    assert captured["response_format_override"] == "json_object"


def test_request_altitude_map_survey_mode_returns_opinions(monkeypatch):
    import compression_assay as ca

    captured: dict[str, object] = {}

    def fake_format_cycle_prompt(*args, **kwargs):
        return [
            {"role": "system", "content": "unused"},
            {"role": "user", "content": "survey prompt"},
        ]

    def fake_invoke_openai(messages, model, api_base, **kwargs):
        captured["system_content"] = messages[0]["content"]
        return {
            "altitude_map": "Comparison analysis here",
            "opinions_md": "Updated theory based on graveyard comparison",
        }

    monkeypatch.setattr(ca.hv, "format_cycle_prompt", fake_format_cycle_prompt)
    monkeypatch.setattr(ca.hv, "invoke_openai", fake_invoke_openai)

    args = argparse.Namespace(
        max_cycles=20,
        model="anthropic/claude-haiku-4-5",
        api_base="https://api.haimaker.ai/v1",
        api_key_env="HAIMAKER_KEY",
    )
    gradient = GradientState(initial_prompt_budget=1200, floor=400, decay="linear", total_cycles=100)

    result = request_altitude_map(
        cycle=10,
        args=args,
        gradient=gradient,
        current_state={},
        altitude_mode="survey",
        previous_map="",
    )

    assert result["map"] == "Comparison analysis here"
    assert result["opinions_md"] == "Updated theory based on graveyard comparison"
    assert "two keys" in captured["system_content"]
    assert "opinions_md" in captured["system_content"]


def test_request_altitude_map_survey_mode_empty_opinions(monkeypatch):
    import compression_assay as ca

    def fake_format_cycle_prompt(*args, **kwargs):
        return [
            {"role": "system", "content": "unused"},
            {"role": "user", "content": "survey prompt"},
        ]

    def fake_invoke_openai(messages, model, api_base, **kwargs):
        return {"altitude_map": "Analysis only"}

    monkeypatch.setattr(ca.hv, "format_cycle_prompt", fake_format_cycle_prompt)
    monkeypatch.setattr(ca.hv, "invoke_openai", fake_invoke_openai)

    args = argparse.Namespace(
        max_cycles=20,
        model="anthropic/claude-haiku-4-5",
        api_base="https://api.haimaker.ai/v1",
        api_key_env="HAIMAKER_KEY",
    )
    gradient = GradientState(initial_prompt_budget=1200, floor=400, decay="linear", total_cycles=100)

    result = request_altitude_map(
        cycle=10, args=args, gradient=gradient,
        current_state={}, altitude_mode="survey", previous_map="",
    )

    assert result["map"] == "Analysis only"
    assert result["opinions_md"] == ""


def test_request_altitude_map_negative_space_mode_returns_opinions(monkeypatch):
    import compression_assay as ca

    captured: dict[str, object] = {}

    def fake_format_cycle_prompt(*args, **kwargs):
        return [
            {"role": "system", "content": "unused"},
            {"role": "user", "content": "negative space prompt"},
        ]

    def fake_invoke_openai(messages, model, api_base, **kwargs):
        captured["system_content"] = messages[0]["content"]
        return {
            "altitude_map": "Untested structure lies between elements.",
            "opinions_md": "Investigate relational structure between elements.",
        }

    monkeypatch.setattr(ca.hv, "format_cycle_prompt", fake_format_cycle_prompt)
    monkeypatch.setattr(ca.hv, "invoke_openai", fake_invoke_openai)

    args = argparse.Namespace(
        max_cycles=20,
        model="anthropic/claude-haiku-4-5",
        api_base="https://api.haimaker.ai/v1",
        api_key_env="HAIMAKER_KEY",
    )
    gradient = GradientState(initial_prompt_budget=1200, floor=400, decay="linear", total_cycles=100)

    result = request_altitude_map(
        cycle=10,
        args=args,
        gradient=gradient,
        current_state={},
        altitude_mode="negative-space",
        previous_map="",
    )

    assert result["map"] == "Untested structure lies between elements."
    assert result["opinions_md"] == "Investigate relational structure between elements."
    assert "two keys" in captured["system_content"]
    assert "opinions_md" in captured["system_content"]


# ---------------------------------------------------------------------------
# Slot rendering tests
# ---------------------------------------------------------------------------

class TestRenderSlots:
    def test_full_slots(self):
        slots = {
            "core_rule": "Negate elements in even-length cycles",
            "alt_rule": "Position-value parity determines sign",
            "key_exclusion": "Neighbor comparison fails on [3,1,2]",
            "uncertainty": "Whether cycle length matters",
        }
        rendered = _render_opinions_from_slots(slots)
        assert "Core rule:" in rendered
        assert "Alternative:" in rendered
        assert "Key exclusion:" in rendered
        assert "Uncertainty:" in rendered
        assert rendered.count("\n") == 3  # 4 lines, 3 newlines

    def test_empty_alt_rule_omitted(self):
        slots = {
            "core_rule": "Some rule",
            "alt_rule": "",
            "key_exclusion": "Some exclusion",
            "uncertainty": "Some question",
        }
        rendered = _render_opinions_from_slots(slots)
        assert "Alternative:" not in rendered
        assert rendered.count("\n") == 2

    def test_all_empty(self):
        slots = {"core_rule": "", "alt_rule": "", "key_exclusion": "", "uncertainty": ""}
        rendered = _render_opinions_from_slots(slots)
        assert rendered == ""


# ---------------------------------------------------------------------------
# Alt-rule duplication tests
# ---------------------------------------------------------------------------

class TestAltRuleDuplication:
    def test_exact_match(self):
        assert _check_alt_rule_duplication("negate even cycles", "negate even cycles")

    def test_case_insensitive(self):
        assert _check_alt_rule_duplication("Negate Even Cycles", "negate even cycles")

    def test_substring(self):
        assert _check_alt_rule_duplication(
            "negate elements in even cycles",
            "negate elements in even cycles of the permutation"
        )

    def test_high_token_overlap(self):
        assert _check_alt_rule_duplication(
            "negate values in even-length cycles",
            "negate values in even-length orbits"  # 4/5 overlap
        )

    def test_genuinely_different(self):
        assert not _check_alt_rule_duplication(
            "negate elements in even-length cycles",
            "position-value parity determines sign"
        )

    def test_empty_alt(self):
        assert not _check_alt_rule_duplication("some rule", "")

    def test_both_empty(self):
        assert not _check_alt_rule_duplication("", "")


# ---------------------------------------------------------------------------
# Slot validation tests
# ---------------------------------------------------------------------------

class TestValidateSlots:
    def test_valid_slots(self):
        raw = {
            "core_rule": "Negate even-cycle elements",
            "alt_rule": "Position parity",
            "key_exclusion": "Neighbor diff fails",
            "uncertainty": "Cycle length role",
        }
        slots, reason = _validate_compression_slots(raw, target_len=500, theory_len_before=1000)
        assert slots is not None
        assert reason == ""

    def test_extra_keys_rejected(self):
        raw = {
            "core_rule": "Rule",
            "alt_rule": "",
            "key_exclusion": "Excl",
            "uncertainty": "?",
            "extra_field": "bad",
        }
        slots, reason = _validate_compression_slots(raw, target_len=500, theory_len_before=1000)
        assert slots is None
        assert "extra_keys" in reason

    def test_core_rule_overflow(self):
        raw = {
            "core_rule": "x" * 130,  # > 120 chars
            "alt_rule": "",
            "key_exclusion": "",
            "uncertainty": "",
        }
        slots, reason = _validate_compression_slots(raw, target_len=500, theory_len_before=1000)
        assert slots is None
        assert "core_rule_overflow" in reason

    def test_alt_rule_overflow(self):
        raw = {
            "core_rule": "Rule",
            "alt_rule": "x" * 90,  # > 80 chars
            "key_exclusion": "",
            "uncertainty": "",
        }
        slots, reason = _validate_compression_slots(raw, target_len=500, theory_len_before=1000)
        assert slots is None
        assert "alt_rule_overflow" in reason

    def test_key_exclusion_overflow(self):
        raw = {
            "core_rule": "Rule",
            "alt_rule": "",
            "key_exclusion": "x" * 100,  # > 95 chars
            "uncertainty": "",
        }
        slots, reason = _validate_compression_slots(raw, target_len=500, theory_len_before=1000)
        assert slots is None
        assert "key_exclusion_overflow" in reason

    def test_uncertainty_overflow(self):
        raw = {
            "core_rule": "Rule",
            "alt_rule": "",
            "key_exclusion": "",
            "uncertainty": "x" * 80,  # > 75 chars
        }
        slots, reason = _validate_compression_slots(raw, target_len=500, theory_len_before=1000)
        assert slots is None
        assert "uncertainty_overflow" in reason

    def test_rendered_overflow(self):
        raw = {
            "core_rule": "x" * 120,
            "alt_rule": "y" * 80,
            "key_exclusion": "z" * 95,
            "uncertainty": "w" * 75,
        }
        # Total rendered will be far above the tiny target after labels are added.
        slots, reason = _validate_compression_slots(raw, target_len=50, theory_len_before=1000)
        assert slots is None
        assert "rendered_overflow" in reason

    def test_empty_core_rule_rejected(self):
        raw = {
            "core_rule": "",
            "alt_rule": "Something",
            "key_exclusion": "Exclusion",
            "uncertainty": "Question",
        }
        slots, reason = _validate_compression_slots(raw, target_len=500, theory_len_before=1000)
        assert slots is None
        assert "core_rule_empty" in reason

    def test_duplicate_alt_rule_rejected_substring(self):
        raw = {
            "core_rule": "negate even-length cycles",
            "alt_rule": "negate even-length cycles always",
            "key_exclusion": "Exclusion",
            "uncertainty": "Question",
        }
        slots, reason = _validate_compression_slots(raw, target_len=500, theory_len_before=1000)
        assert slots is None
        assert "alt_rule_duplicates_core" in reason

    def test_duplicate_alt_rule_rejected_high_overlap(self):
        raw = {
            "core_rule": "negate elements in even-length disjoint cycles",
            "alt_rule": "negate elements in even-length disjoint orbits",
            "key_exclusion": "Exclusion",
            "uncertainty": "Question",
        }
        # 5/6 token overlap = 83% > 80% threshold
        slots, reason = _validate_compression_slots(raw, target_len=500, theory_len_before=1000)
        assert slots is None
        assert "alt_rule_duplicates_core" in reason

    def test_empty_alt_rule_accepted(self):
        raw = {
            "core_rule": "Some valid rule",
            "alt_rule": "",
            "key_exclusion": "An exclusion",
            "uncertainty": "A question",
        }
        slots, reason = _validate_compression_slots(raw, target_len=500, theory_len_before=1000)
        assert slots is not None
        assert reason == ""

    def test_missing_keys_rejected(self):
        raw = {"core_rule": "A rule"}
        slots, reason = _validate_compression_slots(raw, target_len=500, theory_len_before=1000)
        assert slots is None
        assert "missing_keys" in reason

    def test_non_string_value_rejected(self):
        raw = {
            "core_rule": "A rule",
            "alt_rule": 42,
            "key_exclusion": "Exclusion",
            "uncertainty": "Question",
        }
        slots, reason = _validate_compression_slots(raw, target_len=500, theory_len_before=1000)
        assert slots is None
        assert "alt_rule_not_string" in reason

    def test_list_value_rejected(self):
        raw = {
            "core_rule": "A rule",
            "alt_rule": "",
            "key_exclusion": ["a", "b"],
            "uncertainty": "Question",
        }
        slots, reason = _validate_compression_slots(raw, target_len=500, theory_len_before=1000)
        assert slots is None
        assert "key_exclusion_not_string" in reason

    def test_not_shorter_than_input_rejected(self):
        raw = {
            "core_rule": "a" * 100,
            "alt_rule": "b" * 50,
            "key_exclusion": "c" * 40,
            "uncertainty": "d" * 20,
        }
        slots, reason = _validate_compression_slots(raw, target_len=500, theory_len_before=120)
        assert slots is None
        assert "not_shorter_than_input" in reason


class TestCompressionBudgetArithmetic:
    def test_max_rendered_slot_len_includes_labels(self):
        assert _max_rendered_slot_len() > (120 + 80 + 95 + 75)

    def test_compression_target_len_clamps_up_to_min_viable_floor(self):
        target = _compression_target_len(theory_len_before=200, target_compression=0.5)
        assert target == 220

    def test_compression_target_len_keeps_larger_ratio_target(self):
        target = _compression_target_len(theory_len_before=1000, target_compression=0.75)
        assert target == 750

    def test_cycle_usage_aliases_mirror_hypervisor_keys(self, monkeypatch):
        import compression_assay as assay

        monkeypatch.setattr(
            assay.hv,
            "_cycle_usage",
            {
                "api_call_count_cycle": 2,
                "api_prompt_tokens_cycle": 101,
                "api_completion_tokens_cycle": 37,
                "api_total_tokens_cycle": 138,
                "api_reasoning_tokens_cycle": 12,
            },
        )
        assert _cycle_usage_aliases() == {
            "call_count": 2,
            "prompt_tokens": 101,
            "completion_tokens": 37,
            "total_tokens": 138,
            "reasoning_tokens": 12,
        }


class TestTerminalMarkers:
    def test_load_status_progress_defaults_when_missing(self, monkeypatch, tmp_path):
        import compression_assay as assay

        monkeypatch.setattr(assay.hv, "STATUS_FILE", str(tmp_path / "missing-status.json"))
        cycle, max_cycles = _load_status_progress(default_max_cycles=200)
        assert cycle == 0
        assert max_cycles == 200

    def test_write_terminal_marker_uses_existing_status_progress(self, monkeypatch, tmp_path):
        import compression_assay as assay

        status_path = tmp_path / "status.json"
        telemetry_path = tmp_path / "telemetry.jsonl"
        status_path.write_text(json.dumps({"cycle": 17, "max_cycles": 200}), encoding="utf-8")

        recorded: dict[str, object] = {}

        def fake_write_status(cycle, max_cycles, phase, last_result=None, last_error=None, metrics=None):
            recorded.update(
                {
                    "cycle": cycle,
                    "max_cycles": max_cycles,
                    "phase": phase,
                    "last_result": last_result,
                    "last_error": last_error,
                }
            )

        monkeypatch.setattr(assay.hv, "STATUS_FILE", str(status_path))
        monkeypatch.setattr(assay, "TELEMETRY_FILE", str(telemetry_path))
        monkeypatch.setattr(assay.hv, "write_status", fake_write_status)

        _write_terminal_marker("CRASH", "FAIL", "boom", default_max_cycles=200)

        assert recorded == {
            "cycle": 17,
            "max_cycles": 200,
            "phase": "CRASH",
            "last_result": "FAIL",
            "last_error": "boom",
        }

        rows = telemetry_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(rows) == 1
        payload = json.loads(rows[0])
        assert payload["cycle"] == 17
        assert payload["event"] == "terminal_marker"
        assert payload["phase"] == "CRASH"
