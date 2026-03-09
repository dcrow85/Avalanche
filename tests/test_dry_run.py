"""Feature tests for --dry-run flag (MUST FAIL on seed)."""
import importlib
from unittest.mock import patch
import avalanche


def test_module_exposes_dry_run():
    """Module should have a DRY_RUN attribute defined at module level."""
    # Re-import to check the module's own namespace (not dynamically set attrs)
    mod = importlib.reload(avalanche)
    assert "DRY_RUN" in vars(mod), "DRY_RUN must be defined at module level"


def test_invoke_claude_skips_cli_when_dry_run(workspace, blueprint_file):
    """invoke_claude should not call claude CLI when DRY_RUN is True."""
    # Guard: feature must exist first
    assert "DRY_RUN" in vars(avalanche), "DRY_RUN not defined at module level"
    avalanche.DRY_RUN = True
    try:
        with patch("avalanche.subprocess.run") as mock_run:
            avalanche.invoke_claude("test prompt")
            for c in mock_run.call_args_list:
                args = c[0][0]
                if isinstance(args, list) and "claude" in args:
                    raise AssertionError("claude CLI was invoked during dry run")
    finally:
        avalanche.DRY_RUN = False


def test_dry_run_still_runs_compression(workspace, overstuffed_blueprint):
    """enforce_compression should still run in dry-run mode."""
    assert "DRY_RUN" in vars(avalanche), "DRY_RUN not defined at module level"
    avalanche.DRY_RUN = True
    try:
        with patch("avalanche.subprocess.run"):
            avalanche.invoke_claude("test prompt")
        content = (workspace / avalanche.STATE_FILE).read_text(encoding="utf-8")
        assert "[WARNING:" in content
    finally:
        avalanche.DRY_RUN = False


def test_dry_run_still_runs_amnesia(workspace, blueprint_file):
    """enforce_amnesia should still run in dry-run mode."""
    assert "DRY_RUN" in vars(avalanche), "DRY_RUN not defined at module level"
    claude_dir = workspace / ".claude"
    claude_dir.mkdir()
    (claude_dir / "data.json").write_text("{}", encoding="utf-8")

    avalanche.DRY_RUN = True
    try:
        with patch("avalanche.subprocess.run"):
            avalanche.invoke_claude("test prompt")
        assert not claude_dir.exists()
    finally:
        avalanche.DRY_RUN = False


def test_main_accepts_dry_run_arg(monkeypatch):
    """main() should accept --dry-run CLI arg and set DRY_RUN=True."""
    assert "DRY_RUN" in vars(avalanche), "DRY_RUN not defined at module level"
    monkeypatch.setattr("sys.argv", ["avalanche.py", "--dry-run", "pytest -v"])
    with patch("avalanche.setup"):
        with patch("avalanche.run_test") as mock_test:
            mock_test.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            with patch("avalanche.invoke_claude"):
                with patch("builtins.input", return_value=""):
                    try:
                        avalanche.main()
                    except SystemExit:
                        pass
    assert avalanche.DRY_RUN is True, "--dry-run should set DRY_RUN to True"
