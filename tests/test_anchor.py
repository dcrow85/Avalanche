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


class TestAnchorAssayHooks:
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
        assert "solver_py" in source


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
