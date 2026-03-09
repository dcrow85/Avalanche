"""Regression tests for run_git() / run_test()."""
from unittest.mock import patch, call
import subprocess
import avalanche


@patch("avalanche.subprocess.run")
def test_run_git_returns_completed_process(mock_run):
    """run_git returns a CompletedProcess."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=["git", "status"], returncode=0, stdout="", stderr=""
    )
    result = avalanche.run_git("status")
    assert isinstance(result, subprocess.CompletedProcess)


@patch("avalanche.subprocess.run")
def test_run_git_passes_args_as_list(mock_run):
    """run_git passes arguments as a list starting with 'git'."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=["git", "add", "."], returncode=0, stdout="", stderr=""
    )
    avalanche.run_git("add", ".")
    args, kwargs = mock_run.call_args
    cmd = args[0]
    assert isinstance(cmd, list)
    assert cmd == ["git", "add", "."]


@patch("avalanche.subprocess.run")
def test_run_git_uses_capture_output(mock_run):
    """run_git passes capture_output=True."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=["git", "status"], returncode=0, stdout="", stderr=""
    )
    avalanche.run_git("status")
    _, kwargs = mock_run.call_args
    assert kwargs.get("capture_output") is True


@patch("avalanche.subprocess.run")
def test_run_git_uses_utf8(mock_run):
    """run_git passes encoding='utf-8'."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=["git", "status"], returncode=0, stdout="", stderr=""
    )
    avalanche.run_git("status")
    _, kwargs = mock_run.call_args
    assert kwargs.get("encoding") == "utf-8"


@patch("avalanche.subprocess.run")
def test_run_git_no_shell(mock_run):
    """run_git does NOT use shell=True."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=["git", "status"], returncode=0, stdout="", stderr=""
    )
    avalanche.run_git("status")
    _, kwargs = mock_run.call_args
    assert kwargs.get("shell") is not True


@patch("avalanche.subprocess.run")
def test_run_test_returns_completed_process(mock_run):
    """run_test returns a CompletedProcess."""
    mock_run.return_value = subprocess.CompletedProcess(
        args="pytest -v", returncode=0, stdout="", stderr=""
    )
    result = avalanche.run_test("pytest -v")
    assert isinstance(result, subprocess.CompletedProcess)


@patch("avalanche.subprocess.run")
def test_run_test_uses_shell(mock_run):
    """run_test uses shell=True."""
    mock_run.return_value = subprocess.CompletedProcess(
        args="pytest -v", returncode=0, stdout="", stderr=""
    )
    avalanche.run_test("pytest -v")
    _, kwargs = mock_run.call_args
    assert kwargs.get("shell") is True


@patch("avalanche.subprocess.run")
def test_run_test_passes_string(mock_run):
    """run_test passes the command as a string (not a list)."""
    mock_run.return_value = subprocess.CompletedProcess(
        args="pytest -v", returncode=0, stdout="", stderr=""
    )
    avalanche.run_test("pytest -v")
    args, _ = mock_run.call_args
    cmd = args[0]
    assert isinstance(cmd, str)
