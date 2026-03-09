"""Feature tests for distinct exit codes (MUST FAIL on seed)."""
from unittest.mock import patch
import subprocess
import sys
import pytest
import avalanche


def test_check_prerequisites_exits_code_2():
    """check_prerequisites() should exit with code 2 when a tool is missing."""
    mock_result = subprocess.CompletedProcess(
        args=["where", "git"], returncode=1, stdout="", stderr=""
    )
    with patch("avalanche.subprocess.run", return_value=mock_result):
        with pytest.raises(SystemExit) as exc_info:
            avalanche.check_prerequisites()
        assert exc_info.value.code == 2


def test_cycle_cap_exits_code_1(monkeypatch):
    """Cycle cap exhaustion should exit with code 1."""
    monkeypatch.setattr("sys.argv", ["avalanche.py", "pytest -v"])
    monkeypatch.setattr(avalanche, "MAX_CYCLES", 1)

    with patch("avalanche.check_prerequisites"):
        with patch("os.path.exists", side_effect=lambda p: p != ".git" if isinstance(p, str) and p == ".git" else True):
            with patch("avalanche.invoke_claude"):
                with patch("avalanche.run_test") as mock_test:
                    mock_test.return_value = subprocess.CompletedProcess(
                        args="pytest", returncode=1, stdout="FAIL", stderr=""
                    )
                    with patch("avalanche.run_git"):
                        with patch("avalanche.read_file", return_value="blueprint"):
                            with patch("avalanche.write_file"):
                                with pytest.raises(SystemExit) as exc_info:
                                    avalanche.main()
                                assert exc_info.value.code == 1


def test_module_exposes_exit_constants():
    """Module should expose EXIT_SUCCESS constant or EXIT_CODES mapping."""
    has_exit_success = hasattr(avalanche, "EXIT_SUCCESS")
    has_exit_codes = hasattr(avalanche, "EXIT_CODES")
    assert has_exit_success or has_exit_codes, (
        "Module must expose EXIT_SUCCESS constant or EXIT_CODES mapping"
    )
