"""Regression tests for enforce_amnesia()."""
import os
import avalanche


def test_removes_claude_dir(workspace):
    """Removes .claude/ directory and all nested contents."""
    claude_dir = workspace / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text("{}", encoding="utf-8")
    nested = claude_dir / "sub"
    nested.mkdir()
    (nested / "deep.txt").write_text("deep", encoding="utf-8")

    avalanche.enforce_amnesia()
    assert not claude_dir.exists()


def test_noop_when_absent(workspace):
    """No error when .claude/ does not exist."""
    # Should not raise
    avalanche.enforce_amnesia()


def test_does_not_remove_other_dirs(workspace):
    """Does not remove .git/ or other directories."""
    git_dir = workspace / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]", encoding="utf-8")

    other_dir = workspace / "src"
    other_dir.mkdir()
    (other_dir / "main.py").write_text("print(1)", encoding="utf-8")

    avalanche.enforce_amnesia()

    assert git_dir.exists()
    assert other_dir.exists()
