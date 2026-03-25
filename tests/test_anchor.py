"""Tests for V4.7.2 Anchor sidecar support."""
from __future__ import annotations

import importlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _load_hv():
    os.environ.pop("AVALANCHE_ACTIVE", None)
    return importlib.import_module("hypervisor_v44")


SAMPLE_DEAD_ENDS = {
    "basins": [
        {
            "id": "B6",
            "status": "ACTIVE",
            "claim": "inversion count determines negation",
            "cited_families": ["F12", "F13"],
        },
    ],
    "families": [
        {
            "id": "F12",
            "status": "ACTIVE",
            "claim": "negate if element precedes a smaller value",
            "falsifying_arrays": [[3, 1, 2], [2, 1, 4, 3]],
        },
        {
            "id": "F13",
            "status": "SUPERSEDED",
            "claim": "negate if inversion count is odd",
            "falsifying_arrays": [[2, 1, 3], [4, 1, 3, 2]],
        },
    ],
    "locals": [],
}


class TestAnchorPrompt:
    def test_anchor_prompt_names_dissociation_and_landing_goal(self, monkeypatch, tmp_path):
        hv = _load_hv()
        monkeypatch.chdir(tmp_path)
        (tmp_path / hv.GOAL_FILE).write_text("Find the hidden law.", encoding="utf-8")
        (tmp_path / hv.DATA_FILE).write_text("[]", encoding="utf-8")
        (tmp_path / hv.OPINIONS_FILE).write_text(
            "Current workspace theory: rank in sorted order determines negation.",
            encoding="utf-8",
        )
        (tmp_path / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(SAMPLE_DEAD_ENDS, indent=2), encoding="utf-8")

        prompt = hv.format_cycle_prompt(
            1, 20, "grind", hv.blank_state(),
            altitude_mode="anchor",
        )[-1]["content"]

        assert "ANCHOR ALTITUDE" in prompt
        assert "workspace and graveyard have drifted apart" in prompt
        assert "land where you already are" in prompt.lower()
        assert "discriminating oracle test" in prompt.lower()
        assert "do not retreat to parity, identity, value-threshold" in prompt.lower()
        assert "Current workspace theory" in prompt
        assert "inversion count determines negation" in prompt

    def test_anchor_v2_prompt_forbids_schema_expansion_and_branching(self, monkeypatch, tmp_path):
        hv = _load_hv()
        monkeypatch.chdir(tmp_path)
        (tmp_path / hv.GOAL_FILE).write_text("Find the hidden law.", encoding="utf-8")
        (tmp_path / hv.DATA_FILE).write_text("[]", encoding="utf-8")
        (tmp_path / hv.OPINIONS_FILE).write_text(
            "Current workspace theory: rank in sorted order determines negation.",
            encoding="utf-8",
        )
        (tmp_path / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(SAMPLE_DEAD_ENDS, indent=2), encoding="utf-8")

        prompt = hv.format_cycle_prompt(
            1, 20, "grind", hv.blank_state(),
            altitude_mode="anchor-v2",
        )[-1]["content"]

        assert "ANCHOR WINDOW (V2)" in prompt
        assert "not for exploration" in prompt.lower()
        assert "do not add any new basin ids or family ids" in prompt.lower()
        assert "do not branch" in prompt.lower()
        assert "if the solver fails, that failure is the evidence" in prompt.lower()

    def test_anchor_v3_prompt_requires_supersession_with_replacement(self, monkeypatch, tmp_path):
        hv = _load_hv()
        monkeypatch.chdir(tmp_path)
        (tmp_path / hv.GOAL_FILE).write_text("Find the hidden law.", encoding="utf-8")
        (tmp_path / hv.DATA_FILE).write_text("[]", encoding="utf-8")
        (tmp_path / hv.OPINIONS_FILE).write_text(
            "Current workspace theory: rank in sorted order determines negation.",
            encoding="utf-8",
        )
        (tmp_path / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(SAMPLE_DEAD_ENDS, indent=2), encoding="utf-8")

        prompt = hv.format_cycle_prompt(
            1, 30, "grind", hv.blank_state(),
            altitude_mode="anchor-v3",
        )[-1]["content"]

        assert "ANCHOR WINDOW (V3)" in prompt
        assert "two-phase landing operation" in prompt.lower()
        assert "do not supersede b2, f5, or f7 until you are ready to record their replacement in the same operation" in prompt.lower()
        assert "add at most one new basin id" in prompt.lower()
        assert "replacement basin label" in prompt.lower()

    def test_anchor_v4_prompt_declares_locked_basin_and_replacement_type(self, monkeypatch, tmp_path):
        hv = _load_hv()
        monkeypatch.chdir(tmp_path)
        (tmp_path / hv.GOAL_FILE).write_text("Find the hidden law.", encoding="utf-8")
        (tmp_path / hv.DATA_FILE).write_text("[]", encoding="utf-8")
        (tmp_path / hv.OPINIONS_FILE).write_text(
            "Current workspace theory: rank in sorted order determines negation.",
            encoding="utf-8",
        )
        (tmp_path / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(SAMPLE_DEAD_ENDS, indent=2), encoding="utf-8")
        current_state = hv.blank_state()
        current_state["active"] = json.loads(json.dumps(SAMPLE_DEAD_ENDS))
        current_state["anchor_lock"] = {
            "active": True,
            "locked_basin_id": "B6",
            "locked_basin_hash": "abc123",
            "replacement_theory_type": "rank-based negation",
            "lock_activated_cycle": 10,
            "lock_cleared_cycle": None,
        }

        prompt = hv.format_cycle_prompt(
            10, 30, "grind", current_state,
            altitude_mode="anchor-v4",
        )[-1]["content"]

        assert "ANCHOR WINDOW — LOCKED (V4)" in prompt
        assert "Contrast basin: B6" in prompt
        assert "content locked by validator" in prompt
        assert "Replacement theory type required: rank-based negation" in prompt
        assert "do not modify the locked basin content" in prompt.lower()

    def test_anchor_v45_prompt_mentions_persisted_oracle_memory(self, monkeypatch, tmp_path):
        hv = _load_hv()
        monkeypatch.chdir(tmp_path)
        (tmp_path / hv.GOAL_FILE).write_text("Find the hidden law.", encoding="utf-8")
        (tmp_path / hv.DATA_FILE).write_text("[]", encoding="utf-8")
        (tmp_path / hv.OPINIONS_FILE).write_text(
            "Current workspace theory: rank in sorted order determines negation.",
            encoding="utf-8",
        )
        (tmp_path / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(SAMPLE_DEAD_ENDS, indent=2), encoding="utf-8")
        current_state = hv.blank_state()
        current_state["active"] = json.loads(json.dumps(SAMPLE_DEAD_ENDS))
        current_state["anchor_lock"] = {
            "active": True,
            "locked_basin_id": "B6",
            "locked_basin_hash": "abc123",
            "replacement_theory_type": "rank-based negation",
            "lock_activated_cycle": 10,
            "lock_cleared_cycle": None,
        }

        prompt = hv.format_cycle_prompt(
            11,
            30,
            "grind",
            current_state,
            altitude_mode="anchor-v4.5",
            oracle_memory_note="Recent fixed-suite oracle results:\n- cycle 9: score=0.1667",
        )[-1]["content"]

        assert "ANCHOR WINDOW — LOCKED (V4.5)" in prompt
        assert "persisted recent oracle memory" in prompt.lower()
        assert "# lock_window_oracle_memory" in prompt
        assert "Recent fixed-suite oracle results" in prompt

    def test_anchor_v46_prompt_mentions_minimal_recent_oracle_history(self, monkeypatch, tmp_path):
        hv = _load_hv()
        monkeypatch.chdir(tmp_path)
        (tmp_path / hv.GOAL_FILE).write_text("Find the hidden law.", encoding="utf-8")
        (tmp_path / hv.DATA_FILE).write_text("[]", encoding="utf-8")
        (tmp_path / hv.OPINIONS_FILE).write_text(
            "Current workspace theory: rank in sorted order determines negation.",
            encoding="utf-8",
        )
        (tmp_path / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(SAMPLE_DEAD_ENDS, indent=2), encoding="utf-8")
        current_state = hv.blank_state()
        current_state["active"] = json.loads(json.dumps(SAMPLE_DEAD_ENDS))
        current_state["anchor_lock"] = {
            "active": True,
            "locked_basin_id": "B6",
            "locked_basin_hash": "abc123",
            "replacement_theory_type": "rank-based negation",
            "lock_activated_cycle": 10,
            "lock_cleared_cycle": None,
        }

        prompt = hv.format_cycle_prompt(
            11,
            30,
            "grind",
            current_state,
            altitude_mode="anchor-v4.6",
            oracle_memory_note="Recent Oracle History (last 3 cycles)\nCycle 9: oracle_fixed = 0.1667, oracle_combined = 0.1176, hamming_distance = 2",
        )[-1]["content"]

        assert "ANCHOR WINDOW — LOCKED (V4.6)" in prompt
        assert "minimal recent-oracle summary" in prompt.lower()
        assert "# lock_window_oracle_memory" in prompt
        assert "Recent Oracle History (last 3 cycles)" in prompt

    def test_anchor_v5_prompt_mentions_differential_oracle_ledger(self, monkeypatch, tmp_path):
        hv = _load_hv()
        monkeypatch.chdir(tmp_path)
        (tmp_path / hv.GOAL_FILE).write_text("Find the hidden law.", encoding="utf-8")
        (tmp_path / hv.DATA_FILE).write_text("[]", encoding="utf-8")
        (tmp_path / hv.OPINIONS_FILE).write_text(
            "Current workspace theory: rank in sorted order determines negation.",
            encoding="utf-8",
        )
        (tmp_path / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(SAMPLE_DEAD_ENDS, indent=2), encoding="utf-8")
        current_state = hv.blank_state()
        current_state["active"] = json.loads(json.dumps(SAMPLE_DEAD_ENDS))
        current_state["anchor_lock"] = {
            "active": True,
            "locked_basin_id": "B6",
            "locked_basin_hash": "abc123",
            "replacement_theory_type": "rank-based negation",
            "lock_activated_cycle": 10,
            "lock_cleared_cycle": None,
        }

        prompt = hv.format_cycle_prompt(
            11,
            30,
            "grind",
            current_state,
            altitude_mode="anchor-v5",
            oracle_memory_note="Validator-written differential oracle ledger.\nReplacement readiness threshold: NOT READY yet.",
        )[-1]["content"]

        assert "ANCHOR WINDOW — LOCKED (V5)" in prompt
        assert "validator-written differential oracle ledger" in prompt.lower()
        assert "replacement readiness threshold" in prompt.lower()
        assert "# lock_window_oracle_memory" in prompt

    def test_anchor_v51_prompt_switches_to_replacement_attempt_mode_when_ready(self, monkeypatch, tmp_path):
        hv = _load_hv()
        monkeypatch.chdir(tmp_path)
        (tmp_path / hv.GOAL_FILE).write_text("Find the hidden law.", encoding="utf-8")
        (tmp_path / hv.DATA_FILE).write_text("[]", encoding="utf-8")
        (tmp_path / hv.OPINIONS_FILE).write_text(
            "Current workspace theory: broad rank-based negation.",
            encoding="utf-8",
        )
        (tmp_path / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(SAMPLE_DEAD_ENDS, indent=2), encoding="utf-8")
        current_state = hv.blank_state()
        current_state["active"] = json.loads(json.dumps(SAMPLE_DEAD_ENDS))
        current_state["anchor_lock"] = {
            "active": True,
            "locked_basin_id": "B6",
            "locked_basin_hash": "abc123",
            "replacement_theory_type": "rank-based negation",
            "lock_activated_cycle": 10,
            "lock_cleared_cycle": None,
        }
        current_state["anchor_ledger"] = {
            "active": True,
            "baseline_cycle": 9,
            "baseline_fixed_vector": [False, True, False, False],
            "baseline_fixed_score": 0.0833,
            "last_cycle": 23,
            "last_fixed_vector": [True, False, True, True],
            "last_fixed_score": 0.5,
            "positive_flip_counts": {"1": 2, "3": 2, "4": 1},
            "negative_flip_counts": {"2": 1},
            "coverage_cases": [1, 2, 3, 4],
            "recurring_positive_cases": [1, 3],
            "recurring_negative_cases": [],
            "ready_for_replacement": True,
        }

        prompt = hv.format_cycle_prompt(
            24,
            30,
            "grind",
            current_state,
            altitude_mode="anchor-v5.1",
            oracle_memory_note=(
                "LEDGER STATUS: READY FOR REPLACEMENT.\n"
                "You must now attempt supersession-with-replacement in this cycle.\n"
                "Replacement readiness threshold: READY (coverage>=4 and recurring positive flips>=2)."
            ),
        )[-1]["content"]

        assert "REPLACEMENT ATTEMPT MODE — LEDGER READY (V5.1)" in prompt
        assert "You must now attempt supersession-with-replacement in this cycle." in prompt
        assert "begin exactly with: Ledger status: READY" in prompt
        assert "# lock_window_oracle_memory" in prompt

    def test_anchor_v52_prompt_adds_minimal_replacement_transaction_rules(self, monkeypatch, tmp_path):
        hv = _load_hv()
        monkeypatch.chdir(tmp_path)
        (tmp_path / hv.GOAL_FILE).write_text("Find the hidden law.", encoding="utf-8")
        (tmp_path / hv.DATA_FILE).write_text("[]", encoding="utf-8")
        (tmp_path / hv.OPINIONS_FILE).write_text(
            "Current workspace theory: broad rank-based negation.",
            encoding="utf-8",
        )
        (tmp_path / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(SAMPLE_DEAD_ENDS, indent=2), encoding="utf-8")
        current_state = hv.blank_state()
        current_state["active"] = json.loads(json.dumps(SAMPLE_DEAD_ENDS))
        current_state["anchor_lock"] = {
            "active": True,
            "locked_basin_id": "B2",
            "locked_basin_hash": "abc123",
            "replacement_theory_type": "rank-based negation",
            "lock_activated_cycle": 10,
            "lock_cleared_cycle": None,
        }
        current_state["anchor_ledger"] = {
            "active": True,
            "baseline_cycle": 9,
            "baseline_fixed_vector": [False, True, False, False],
            "baseline_fixed_score": 0.0833,
            "last_cycle": 23,
            "last_fixed_vector": [True, False, True, True],
            "last_fixed_score": 0.5,
            "positive_flip_counts": {"1": 2, "3": 2, "4": 1},
            "negative_flip_counts": {"2": 1},
            "coverage_cases": [1, 2, 3, 4],
            "recurring_positive_cases": [1, 3],
            "recurring_negative_cases": [],
            "ready_for_replacement": True,
        }

        prompt = hv.format_cycle_prompt(
            24,
            30,
            "grind",
            current_state,
            altitude_mode="anchor-v5.2",
            oracle_memory_note=(
                "LEDGER STATUS: READY FOR REPLACEMENT.\n"
                "You must now attempt supersession-with-replacement in this cycle.\n"
                "Replacement readiness threshold: READY (coverage>=4 and recurring positive flips>=2)."
            ),
        )[-1]["content"]

        assert "REPLACEMENT ATTEMPT MODE — LEDGER READY (V5.2)" in prompt
        assert "Replacement Transaction Rules:" in prompt
        assert "NEVER modify B2, F5, or F7" in prompt
        assert "B3 may contain AT MOST 3 families" in prompt
        assert "fewest families" not in prompt
        assert "Create B3 and mark B2 as SUPERSEDED in the same dead_ends payload." in prompt


class TestAnchorAssayHooks:
    def test_anchor_lock_setup_raises_prelock_escape_for_superseded_only_state(self):
        import compression_assay as ca

        previous_state = {
            "active": {
                "basins": [
                    {
                        "id": "B2",
                        "status": "SUPERSEDED",
                        "claim": "element inversion count determines negation",
                    }
                ],
                "families": [],
                "locals": [],
            },
            "anchor_lock": {
                "active": False,
                "locked_basin_id": None,
                "locked_basin_hash": None,
                "replacement_theory_type": None,
                "lock_activated_cycle": None,
                "lock_cleared_cycle": None,
            },
        }

        with pytest.raises(ca.AnchorPrelockEscape):
            ca._ensure_anchor_v4_lock(previous_state, cycle=10)

    def test_parse_args_accepts_anchor_and_fire_cycles(self, monkeypatch):
        import compression_assay as ca

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "compression_assay.py",
                "--run-id", "1",
                "--altitude-prompt", "anchor",
                "--altitude-fire-cycles", "1,10",
            ],
        )
        args = ca.parse_args()
        assert args.altitude_prompt == "anchor"
        assert args.altitude_fire_cycles == "1,10"

    def test_parse_args_accepts_anchor_v2(self, monkeypatch):
        import compression_assay as ca

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "compression_assay.py",
                "--run-id", "1",
                "--altitude-prompt", "anchor-v2",
            ],
        )
        args = ca.parse_args()
        assert args.altitude_prompt == "anchor-v2"

    def test_parse_args_accepts_anchor_v3(self, monkeypatch):
        import compression_assay as ca

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "compression_assay.py",
                "--run-id", "1",
                "--altitude-prompt", "anchor-v3",
            ],
        )
        args = ca.parse_args()
        assert args.altitude_prompt == "anchor-v3"

    def test_parse_args_accepts_anchor_v4(self, monkeypatch):
        import compression_assay as ca

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "compression_assay.py",
                "--run-id", "1",
                "--altitude-prompt", "anchor-v4",
            ],
        )
        args = ca.parse_args()
        assert args.altitude_prompt == "anchor-v4"

    def test_parse_args_accepts_anchor_v45(self, monkeypatch):
        import compression_assay as ca

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "compression_assay.py",
                "--run-id", "1",
                "--altitude-prompt", "anchor-v4.5",
            ],
        )
        args = ca.parse_args()
        assert args.altitude_prompt == "anchor-v4.5"

    def test_parse_args_accepts_anchor_v46(self, monkeypatch):
        import compression_assay as ca

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "compression_assay.py",
                "--run-id", "1",
                "--altitude-prompt", "anchor-v4.6",
            ],
        )
        args = ca.parse_args()
        assert args.altitude_prompt == "anchor-v4.6"

    def test_parse_args_accepts_anchor_v5(self, monkeypatch):
        import compression_assay as ca

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "compression_assay.py",
                "--run-id", "1",
                "--altitude-prompt", "anchor-v5",
            ],
        )
        args = ca.parse_args()
        assert args.altitude_prompt == "anchor-v5"

    def test_parse_args_accepts_anchor_v51(self, monkeypatch):
        import compression_assay as ca

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "compression_assay.py",
                "--run-id", "1",
                "--altitude-prompt", "anchor-v5.1",
            ],
        )
        args = ca.parse_args()
        assert args.altitude_prompt == "anchor-v5.1"

    def test_parse_args_accepts_anchor_v52(self, monkeypatch):
        import compression_assay as ca

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "compression_assay.py",
                "--run-id", "1",
                "--altitude-prompt", "anchor-v5.2",
            ],
        )
        args = ca.parse_args()
        assert args.altitude_prompt == "anchor-v5.2"

    def test_parse_cycle_list(self):
        import compression_assay as ca

        assert ca._parse_cycle_list("1,10,15") == {1, 10, 15}
        assert ca._parse_cycle_list(None) == set()
        with pytest.raises(ValueError):
            ca._parse_cycle_list("0")

    def test_altitude_state_can_use_explicit_fire_cycles(self):
        import compression_assay as ca

        state = ca.AltitudeState(frequency=10, prompt_style="anchor", fire_cycles={1, 10})
        assert state.should_fire(1) is True
        assert state.should_fire(2) is False
        assert state.should_fire(10) is True

    def test_request_altitude_map_source_mentions_anchor_solver(self):
        import compression_assay as ca
        import inspect

        source = inspect.getsource(ca.request_altitude_map)
        assert '"anchor"' in source or "'anchor'" in source
        assert '"anchor-v2"' in source or "'anchor-v2'" in source
        assert '"anchor-v3"' in source or "'anchor-v3'" in source
        assert '"anchor-v4"' in source or "'anchor-v4'" in source
        assert '"anchor-v4.5"' in source or "'anchor-v4.5'" in source
        assert '"anchor-v4.6"' in source or "'anchor-v4.6'" in source
        assert '"anchor-v5"' in source or "'anchor-v5'" in source
        assert '"anchor-v5.1"' in source or "'anchor-v5.1'" in source
        assert '"anchor-v5.2"' in source or "'anchor-v5.2'" in source
        assert "solver_py" in source

    def test_anchor_v45_oracle_memory_is_derived_from_recent_telemetry(self, monkeypatch, tmp_path):
        import compression_assay as ca

        monkeypatch.chdir(tmp_path)
        rows = [
            {
                "cycle": 9,
                "cycle_type": "grind",
                "oracle_fixed": 0.1667,
                "fixed_suite_vector": [True, False, False, False],
            },
            {
                "cycle": 10,
                "cycle_type": "altitude_anchor-v4.5",
                "altitude_mode": "anchor-v4.5",
            },
            {
                "cycle": 10,
                "cycle_type": "grind",
                "oracle_fixed": 0.5833,
                "fixed_suite_vector": [True, True, False, True],
            },
            {
                "cycle": 11,
                "cycle_type": "grind",
                "oracle_fixed": 0.3333,
                "fixed_suite_vector": [True, False, True, True],
            },
        ]
        (tmp_path / ca.TELEMETRY_FILE).write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )
        previous_state = {
            "anchor_lock": {
                "active": True,
                "locked_basin_id": "B2",
                "locked_basin_hash": "abc123",
                "replacement_theory_type": "rank-based negation",
                "lock_activated_cycle": 10,
                "lock_cleared_cycle": None,
            }
        }

        note = ca._build_anchor_v45_oracle_memory(previous_state)

        assert "Locked contrast basin: B2." in note
        assert "Replacement theory type: rank-based negation." in note
        assert "cycle 9: score=0.1667" in note
        assert "cycle 10: score=0.5833" in note
        assert "cycle 11: score=0.3333" in note
        assert "9→10" in note
        assert "10→11" in note

    def test_anchor_v46_oracle_memory_is_minimal_recent_summary(self, monkeypatch, tmp_path):
        import compression_assay as ca

        monkeypatch.chdir(tmp_path)
        rows = [
            {
                "cycle": 9,
                "cycle_type": "grind",
                "oracle_fixed": 0.1667,
                "oracle_combined": 0.1176,
                "hamming_distance": 2,
                "fixed_suite_vector": [True, False, False, False],
            },
            {
                "cycle": 10,
                "cycle_type": "grind",
                "oracle_fixed": 0.5833,
                "oracle_combined": 0.4706,
                "hamming_distance": 4,
                "fixed_suite_vector": [True, True, False, True],
            },
            {
                "cycle": 11,
                "cycle_type": "grind",
                "oracle_fixed": 0.3333,
                "oracle_combined": 0.2353,
                "hamming_distance": 1,
                "fixed_suite_vector": [True, False, True, True],
            },
        ]
        (tmp_path / ca.TELEMETRY_FILE).write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )
        previous_state = {
            "anchor_lock": {
                "active": True,
                "locked_basin_id": "B2",
                "locked_basin_hash": "abc123",
                "replacement_theory_type": "rank-based negation",
                "lock_activated_cycle": 10,
                "lock_cleared_cycle": None,
            }
        }

        note = ca._build_anchor_v46_oracle_memory(previous_state)

        assert "Recent Oracle History (last 3 cycles)" in note
        assert "Cycle 9: oracle_fixed = 0.1667, oracle_combined = 0.1176, hamming_distance = 2" in note
        assert "Cycle 10: oracle_fixed = 0.5833, oracle_combined = 0.4706, hamming_distance = 4" in note
        assert "Cycle 11: oracle_fixed = 0.3333, oracle_combined = 0.2353, hamming_distance = 1" in note
        assert "Score trend: improving" in note
        assert "Best score in window: 0.5833 at cycle 10" in note

    def test_restore_runtime_state_after_workspace_reset_rewrites_lock_state(self, monkeypatch, tmp_path):
        import compression_assay as ca
        import v44_epistemics as ep

        monkeypatch.chdir(tmp_path)
        state = ep.blank_state()
        state["active"] = json.loads(json.dumps(SAMPLE_DEAD_ENDS))
        state = ep.activate_anchor_lock(
            state,
            locked_basin_id="B6",
            replacement_theory_type="rank-based negation",
            cycle=10,
        )

        ca._restore_runtime_state_after_workspace_reset(state)
        restored = ep.load_state(ca.hv.DEAD_END_STATE_FILE)

        assert restored["anchor_lock"]["active"] is True
        assert restored["anchor_lock"]["locked_basin_id"] == "B6"
        assert restored["anchor_lock"]["lock_activated_cycle"] == 10

    def test_anchor_v5_ledger_accumulates_baseline_relative_flips(self, monkeypatch, tmp_path):
        import compression_assay as ca
        import v44_epistemics as ep

        monkeypatch.chdir(tmp_path)
        rows = [
            {
                "cycle": 9,
                "cycle_type": "grind",
                "oracle_fixed": 0.0833,
                "fixed_suite_vector": [False, True, False, False],
            }
        ]
        (tmp_path / ca.TELEMETRY_FILE).write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )

        state = ep.blank_state()
        state["active"] = json.loads(json.dumps(SAMPLE_DEAD_ENDS))
        state = ep.activate_anchor_lock(
            state,
            locked_basin_id="B6",
            replacement_theory_type="rank-based negation",
            cycle=10,
        )

        state = ca._update_anchor_v5_ledger(
            state,
            cycle=11,
            fixed_score=0.3333,
            fixed_vector=[True, True, True, False],
        )
        state = ca._update_anchor_v5_ledger(
            state,
            cycle=12,
            fixed_score=0.5,
            fixed_vector=[True, False, True, True],
        )

        ledger = state["anchor_ledger"]
        assert ledger["active"] is True
        assert ledger["baseline_cycle"] == 9
        assert ledger["coverage_cases"] == [1, 2, 3, 4]
        assert ledger["recurring_positive_cases"] == [1, 3]
        assert ledger["recurring_negative_cases"] == []
        assert ledger["ready_for_replacement"] is True

    def test_anchor_v5_ledger_note_reports_threshold(self):
        import compression_assay as ca

        state = {
            "anchor_lock": {
                "active": True,
                "locked_basin_id": "B2",
                "locked_basin_hash": "abc123",
                "replacement_theory_type": "rank-based negation",
                "lock_activated_cycle": 10,
                "lock_cleared_cycle": None,
            },
            "anchor_ledger": {
                "active": True,
                "baseline_cycle": 9,
                "baseline_fixed_vector": [False, True, False, False],
                "baseline_fixed_score": 0.0833,
                "last_cycle": 12,
                "last_fixed_vector": [True, False, True, True],
                "last_fixed_score": 0.5,
                "positive_flip_counts": {"1": 2, "3": 2, "4": 1},
                "negative_flip_counts": {"2": 1},
                "coverage_cases": [1, 2, 3, 4],
                "recurring_positive_cases": [1, 3],
                "recurring_negative_cases": [],
                "ready_for_replacement": True,
            },
        }

        note = ca._build_anchor_v5_oracle_ledger_note(state)

        assert "Validator-written differential oracle ledger" in note
        assert "Baseline fixed-suite row: cycle 9" in note
        assert "Coverage cases relative to baseline: 1,2,3,4" in note
        assert "Recurring positive flips" in note
        assert "READY" in note

    def test_anchor_v51_ledger_note_escalates_ready_state(self):
        import compression_assay as ca

        state = {
            "anchor_lock": {
                "active": True,
                "locked_basin_id": "B2",
                "locked_basin_hash": "abc123",
                "replacement_theory_type": "rank-based negation",
                "lock_activated_cycle": 10,
                "lock_cleared_cycle": None,
            },
            "anchor_ledger": {
                "active": True,
                "baseline_cycle": 9,
                "baseline_fixed_vector": [False, True, False, False],
                "baseline_fixed_score": 0.0833,
                "last_cycle": 23,
                "last_fixed_vector": [True, False, True, True],
                "last_fixed_score": 0.5,
                "positive_flip_counts": {"1": 2, "3": 2, "4": 1},
                "negative_flip_counts": {"2": 1},
                "coverage_cases": [1, 2, 3, 4],
                "recurring_positive_cases": [1, 3],
                "recurring_negative_cases": [],
                "ready_for_replacement": True,
            },
        }

        note = ca._build_anchor_v5_oracle_ledger_note(state, escalate_ready=True)

        assert "LEDGER STATUS: READY FOR REPLACEMENT." in note
        assert "This overrides any earlier NOT READY statement in opinions.md." in note
        assert "You must now attempt supersession-with-replacement in this cycle." in note


class TestAnchorForkSnapshot:
    def test_apply_fork_snapshot_copies_optional_context(self, monkeypatch, tmp_path):
        import compression_assay as ca
        import hypervisor_v44 as hv
        from v44_epistemics import blank_state, save_state, load_state

        snap_dir = tmp_path / "snapshot"
        snap_dir.mkdir()
        (snap_dir / hv.OPINIONS_FILE).write_text("Rank-based workspace theory.", encoding="utf-8")
        (snap_dir / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(SAMPLE_DEAD_ENDS, indent=2), encoding="utf-8")
        (snap_dir / hv.GOAL_FILE).write_text("Goal copy.", encoding="utf-8")
        (snap_dir / hv.DATA_FILE).write_text('[{"input": [2, 1, 3]}]', encoding="utf-8")
        (snap_dir / hv.SOLVER_FILE).write_text(
            "def transduce(arr: list[int]) -> list[int]:\n    return arr\n",
            encoding="utf-8",
        )
        snap_state = blank_state()
        snap_state["active"] = SAMPLE_DEAD_ENDS
        save_state(str(snap_dir / hv.DEAD_END_STATE_FILE), snap_state)

        ws = tmp_path / "workspace"
        ws.mkdir()
        monkeypatch.chdir(ws)

        copied = ca._apply_fork_snapshot(snap_dir)

        assert set(copied) >= {hv.GOAL_FILE, hv.DATA_FILE, hv.SOLVER_FILE, hv.DEAD_END_STATE_FILE}
        assert (ws / hv.OPINIONS_FILE).read_text(encoding="utf-8") == "Rank-based workspace theory."
        assert json.loads((ws / hv.DEAD_ENDS_JSON_FILE).read_text(encoding="utf-8"))["basins"][0]["id"] == "B6"
        assert (ws / hv.GOAL_FILE).read_text(encoding="utf-8") == "Goal copy."
        assert json.loads((ws / hv.DATA_FILE).read_text(encoding="utf-8"))[0]["input"] == [2, 1, 3]
        assert "def transduce" in (ws / hv.SOLVER_FILE).read_text(encoding="utf-8")
        loaded_state = load_state(str(ws / hv.DEAD_END_STATE_FILE))
        assert loaded_state["active"]["basins"][0]["claim"] == "inversion count determines negation"


class TestAnchorLockValidator:
    def test_anchor_lock_rejects_in_place_mutation(self):
        import v44_epistemics as ep

        state = ep.blank_state()
        state["active"] = json.loads(json.dumps(SAMPLE_DEAD_ENDS))
        state = ep.activate_anchor_lock(
            state,
            locked_basin_id="B6",
            replacement_theory_type="rank-based negation",
            cycle=10,
        )
        mutated = json.loads(json.dumps(SAMPLE_DEAD_ENDS))
        mutated["families"][0]["claim"] = "negate if element is greater than next element"

        errors = ep.validate_dead_ends(mutated, state["active"], state)

        assert any("ANCHOR_LOCK_VIOLATION" in err for err in errors)
        assert any("content modified without supersession-with-replacement" in err for err in errors)

    def test_anchor_lock_rejects_bare_supersession(self):
        import v44_epistemics as ep

        state = ep.blank_state()
        state["active"] = json.loads(json.dumps(SAMPLE_DEAD_ENDS))
        state = ep.activate_anchor_lock(
            state,
            locked_basin_id="B6",
            replacement_theory_type="rank-based negation",
            cycle=10,
        )
        candidate = json.loads(json.dumps(SAMPLE_DEAD_ENDS))
        candidate["basins"][0]["status"] = "SUPERSEDED"

        errors = ep.validate_dead_ends(candidate, state["active"], state)

        assert any("ANCHOR_LOCK_VIOLATION" in err for err in errors)
        assert any("superseded without replacement" in err for err in errors)

    def test_anchor_lock_allows_valid_supersession_with_replacement(self):
        import v44_epistemics as ep

        state = ep.blank_state()
        state["active"] = json.loads(json.dumps(SAMPLE_DEAD_ENDS))
        state = ep.activate_anchor_lock(
            state,
            locked_basin_id="B6",
            replacement_theory_type="rank-based negation",
            cycle=10,
        )
        candidate = {
            "basins": [
                {
                    "id": "B6",
                    "status": "SUPERSEDED",
                    "claim": "inversion count determines negation",
                    "cited_families": ["F12", "F13"],
                },
                {
                    "id": "B7",
                    "status": "ACTIVE",
                    "claim": "rank-based negation determines output",
                    "cited_families": ["F12", "F20"],
                },
            ],
            "families": [
                {
                    "id": "F12",
                    "status": "ACTIVE",
                    "claim": "negate if element precedes a smaller value",
                    "falsifying_arrays": [[3, 1, 2], [2, 1, 4, 3]],
                },
                {
                    "id": "F13",
                    "status": "SUPERSEDED",
                    "claim": "negate if inversion count is odd",
                    "falsifying_arrays": [[2, 1, 3], [4, 1, 3, 2]],
                },
                {
                    "id": "F20",
                    "status": "ACTIVE",
                    "claim": "Negate if rank in sorted order is below threshold",
                    "falsifying_arrays": [[1, 3, 2], [4, 2, 1, 3]],
                },
            ],
            "locals": [],
        }

        errors = ep.validate_dead_ends(candidate, state["active"], state)
        assert errors == []

        merged = ep.merge_state(state, candidate, cycle=12)
        lock = merged["anchor_lock"]
        assert lock["active"] is False
        assert lock["lock_cleared_cycle"] == 12
