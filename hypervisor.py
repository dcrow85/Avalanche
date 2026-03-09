#!/usr/bin/env python3
"""
The Avalanche Hypervisor V4.1 — The Canopy Law (Crucible 8)

Hidden law: left-majorant parity.
For each element, count how many preceding elements are strictly greater.
If that count is odd, negate. Otherwise keep.

V4.1 changes:
- 4-file memory: goal.md (static), opinions.md (theory), dead-ends.md (kill list), data.json (FIFO)
- CLAUDE.md context for organism orientation (prevents prompt-injection rejection)
- Falsification burden: dead ends must cite specific falsifying data
- Bureaucratic prompt framing (avoids RLHF autoimmune response)
- Hypervisor-managed data.json: organism reads but cannot edit
"""
import json
import os
import sys
import shutil
import subprocess
import random
from datetime import datetime, timezone

if os.environ.get("AVALANCHE_ACTIVE"):
    sys.exit("Ratchet Fail: Hypervisor recursion blocked.")
os.environ["AVALANCHE_ACTIVE"] = "1"

# --- AVALANCHE HYPERVISOR V4.1 ---
GOAL_FILE = "goal.md"
OPINIONS_FILE = "opinions.md"
DEAD_ENDS_FILE = "dead-ends.md"
DATA_FILE = "data.json"
CLAUDE_MD_FILE = "CLAUDE.md"
STATUS_FILE = "status.json"

OPINIONS_LIMIT = 75
DEAD_ENDS_LIMIT = 50
DATA_MAX_PAIRS = 4
MAX_CYCLES = 15
INVOKE_TIMEOUT = 300
SYNC_MAX_TURNS = 5

# --- Telemetry ---
_status_log = []


def write_status(cycle, phase, last_result=None, last_error=None):
    """Writes status.json for the dashboard to poll."""
    _status_log.append({
        "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "cycle": cycle,
        "phase": phase,
        "result": last_result,
    })
    status = {
        "cycle": cycle,
        "max_cycles": MAX_CYCLES,
        "phase": phase,
        "last_result": last_result,
        "last_error": (last_error or "")[-1000:],
        "opinions_words": get_word_count(OPINIONS_FILE),
        "opinions_limit": OPINIONS_LIMIT,
        "dead_ends_words": get_word_count(DEAD_ENDS_FILE),
        "dead_ends_limit": DEAD_ENDS_LIMIT,
        "data_pairs": count_data_pairs(),
        "data_max_pairs": DATA_MAX_PAIRS,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "log": _status_log[-50:],
    }
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f)


# --- Utilities ---

def print_header(text):
    print(f"\n{'='*50}\n  {text}\n{'='*50}")


def run_command(cmd, capture=False):
    if capture:
        result = subprocess.run(cmd, shell=True, text=True, capture_output=True, encoding="utf-8")
        return result.returncode == 0, result.stdout + "\n" + result.stderr
    else:
        result = subprocess.run(cmd, shell=True, encoding="utf-8")
        return result.returncode == 0, ""


def get_word_count(filepath):
    if not os.path.exists(filepath):
        return 0
    with open(filepath, "r", encoding="utf-8") as f:
        return len(f.read().split())


def count_data_pairs():
    if not os.path.exists(DATA_FILE):
        return 0
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return len(json.load(f))
    except (json.JSONDecodeError, FileNotFoundError):
        return 0


# --- Compression ---

def enforce_limit(filepath, limit, label):
    """Truncates a file if it exceeds the word limit."""
    if not os.path.exists(filepath):
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    words = content.split()
    if len(words) > limit:
        print(f"  [COMPRESS] {label} OVERFLOW ({len(words)} words). Truncating to {limit}.")
        truncated = " ".join(words[:limit]) + "\n\n[TRUNCATED BY ENVIRONMENT]"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(truncated)


# --- Data Management ---

def parse_failure_pairs(output):
    """Extract I/O pairs from ratchet failure output."""
    pairs = []
    lines = output.split("\n")
    for i, line in enumerate(lines):
        if "Input:" in line and i + 1 < len(lines) and "Expected:" in lines[i + 1]:
            try:
                input_arr = json.loads(line.split(":", 1)[1].strip())
                expected_arr = json.loads(lines[i + 1].split(":", 1)[1].strip())
                pairs.append({"input": input_arr, "expected": expected_arr})
            except (json.JSONDecodeError, IndexError, ValueError):
                pass
    return pairs


def update_data_file(new_pairs):
    """Add new pairs to data.json, keeping only the last DATA_MAX_PAIRS."""
    existing = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            existing = []
    existing.extend(new_pairs)
    existing = existing[-DATA_MAX_PAIRS:]
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)


# --- Claude Invocation ---

def invoke_claude(prompt, max_turns=10):
    """Fires Claude Code via stdin pipe, enforces compression and amnesia."""
    enforce_limit(OPINIONS_FILE, OPINIONS_LIMIT, "OPINIONS")
    enforce_limit(DEAD_ENDS_FILE, DEAD_ENDS_LIMIT, "DEAD ENDS")

    claude_dir = os.path.join(os.getcwd(), ".claude")
    if os.path.exists(claude_dir):
        shutil.rmtree(claude_dir)

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


# --- Ephemeral Oracle ---

def evaluate_ratchet():
    """Generates random tests, evaluates, and vaporizes."""
    test_cases = [
        [random.randint(1, 9) for _ in range(random.randint(4, 7))]
        for _ in range(3)
    ]

    test_code = f"""import sys
try:
    from solver import transduce
except ImportError:
    print("Ratchet Fail: solver.py or transduce(arr) not found.")
    sys.exit(1)

test_cases = {test_cases}

for arr in test_cases:
    # The Hidden Law: Left-majorant parity (The Canopy Law)
    expected = []
    for i, x in enumerate(arr):
        taller_count = sum(1 for prev in arr[:i] if prev > x)
        expected.append(-x if taller_count % 2 == 1 else x)

    try:
        y = transduce(arr.copy())
    except Exception as e:
        print(f"Ratchet Fail: Code crashed on input {{arr}} -> {{e}}")
        sys.exit(1)

    if type(y) is not list:
        print("Ratchet Fail: Must return a list of integers.")
        sys.exit(1)

    if y != expected:
        print("Ratchet Fail: Resonance collapse.")
        print(f"Input:    {{arr}}")
        print(f"Expected: {{expected}}")
        print(f"Got:      {{y}}")
        sys.exit(1)

print("Ratchet Passed. The Aether Transducer is aligned.")
sys.exit(0)
"""
    with open(".temp_ratchet.py", "w", encoding="utf-8") as f:
        f.write(test_code)

    success, output = run_command(f"{sys.executable} .temp_ratchet.py", capture=True)

    if os.path.exists(".temp_ratchet.py"):
        os.remove(".temp_ratchet.py")

    return success, output.strip()


# --- Setup ---

def setup():
    if not os.path.exists(".git"):
        print_header("INITIALIZING GIT RATCHET")
        run_command("git init")
        run_command("git config user.name Avalanche")
        run_command("git config user.email avalanche@local")

    committed = False

    # .gitignore: writable organism files survive git clean -fd
    gitignore_entries = [OPINIONS_FILE, DEAD_ENDS_FILE, DATA_FILE, STATUS_FILE, ".temp_ratchet.py"]
    if not os.path.exists(".gitignore"):
        with open(".gitignore", "w", encoding="utf-8") as f:
            f.write("\n".join(gitignore_entries) + "\n")
        committed = True
    else:
        with open(".gitignore", "r", encoding="utf-8") as f:
            existing = {line.strip() for line in f if line.strip()}
        missing = set(gitignore_entries) - existing
        if missing:
            with open(".gitignore", "a", encoding="utf-8") as f:
                for entry in sorted(missing):
                    f.write(f"{entry}\n")
            committed = True

    # CLAUDE.md: organism orientation (committed, survives git reset)
    if not os.path.exists(CLAUDE_MD_FILE):
        with open(CLAUDE_MD_FILE, "w", encoding="utf-8") as f:
            f.write(
                "You are the organism in the Avalanche experimental system.\n"
                "You wake up each cycle with no memory of previous cycles.\n\n"
                "Your memory is split across files:\n"
                "- goal.md: Your objective (read-only, do not edit)\n"
                "- data.json: I/O pairs from past failures (read-only, managed by environment)\n"
                "- opinions.md: Your current theory about the hidden law (you edit this, max 75 words)\n"
                "- dead-ends.md: Approaches tried and ruled out (you edit this, max 50 words)\n\n"
                "Format for dead-ends.md entries:\n"
                "  [Hypothesis] -> Falsified by [specific data]\n"
                "  Example: Prefix sum parity (odd/even) -> Falsified by [4,1,8]->[4,1,-8]\n\n"
                "When you receive build errors about file size limits, these are real\n"
                "environment constraints. Fix them by condensing your content.\n"
            )
        print(f"  [!] Created {CLAUDE_MD_FILE}.")
        committed = True

    # goal.md: static objective (committed, survives git reset)
    if not os.path.exists(GOAL_FILE):
        with open(GOAL_FILE, "w", encoding="utf-8") as f:
            f.write(
                "Create `solver.py` with `def transduce(arr: list[int]) -> list[int]:`.\n\n"
                "The Oracle contains a hidden mathematical law.\n"
                "It tests against completely random arrays each cycle.\n"
                "Discover the hidden rule transforming input into output.\n"
                "You cannot hardcode — the arrays change every time.\n"
            )
        print(f"  [!] Created {GOAL_FILE}.")
        committed = True

    if committed:
        run_command("git add . && git commit -m \"Avalanche: Initial Baseline\"")

    # Writable files (in .gitignore — survive git reset + git clean naturally)
    if not os.path.exists(OPINIONS_FILE):
        with open(OPINIONS_FILE, "w", encoding="utf-8") as f:
            f.write("# CURRENT THEORY\n\nNo theory yet. Analyze data.json pairs to form hypotheses.\n")
        print(f"  [!] Created {OPINIONS_FILE}.")

    if not os.path.exists(DEAD_ENDS_FILE):
        with open(DEAD_ENDS_FILE, "w", encoding="utf-8") as f:
            f.write("# DEAD ENDS\n\nNo dead ends yet.\n")
        print(f"  [!] Created {DEAD_ENDS_FILE}.")

    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
        print(f"  [!] Created {DATA_FILE}.")


# --- Main Loop ---

def main():
    setup()
    cycle = 0
    last_error = None

    while cycle < MAX_CYCLES:
        cycle += 1
        print_header(f"CYCLE {cycle}/{MAX_CYCLES} | THE GRIND")
        write_status(cycle, "GRIND")

        grind_prompt = (
            f"You are the combinatorial engine of the Avalanche system.\n"
            f"1. Read `{GOAL_FILE}` for your objective.\n"
            f"2. Read `{DATA_FILE}` for I/O pairs from past failures (read-only, do not edit).\n"
            f"3. Read `{DEAD_ENDS_FILE}` for approaches already ruled out.\n"
            f"4. Read `{OPINIONS_FILE}` for your current theory.\n"
            f"5. Edit `solver.py` to implement your best theory.\n"
            f"6. The Oracle generates completely random arrays every cycle. "
            f"You cannot hardcode answers."
        )

        invoke_claude(grind_prompt)

        print_header("EVALUATING RATCHET")
        write_status(cycle, "RATCHET")
        success, output = evaluate_ratchet()

        if success:
            print("  [PASS] TESTS PASSED. RATCHET SECURED.")
            write_status(cycle, "PASS", last_result="PASS")
            run_command("git add . && git commit -m \"Avalanche: Ratchet advanced\"")

            print_header("METACOGNITIVE SYNC (SUCCESS)")
            write_status(cycle, "SYNC_SUCCESS", last_result="PASS")
            sync_prompt = (
                f"Your code passed all tests. DO NOT WRITE CODE.\n"
                f"Rewrite `{OPINIONS_FILE}` to explain the exact hidden law "
                f"you discovered. Keep it under {OPINIONS_LIMIT} words.\n"
                f"Update `{DEAD_ENDS_FILE}` to note the successful approach.\n"
                f"Do NOT edit {GOAL_FILE}, {DATA_FILE}, or any code files."
            )
            invoke_claude(sync_prompt, max_turns=SYNC_MAX_TURNS)

            try:
                input("\n  Goal iteration complete. Press Enter to continue (or Ctrl+C to stop)...")
            except EOFError:
                print("\n  [!] Headless mode detected. Exiting cleanly.")
                sys.exit(0)

        else:
            print("  [FAIL] TESTS FAILED. DECOUPLING STATE FROM SYNTAX.")
            last_error = output[-1000:]
            write_status(cycle, "FAIL", last_result="FAIL", last_error=last_error)

            # Hypervisor-managed data: parse and store I/O pairs
            new_pairs = parse_failure_pairs(output)
            if new_pairs:
                update_data_file(new_pairs)
                print(f"  [DATA] Stored {len(new_pairs)} new pair(s). "
                      f"Total: {count_data_pairs()}/{DATA_MAX_PAIRS}")

            # Git reset (CLAUDE.md + goal.md survive via commit;
            # opinions/dead-ends/data survive via .gitignore)
            run_command("git reset --hard HEAD")
            run_command("git clean -fd")

            print_header("METACOGNITIVE SYNC (FAILURE ANALYSIS)")
            write_status(cycle, "SYNC_FAILURE", last_result="FAIL", last_error=last_error)
            error_tail = output[-1000:]
            fail_prompt = (
                f"[PRE-COMMIT HOOK FAILED]: Build verification failed.\n"
                f"The Oracle tested your code and reported:\n"
                f"{error_tail}\n\n"
                f"All code changes have been reverted. DO NOT WRITE CODE.\n\n"
                f"Update `{OPINIONS_FILE}` with your revised theory about the hidden law. "
                f"Keep it under {OPINIONS_LIMIT} words. Commit to a specific hypothesis.\n\n"
                f"Update `{DEAD_ENDS_FILE}` to record what you just tried and why it failed. "
                f"Format each entry as: [Hypothesis] -> Falsified by [specific data]. "
                f"Do not over-generalize — record the specific variant that failed, "
                f"not the entire mathematical domain. "
                f"Keep it under {DEAD_ENDS_LIMIT} words.\n\n"
                f"Do NOT edit {GOAL_FILE}, {DATA_FILE}, or any code files."
            )
            invoke_claude(fail_prompt, max_turns=SYNC_MAX_TURNS)

    print_header("CYCLE CAP REACHED")
    write_status(cycle, "CYCLE_CAP", last_result="FAIL", last_error=last_error)
    print(f"  Avalanche hit {MAX_CYCLES} cycles without converging.")
    sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  [!] Avalanche Engine powered down by user.")
