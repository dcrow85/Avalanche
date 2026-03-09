#!/usr/bin/env python3
"""
The Avalanche Engine — Self-Correcting Agentic Code Loop

Orchestrates Claude Code CLI in a test-driven cycle:
  1. GRIND: Claude edits code to pass the test command
  2. RATCHET: Run tests. Pass = commit. Fail = git reset --hard.
  3. SYNC: Claude rewrites blueprint.md to record what happened.

Usage: python avalanche.py "<test_command>"
Example: python avalanche.py "pytest -v"
"""
import json
import os
import re
import sys
import shutil
import subprocess

# --- AVALANCHE CONFIGURATION ---
STATE_FILE = "blueprint.md"
WORD_LIMIT = 200
MAX_CYCLES = 15
GRIND_MAX_TURNS = 10
SYNC_MAX_TURNS = 5
INVOKE_TIMEOUT = 300  # seconds per Claude invocation
TEST_TIMEOUT = 30     # seconds per test run (kill-switch for infinite loops)
DRY_RUN = False
EXIT_SUCCESS = 0


def print_header(text):
    print(f"\n{'='*50}\n  {text}\n{'='*50}")


def run_git(*args):
    """Executes a git command using list-based subprocess (cross-platform)."""
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0 and result.stderr.strip():
        print(f"  [GIT] {result.stderr.strip()}")
    return result


def run_test(cmd):
    """Executes the user's test command. Shell=True because it's an arbitrary string.
    Enforces TEST_TIMEOUT to prevent infinite loops or exponential algorithms from hanging."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=TEST_TIMEOUT,
        )
        return result
    except subprocess.TimeoutExpired:
        print(f"  [KILL-SWITCH] Test command exceeded {TEST_TIMEOUT}s. Terminated.")
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr=f"TIMEOUT: Test command exceeded {TEST_TIMEOUT}s and was killed.",
        )


def parse_test_results(output):
    """Parses pytest -v output into {test_name: bool}. Stops at FAILURES section.
    Excludes SKIPPED tests."""
    results = {}
    for line in output.split("\n"):
        # Stop parsing at the FAILURES section boundary (a line of "=" containing "FAILURES")
        if re.match(r"^=+\s.*FAILURES.*\s=+$", line.strip()):
            break
        # Match lines like: "path::name PASSED [ N%]" or "path::name FAILED [ N%]"
        m = re.match(r"^(.*?::\S+)\s+(PASSED|FAILED|SKIPPED)\b", line)
        if m:
            test_name = m.group(1).strip()
            status = m.group(2)
            if status == "SKIPPED":
                continue
            results[test_name] = (status == "PASSED")
    return results


def format_grind_prompt(test_command, state_file, failing_tests=None):
    """Generates a GRIND prompt string for Claude Code."""
    prompt = (
        f"You are the combinatorial engine of the Avalanche system.\n"
        f"1. Read `{state_file}` for your objective, current architectural state, "
        f"and memory of past failures.\n"
        f"2. Edit the codebase to achieve the goal and ensure this test command "
        f"will pass: `{test_command}`\n"
        f"3. Do NOT run the tests yourself. I am the environment; I will run "
        f"the tests. Edit the files and exit."
    )
    if failing_tests:
        prompt += "\n\nThe following tests are currently failing:\n"
        for t in failing_tests:
            prompt += f"  - {t}\n"
    return prompt


def save_test_state(results):
    """Persists test results to .avalanche/test_state.json."""
    av_dir = os.path.join(os.getcwd(), ".avalanche")
    os.makedirs(av_dir, exist_ok=True)
    path = os.path.join(av_dir, "test_state.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f)


def load_test_state():
    """Loads test results from .avalanche/test_state.json. Returns {} if missing."""
    path = os.path.join(os.getcwd(), ".avalanche", "test_state.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def detect_regressions(prev, curr):
    """Returns list of tests that went True->False. New tests are not regressions."""
    regressions = []
    for test_name, prev_passed in prev.items():
        if prev_passed and test_name in curr and not curr[test_name]:
            regressions.append(test_name)
    return regressions


def has_progress(prev, curr):
    """Returns True if any test newly passes (True in curr, not True in prev)."""
    for test_name, passed in curr.items():
        if passed and not prev.get(test_name, False):
            return True
    return False


def enforce_amnesia():
    """Wipes Claude Code's local project history to prevent context bleed between cycles."""
    claude_dir = os.path.join(os.getcwd(), ".claude")
    if os.path.exists(claude_dir):
        shutil.rmtree(claude_dir)


def smart_compress(content, limit):
    """Section-aware compression: sacrifice graveyard oldest-first, then
    truncate architecture, then goal. Falls back to dumb word truncation
    if no sections found. Pure function: string in, string out, no warning."""
    if len(content.split()) <= limit:
        return content

    # Detect sections by line-start headers only (not inside graveyard body)
    lines = content.split("\n")

    # Find section boundaries: only lines that start with a section header
    # AND are not continuation lines inside a graveyard entry
    section_starts = {}  # name -> line index
    in_graveyard = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Once we enter the graveyard section, only bullet lines and
        # continuation lines belong to it. A new section header at the
        # start of a line (not indented) exits the graveyard.
        if in_graveyard:
            # A true section header must be at the start of the line (no leading whitespace)
            # and not be a graveyard bullet or continuation
            if not line.startswith(" ") and not line.startswith("\t") and not stripped.startswith("- "):
                for name in ("Goal", "Architecture", "Graveyard"):
                    if stripped.startswith(f"**{name}:") or stripped.startswith(f"**{name}**"):
                        section_starts[name] = i
                        in_graveyard = (name == "Graveyard")
                        break
        else:
            for name in ("Goal", "Architecture", "Graveyard"):
                if stripped.startswith(f"**{name}:") or stripped.startswith(f"**{name}**"):
                    section_starts[name] = i
                    in_graveyard = (name == "Graveyard")
                    break

    # Fallback: no sections detected
    if not section_starts:
        words = content.split()
        return " ".join(words[:limit])

    # Parse graveyard entries as multi-line units
    graveyard_entries = []  # list of (start_line, end_line) exclusive
    if "Graveyard" in section_starts:
        gy_start = section_starts["Graveyard"]
        # Find end of graveyard section (next section or end of file)
        gy_end = len(lines)
        for name, idx in section_starts.items():
            if name != "Graveyard" and idx > gy_start:
                gy_end = min(gy_end, idx)

        # Parse entries: a bullet line starts with "- ", continuation lines
        # are indented or don't start with "- "
        entry_start = None
        for i in range(gy_start + 1, gy_end):
            stripped = lines[i].strip()
            if stripped.startswith("- "):
                if entry_start is not None:
                    graveyard_entries.append((entry_start, i))
                entry_start = i
            elif stripped == "":
                if entry_start is not None:
                    graveyard_entries.append((entry_start, i))
                    entry_start = None
            else:
                # Continuation line — part of current entry
                pass
        if entry_start is not None:
            graveyard_entries.append((entry_start, gy_end))

    # Build working copy of lines, removing graveyard entries oldest-first
    working_lines = list(lines)
    removed_indices = set()

    # Remove oldest graveyard entries first (they appear first in the list)
    for entry_start, entry_end in graveyard_entries:
        if len("\n".join(l for i, l in enumerate(working_lines) if i not in removed_indices).split()) <= limit:
            break
        for i in range(entry_start, entry_end):
            removed_indices.add(i)

    def current_text():
        return "\n".join(l for i, l in enumerate(working_lines) if i not in removed_indices)

    def current_word_count():
        return len(current_text().split())

    if current_word_count() <= limit:
        return current_text()

    # Truncate architecture body
    if "Architecture" in section_starts:
        arch_idx = section_starts["Architecture"]
        if arch_idx not in removed_indices:
            arch_line = working_lines[arch_idx]
            # Find architecture body: everything after "**Architecture:**"
            marker = "**Architecture:**"
            pos = arch_line.find(marker)
            if pos != -1:
                header_part = arch_line[:pos + len(marker)]
                body_words = arch_line[pos + len(marker):].split()
                # Binary search: remove words from the end of architecture body
                while body_words and current_word_count() > limit:
                    body_words.pop()
                    working_lines[arch_idx] = header_part + (" " + " ".join(body_words) if body_words else "")

    if current_word_count() <= limit:
        return current_text()

    # Clear architecture entirely if still over
    if "Architecture" in section_starts:
        arch_idx = section_starts["Architecture"]
        if arch_idx not in removed_indices:
            working_lines[arch_idx] = "**Architecture:**"

    if current_word_count() <= limit:
        return current_text()

    # Truncate goal body as last resort
    if "Goal" in section_starts:
        goal_idx = section_starts["Goal"]
        if goal_idx not in removed_indices:
            goal_line = working_lines[goal_idx]
            marker = "**Goal:**"
            pos = goal_line.find(marker)
            if pos != -1:
                header_part = goal_line[:pos + len(marker)]
                body_words = goal_line[pos + len(marker):].split()
                while body_words and current_word_count() > limit:
                    body_words.pop()
                    working_lines[goal_idx] = header_part + (" " + " ".join(body_words) if body_words else "")

    if current_word_count() <= limit:
        return current_text()

    # Final fallback: dumb truncation
    text = current_text()
    words = text.split()
    return " ".join(words[:limit])


def enforce_compression():
    """Forces the epistemic bottleneck by truncating blueprint.md to WORD_LIMIT."""
    if not os.path.exists(STATE_FILE):
        return
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    words = content.split()
    if len(words) > WORD_LIMIT:
        print(f"  [COMPRESS] STATE OVERFLOW ({len(words)} words). Truncating to {WORD_LIMIT}.")
        compressed = smart_compress(content, WORD_LIMIT)
        truncated = compressed + "\n\n[WARNING: PREVIOUS THOUGHTS TRUNCATED BY ENVIRONMENT]"
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write(truncated)


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def validate_blueprint(content):
    """Returns a list of missing section names from blueprint content."""
    required = ["Goal", "Architecture", "Graveyard"]
    missing = []
    for section in required:
        if f"**{section}:" not in content and f"**{section}**" not in content:
            missing.append(section)
    return missing


def invoke_claude(prompt, max_turns=GRIND_MAX_TURNS):
    """Fires Claude Code in stateless, single-shot mode via stdin."""
    enforce_amnesia()
    enforce_compression()

    if DRY_RUN:
        print("  [DRY RUN] Skipping Claude Code invocation.")
        return

    print("  [NUCLEUS] Waking Claude Code...")
    try:
        subprocess.run(
            f"claude -p --max-turns {max_turns} --dangerously-skip-permissions",
            input=prompt,
            shell=True,
            text=True,
            encoding="utf-8",
            timeout=INVOKE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT] Claude invocation exceeded {INVOKE_TIMEOUT}s. Moving on.")
    except FileNotFoundError:
        print("  [FATAL] 'claude' command not found. Is Claude Code CLI installed?")
        sys.exit(1)


def check_prerequisites():
    """Fail fast if git or claude aren't available."""
    which_cmd = "where" if os.name == "nt" else "which"
    for tool in ["git", "claude"]:
        result = subprocess.run(
            [which_cmd, tool],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            print(f"  [FATAL] '{tool}' not found on PATH. Install it and retry.")
            sys.exit(2)


def setup():
    """Prepares the workspace and Git ratchet."""
    check_prerequisites()

    if not os.path.exists(".git"):
        print_header("INITIALIZING GIT RATCHET")
        run_git("init")
        run_git("add", ".")
        run_git("commit", "-m", "Avalanche: Initial Baseline")

    if not os.path.exists(STATE_FILE):
        write_file(STATE_FILE, (
            "# THE BLUEPRINT\n\n"
            "**Goal:** Write what we are building here.\n\n"
            "**Architecture:** TBD\n\n"
            "**Graveyard:**\n"
            "- None yet.\n"
        ))
        print(f"  [!] Created {STATE_FILE}. Define your goal in it, then run the script again.")
        sys.exit(0)


def main():
    global DRY_RUN
    args = sys.argv[1:]
    if "--dry-run" in args:
        DRY_RUN = True
        args.remove("--dry-run")

    if len(args) < 1:
        print("Usage: python avalanche.py \"<test_command>\"")
        print("Example: python avalanche.py \"pytest -v\"")
        sys.exit(1)

    test_command = args[0]
    setup()

    cycle = 0
    while cycle < MAX_CYCLES:
        cycle += 1
        print_header(f"CYCLE {cycle}/{MAX_CYCLES} | THE GRIND")

        # 1. THE GRIND (Combinatorial Search)
        grind_prompt = (
            f"You are the combinatorial engine of the Avalanche system.\n"
            f"1. Read `{STATE_FILE}` for your objective, current architectural state, "
            f"and memory of past failures.\n"
            f"2. Edit the codebase to achieve the goal and ensure this test command "
            f"will pass: `{test_command}`\n"
            f"3. THE RAZOR: Write the absolute simplest, most naive code that "
            f"satisfies the current known state. DO NOT over-engineer. DO NOT "
            f"anticipate errors, edge-cases, or traps that are not explicitly "
            f"documented in your Graveyard.\n"
            f"4. Do NOT run the tests yourself. I am the environment; I will run "
            f"the tests. Edit the files and exit."
        )
        invoke_claude(grind_prompt, max_turns=GRIND_MAX_TURNS)

        # 2. THE RATCHET (Environmental Feedback)
        print_header("EVALUATING RATCHET")
        print(f"  Running: {test_command}")
        result = run_test(test_command)
        test_output = result.stdout + "\n" + result.stderr

        if result.returncode == 0:
            print("  [PASS] TESTS PASSED. RATCHET SECURED.")
            run_git("add", ".")
            run_git("commit", "-m", "Avalanche: Ratchet advanced")

            # 3. CONSOLIDATION (The Cure for Metacognitive Lag)
            print_header("METACOGNITIVE SYNC (SUCCESS)")
            sync_prompt = (
                f"You are the memory module of the Avalanche build system.\n"
                f"The tests just passed and the code has been committed.\n"
                f"Read the codebase, then completely rewrite `{STATE_FILE}` to reflect "
                f"the current state. Explain what the architecture looks like now and "
                f"why it works. Do not edit any code files — only `{STATE_FILE}`.\n"
                f"Must be strictly under {WORD_LIMIT} words."
            )
            invoke_claude(sync_prompt, max_turns=SYNC_MAX_TURNS)

            print(f"\n  Goal iteration complete. Update {STATE_FILE} for a new target.")
            try:
                input("Press Enter to continue to next cycle (or Ctrl+C to stop)...")
            except EOFError:
                print("\n[!] Headless mode detected. Engine pausing cleanly. Re-run to continue.")
                sys.exit(0)

        else:
            print("  [FAIL] TESTS FAILED. DECOUPLING STATE FROM SYNTAX.")
            # Preserve the memory before nuking
            current_state = read_file(STATE_FILE)

            # Violently revert the codebase
            run_git("reset", "--hard", "HEAD")
            run_git("clean", "-fd")

            # Restore the memory
            write_file(STATE_FILE, current_state)

            # 4. FAILURE ANALYSIS (Forced Learning)
            print_header("METACOGNITIVE SYNC (FAILURE ANALYSIS)")
            error_tail = test_output[-1500:]  # Last 1500 chars to avoid bloat
            fail_prompt = (
                f"You are the memory module of the Avalanche build system.\n"
                f"The tests just failed. All code changes have been reverted — the "
                f"codebase is back to the last known good state.\n"
                f"Here is the test output:\n{error_tail}\n\n"
                f"Your task: rewrite `{STATE_FILE}`. Update the Graveyard section "
                f"to document what was just attempted and why it failed, so the next "
                f"attempt does not repeat the same mistake.\n"
                f"Do not edit any code files — only `{STATE_FILE}`.\n"
                f"Must be strictly under {WORD_LIMIT} words."
            )
            invoke_claude(fail_prompt, max_turns=SYNC_MAX_TURNS)

    # Cycle cap exhausted
    print_header("CYCLE CAP REACHED")
    print(f"  Avalanche hit {MAX_CYCLES} cycles without converging.")
    print(f"  Read {STATE_FILE} for failure history, then intervene manually.")
    sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  [!] Avalanche Engine powered down by user.")
