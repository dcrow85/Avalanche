#!/usr/bin/env python3
"""
The Avalanche Hypervisor V4 — The Index-Entangled Cipher

Hidden law: output[i] = input[i] + i (even index), input[i] - i (odd index).
Test arrays are generated randomly on every cycle. The organism cannot hardcode.

V4 changes (from V3):
- Bifurcated memory: blueprint.md (declarative) + heuristics.md (procedural)
- Compression sync: forced abstraction cycle when memory approaches capacity
- Crucible 7.5: stateless index-entangled cipher (replaces C7 state machine)
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

# --- AVALANCHE HYPERVISOR V4 ---
STATE_FILE = "blueprint.md"
HEURISTICS_FILE = "heuristics.md"
WORD_LIMIT = 150               # Declarative memory cap
HEURISTICS_WORD_LIMIT = 100    # Procedural memory cap
COMPRESSION_THRESHOLD = 120    # Triggers active compression sync
MAX_CYCLES = 15
INVOKE_TIMEOUT = 300
SYNC_MAX_TURNS = 5
STATUS_FILE = "status.json"


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
        "blueprint_words": get_word_count(STATE_FILE),
        "blueprint_limit": WORD_LIMIT,
        "heuristics_words": get_word_count(HEURISTICS_FILE),
        "heuristics_limit": HEURISTICS_WORD_LIMIT,
        "compression_threshold": COMPRESSION_THRESHOLD,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "log": _status_log[-50:],
    }
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f)


def print_header(text):
    print(f"\n{'='*50}\n  {text}\n{'='*50}")


def run_command(cmd, capture=False):
    if capture:
        result = subprocess.run(cmd, shell=True, text=True, capture_output=True, encoding="utf-8")
        return result.returncode == 0, result.stdout + "\n" + result.stderr
    else:
        result = subprocess.run(cmd, shell=True, encoding="utf-8")
        return result.returncode == 0, ""


def enforce_compression():
    """Forces the epistemic bottleneck by physically amputating bloat."""
    if not os.path.exists(STATE_FILE):
        return
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    words = content.split()
    if len(words) > WORD_LIMIT:
        print(f"  [COMPRESS] MEMORY OVERFLOW ({len(words)} words). Compressing to {WORD_LIMIT}.")
        truncated = " ".join(words[:WORD_LIMIT]) + "\n\n[WARNING: PREVIOUS THOUGHTS TRUNCATED BY ENVIRONMENT]"
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write(truncated)


def enforce_heuristics_compression():
    """Truncates heuristics.md if it exceeds HEURISTICS_WORD_LIMIT."""
    if not os.path.exists(HEURISTICS_FILE):
        return
    with open(HEURISTICS_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    words = content.split()
    if len(words) > HEURISTICS_WORD_LIMIT:
        print(f"  [COMPRESS] HEURISTICS OVERFLOW ({len(words)} words). Truncating to {HEURISTICS_WORD_LIMIT}.")
        truncated = " ".join(words[:HEURISTICS_WORD_LIMIT]) + "\n\n[WARNING: HEURISTICS TRUNCATED BY ENVIRONMENT]"
        with open(HEURISTICS_FILE, "w", encoding="utf-8") as f:
            f.write(truncated)


def get_word_count(filepath):
    """Returns word count of a file, or 0 if missing."""
    if not os.path.exists(filepath):
        return 0
    with open(filepath, "r", encoding="utf-8") as f:
        return len(f.read().split())


def compression_sync():
    """Forces active compression: organism must abstract raw data into theory."""
    print_header("COMPRESSION SYNC (FORCED ABSTRACTION)")
    prompt = (
        f"[ENVIRONMENTAL OVERRIDE: METABOLIC LIMIT REACHED]\n"
        f"Your memory ({STATE_FILE}) is approaching capacity. You are forbidden "
        f"from writing code this cycle. Read {STATE_FILE}. You MUST:\n"
        f"1. Identify raw data pairs (input/output arrays) in the Graveyard\n"
        f"2. Deduce a generalized pattern or rule from those pairs\n"
        f"3. Replace the raw arrays with a compact theory statement (under 20 words)\n"
        f"4. Delete the raw data to free space\n"
        f"If you simply truncate without abstracting, you will lose the coordinates "
        f"needed to solve the puzzle. Compress or die.\n"
        f"Do not edit any code files — only {STATE_FILE}.\n"
        f"Must stay under {WORD_LIMIT} words."
    )
    invoke_claude(prompt, max_turns=SYNC_MAX_TURNS)


def invoke_claude(prompt, max_turns=10):
    """Fires Claude Code via stdin pipe, enforces compression and amnesia."""
    enforce_compression()
    enforce_heuristics_compression()

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


def evaluate_ratchet():
    """The Ephemeral Oracle: Generates random tests, evaluates, and vaporizes."""
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
    # The Hidden Law
    expected = []
    for i, x in enumerate(arr):
        if i % 2 == 0:
            expected.append(x + i)
        else:
            expected.append(x - i)

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

print("Ratchet Passed. The cipher is aligned.")
sys.exit(0)
"""
    # 1. Materialize
    with open(".temp_ratchet.py", "w", encoding="utf-8") as f:
        f.write(test_code)

    # 2. Test
    success, output = run_command(f"{sys.executable} .temp_ratchet.py", capture=True)

    # 3. Vaporize
    if os.path.exists(".temp_ratchet.py"):
        os.remove(".temp_ratchet.py")

    return success, output.strip()


def setup():
    if not os.path.exists(".git"):
        print_header("INITIALIZING GIT RATCHET")
        run_command("git init")
        run_command("git config user.name Avalanche")
        run_command("git config user.email avalanche@local")

    created = False

    if not os.path.exists(STATE_FILE):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write(
                "# THE BLUEPRINT\n\n"
                "**Goal:** Create `solver.py` with "
                "`def transduce(arr: list[int]) -> list[int]:`. "
                "The Oracle contains a hidden mathematical law. "
                "It tests against completely random arrays. "
                "Discover the hidden rule transforming the input "
                "into the expected output.\n\n"
                "**Architecture:** TBD\n\n"
                "**Graveyard:**\n- None yet.\n"
            )
        print(f"  [!] Created {STATE_FILE}.")
        created = True

    if not os.path.exists(HEURISTICS_FILE):
        with open(HEURISTICS_FILE, "w", encoding="utf-8") as f:
            f.write(
                "# SEARCH HEURISTICS\n\n"
                "No rules yet. After each failed cycle, record strategic "
                "lessons here: what approach families are dead ends, "
                "what directions to explore instead.\n"
            )
        print(f"  [!] Created {HEURISTICS_FILE}.")
        created = True

    # Ensure status.json survives git clean
    gitignore_path = ".gitignore"
    ignore_entries = {"status.json", ".temp_ratchet.py"}
    existing = set()
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            existing = {line.strip() for line in f if line.strip()}
    missing = ignore_entries - existing
    if missing:
        with open(gitignore_path, "a", encoding="utf-8") as f:
            for entry in sorted(missing):
                f.write(f"{entry}\n")
        created = True

    if created:
        run_command("git add . && git commit -m \"Avalanche: Initial Baseline\"")


def main():
    setup()
    cycle = 0
    last_error = None

    while cycle < MAX_CYCLES:
        cycle += 1
        print_header(f"CYCLE {cycle}/{MAX_CYCLES} | THE GRIND")
        write_status(cycle, "GRIND")

        grind_prompt = (
            f"You are the combinatorial engine of Avalanche.\n"
            f"1. Read `{STATE_FILE}` for your objective and memory of past I/O pairs.\n"
            f"2. Read `{HEURISTICS_FILE}` for accumulated search strategy rules — "
            f"these persist across cycles and tell you what approach families are dead ends.\n"
            f"3. Edit `solver.py` to achieve the goal.\n"
            f"4. THE AIRLOCK: The Oracle generates completely random arrays every "
            f"single cycle. You cannot hardcode answers. You must deduce the "
            f"generalized mathematical/logical law from your Graveyard examples."
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
                f"[ENVIRONMENTAL OVERRIDE: SUCCESS]\n"
                f"Your code passed. DO NOT WRITE CODE.\n"
                f"Rewrite `{STATE_FILE}` to explain the exact logic of the hidden "
                f"law you discovered. Must be under {WORD_LIMIT} words.\n"
                f"Also update `{HEURISTICS_FILE}` to record the successful strategy."
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
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                current_state = f.read()
            heuristics_state = ""
            if os.path.exists(HEURISTICS_FILE):
                with open(HEURISTICS_FILE, "r", encoding="utf-8") as f:
                    heuristics_state = f.read()

            run_command("git reset --hard HEAD")
            run_command("git clean -fd")

            with open(STATE_FILE, "w", encoding="utf-8") as f:
                f.write(current_state)
            with open(HEURISTICS_FILE, "w", encoding="utf-8") as f:
                f.write(heuristics_state)

            print_header("METACOGNITIVE SYNC (FAILURE ANALYSIS)")
            write_status(cycle, "SYNC_FAILURE", last_result="FAIL", last_error=last_error)
            error_tail = output[-1000:]
            fail_prompt = (
                f"[ENVIRONMENTAL OVERRIDE: FAILURE]\n"
                f"The Oracle evaluated your code and reported:\n"
                f"{error_tail}\n\n"
                f"I have violently reverted all your code changes. DO NOT WRITE CODE.\n"
                f"Rewrite `{STATE_FILE}`. Update the Graveyard to record this exact "
                f"Input/Expected Output pair. Analyze the pairs to deduce the hidden "
                f"mathematical law. To survive the strict {WORD_LIMIT}-word memory "
                f"limit, you MUST compress old arrays into generalized theories. "
                f"If you exceed the word limit, your memory will be violently truncated.\n"
                f"Also update `{HEURISTICS_FILE}` with any strategic meta-rules about "
                f"what approach families to permanently avoid. This file persists across "
                f"cycles. Keep it under {HEURISTICS_WORD_LIMIT} words. Focus on *what "
                f"directions are dead*, not raw data."
            )
            invoke_claude(fail_prompt, max_turns=SYNC_MAX_TURNS)

            # Compression sync: if blueprint is getting full, force active abstraction
            wc = get_word_count(STATE_FILE)
            if wc > COMPRESSION_THRESHOLD:
                print(f"  [!] Blueprint at {wc} words (threshold: {COMPRESSION_THRESHOLD}). Forcing compression sync.")
                write_status(cycle, "COMPRESSION_SYNC", last_result="FAIL", last_error=last_error)
                compression_sync()

    print_header("CYCLE CAP REACHED")
    write_status(cycle, "CYCLE_CAP", last_result="FAIL", last_error=last_error)
    print(f"  Avalanche hit {MAX_CYCLES} cycles without converging.")
    sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  [!] Avalanche Engine powered down by user.")
