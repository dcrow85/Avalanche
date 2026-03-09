import sys
import os
import pytest

# Make avalanche importable from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Chdir to a fresh temp directory for isolation."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def blueprint_file(workspace):
    """Creates a valid blueprint.md with Goal/Architecture/Graveyard."""
    content = (
        "# THE BLUEPRINT\n\n"
        "**Goal:** Build the thing.\n\n"
        "**Architecture:** One file.\n\n"
        "**Graveyard:**\n"
        "- None yet.\n"
    )
    path = workspace / "blueprint.md"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def overstuffed_blueprint(workspace):
    """Creates a 250-word blueprint.md that exceeds the word limit."""
    words = ["word"] * 250
    content = " ".join(words)
    path = workspace / "blueprint.md"
    path.write_text(content, encoding="utf-8")
    return path
