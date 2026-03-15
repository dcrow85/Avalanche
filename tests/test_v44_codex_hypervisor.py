"""Focused tests for V4.4.1 Codex hypervisor constraints."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys


def load_module():
    os.environ.pop("AVALANCHE_ACTIVE", None)
    sys.modules.pop("hypervisor_v44_codex", None)
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


def test_setup_workspace_creates_report_logs(tmp_path, monkeypatch):
    hv = load_module()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(hv, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(hv, "run_command", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(hv, "has_git_head", lambda: True)

    hv.setup_workspace()

    assert (tmp_path / hv.VALIDATION_LOG_FILE).exists()
    assert (tmp_path / hv.INVOCATION_LOG_FILE).exists()


def test_invoke_codex_logs_nonzero_exit(monkeypatch, tmp_path):
    hv = load_module()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(hv, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(hv, "build_codex_command", lambda max_turns: ["codex", "exec"])
    captured: list[dict[str, object]] = []
    monkeypatch.setattr(hv, "append_invocation_event", captured.append)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 7, stdout="partial", stderr="bad")

    monkeypatch.setattr(hv.subprocess, "run", fake_run)
    hv.invoke_codex("test prompt", max_turns=4, label="GRIND", cycle=2, phase="GRIND")

    assert captured
    event = captured[-1]
    assert event["outcome"] == "nonzero_exit"
    assert event["returncode"] == 7
    assert event["label"] == "GRIND"
    assert event["cycle"] == 2
    assert event["phase"] == "GRIND"
    assert event["stdout"] == "partial"
    assert event["stderr"] == "bad"


def test_invoke_codex_logs_timeout(monkeypatch, tmp_path):
    hv = load_module()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(hv, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(hv, "build_codex_command", lambda max_turns: ["codex", "exec"])
    captured: list[dict[str, object]] = []
    monkeypatch.setattr(hv, "append_invocation_event", captured.append)

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(hv.subprocess, "run", fake_run)
    hv.invoke_codex("test prompt", max_turns=3, timeout=12, label="FAIL_SYNC", cycle=5, phase="FAIL_SYNC")

    assert captured
    event = captured[-1]
    assert event["outcome"] == "timeout"
    assert event["timeout_seconds"] == 12
    assert event["label"] == "FAIL_SYNC"
    assert event["cycle"] == 5
    assert event["phase"] == "FAIL_SYNC"


def test_enforce_workspace_valid_returns_and_logs_exact_error(monkeypatch):
    hv = load_module()
    events: list[dict[str, object]] = []
    repairs: list[tuple[str, int, str]] = []
    monkeypatch.setattr(hv, "append_validation_event", lambda **payload: events.append(payload))
    monkeypatch.setattr(
        hv,
        "validate_workspace_output_for_phase",
        lambda *args, **kwargs: "schema mismatch: missing family falsifier",
    )
    monkeypatch.setattr(
        hv,
        "invoke_codex",
        lambda prompt, max_turns=10, timeout=None, label="CODEX_CALL", cycle=None, phase=None: repairs.append(
            (prompt, max_turns, label)
        ),
    )
    monkeypatch.setattr(hv, "cleanup_workspace_artifacts", lambda: None)

    valid, error = hv.enforce_workspace_valid({"active": hv.blank_dead_ends()})

    assert not valid
    assert error == "schema mismatch: missing family falsifier"
    assert len(repairs) == hv.SYNC_MAX_TURNS
    assert all(label == "LINTER_REPAIR" for _, _, label in repairs)
    assert events[0]["attempt"] == 1
    assert events[-1]["attempt"] == hv.SYNC_MAX_TURNS + 1
    assert events[-1]["error"] == "schema mismatch: missing family falsifier"
