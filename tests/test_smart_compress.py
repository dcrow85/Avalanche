"""Feature tests for smart_compress() (MUST FAIL on seed)."""
import avalanche


def test_function_exists():
    """smart_compress should exist and be callable."""
    assert hasattr(avalanche, "smart_compress")
    assert callable(avalanche.smart_compress)


def test_under_limit_unchanged():
    """Content under the word limit is returned unchanged."""
    content = (
        "**Goal:** Build the app.\n\n"
        "**Architecture:** Single file.\n\n"
        "**Graveyard:**\n"
        "- Tried classes, too complex.\n"
    )
    result = avalanche.smart_compress(content, 50)
    assert result == content


def test_over_limit_trims_oldest_graveyard():
    """When over limit, removes oldest (first) graveyard entry, keeps newest."""
    old_entry = "- " + " ".join(["alpha"] * 20)
    new_entry = "- " + " ".join(["omega"] * 5)
    content = (
        "**Goal:** Build it.\n\n"
        "**Architecture:** One file.\n\n"
        "**Graveyard:**\n"
        f"{old_entry}\n"
        f"{new_entry}\n"
    )
    # 34 words total, limit 20
    result = avalanche.smart_compress(content, 20)
    assert "alpha" not in result
    assert "omega" in result
    assert "**Goal:**" in result
    assert "**Architecture:**" in result


def test_no_sections_fallback():
    """Content with no recognizable sections falls back to word truncation."""
    words = ["plain"] * 40
    content = " ".join(words)
    result = avalanche.smart_compress(content, 20)
    assert len(result.split()) == 20
    assert result == " ".join(["plain"] * 20)


def test_exact_limit_unchanged():
    """Content at exactly the word limit is returned unchanged."""
    content = (
        "**Goal:** Build the app.\n\n"
        "**Architecture:** Single file design.\n\n"
        "**Graveyard:**\n"
        "- Tried one thing.\n"
    )
    word_count = len(content.split())
    result = avalanche.smart_compress(content, word_count)
    assert result == content


# --- Edge cases below: designed to force multi-cycle convergence ---


def test_section_header_in_graveyard_body():
    """Section header text in graveyard must not create a false section boundary."""
    padding = " ".join(["verbose"] * 15)
    content = (
        "**Goal:** Build it.\n\n"
        "**Architecture:** Modular design.\n\n"
        "**Graveyard:**\n"
        f"- Changed **Architecture:** to monolith. {padding} Failed.\n"
    )
    # 28 words total, limit 15. Graveyard entry must be removed.
    result = avalanche.smart_compress(content, 15)
    # Real Architecture content must survive, not the text inside graveyard
    assert "Modular" in result
    assert "**Goal:**" in result


def test_multi_line_graveyard_entry():
    """Multi-line graveyard entry is removed as a complete unit."""
    content = (
        "**Goal:** Build it.\n\n"
        "**Architecture:** One file.\n\n"
        "**Graveyard:**\n"
        "- First attempt failed.\n"
        "  Root cause was bad parsing.\n"
        "  Also had edge case bugs.\n"
        "- Second attempt worked partially.\n"
    )
    # 26 words total, limit 20. Remove oldest (multi-line) entry.
    result = avalanche.smart_compress(content, 20)
    assert "Root cause" not in result
    assert "edge case" not in result
    assert "Second attempt" in result


def test_graveyard_gone_truncates_architecture():
    """After graveyard is fully removed, architecture body is truncated."""
    arch_body = " ".join(["component"] * 25)
    content = (
        "**Goal:** Build it.\n\n"
        f"**Architecture:** {arch_body}\n\n"
        "**Graveyard:**\n"
    )
    # 30 words, limit 15. No graveyard entries to remove. Truncate arch.
    result = avalanche.smart_compress(content, 15)
    assert "**Goal:** Build it." in result
    assert "**Architecture:**" in result
    assert len(result.split()) <= 15


def test_everything_sacrificed_truncates_goal():
    """When goal alone exceeds limit, goal body is truncated as last resort."""
    goal_body = " ".join(["objective"] * 30)
    content = (
        f"**Goal:** {goal_body}\n\n"
        "**Architecture:** Design.\n\n"
        "**Graveyard:**\n"
        "- Entry one.\n"
    )
    # 37 words, limit 10. Must sacrifice graveyard, arch, then truncate goal.
    result = avalanche.smart_compress(content, 10)
    assert "**Goal:**" in result
    assert len(result.split()) <= 10


def test_enforce_compression_is_section_aware(workspace):
    """enforce_compression should use section-aware compression."""
    grave_words = " ".join(["debris"] * 195)
    content = (
        "**Goal:** Build it.\n\n"
        "**Architecture:** One file.\n\n"
        "**Graveyard:**\n"
        f"- {grave_words}\n"
    )
    # 203 words — over WORD_LIMIT (200)
    (workspace / avalanche.STATE_FILE).write_text(content, encoding="utf-8")
    avalanche.enforce_compression()
    result = (workspace / avalanche.STATE_FILE).read_text(encoding="utf-8")
    # Smart: graveyard entry fully removed, ~7 words remain. debris count = 0.
    # Dumb: first 200 words kept, debris count ~192.
    assert result.count("debris") < 10
    assert "**Goal:**" in result
    assert "[WARNING:" in result
