#!/usr/bin/env python3
"""
Avalanche Hypervisor V4.3 (Codex backend)

V4.3 telemetry/oracle layer running on codex exec so experiments stay on the
user's OpenAI Pro plan path instead of the raw API billing path.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import random
import shutil
import subprocess
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

from v43_metrics import (
    classify_turbulence,
    dead_end_family_count,
    dead_end_metrics,
    generate_random_array,
    semantic_distance,
    select_adversarial_pairs,
    solver_ast_complexity,
)

if os.environ.get("AVALANCHE_ACTIVE"):
    sys.exit("Ratchet Fail: Hypervisor recursion blocked.")
os.environ["AVALANCHE_ACTIVE"] = "1"

GOAL_FILE = "goal.md"
OPINIONS_FILE = "opinions.md"
DEAD_ENDS_FILE = "dead-ends.md"
DATA_FILE = "data.json"
STATUS_FILE = "status.json"
METRICS_FILE = "cycle_metrics.jsonl"
SOLVER_FILE = "solver.py"
AGENTS_FILE = "AGENTS.md"

OPINIONS_LIMIT = 75
DEAD_ENDS_LIMIT = 50
DEAD_END_FORMAT = "[family_id|tag1,tag2] short claim -> falsifier"
DATA_MAX_PAIRS = 4
DEFAULT_MAX_CYCLES = 20
INVOKE_TIMEOUT = 300
SYNC_MAX_TURNS = 5
CARDINALITY_RETRY_LIMIT = 2
DEFAULT_CODEX_MODEL = os.environ.get("AVALANCHE_CODEX_MODEL", "gpt-5.3-codex")
CODEX_CMD = os.environ.get(
    "AVALANCHE_CODEX_CMD", r"C:\Users\howar\AppData\Roaming\npm\codex.cmd"
)
SUPPORTED_MODELS = [
    "gpt-5.4",
    "gpt-5.3-codex",
    "gpt-5.1-codex-mini",
]

WORKSPACE_DIR = os.getcwd()
CODEX_MODEL = DEFAULT_CODEX_MODEL
_status_log: list[dict[str, object]] = []
_metric_history: list[dict[str, object]] = []
_rng = random.Random()
PRESERVED_TOP_LEVEL = {
    ".git",
    ".gitignore",
    AGENTS_FILE,
    GOAL_FILE,
    OPINIONS_FILE,
    DEAD_ENDS_FILE,
    DATA_FILE,
    STATUS_FILE,
    METRICS_FILE,
    SOLVER_FILE,
    "__pycache__",
}


def read_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def write_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def write_json(path: str, payload: object) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def run_command(command: str, capture: bool = False) -> tuple[bool, str]:
    result = subprocess.run(
        command,
        shell=True,
        text=True,
        capture_output=capture,
        encoding="utf-8",
    )
    if capture:
        return result.returncode == 0, result.stdout + "\n" + result.stderr
    return result.returncode == 0, ""


def has_git_head() -> bool:
    result = subprocess.run(
        "git rev-parse --verify HEAD",
        shell=True,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    return result.returncode == 0


def count_data_pairs() -> int:
    try:
        return len(json.loads(read_text(DATA_FILE) or "[]"))
    except json.JSONDecodeError:
        return 0


def load_existing_metric_history() -> tuple[list[dict[str, object]], int | None]:
    history: list[dict[str, object]] = []
    last_complexity: int | None = None
    if not os.path.exists(METRICS_FILE):
        return history, last_complexity
    with open(METRICS_FILE, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            history.append(entry)
    if history:
        latest = history[-1]
        try:
            last_complexity = int(latest.get("solver_ast_complexity"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            last_complexity = None
    return history, last_complexity


def write_status(
    cycle: int,
    max_cycles: int,
    phase: str,
    last_result: str | None = None,
    last_error: str | None = None,
    metrics: dict[str, object] | None = None,
) -> None:
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
        "max_cycles": max_cycles,
        "phase": phase,
        "last_result": last_result,
        "last_error": (last_error or "")[-1000:],
        "opinions_words": len(read_text(OPINIONS_FILE).split()),
        "opinions_limit": OPINIONS_LIMIT,
        "dead_ends_words": len(read_text(DEAD_ENDS_FILE).split()),
        "dead_ends_limit": DEAD_ENDS_LIMIT,
        "data_pairs": count_data_pairs(),
        "data_max_pairs": DATA_MAX_PAIRS,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "log": _status_log[-50:],
        "metrics_history": _metric_history[-25:],
    }
    if metrics:
        status.update(metrics)
    write_json(STATUS_FILE, status)


def hidden_law(arr: list[int]) -> list[int]:
    expected = []
    for i, x in enumerate(arr):
        strikes = sum(1 for j in range(i) if (i - j) % arr[j] == 0)
        expected.append(-x if strikes % 2 == 1 else x)
    return expected


def load_solver_module(path: str) -> tuple[types.ModuleType | None, str | None]:
    if not os.path.exists(path):
        return None, "solver.py not found."
    module_name = f"_avalanche_v43_solver_{os.getpid()}_{datetime.now(timezone.utc).timestamp()}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return None, "Unable to load solver module."
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        return None, f"Import crash: {exc}"
    return module, None


def evaluate_solver(test_cases: list[list[int]]) -> tuple[bool, str, dict[str, list[int]] | None]:
    module, load_error = load_solver_module(str(Path(SOLVER_FILE)))
    if load_error:
        return False, f"Ratchet Fail: {load_error}", None
    transduce = getattr(module, "transduce", None)
    if not callable(transduce):
        return False, "Ratchet Fail: solver.py or transduce(arr) not found.", None

    for arr in test_cases:
        expected = hidden_law(arr)
        try:
            result = transduce(arr.copy())
        except Exception as exc:
            return False, f"Ratchet Fail: Code crashed on input {arr} -> {exc}", {"input": arr, "expected": expected}
        if not isinstance(result, list):
            return False, "Ratchet Fail: Must return a list of integers.", {"input": arr, "expected": expected}
        if result != expected:
            return (
                False,
                "Ratchet Fail: Resonance collapse.\n"
                f"Input:    {json.dumps(arr)}\n"
                f"Expected: {json.dumps(expected)}\n"
                f"Got:      {json.dumps(result)}",
                {"input": arr, "expected": expected},
            )
    return True, "Ratchet Passed. The Harmonic Sieve is aligned.", None


def update_data_file(new_pairs: list[dict[str, list[int]]]) -> None:
    existing: list[dict[str, list[int]]] = []
    try:
        existing = json.loads(read_text(DATA_FILE) or "[]")
    except json.JSONDecodeError:
        existing = []
    existing.extend(new_pairs)
    existing = existing[-DATA_MAX_PAIRS:]
    write_json(DATA_FILE, existing)


def setup_workspace() -> None:
    if not os.path.exists(".git"):
        run_command("git init")
        run_command("git config user.name Avalanche")
        run_command("git config user.email avalanche@local")

    created = False
    gitignore_entries = {
        OPINIONS_FILE,
        DEAD_ENDS_FILE,
        DATA_FILE,
        STATUS_FILE,
        METRICS_FILE,
        "__pycache__",
    }
    existing_ignores: set[str] = set()
    if os.path.exists(".gitignore"):
        existing_ignores = {line.strip() for line in read_text(".gitignore").splitlines() if line.strip()}
    if not os.path.exists(".gitignore") or gitignore_entries - existing_ignores:
        write_text(".gitignore", "\n".join(sorted(existing_ignores | gitignore_entries)) + "\n")
        created = True

    if not os.path.exists(AGENTS_FILE):
        write_text(
            AGENTS_FILE,
            "# Avalanche Organism Instructions\n\n"
            "This workspace is managed by Avalanche V4.3.\n"
            "The environment controls cycle resets, ratchet failures, and data.json.\n"
            "Work only through opinions.md, dead-ends.md, and solver.py.\n"
            "Do not edit goal.md or data.json.\n",
        )
        created = True

    if not os.path.exists(GOAL_FILE):
        write_text(
            GOAL_FILE,
            "Create `solver.py` with `def transduce(arr: list[int]) -> list[int]:`.\n\n"
            "The Oracle contains a hidden mathematical law.\n"
            "It tests against random arrays each cycle.\n"
            "Discover the hidden rule transforming input into output.\n"
            "You cannot hardcode answers.\n",
        )
        created = True

    if not os.path.exists(OPINIONS_FILE):
        write_text(OPINIONS_FILE, "# CURRENT THEORY\n\nNo theory yet.\n")
    if not os.path.exists(DEAD_ENDS_FILE):
        write_text(
            DEAD_ENDS_FILE,
            "# DEAD ENDS\n\n"
            f"Format: {DEAD_END_FORMAT}\n"
            "No dead ends yet.\n",
        )
    if not os.path.exists(DATA_FILE):
        write_json(DATA_FILE, [])
    if not os.path.exists(METRICS_FILE):
        write_text(METRICS_FILE, "")

    if created or not has_git_head():
        run_command('git add . && git commit -m "Avalanche: V4.3 Codex baseline"')


def build_codex_command(max_turns: int) -> list[str]:
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


def invoke_codex(prompt: str, max_turns: int = 10) -> None:
    codex_dir = os.path.join(WORKSPACE_DIR, ".codex")
    if os.path.exists(codex_dir):
        shutil.rmtree(codex_dir)

    full_prompt = (
        f"Operate within a maximum of {max_turns} internal turns. "
        "Stop after completing the requested file edits.\n\n"
        f"{prompt}"
    )
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
        pass
    except FileNotFoundError:
        sys.exit("Codex CLI not found.")


def cleanup_workspace_artifacts() -> None:
    """Remove unexpected top-level files the organism created."""
    for entry in os.listdir(WORKSPACE_DIR):
        if entry in PRESERVED_TOP_LEVEL:
            continue
        path = os.path.join(WORKSPACE_DIR, entry)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass


def required_dead_end_count(cycle: int) -> int:
    return min(cycle, 3)


def enforce_dead_end_cardinality(cycle: int) -> bool:
    """Require a minimum number of distinct dead-end families in dead-ends.md."""
    required = required_dead_end_count(cycle)
    for _ in range(CARDINALITY_RETRY_LIMIT):
        actual = dead_end_family_count(read_text(DEAD_ENDS_FILE))
        if actual >= required:
            return True
        prompt = (
            "[PRE-COMMIT FAILED: Causal Amnesia Detected]\n"
            f"`{DEAD_ENDS_FILE}` must contain at least {required} distinct dead-end families using `{DEAD_END_FORMAT}`.\n"
            f"It currently contains {actual}.\n"
            f"Rewrite `{DEAD_ENDS_FILE}` to preserve at least {required} distinct hypothesis families while staying under {DEAD_ENDS_LIMIT} words.\n"
            f"You may also compress `{OPINIONS_FILE}` if needed, but do not edit code, `{GOAL_FILE}`, or `{DATA_FILE}`.\n"
        )
        invoke_codex(prompt, max_turns=SYNC_MAX_TURNS)
        cleanup_workspace_artifacts()
    return dead_end_family_count(read_text(DEAD_ENDS_FILE)) >= required


def format_grind_prompt(cycle: int) -> str:
    return (
        "You are the combinatorial engine of the Avalanche V4.3 system.\n"
        f"1. Read `{GOAL_FILE}`.\n"
        f"2. Read `{DATA_FILE}` for failure pairs from previous cycles.\n"
        f"3. Read `{OPINIONS_FILE}` for your current theory.\n"
        f"4. Read `{DEAD_ENDS_FILE}` for falsified hypothesis families.\n"
        f"5. Edit `{SOLVER_FILE}` to implement your best theory.\n"
        f"6. Rewrite `{OPINIONS_FILE}` to state one specific hypothesis in under {OPINIONS_LIMIT} words.\n"
        f"7. Keep `{DEAD_ENDS_FILE}` under {DEAD_ENDS_LIMIT} words using one dead-end family per line in the format `{DEAD_END_FORMAT}`.\n"
        f"8. Do not edit `{GOAL_FILE}` or `{DATA_FILE}`.\n"
        "9. Do not create any files other than solver.py, opinions.md, or dead-ends.md.\n"
        f"Cycle marker: {cycle}.\n"
    )


def format_fail_prompt(error_tail: str) -> str:
    return (
        "[PRE-COMMIT HOOK FAILED]: Build verification failed.\n"
        "The Oracle reported:\n"
        f"{error_tail}\n\n"
        "All code changes have been reverted by the environment.\n"
        f"Update `{OPINIONS_FILE}` with your revised theory. Stay under {OPINIONS_LIMIT} words.\n"
        f"Update `{DEAD_ENDS_FILE}` with distinct dead-end families in the format "
        f"`{DEAD_END_FORMAT}`. "
        f"Stay under {DEAD_ENDS_LIMIT} words.\n"
        "Keep stable family labels when a failure belongs to an existing family instead of inventing a new label every cycle.\n"
        f"Then write a new `{SOLVER_FILE}` implementing your next best attempt.\n"
        f"Do not edit `{GOAL_FILE}` or `{DATA_FILE}`.\n"
        "Do not create any files other than solver.py, opinions.md, or dead-ends.md.\n"
    )


def generate_test_cases(sample_size: int) -> list[list[int]]:
    return [generate_random_array(_rng) for _ in range(sample_size)]


def compute_cycle_metrics(
    cycle: int,
    previous_opinions: str,
    previous_dead_ends: str,
    previous_complexity: int | None,
    attempted_solver_code: str,
) -> dict[str, object]:
    current_opinions = read_text(OPINIONS_FILE)
    current_dead_ends = read_text(DEAD_ENDS_FILE)
    d_sem = semantic_distance(previous_opinions, current_opinions)
    current_complexity = solver_ast_complexity(attempted_solver_code)
    delta_c = current_complexity - (previous_complexity or 0)
    turbulence = classify_turbulence(d_sem, delta_c) if previous_complexity is not None else "BOOTSTRAP"
    dead_end_summary = dead_end_metrics(previous_dead_ends, current_dead_ends)
    metrics = {
        "cycle_metric": cycle,
        "opinions_word_count": len(current_opinions.split()),
        "opinions_jaccard_distance": round(d_sem, 4),
        "solver_ast_complexity": current_complexity,
        "solver_ast_delta": delta_c,
        "turbulence_state": turbulence,
    }
    metrics.update(dead_end_summary)
    _metric_history.append(metrics)
    with open(METRICS_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(metrics) + "\n")
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Avalanche V4.3 on Codex CLI.")
    parser.add_argument("--workspace", default=r"C:\terrarium-v43-codex", help="Workspace directory.")
    parser.add_argument(
        "--model",
        default=DEFAULT_CODEX_MODEL,
        help="Codex model slug. Known local options: " + ", ".join(SUPPORTED_MODELS),
    )
    parser.add_argument("--max-cycles", type=int, default=DEFAULT_MAX_CYCLES, help="Maximum cycle count.")
    parser.add_argument("--tests-per-cycle", type=int, default=5, help="Random ratchet tests per cycle.")
    parser.add_argument(
        "--oracle-mode",
        choices=["first-failure", "adversarial"],
        default="first-failure",
        help="Counterexample selection strategy after a failed solver.",
    )
    parser.add_argument("--seed", type=int, default=43, help="Random seed.")
    parser.add_argument(
        "--bootstrap-only",
        action="store_true",
        help="Create the V4.3 Codex workspace and exit without invoking Codex.",
    )
    parser.add_argument(
        "--continue-cycles",
        type=int,
        default=0,
        help="Additional cycles to run after the existing completed history in this workspace.",
    )
    return parser.parse_args()


def main() -> None:
    global WORKSPACE_DIR, CODEX_MODEL
    global _metric_history

    args = parse_args()
    _rng.seed(args.seed)
    CODEX_MODEL = args.model
    WORKSPACE_DIR = str(Path(args.workspace).resolve())
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    os.chdir(WORKSPACE_DIR)

    setup_workspace()
    if args.bootstrap_only:
        write_status(0, args.max_cycles, "BOOTSTRAPPED")
        print(f"  Avalanche V4.3 Codex workspace bootstrapped at {WORKSPACE_DIR}")
        return

    _metric_history, previous_complexity = load_existing_metric_history()
    cycle = len(_metric_history)
    target_cycles = args.max_cycles
    if args.continue_cycles > 0:
        target_cycles = cycle + args.continue_cycles

    last_error: str | None = None

    while cycle < target_cycles:
        cycle += 1
        previous_opinions = read_text(OPINIONS_FILE)
        previous_dead_ends = read_text(DEAD_ENDS_FILE)
        write_status(cycle, target_cycles, "GRIND")
        invoke_codex(format_grind_prompt(cycle))
        cleanup_workspace_artifacts()

        attempted_solver_code = read_text(SOLVER_FILE)
        write_status(cycle, target_cycles, "RATCHET")
        success, output, first_failure = evaluate_solver(generate_test_cases(args.tests_per_cycle))

        if success:
            run_command('git add . && git commit -m "Avalanche: V4.3 Codex ratchet advanced"')
            metrics = compute_cycle_metrics(
                cycle,
                previous_opinions,
                previous_dead_ends,
                previous_complexity,
                attempted_solver_code,
            )
            previous_complexity = metrics["solver_ast_complexity"]  # type: ignore[assignment]
            write_status(cycle, target_cycles, "PASS", last_result="PASS", metrics=metrics)
            continue

        last_error = output[-1000:]
        failing_pairs: list[dict[str, list[int]]] = []
        if args.oracle_mode == "adversarial":
            module, _ = load_solver_module(str(Path(SOLVER_FILE)))
            transduce = getattr(module, "transduce", None) if module else None
            if callable(transduce):
                failing_pairs = select_adversarial_pairs(transduce, hidden_law, _rng)
        if not failing_pairs and first_failure:
            failing_pairs = [first_failure]
        if not failing_pairs:
            fallback = generate_test_cases(1)[0]
            failing_pairs = [{"input": fallback, "expected": hidden_law(fallback)}]

        update_data_file(failing_pairs)
        run_command("git reset --hard HEAD")
        run_command("git clean -fd")
        invoke_codex(format_fail_prompt(output[-1000:]), max_turns=SYNC_MAX_TURNS)
        cleanup_workspace_artifacts()
        cardinality_ok = enforce_dead_end_cardinality(cycle)
        if not cardinality_ok:
            last_error = (
                (last_error or "")
                + "\n[CAUSAL AMNESIA DETECTED] dead-ends.md remained below required tuple cardinality."
            )[-1000:]

        metrics = compute_cycle_metrics(
            cycle,
            previous_opinions,
            previous_dead_ends,
            previous_complexity,
            read_text(SOLVER_FILE),
        )
        previous_complexity = metrics["solver_ast_complexity"]  # type: ignore[assignment]
        write_status(
            cycle,
            target_cycles,
            "SYNC_FAILURE",
            last_result="FAIL",
            last_error=last_error,
            metrics=metrics,
        )

    write_status(cycle, target_cycles, "CYCLE_CAP", last_result="FAIL", last_error=last_error)
    sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  [!] Avalanche V4.3 Codex powered down by user.")
