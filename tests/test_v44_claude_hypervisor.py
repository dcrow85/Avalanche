"""Focused tests for V4.4.2 Claude hypervisor startup behavior."""

from __future__ import annotations

import importlib
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def load_module():
    os.environ.pop("AVALANCHE_ACTIVE", None)
    return importlib.import_module("hypervisor_v44_claude")


def test_default_claude_cmd_uses_cmd_shim_on_windows():
    hv = load_module()
    if hv.os.name != "nt":
        return
    assert hv.DEFAULT_CLAUDE_CMD.lower().endswith("claude.cmd")


def test_build_claude_env_sets_git_bash_on_windows():
    hv = load_module()
    env = hv.build_claude_env()
    if hv.os.name != "nt":
        assert "CLAUDE_CODE_GIT_BASH_PATH" not in env or env["CLAUDE_CODE_GIT_BASH_PATH"]
        return
    assert env["CLAUDE_CODE_GIT_BASH_PATH"].lower().endswith("bash.exe")


def test_build_claude_command_keeps_session_persistence_enabled():
    hv = load_module()
    command = hv.build_claude_command()
    assert "--no-session-persistence" not in command


def test_build_claude_command_uses_json_output_format():
    hv = load_module()
    command = hv.build_claude_command()
    assert "--output-format" in command
    idx = command.index("--output-format")
    assert command[idx + 1] == "json"


def test_fail_sync_timeout_defaults_are_model_aware():
    hv = load_module()
    with patch.dict(hv.os.environ, {}, clear=False):
        hv.CLAUDE_MODEL = "sonnet"
        assert hv.current_fail_sync_timeout() == 900
        hv.CLAUDE_MODEL = "opus"
        assert hv.current_fail_sync_timeout() == 1200


def test_grind_timeout_defaults_are_model_aware():
    hv = load_module()
    with patch.dict(hv.os.environ, {}, clear=False):
        hv.CLAUDE_MODEL = "sonnet"
        assert hv.current_grind_timeout() == 600
        hv.CLAUDE_MODEL = "opus"
        assert hv.current_grind_timeout() == 900


def test_fail_sync_timeout_prefers_env_override():
    hv = load_module()
    with patch.dict(hv.os.environ, {"AVALANCHE_CLAUDE_FAIL_SYNC_TIMEOUT": "777"}, clear=False):
        hv.CLAUDE_MODEL = "opus"
        assert hv.current_fail_sync_timeout() == 777


def test_invoke_claude_returns_nonzero_exit_on_cli_failure():
    hv = load_module()
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ("", "OAuth token has expired.")
    mock_proc.returncode = 1
    with patch.object(hv.subprocess, "Popen", return_value=mock_proc):
        with patch.object(hv.os.path, "exists", return_value=False):
            with patch.object(hv, "_save_trace", return_value="traces/001_GRIND.json"):
                with patch.object(hv, "append_invocation_event") as append_invocation_event:
                    outcome = hv.invoke_claude("test prompt", label="TEST", phase="GRIND")
    assert outcome == "nonzero_exit"
    assert append_invocation_event.call_count == 1
    payload = append_invocation_event.call_args.args[0]
    assert payload["outcome"] == "nonzero_exit"
    assert payload["stderr"] == "OAuth token has expired."
    assert payload["trace_file"] == "traces/001_GRIND.json"


def test_enforce_workspace_valid_returns_and_logs_exact_error():
    hv = load_module()
    with patch.object(hv, "SYNC_MAX_TURNS", 2):
        with patch.object(hv, "validate_workspace_output_for_phase", side_effect=["bad family arrays", "bad family arrays", "bad family arrays"]):
            with patch.object(hv, "invoke_claude", return_value="ok"):
                with patch.object(hv, "cleanup_workspace_artifacts"):
                    with patch.object(hv, "current_dead_end_summary", return_value="state summary"):
                        with patch.object(hv, "append_validation_event") as append_validation_event:
                            ok, error = hv.enforce_workspace_valid({}, cycle=2, phase="FAIL_SYNC")

    assert not ok
    assert error == "bad family arrays"
    assert append_validation_event.call_count == 3
    first_call = append_validation_event.call_args_list[0].kwargs
    last_call = append_validation_event.call_args_list[-1].kwargs
    assert first_call["phase"] == "FAIL_SYNC"
    assert first_call["attempt"] == 1
    assert last_call["error"] == "bad family arrays"


def test_invoke_claude_returns_timeout_and_captures_partial_output():
    hv = load_module()
    mock_proc = MagicMock()
    mock_proc.communicate.side_effect = [
        hv.subprocess.TimeoutExpired(cmd="claude", timeout=hv.INVOKE_TIMEOUT),
        ("partial stdout here", "partial stderr here"),
    ]
    mock_proc.returncode = -9
    mock_proc.pid = 12345
    with patch.object(hv.subprocess, "Popen", return_value=mock_proc):
        with patch.object(hv.os.path, "exists", return_value=False):
            with patch.object(hv, "_kill_process_tree"):
                with patch.object(hv, "_save_trace", return_value="traces/001_FAIL_SYNC.json") as save_trace:
                    with patch.object(hv, "append_invocation_event") as append_invocation_event:
                        outcome = hv.invoke_claude("test prompt", label="TEST", phase="FAIL_SYNC")
    assert outcome == "timeout"
    assert append_invocation_event.call_count == 1
    payload = append_invocation_event.call_args.args[0]
    assert payload["outcome"] == "timeout"
    assert payload["trace_file"] == "traces/001_FAIL_SYNC.json"
    assert payload["stderr"] == "partial stderr here"
    # Verify _save_trace was called with the partial stdout
    assert save_trace.call_args.args[3] == "partial stdout here"


def test_invoke_claude_returns_cli_not_found():
    hv = load_module()
    with patch.object(hv.subprocess, "Popen", side_effect=FileNotFoundError):
        with patch.object(hv.os.path, "exists", return_value=False):
            with patch.object(hv, "_save_trace", return_value=""):
                with patch.object(hv, "append_invocation_event") as append_invocation_event:
                    outcome = hv.invoke_claude("test prompt", label="TEST", phase="GRIND")
    assert outcome == "cli_not_found"
    assert append_invocation_event.call_count == 1
    assert append_invocation_event.call_args.args[0]["outcome"] == "cli_not_found"


def test_enforce_workspace_valid_breaks_on_linter_timeout():
    hv = load_module()
    with patch.object(hv, "SYNC_MAX_TURNS", 3):
        with patch.object(hv, "validate_workspace_output_for_phase", return_value="bad state"):
            with patch.object(hv, "invoke_claude", return_value="timeout"):
                with patch.object(hv, "cleanup_workspace_artifacts"):
                    with patch.object(hv, "current_dead_end_summary", return_value="state summary"):
                        with patch.object(hv, "append_validation_event") as append_validation_event:
                            ok, error = hv.enforce_workspace_valid({}, cycle=2, phase="FAIL_SYNC")

    assert not ok
    # Should have attempted validation once, invoked linter once (timeout), then broken out
    # Final validation check also happens, so 2 validation events total
    assert append_validation_event.call_count == 2


def test_format_fail_prompt_is_memory_only():
    hv = load_module()
    with patch.object(hv, "current_dead_end_summary", return_value="state summary"):
        prompt = hv.format_fail_prompt("oracle fail", {})
    assert f"Do not write `{hv.SOLVER_FILE}`" in prompt
    assert "contradiction-absorption pass only" in prompt
    assert "record it as a local" in prompt


def test_enforce_workspace_valid_memory_only_linter_does_not_request_solver():
    hv = load_module()
    with patch.object(hv, "SYNC_MAX_TURNS", 2):
        with patch.object(hv, "validate_workspace_output_for_phase", side_effect=["bad family arrays", None]):
            with patch.object(hv, "cleanup_workspace_artifacts"):
                with patch.object(hv, "current_dead_end_summary", return_value="state summary"):
                    with patch.object(hv, "append_validation_event"):
                        with patch.object(hv, "_save_dead_ends"):
                            with patch.object(hv, "invoke_claude", return_value="ok") as invoke_claude:
                                ok, error = hv.enforce_workspace_valid({}, require_solver=False, cycle=2, phase="FAIL_SYNC")

    assert ok
    assert error is None
    prompt = invoke_claude.call_args.args[0]
    assert f"Fix `{hv.DEAD_ENDS_JSON_FILE}` and `{hv.OPINIONS_FILE}` only." in prompt
    assert f"Do not create `{hv.SOLVER_FILE}`" in prompt
    assert invoke_claude.call_args.kwargs["timeout"] == hv.current_linter_timeout()


def test_solver_compression_ratio_detects_repetitive_code():
    from v43_metrics import solver_compression_ratio
    # Highly repetitive code compresses well (higher ratio is more compressed but zlib ratio < 1)
    epicycle = "if x == 1:\n    return 1\n" * 50
    dense = "return (a * b + c) % d ^ (e << f) // (g - h) | (i & j)"
    ratio_epic = solver_compression_ratio(epicycle)
    ratio_dense = solver_compression_ratio(dense)
    assert ratio_epic > 0
    assert ratio_dense > 0
    # Repetitive code should have LOWER compression ratio (compresses better)
    assert ratio_epic < ratio_dense


def test_solver_ast_decomposition_classifies_node_types():
    from v43_metrics import solver_ast_decomposition
    code = "def f(x):\n    if x > 0:\n        return x % 2 + x // 3\n    return x - 1\n"
    d = solver_ast_decomposition(code)
    assert d["ast_conditional"] >= 1  # the if statement
    assert d["ast_arithmetic"] >= 1   # Mod, FloorDiv, BinOp
    assert d["ast_total_nodes"] > 0
    assert d["ast_loop"] == 0         # no loops


def test_solver_ast_decomposition_handles_syntax_error():
    from v43_metrics import solver_ast_decomposition
    d = solver_ast_decomposition("def f(:\n    broken")
    assert d == {"ast_conditional": 0, "ast_arithmetic": 0, "ast_loop": 0, "ast_total_nodes": 0}


def test_traces_dir_in_preserved_top_level():
    hv = load_module()
    assert hv.TRACES_DIR in hv.PRESERVED_TOP_LEVEL
