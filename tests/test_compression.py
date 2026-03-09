"""Regression tests for enforce_compression()."""
import avalanche


def test_truncates_over_200_words(workspace):
    """Files with >200 words are truncated to exactly 200 + warning."""
    words = ["hello"] * 210
    (workspace / avalanche.STATE_FILE).write_text(" ".join(words), encoding="utf-8")
    avalanche.enforce_compression()
    result = (workspace / avalanche.STATE_FILE).read_text(encoding="utf-8")
    # The truncated content should have exactly 200 real words before the warning
    lines = result.split("\n")
    body = lines[0]
    assert len(body.split()) == 200
    assert "[WARNING:" in result


def test_leaves_short_file_untouched(workspace):
    """Files with <=200 words are left unchanged."""
    original = "short content here"
    (workspace / avalanche.STATE_FILE).write_text(original, encoding="utf-8")
    avalanche.enforce_compression()
    result = (workspace / avalanche.STATE_FILE).read_text(encoding="utf-8")
    assert result == original


def test_noop_when_file_missing(workspace):
    """No error when STATE_FILE does not exist."""
    # Should not raise
    avalanche.enforce_compression()


def test_exact_boundary_not_truncated(workspace):
    """Exactly 200 words should NOT be truncated."""
    words = ["boundary"] * 200
    original = " ".join(words)
    (workspace / avalanche.STATE_FILE).write_text(original, encoding="utf-8")
    avalanche.enforce_compression()
    result = (workspace / avalanche.STATE_FILE).read_text(encoding="utf-8")
    assert result == original
    assert "[WARNING:" not in result


def test_201_words_triggers_truncation(workspace):
    """201 words should trigger truncation."""
    words = ["extra"] * 201
    (workspace / avalanche.STATE_FILE).write_text(" ".join(words), encoding="utf-8")
    avalanche.enforce_compression()
    result = (workspace / avalanche.STATE_FILE).read_text(encoding="utf-8")
    assert "[WARNING:" in result
    body = result.split("\n")[0]
    assert len(body.split()) == 200
