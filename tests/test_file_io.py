"""Regression tests for read_file() / write_file()."""
import pytest
import avalanche


def test_ascii_roundtrip(workspace):
    """Plain ASCII content survives write/read cycle."""
    path = str(workspace / "test.txt")
    avalanche.write_file(path, "hello world")
    assert avalanche.read_file(path) == "hello world"


def test_unicode_roundtrip(workspace):
    """Unicode content (emoji, CJK, accents) survives write/read cycle."""
    content = "Hello \U0001f680 \u4f60\u597d caf\u00e9"
    path = str(workspace / "unicode.txt")
    avalanche.write_file(path, content)
    assert avalanche.read_file(path) == content


def test_multiline_with_blank_lines(workspace):
    """Multiline content with blank lines is preserved exactly."""
    content = "line1\n\nline3\n\n\nline6\n"
    path = str(workspace / "multi.txt")
    avalanche.write_file(path, content)
    assert avalanche.read_file(path) == content


def test_write_overwrites(workspace):
    """write_file overwrites existing content, does not append."""
    path = str(workspace / "overwrite.txt")
    avalanche.write_file(path, "first")
    avalanche.write_file(path, "second")
    assert avalanche.read_file(path) == "second"


def test_read_nonexistent_raises(workspace):
    """Reading a nonexistent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        avalanche.read_file(str(workspace / "nope.txt"))


def test_empty_string_roundtrip(workspace):
    """Empty string survives write/read cycle."""
    path = str(workspace / "empty.txt")
    avalanche.write_file(path, "")
    assert avalanche.read_file(path) == ""
