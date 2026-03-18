#!/usr/bin/env python3
"""Unit tests for compression_assay.py — V4.7 dataclasses and logic."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compression_assay import (
    AltitudeState,
    CompressionPassState,
    GradientState,
    extract_altitude_map,
    request_altitude_map,
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
        a = AltitudeState(frequency=5)
        assert a.next_altitude() == "low"
        assert a.next_altitude() == "medium"
        assert a.next_altitude() == "high"
        assert a.next_altitude() == "low"  # wraps

    def test_custom_frequency(self):
        a = AltitudeState(frequency=3)
        assert a.should_fire(3)
        assert not a.should_fire(4)
        assert a.should_fire(6)


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

    assert result == "Map body"
    assert captured["prompt_budget_tokens"] == gradient.prompt_budget
    assert captured["response_format_override"] == "json_object"
