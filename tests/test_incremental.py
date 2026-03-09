"""Feature tests for incremental ratchet (MUST FAIL on seed).

Three interconnected features:
  Level 1: parse_test_results — pytest output → structured data
  Level 2: format_grind_prompt — dynamic prompts with failing test names
  Level 3: State persistence + regression detection
"""
import avalanche


# --- Pytest -v output fixtures ---

SIMPLE_OUTPUT = """\
============================= test session starts =============================
platform win32 -- Python 3.14.2, pytest-9.0.2
collected 3 items

tests/test_foo.py::test_one PASSED                                       [ 33%]
tests/test_foo.py::test_two FAILED                                       [ 66%]
tests/test_foo.py::test_three PASSED                                     [100%]

=========================== short test summary info ===========================
FAILED tests/test_foo.py::test_two - AssertionError
====================== 2 passed, 1 failed in 0.15s ===========================
"""

PARAMETRIZED_OUTPUT = """\
============================= test session starts =============================
collected 4 items

tests/test_math.py::test_add[1-2] PASSED                                [ 25%]
tests/test_math.py::test_add[3-4] FAILED                                [ 50%]
tests/test_math.py::test_sub[5-3] PASSED                                [ 75%]
tests/test_math.py::test_sub[0-0] PASSED                                [100%]

====================== 3 passed, 1 failed in 0.10s ===========================
"""

TRICKY_OUTPUT = """\
============================= test session starts =============================
collected 4 items

tests/test_core.py::test_basic PASSED                                    [ 25%]
tests/test_core.py::test_tricky FAILED                                   [ 50%]
tests/test_core.py::test_skip SKIPPED (not relevant)                     [ 75%]
tests/test_core.py::test_edge PASSED                                     [100%]

================================== FAILURES ===================================
_________________________________ test_tricky _________________________________

    def test_tricky():
>       assert status == "PASSED"
E       AssertionError: assert 'FAILED' == 'PASSED'

tests/test_core.py:10: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_core.py::test_tricky - AssertionError
================== 2 passed, 1 failed, 1 skipped in 0.20s ====================
"""


# ===== Level 1: parse_test_results =====

def test_parse_test_results_exists():
    """parse_test_results should exist and be callable."""
    assert hasattr(avalanche, "parse_test_results")
    assert callable(avalanche.parse_test_results)


def test_parse_basic_output():
    """Parses simple PASSED/FAILED lines from pytest -v output."""
    results = avalanche.parse_test_results(SIMPLE_OUTPUT)
    assert results["tests/test_foo.py::test_one"] is True
    assert results["tests/test_foo.py::test_two"] is False
    assert results["tests/test_foo.py::test_three"] is True
    assert len(results) == 3


def test_parse_parametrized():
    """Handles parametrized test names with bracket suffixes."""
    results = avalanche.parse_test_results(PARAMETRIZED_OUTPUT)
    assert results["tests/test_math.py::test_add[1-2]"] is True
    assert results["tests/test_math.py::test_add[3-4]"] is False
    assert results["tests/test_math.py::test_sub[5-3]"] is True
    assert results["tests/test_math.py::test_sub[0-0]"] is True
    assert len(results) == 4


def test_parse_ignores_failures_section():
    """Does not count PASSED/FAILED in assertion text as test results."""
    results = avalanche.parse_test_results(TRICKY_OUTPUT)
    # The FAILURES section contains: assert status == "PASSED"
    # and: AssertionError: assert 'FAILED' == 'PASSED'
    # These must NOT create phantom test entries.
    assert len(results) == 3  # basic, tricky, edge (skip excluded)
    assert results["tests/test_core.py::test_basic"] is True
    assert results["tests/test_core.py::test_tricky"] is False
    assert results["tests/test_core.py::test_edge"] is True


def test_parse_excludes_skipped():
    """SKIPPED tests are not included in results."""
    results = avalanche.parse_test_results(TRICKY_OUTPUT)
    assert "tests/test_core.py::test_skip" not in results


# ===== Level 2: format_grind_prompt =====

def test_format_grind_prompt_exists():
    """format_grind_prompt should exist and be callable."""
    assert hasattr(avalanche, "format_grind_prompt")
    assert callable(avalanche.format_grind_prompt)


def test_format_grind_prompt_includes_failures():
    """When failing tests provided, their names appear in the prompt."""
    failing = ["tests/test_foo.py::test_one", "tests/test_foo.py::test_two"]
    prompt = avalanche.format_grind_prompt(
        "pytest -v", "blueprint.md", failing_tests=failing
    )
    assert "tests/test_foo.py::test_one" in prompt
    assert "tests/test_foo.py::test_two" in prompt
    assert "pytest -v" in prompt


def test_format_grind_prompt_without_results():
    """Works without test results (backward compatible)."""
    prompt = avalanche.format_grind_prompt("pytest -v", "blueprint.md")
    assert isinstance(prompt, str)
    assert "pytest -v" in prompt
    assert "blueprint.md" in prompt


# ===== Level 3: State persistence & regression detection =====

def test_save_load_roundtrip(workspace):
    """save/load roundtrip and state lives in .avalanche/ directory."""
    data = {
        "tests/test_a.py::test_one": True,
        "tests/test_a.py::test_two": False,
    }
    avalanche.save_test_state(data)
    loaded = avalanche.load_test_state()
    assert loaded == data
    # Must be in .avalanche/, not .claude/ or elsewhere
    assert (workspace / ".avalanche" / "test_state.json").exists()


def test_load_missing_returns_empty(workspace):
    """load_test_state returns empty dict when no state file exists."""
    result = avalanche.load_test_state()
    assert result == {}


def test_detect_regressions_basic():
    """Finds tests that went from passing to failing."""
    prev = {"test_a": True, "test_b": True, "test_c": False}
    curr = {"test_a": True, "test_b": False, "test_c": False}
    regressions = avalanche.detect_regressions(prev, curr)
    assert "test_b" in regressions
    assert "test_a" not in regressions
    assert "test_c" not in regressions


def test_detect_regressions_ignores_new():
    """New tests not in previous state are not regressions."""
    prev = {"test_a": True}
    curr = {"test_a": True, "test_b": False}
    regressions = avalanche.detect_regressions(prev, curr)
    assert regressions == []


def test_has_progress():
    """Detects new passing tests; returns False when nothing changed."""
    prev = {"test_a": True, "test_b": False}
    curr_progress = {"test_a": True, "test_b": True}
    curr_same = {"test_a": True, "test_b": False}
    assert avalanche.has_progress(prev, curr_progress) is True
    assert avalanche.has_progress(prev, curr_same) is False


def test_amnesia_preserves_avalanche_state(workspace):
    """enforce_amnesia must NOT wipe .avalanche/ directory."""
    av_dir = workspace / ".avalanche"
    av_dir.mkdir()
    (av_dir / "test_state.json").write_text('{"a": true}', encoding="utf-8")
    claude_dir = workspace / ".claude"
    claude_dir.mkdir()
    (claude_dir / "data.json").write_text("{}", encoding="utf-8")

    avalanche.enforce_amnesia()

    assert not claude_dir.exists()
    assert av_dir.exists()
    assert (av_dir / "test_state.json").exists()


def test_first_cycle_no_regressions():
    """With empty previous state, no regressions are possible."""
    prev = {}
    curr = {"test_a": True, "test_b": False, "test_c": True}
    regressions = avalanche.detect_regressions(prev, curr)
    assert regressions == []
    assert avalanche.has_progress(prev, curr) is True


def test_parse_to_regression_pipeline(workspace):
    """Full pipeline: parse → save → parse new → detect regressions."""
    # Cycle N: parse and save state
    prev_results = avalanche.parse_test_results(SIMPLE_OUTPUT)
    avalanche.save_test_state(prev_results)

    # Cycle N+1: test_one regresses, test_two now passes
    new_output = SIMPLE_OUTPUT.replace(
        "tests/test_foo.py::test_one PASSED",
        "tests/test_foo.py::test_one FAILED",
    ).replace(
        "tests/test_foo.py::test_two FAILED",
        "tests/test_foo.py::test_two PASSED",
    )
    curr_results = avalanche.parse_test_results(new_output)
    loaded_prev = avalanche.load_test_state()

    regressions = avalanche.detect_regressions(loaded_prev, curr_results)
    assert "tests/test_foo.py::test_one" in regressions

    assert avalanche.has_progress(loaded_prev, curr_results) is True
