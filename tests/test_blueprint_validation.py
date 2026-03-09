"""Feature tests for validate_blueprint() (MUST FAIL on seed)."""
import avalanche


def test_function_exists():
    """validate_blueprint should exist and be callable."""
    assert hasattr(avalanche, "validate_blueprint")
    assert callable(avalanche.validate_blueprint)


def test_valid_blueprint_returns_empty():
    """Valid blueprint with all 3 sections returns empty list."""
    content = (
        "# THE BLUEPRINT\n\n"
        "**Goal:** Build it.\n\n"
        "**Architecture:** One file.\n\n"
        "**Graveyard:**\n- None.\n"
    )
    result = avalanche.validate_blueprint(content)
    assert result == []


def test_missing_goal():
    """Missing Goal section returns list containing 'Goal'."""
    content = "**Architecture:** A\n**Graveyard:**\n- None.\n"
    result = avalanche.validate_blueprint(content)
    assert "Goal" in result


def test_missing_architecture():
    """Missing Architecture section returns list containing 'Architecture'."""
    content = "**Goal:** A\n**Graveyard:**\n- None.\n"
    result = avalanche.validate_blueprint(content)
    assert "Architecture" in result


def test_missing_graveyard():
    """Missing Graveyard section returns list containing 'Graveyard'."""
    content = "**Goal:** A\n**Architecture:** B\n"
    result = avalanche.validate_blueprint(content)
    assert "Graveyard" in result


def test_missing_all_three():
    """Missing all sections returns 3-element list with all section names."""
    content = "This blueprint has no sections at all."
    result = avalanche.validate_blueprint(content)
    assert set(result) == {"Goal", "Architecture", "Graveyard"}
    assert len(result) == 3


def test_return_type_is_list():
    """Return type is always a list."""
    content = "**Goal:** A\n**Architecture:** B\n**Graveyard:**\n"
    result = avalanche.validate_blueprint(content)
    assert isinstance(result, list)
