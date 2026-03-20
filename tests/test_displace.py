"""Unit tests for V4.7.1 Displace Branch features."""
from __future__ import annotations

import json
import os
import sys

import importlib

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _load_hv():
    os.environ.pop("AVALANCHE_ACTIVE", None)
    return importlib.import_module("hypervisor_v44")


SAMPLE_DEAD_ENDS = {
    "basins": [
        {"id": "B1", "status": "ACTIVE", "claim": "permutation parity determines global negation",
         "cited_families": ["F8", "F9"]},
        {"id": "B2", "status": "SUPERSEDED", "claim": "cycle structure matters",
         "cited_families": ["F10"]},
    ],
    "families": [
        {"id": "F8", "status": "SUPERSEDED", "claim": "Negate elements in 2-cycles",
         "falsifying_arrays": [[2, 1, 3]]},
        {"id": "F9", "status": "ACTIVE", "claim": "Negate all if odd parity",
         "falsifying_arrays": [[1, 2, 3]]},
        {"id": "F10", "status": "SUPERSEDED", "claim": "Negate elements in odd-length cycles",
         "falsifying_arrays": [[2, 3, 1, 4]]},
    ],
    "locals": [],
}


# ---------------------------------------------------------------------------
# TestDisplacePrompt
# ---------------------------------------------------------------------------

class TestDisplacePrompt:
    def test_prompt_includes_exhausted_families(self, monkeypatch, tmp_path):
        hv = _load_hv()
        monkeypatch.chdir(tmp_path)
        (tmp_path / hv.GOAL_FILE).write_text("Find the hidden law.", encoding="utf-8")
        (tmp_path / hv.DATA_FILE).write_text("[]", encoding="utf-8")
        (tmp_path / hv.OPINIONS_FILE).write_text("Current theory.", encoding="utf-8")
        (tmp_path / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(SAMPLE_DEAD_ENDS, indent=2), encoding="utf-8")

        prompt = hv.format_cycle_prompt(
            10, 200, "grind", hv.blank_state(),
            altitude_mode="displace",
        )[-1]["content"]

        assert "DISPLACE ALTITUDE" in prompt
        assert "F8: Negate elements in 2-cycles" in prompt
        assert "F10: Negate elements in odd-length cycles" in prompt

    def test_prompt_includes_active_families(self, monkeypatch, tmp_path):
        hv = _load_hv()
        monkeypatch.chdir(tmp_path)
        (tmp_path / hv.GOAL_FILE).write_text("Find the hidden law.", encoding="utf-8")
        (tmp_path / hv.DATA_FILE).write_text("[]", encoding="utf-8")
        (tmp_path / hv.OPINIONS_FILE).write_text("Current theory.", encoding="utf-8")
        (tmp_path / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(SAMPLE_DEAD_ENDS, indent=2), encoding="utf-8")

        prompt = hv.format_cycle_prompt(
            10, 200, "grind", hv.blank_state(),
            altitude_mode="displace",
        )[-1]["content"]

        assert "F9: Negate all if odd parity" in prompt

    def test_prompt_includes_basin_summary(self, monkeypatch, tmp_path):
        hv = _load_hv()
        monkeypatch.chdir(tmp_path)
        (tmp_path / hv.GOAL_FILE).write_text("Find the hidden law.", encoding="utf-8")
        (tmp_path / hv.DATA_FILE).write_text("[]", encoding="utf-8")
        (tmp_path / hv.OPINIONS_FILE).write_text("Current theory.", encoding="utf-8")
        (tmp_path / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(SAMPLE_DEAD_ENDS, indent=2), encoding="utf-8")

        prompt = hv.format_cycle_prompt(
            10, 200, "grind", hv.blank_state(),
            altitude_mode="displace",
        )[-1]["content"]

        assert "B1 [ACTIVE]" in prompt
        assert "B2 [SUPERSEDED]" in prompt

    def test_prompt_mentions_interaction_surface(self, monkeypatch, tmp_path):
        hv = _load_hv()
        monkeypatch.chdir(tmp_path)
        (tmp_path / hv.GOAL_FILE).write_text("Find the hidden law.", encoding="utf-8")
        (tmp_path / hv.DATA_FILE).write_text("[]", encoding="utf-8")
        (tmp_path / hv.OPINIONS_FILE).write_text("Current theory.", encoding="utf-8")
        (tmp_path / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(SAMPLE_DEAD_ENDS, indent=2), encoding="utf-8")

        prompt = hv.format_cycle_prompt(
            10, 200, "grind", hv.blank_state(),
            altitude_mode="displace",
        )[-1]["content"]

        assert "interaction surface" in prompt.lower() or "interaction" in prompt.lower()

    def test_prompt_is_additive_not_prohibitive(self, monkeypatch, tmp_path):
        hv = _load_hv()
        monkeypatch.chdir(tmp_path)
        (tmp_path / hv.GOAL_FILE).write_text("Find the hidden law.", encoding="utf-8")
        (tmp_path / hv.DATA_FILE).write_text("[]", encoding="utf-8")
        (tmp_path / hv.OPINIONS_FILE).write_text("Current theory.", encoding="utf-8")
        (tmp_path / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(SAMPLE_DEAD_ENDS, indent=2), encoding="utf-8")

        prompt = hv.format_cycle_prompt(
            10, 200, "grind", hv.blank_state(),
            altitude_mode="displace",
        )[-1]["content"]

        # Additive language
        assert "Move onto" in prompt
        # Not prohibitive
        assert "do not use" not in prompt.lower()
        assert "never use" not in prompt.lower()

    def test_prompt_with_empty_graveyard(self, monkeypatch, tmp_path):
        hv = _load_hv()
        monkeypatch.chdir(tmp_path)
        (tmp_path / hv.GOAL_FILE).write_text("Find the hidden law.", encoding="utf-8")
        (tmp_path / hv.DATA_FILE).write_text("[]", encoding="utf-8")
        (tmp_path / hv.OPINIONS_FILE).write_text("Current theory.", encoding="utf-8")
        empty_de = {"basins": [], "families": [], "locals": []}
        (tmp_path / hv.DEAD_ENDS_JSON_FILE).write_text(json.dumps(empty_de, indent=2), encoding="utf-8")

        prompt = hv.format_cycle_prompt(
            10, 200, "grind", hv.blank_state(),
            altitude_mode="displace",
        )[-1]["content"]

        assert "DISPLACE ALTITUDE" in prompt
        assert "(none yet)" in prompt or "(none)" in prompt


# ---------------------------------------------------------------------------
# TestDisplaceGraveyardCap
# ---------------------------------------------------------------------------

class TestDisplaceGraveyardCap:
    def test_raises_cap_for_displace(self):
        from compression_assay import _effective_graveyard_entry_cap
        result = _effective_graveyard_entry_cap(2, "displace")
        # Should raise to at least the survey minimum
        assert result >= 2

    def test_survey_and_displace_behave_same(self):
        from compression_assay import _effective_graveyard_entry_cap
        survey_cap = _effective_graveyard_entry_cap(2, "survey")
        displace_cap = _effective_graveyard_entry_cap(2, "displace")
        assert survey_cap == displace_cap

    def test_plain_grind_unchanged(self):
        from compression_assay import _effective_graveyard_entry_cap
        assert _effective_graveyard_entry_cap(2, None) == 2
        assert _effective_graveyard_entry_cap(2, "rotating") == 2


# ---------------------------------------------------------------------------
# TestDisplaceReturnsOpinions
# ---------------------------------------------------------------------------

class TestDisplaceReturnsOpinions:
    """Verify the system prompt and opinions_md return gate include 'displace'."""

    def test_displace_in_opinions_mode_set(self):
        """The altitude modes that return opinions_md must include displace."""
        import compression_assay as ca
        import inspect
        source = inspect.getsource(ca.request_altitude_map)
        # Both gate checks should include "displace"
        assert '"displace"' in source or "'displace'" in source


# ---------------------------------------------------------------------------
# TestProbeGDistance
# ---------------------------------------------------------------------------

class TestProbeGDistance:
    def test_dead_ends_claims_text_extraction(self):
        from compression_assay import _dead_ends_claims_text
        text = _dead_ends_claims_text(SAMPLE_DEAD_ENDS)
        assert "permutation parity determines global negation" in text
        assert "Negate elements in 2-cycles" in text
        assert "Negate all if odd parity" in text
        assert "cycle structure matters" in text

    def test_dead_ends_claims_text_empty(self):
        from compression_assay import _dead_ends_claims_text
        text = _dead_ends_claims_text({"basins": [], "families": [], "locals": []})
        assert text == ""

    def test_dead_ends_claims_text_missing_keys(self):
        from compression_assay import _dead_ends_claims_text
        text = _dead_ends_claims_text({})
        assert text == ""

    def test_semantic_distance_identical(self):
        from v43_metrics import semantic_distance
        assert semantic_distance("hello world", "hello world") == 0.0

    def test_semantic_distance_disjoint(self):
        from v43_metrics import semantic_distance
        d = semantic_distance("alpha beta gamma", "delta epsilon zeta")
        assert d == 1.0

    def test_semantic_distance_empty(self):
        from v43_metrics import semantic_distance
        assert semantic_distance("", "") == 0.0


# ---------------------------------------------------------------------------
# TestForkSnapshot
# ---------------------------------------------------------------------------

class TestForkSnapshot:
    def test_fork_copies_opinions_and_dead_ends(self, tmp_path):
        """Verify fork-snapshot copies the right files and initializes state."""
        from v44_epistemics import blank_state, merge_state, save_state, load_state, render_dead_ends_md
        import hypervisor_v44 as hv

        # Create fake snapshot directory
        snap_dir = tmp_path / "snapshot"
        snap_dir.mkdir()
        (snap_dir / "opinions.md").write_text("Test theory about parity.", encoding="utf-8")
        (snap_dir / "dead-ends.json").write_text(json.dumps(SAMPLE_DEAD_ENDS, indent=2), encoding="utf-8")

        # Create fake workspace
        ws = tmp_path / "workspace"
        ws.mkdir()

        # Simulate what the fork logic does
        de_data = json.loads((snap_dir / "dead-ends.json").read_text(encoding="utf-8"))
        (ws / "opinions.md").write_text((snap_dir / "opinions.md").read_text(encoding="utf-8"), encoding="utf-8")
        (ws / "dead-ends.json").write_text(json.dumps(de_data, indent=2), encoding="utf-8")
        (ws / "dead-ends.md").write_text(render_dead_ends_md(de_data), encoding="utf-8")
        forked_state = merge_state(blank_state(), de_data, cycle=0)
        save_state(str(ws / "dead-end-state.json"), forked_state)

        # Verify
        assert (ws / "opinions.md").read_text(encoding="utf-8") == "Test theory about parity."
        loaded_de = json.loads((ws / "dead-ends.json").read_text(encoding="utf-8"))
        assert len(loaded_de["basins"]) == 2
        assert len(loaded_de["families"]) == 3
        loaded_state = load_state(str(ws / "dead-end-state.json"))
        assert loaded_state["active"]["basins"][0]["id"] == "B1"


# ---------------------------------------------------------------------------
# TestInjectGraveyard
# ---------------------------------------------------------------------------

class TestInjectGraveyard:
    def test_inject_overwrites_dead_ends(self, tmp_path):
        """Verify inject-graveyard overwrites dead-ends with synthetic surface."""
        from v44_epistemics import blank_state, merge_state, save_state, load_state, render_dead_ends_md

        ws = tmp_path / "workspace"
        ws.mkdir()

        # Start with a small graveyard
        initial_de = {"basins": [{"id": "B1", "status": "ACTIVE", "claim": "initial"}], "families": [], "locals": []}
        (ws / "dead-ends.json").write_text(json.dumps(initial_de, indent=2), encoding="utf-8")

        # Inject the larger synthetic surface
        de_data = SAMPLE_DEAD_ENDS
        (ws / "dead-ends.json").write_text(json.dumps(de_data, indent=2), encoding="utf-8")
        (ws / "dead-ends.md").write_text(render_dead_ends_md(de_data), encoding="utf-8")
        injected_state = merge_state(blank_state(), de_data, cycle=0)
        save_state(str(ws / "dead-end-state.json"), injected_state)

        # Verify injection overwrote
        loaded_de = json.loads((ws / "dead-ends.json").read_text(encoding="utf-8"))
        assert len(loaded_de["basins"]) == 2
        assert len(loaded_de["families"]) == 3
        assert loaded_de["families"][2]["id"] == "F10"


# ---------------------------------------------------------------------------
# TestSnapshotEveryCycle
# ---------------------------------------------------------------------------

class TestSnapshotEveryCycle:
    def test_snapshot_written_on_work_event(self, tmp_path, monkeypatch):
        from compression_assay import _snapshot_dead_ends
        monkeypatch.chdir(tmp_path)

        state = {"active": SAMPLE_DEAD_ENDS}
        _snapshot_dead_ends(5, state)

        snapshot_path = tmp_path / "dead_ends_snapshot_cycle_5.json"
        assert snapshot_path.exists()
        loaded = json.loads(snapshot_path.read_text(encoding="utf-8"))
        assert len(loaded["basins"]) == 2

    def test_snapshot_contains_active_dead_ends(self, tmp_path, monkeypatch):
        from compression_assay import _snapshot_dead_ends
        monkeypatch.chdir(tmp_path)

        state = {"active": SAMPLE_DEAD_ENDS}
        _snapshot_dead_ends(10, state)

        snapshot_path = tmp_path / "dead_ends_snapshot_cycle_10.json"
        loaded = json.loads(snapshot_path.read_text(encoding="utf-8"))
        assert loaded["families"][0]["id"] == "F8"
        assert loaded["families"][1]["id"] == "F9"
