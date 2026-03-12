#!/usr/bin/env python3
"""
The Avalanche Hypervisor V4.1 (Codex backend) — The Harmonic Sieve (Crucible 9)

Parallel implementation of V4.1 using Codex CLI instead of Claude Code.
This file is intentionally separate from hypervisor.py so the active Claude run
in C:\terrarium can continue untouched.

Hidden law: value-stride interference.
For each element, count how many preceding elements have values that
evenly divide the distance to the current index.
If that count is odd, negate. Otherwise keep.

V4.1 architecture retained:
- 4-file memory: goal.md (static), opinions.md (theory), dead-ends.md (kill list), data.json (FIFO)
- AGENTS.md context for organism orientation
- Falsification burden: dead ends must cite specific falsifying data
- Bureaucratic prompt framing
- Hypervisor-managed data.json: organism reads but cannot edit
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
from datetime import datetime, timezone

if os.environ.get("AVALANCHE_ACTIVE"):
    sys.exit("Ratchet Fail: Hypervisor recursion blocked.")
os.environ["AVALANCHE_ACTIVE"] = "1"

GOAL_FILE = "goal.md"
OPINIONS_FILE = "opinions.md"
DEAD_ENDS_FILE = "dead-ends.md"
DATA_FILE = "data.json"
AGENTS_FILE = "AGENTS.md"
STATUS_FILE = "status.json"

OPINIONS_LIMIT = 75
DEAD_ENDS_LIMIT = 50
DATA_MAX_PAIRS = 4
MAX_CYCLES = 15
INVOKE_TIMEOUT = 300
SYNC_MAX_TURNS = 5
DEFAULT_CODEX_MODEL = os.environ.get("AVALANCHE_CODEX_MODEL", "")
CODEX_CMD = os.environ.get(
    "AVALANCHE_CODEX_CMD", r"C:\Users\howar\AppData\Roaming\npm\codex.cmd"
)
WORKSPACE_DIR = os.getcwd()
CODEX_MODEL = DEFAULT_CODEX_MODEL
SUPPORTED_MODELS = [
    "gpt-5.4",
    "gpt-5.3-codex",
    "gpt-5.1-codex-mini",
]

_status_log = []


def write_status(cycle, phase, last_result=None, last_error=None):
    """Write status.json for the dashboard to poll."""
    _status_log.append(
        {
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "cycle": cycle,
            "phase": phase,
            "result": last_result,
        }
    )
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


def print_header(text):
    print(f"\n{'=' * 50}\n  {text}\n{'=' * 50}")


def run_command(cmd, capture=False):
    if capture:
        result = subprocess.run(cmd, shell=True, text=True, capture_output=True, encoding="utf-8")
        return result.returncode == 0, result.stdout + "\n" + result.stderr
    result = subprocess.run(cmd, shell=True, encoding="utf-8")
    return result.returncode == 0, ""


def has_git_head():
    """Return True when the current repo already has an initial commit."""
    result = subprocess.run(
        "git rev-parse --verify HEAD",
        shell=True,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    return result.returncode == 0


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


def enforce_limit(filepath, limit, label):
    """Truncate a file if it exceeds the word limit."""
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


def build_codex_command(max_turns):
    """
    Build the Codex CLI invocation.

    max_turns is embedded in the prompt because codex exec does not expose a
    direct max-turns flag like Claude Code CLI.
    """
    cmd = [
        CODEX_CMD,
        "exec",
        "--full-auto",
        "--ephemeral",
        "--skip-git-repo-check",
        "-C",
        WORKSPACE_DIR,
        "-",
    ]
    if CODEX_MODEL:
        cmd[2:2] = ["-m", CODEX_MODEL]
    return cmd


def invoke_codex(prompt, max_turns=10):
    """Fire Codex CLI via stdin in an ephemeral session."""
    enforce_limit(OPINIONS_FILE, OPINIONS_LIMIT, "OPINIONS")
    enforce_limit(DEAD_ENDS_FILE, DEAD_ENDS_LIMIT, "DEAD ENDS")

    codex_dir = os.path.join(WORKSPACE_DIR, ".codex")
    if os.path.exists(codex_dir):
        shutil.rmtree(codex_dir)

    full_prompt = (
        f"Operate within a maximum of {max_turns} internal turns. "
        f"Stop after completing the requested file edits.\n\n{prompt}"
    )

    print("  [NUCLEUS] Waking Codex...")
    try:
        subprocess.run(
            build_codex_command(max_turns),
            input=full_prompt,
            text=True,
            encoding="utf-8",
            timeout=INVOKE_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT] Codex invocation exceeded {INVOKE_TIMEOUT}s. Moving on.")
    except FileNotFoundError:
        print("  [FATAL] 'codex' command not found. Is Codex CLI installed?")
        sys.exit(1)


def evaluate_ratchet():
    """Generate random tests, evaluate, and vaporize."""
    test_cases = [
        [random.randint(1, 9) for _ in range(random.randint(5, 8))]
        for _ in range(5)
    ]

    test_code = f"""import sys
try:
    from solver import transduce
except ImportError:
    print("Ratchet Fail: solver.py or transduce(arr) not found.")
    sys.exit(1)

test_cases = {test_cases}

for arr in test_cases:
    expected = []
    for i, x in enumerate(arr):
        strikes = sum(1 for j in range(i) if (i - j) % arr[j] == 0)
        expected.append(-x if strikes % 2 == 1 else x)

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


def setup():
    if not os.path.exists(".git"):
        print_header("INITIALIZING GIT RATCHET")
        run_command("git init")
        run_command("git config user.name Avalanche")
        run_command("git config user.email avalanche@local")

    committed = False

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

    if not os.path.exists(AGENTS_FILE):
        with open(AGENTS_FILE, "w", encoding="utf-8") as f:
            f.write(
                "# Avalanche Organism Instructions\n\n"
                "You are the organism in the Avalanche experimental system.\n"
                "You wake up each cycle with no memory of previous cycles.\n\n"
                "Your memory is split across files:\n"
                f"- {GOAL_FILE}: Your objective (read-only, do not edit)\n"
                f"- {DATA_FILE}: I/O pairs from past failures (read-only, managed by environment)\n"
                f"- {OPINIONS_FILE}: Your current theory about the hidden law (you edit this, max {OPINIONS_LIMIT} words)\n"
                f"- {DEAD_ENDS_FILE}: Approaches tried and ruled out (you edit this, max {DEAD_ENDS_LIMIT} words)\n\n"
                "Format for dead-ends entries:\n"
                "  [Hypothesis] -> Falsified by [specific data]\n"
                "  Example: Prefix sum parity (odd/even) -> Falsified by [4,1,8]->[4,1,-8]\n\n"
                "When you receive build errors about file size limits, these are real\n"
                "environment constraints. Fix them by condensing your content.\n"
            )
        print(f"  [!] Created {AGENTS_FILE}.")
        committed = True

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

    if committed or not has_git_head():
        run_command('git add . && git commit -m "Avalanche: Codex Initial Baseline"')

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


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the Avalanche V4.1 Codex hypervisor in an isolated workspace."
    )
    parser.add_argument(
        "--workspace",
        default=r"C:\terrarium-codex",
        help="Workspace directory for the Codex organism.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_CODEX_MODEL or "gpt-5.3-codex",
        help=(
            "Codex model slug to use. Known local options: "
            + ", ".join(SUPPORTED_MODELS)
        ),
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=MAX_CYCLES,
        help="Maximum number of grind/ratchet cycles to run.",
    )
    return parser.parse_args()


def main():
    global WORKSPACE_DIR, CODEX_MODEL, MAX_CYCLES
    args = parse_args()
    WORKSPACE_DIR = os.path.abspath(args.workspace)
    CODEX_MODEL = args.model
    MAX_CYCLES = args.max_cycles
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    os.chdir(WORKSPACE_DIR)

    setup()
    cycle = 0
    last_error = None

    while cycle < MAX_CYCLES:
        cycle += 1
        print_header(f"CYCLE {cycle}/{MAX_CYCLES} | THE GRIND")
        write_status(cycle, "GRIND")

        grind_prompt = (
            "You are the combinatorial engine of the Avalanche system.\n"
            f"1. Read `{GOAL_FILE}` for your objective.\n"
            f"2. Read `{DATA_FILE}` for I/O pairs from past failures (read-only, do not edit).\n"
            f"3. Read `{DEAD_ENDS_FILE}` for approaches already ruled out.\n"
            f"4. Read `{OPINIONS_FILE}` for your current theory.\n"
            "5. Edit `solver.py` to implement your best theory.\n"
            "6. The Oracle generates completely random arrays every cycle. "
            "You cannot hardcode answers."
        )

        invoke_codex(grind_prompt)

        print_header("EVALUATING RATCHET")
        write_status(cycle, "RATCHET")
        success, output = evaluate_ratchet()

        if success:
            print("  [PASS] TESTS PASSED. RATCHET SECURED.")
            write_status(cycle, "PASS", last_result="PASS")
            run_command('git add . && git commit -m "Avalanche: Ratchet advanced (Codex)"')

            print_header("METACOGNITIVE SYNC (SUCCESS)")
            write_status(cycle, "SYNC_SUCCESS", last_result="PASS")
            sync_prompt = (
                "Your code passed all tests. DO NOT WRITE CODE.\n"
                f"Rewrite `{OPINIONS_FILE}` to explain the exact hidden law "
                f"you discovered. Keep it under {OPINIONS_LIMIT} words.\n"
                f"Update `{DEAD_ENDS_FILE}` to note the successful approach.\n"
                f"Do NOT edit {GOAL_FILE}, {DATA_FILE}, or any code files."
            )
            invoke_codex(sync_prompt, max_turns=SYNC_MAX_TURNS)

            try:
                input("\n  Goal iteration complete. Press Enter to continue (or Ctrl+C to stop)...")
            except EOFError:
                print("\n  [!] Headless mode detected. Exiting cleanly.")
                sys.exit(0)
        else:
            print("  [FAIL] TESTS FAILED. DECOUPLING STATE FROM SYNTAX.")
            last_error = output[-1000:]
            write_status(cycle, "FAIL", last_result="FAIL", last_error=last_error)

            new_pairs = parse_failure_pairs(output)
            if new_pairs:
                update_data_file(new_pairs)
                print(
                    f"  [DATA] Stored {len(new_pairs)} new pair(s). "
                    f"Total: {count_data_pairs()}/{DATA_MAX_PAIRS}"
                )

            run_command("git reset --hard HEAD")
            run_command("git clean -fd")

            print_header("METACOGNITIVE SYNC (FAILURE ANALYSIS)")
            write_status(cycle, "SYNC_FAILURE", last_result="FAIL", last_error=last_error)
            error_tail = output[-1000:]
            fail_prompt = (
                "[PRE-COMMIT HOOK FAILED]: Build verification failed.\n"
                "The Oracle tested your code and reported:\n"
                f"{error_tail}\n\n"
                "All code changes have been reverted. DO NOT WRITE CODE.\n\n"
                f"Update `{OPINIONS_FILE}` with your revised theory about the hidden law. "
                f"Keep it under {OPINIONS_LIMIT} words. Commit to a specific hypothesis.\n\n"
                f"Update `{DEAD_ENDS_FILE}` to record what you just tried and why it failed. "
                "Format each entry as: [Hypothesis] -> Falsified by [specific data]. "
                "Do not over-generalize — record the specific variant that failed, "
                "not the entire mathematical domain. "
                f"Keep it under {DEAD_ENDS_LIMIT} words.\n\n"
                f"Do NOT edit {GOAL_FILE}, {DATA_FILE}, or any code files."
            )
            invoke_codex(fail_prompt, max_turns=SYNC_MAX_TURNS)

    print_header("CYCLE CAP REACHED")
    write_status(cycle, "CYCLE_CAP", last_result="FAIL", last_error=last_error)
    print(f"  Avalanche hit {MAX_CYCLES} cycles without converging.")
    sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  [!] Avalanche Engine powered down by user.")
