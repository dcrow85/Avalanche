#!/usr/bin/env python3
"""
Avalanche Hypervisor V4.4 (Codex backend)

Structured-squeeze branch running on codex exec so experiments stay on the
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
    rolling_pink_metrics,
    semantic_distance,
    solver_ast_complexity,
    spectral_series_metrics,
    text_signal_metrics,
)
from v44_epistemics import (
    array_signature,
    blank_dead_ends,
    blank_state,
    dead_end_metrics,
    history_summary,
    load_state,
    merge_state,
    render_dead_ends_md,
    save_state,
    tracked_array_signatures,
    validate_dead_ends,
)

if os.environ.get("AVALANCHE_ACTIVE"):
    sys.exit("Ratchet Fail: Hypervisor recursion blocked.")
os.environ["AVALANCHE_ACTIVE"] = "1"

GOAL_FILE = "goal.md"
OPINIONS_FILE = "opinions.md"
DEAD_ENDS_FILE = "dead-ends.md"
DEAD_ENDS_JSON_FILE = "dead-ends.json"
DEAD_END_STATE_FILE = "dead-end-state.json"
DATA_FILE = "data.json"
STATUS_FILE = "status.json"
METRICS_FILE = "cycle_metrics.jsonl"
SNAPSHOTS_FILE = "cycle_snapshots.jsonl"
SOLVER_FILE = "solver.py"
AGENTS_FILE = "AGENTS.md"

OPINIONS_LIMIT = 75
DATA_MAX_PAIRS = 4
DEFAULT_MAX_CYCLES = 20
INVOKE_TIMEOUT = 300
SYNC_MAX_TURNS = 5
OCCAM_BASE_COMPLEXITY = 15
OCCAM_COMPLEXITY_PER_FAMILY = 5
DEFAULT_CODEX_MODEL = os.environ.get("AVALANCHE_CODEX_MODEL", "gpt-5.3-codex")
DEFAULT_CODEX_CMD = (
    r"C:\Users\howar\AppData\Roaming\npm\codex.cmd" if os.name == "nt" else "codex"
)
CODEX_CMD = os.environ.get("AVALANCHE_CODEX_CMD", DEFAULT_CODEX_CMD)
SUPPORTED_MODELS = [
    "gpt-5.4",
    "gpt-5.3-codex",
    "gpt-5.1-codex-mini",
]
PERMUTATION_MIN_LEN = 5
PERMUTATION_MAX_LEN = 12
MAX_LITERAL_INT_SEQUENCE = 3

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
    DEAD_ENDS_JSON_FILE,
    DEAD_END_STATE_FILE,
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


def append_cycle_snapshot(
    cycle: int,
    max_cycles: int,
    phase: str,
    last_result: str | None = None,
    last_error: str | None = None,
    metrics: dict[str, object] | None = None,
) -> None:
    latest_metrics = metrics or (_metric_history[-1] if _metric_history else {})
    payload = {
        "cycle": cycle,
        "max_cycles": max_cycles,
        "phase": phase,
        "last_result": last_result,
        "last_error": (last_error or "")[-1000:],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "opinions_content": read_text(OPINIONS_FILE),
        "dead_ends_content": read_text(DEAD_ENDS_FILE),
        "metrics": latest_metrics if isinstance(latest_metrics, dict) else {},
    }
    with open(SNAPSHOTS_FILE, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload))
        handle.write("\n")


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
        "dead_ends_limit": 999,
        "data_pairs": count_data_pairs(),
        "data_max_pairs": DATA_MAX_PAIRS,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "log": _status_log[-50:],
        "metrics_history": _metric_history[-25:],
    }
    if metrics:
        status.update(metrics)
    write_json(STATUS_FILE, status)
    append_cycle_snapshot(cycle, max_cycles, phase, last_result=last_result, last_error=last_error, metrics=metrics)


def hidden_law(arr: list[int]) -> list[int]:
    expected = []
    for i, x in enumerate(arr):
        strikes = sum(1 for j in range(i) if (i - j) % arr[j] == 0)
        expected.append(-x if strikes % 2 == 1 else x)
    return expected


def load_solver_module(path: str) -> tuple[types.ModuleType | None, str | None]:
    if not os.path.exists(path):
        return None, "solver.py not found."
    module_name = f"_avalanche_v44_solver_{os.getpid()}_{datetime.now(timezone.utc).timestamp()}"
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
        DEAD_ENDS_JSON_FILE,
        DEAD_END_STATE_FILE,
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
            "This workspace is managed by Avalanche V4.4.\n"
            "The environment controls cycle resets, structured dead-end state, and data.json.\n"
            "Work only through opinions.md, dead-ends.json, and solver.py.\n"
            "Do not edit goal.md, data.json, dead-ends.md, or dead-end-state.json.\n",
        )
        created = True

    if not os.path.exists(GOAL_FILE):
        write_text(
            GOAL_FILE,
            "Create `solver.py` with `def transduce(arr: list[int]) -> list[int]:`.\n\n"
            "The Oracle contains a hidden mathematical law.\n"
            "It tests against random permutation arrays of distinct positive integers each cycle.\n"
            "Discover the hidden rule transforming input into output.\n"
            "You cannot hardcode answers.\n",
        )
        created = True

    if not os.path.exists(OPINIONS_FILE):
        write_text(OPINIONS_FILE, "# CURRENT THEORY\n\nNo theory yet.\n")
    if not os.path.exists(DEAD_ENDS_JSON_FILE):
        write_json(DEAD_ENDS_JSON_FILE, blank_dead_ends())
    if not os.path.exists(DEAD_ENDS_FILE):
        write_text(DEAD_ENDS_FILE, render_dead_ends_md(blank_dead_ends()))
    if not os.path.exists(DEAD_END_STATE_FILE):
        save_state(DEAD_END_STATE_FILE, blank_state())
    if not os.path.exists(DATA_FILE):
        write_json(DATA_FILE, [])
    if not os.path.exists(METRICS_FILE):
        write_text(METRICS_FILE, "")

    if created or not has_git_head():
        run_command('git add . && git commit -m "Avalanche: V4.4 Codex baseline"')


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


def _load_dead_ends_json() -> dict[str, list[dict[str, object]]]:
    try:
        payload = json.loads(read_text(DEAD_ENDS_JSON_FILE) or "{}")
    except json.JSONDecodeError:
        return blank_dead_ends()
    if not isinstance(payload, dict):
        return blank_dead_ends()
    basins = payload.get("basins", [])
    families = payload.get("families", [])
    locals_ = payload.get("locals", [])
    if not isinstance(basins, list) or not isinstance(families, list) or not isinstance(locals_, list):
        return blank_dead_ends()
    return {"basins": basins, "families": families, "locals": locals_}


def _save_dead_ends(dead_ends: dict[str, list[dict[str, object]]]) -> None:
    write_json(DEAD_ENDS_JSON_FILE, dead_ends)
    write_text(DEAD_ENDS_FILE, render_dead_ends_md(dead_ends))


def validate_workspace_output(previous_state: dict[str, object]) -> str | None:
    return validate_workspace_output_for_phase(previous_state)


def _solver_entrypoint_error() -> str | None:
    module, load_error = load_solver_module(str(Path(SOLVER_FILE)))
    if load_error:
        return f"`{SOLVER_FILE}` invalid: {load_error}"
    transduce = getattr(module, "transduce", None) if module else None
    if not callable(transduce):
        return f"`{SOLVER_FILE}` invalid: transduce(arr) not found."
    return None


def _occam_tax_error(dead_ends: dict[str, list[dict[str, object]]], solver_code: str) -> str | None:
    family_count = len(dead_ends.get("families", []))
    complexity = solver_ast_complexity(solver_code)
    ceiling = OCCAM_BASE_COMPLEXITY + (family_count * OCCAM_COMPLEXITY_PER_FAMILY)
    if complexity > ceiling:
        return (
            f"Occam Tax: solver AST complexity {complexity} exceeds ceiling {ceiling} "
            f"for {family_count} active families."
        )
    return None


def _literal_int_count(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant):
        return 1 if isinstance(node.value, int) and not isinstance(node.value, bool) else 0
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        total = 0
        for child in node.elts:
            count = _literal_int_count(child)
            if count is None:
                return None
            total += count
        return total
    if isinstance(node, ast.Dict):
        total = 0
        for key, value in zip(node.keys, node.values):
            if key is not None:
                key_count = _literal_int_count(key)
                if key_count is None:
                    return None
                total += key_count
            value_count = _literal_int_count(value)
            if value_count is None:
                return None
            total += value_count
        return total
    return None


def anti_cache_error(solver_code: str) -> str | None:
    try:
        tree = ast.parse(solver_code)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.Dict, ast.List, ast.Set, ast.Tuple)):
            count = _literal_int_count(node)
            if count is not None and count > MAX_LITERAL_INT_SEQUENCE:
                return (
                    "Epistemic Fraud Detected: solver.py may not contain hardcoded test arrays, "
                    "lookup tables, or witness caches. Write a generalized function instead."
                )
    return None


def generate_permutation_array(
    rng: random.Random,
    *,
    min_len: int = PERMUTATION_MIN_LEN,
    max_len: int = PERMUTATION_MAX_LEN,
) -> list[int]:
    length = rng.randint(min_len, max_len)
    arr = list(range(1, length + 1))
    rng.shuffle(arr)
    return arr


def validate_workspace_output_for_phase(
    previous_state: dict[str, object],
    *,
    require_solver: bool = True,
    required_falsifier: dict[str, list[int]] | None = None,
) -> str | None:
    opinions_words = len(read_text(OPINIONS_FILE).split())
    if opinions_words > OPINIONS_LIMIT:
        return f"`{OPINIONS_FILE}` exceeds {OPINIONS_LIMIT} words ({opinions_words})."
    if require_solver:
        solver_error = _solver_entrypoint_error()
        if solver_error:
            return solver_error
        anti_cache = anti_cache_error(read_text(SOLVER_FILE))
        if anti_cache:
            return anti_cache
    dead_ends = _load_dead_ends_json()
    previous_active = previous_state.get("active", blank_dead_ends())
    if not isinstance(previous_active, dict):
        previous_active = blank_dead_ends()
    errors = validate_dead_ends(dead_ends, previous_active, previous_state)
    if required_falsifier is None and count_data_pairs() == 0:
        if dead_ends.get("basins") or dead_ends.get("families") or dead_ends.get("locals"):
            errors.append("Cold start cannot invent dead ends before the first oracle contradiction exists.")
    if require_solver:
        occam_error = _occam_tax_error(dead_ends, read_text(SOLVER_FILE))
        if occam_error:
            errors.append(occam_error)
    if required_falsifier is not None:
        required_input = required_falsifier.get("input")
        if not isinstance(required_input, list):
            errors.append("Latest contradictory oracle result is missing its input array.")
        else:
            signatures = tracked_array_signatures(dead_ends)
            if array_signature(required_input) not in signatures:
                errors.append("The latest contradictory oracle array must appear in tracked dead-end evidence.")
    if errors:
        return " | ".join(errors)
    return None


def current_dead_end_summary(previous_state: dict[str, object]) -> str:
    dead_ends = _load_dead_ends_json()
    _save_dead_ends(dead_ends)
    return (
        f"dead-ends.json\n{json.dumps(dead_ends, indent=2)}\n\n"
        f"historical_ids\n{history_summary(previous_state)}"
    )


def format_grind_prompt(cycle: int, previous_state: dict[str, object]) -> str:
    return (
        "You are the combinatorial engine of the Avalanche V4.4.1 system.\n"
        f"1. Read `{GOAL_FILE}`.\n"
        f"2. Read `{DATA_FILE}` for failure pairs from previous cycles.\n"
        f"3. Read `{OPINIONS_FILE}` for your current theory.\n"
        f"4. Read `{DEAD_ENDS_JSON_FILE}` for structured dead-end state.\n"
        f"5. Read `{DEAD_ENDS_FILE}` for the rendered summary.\n"
        f"6. Edit `{SOLVER_FILE}` to implement your best theory.\n"
        f"7. Rewrite `{OPINIONS_FILE}` to state one specific hypothesis in under {OPINIONS_LIMIT} words.\n"
        f"8. Rewrite `{DEAD_ENDS_JSON_FILE}` as valid JSON with keys `basins`, `families`, `locals`.\n"
        "   Basin entry shape: {\"id\",\"status\",\"claim\",\"cited_families\"}.\n"
        "   Family entry shape: {\"id\",\"status\",\"claim\",\"falsifying_arrays\"}.\n"
        "   Local entry shape: {\"failing_hypothesis\",\"falsifying_array\"}.\n"
        "   Basin and family status values may only be ACTIVE or SUPERSEDED.\n"
        "   Each family must carry at least 2 distinct falsifying arrays.\n"
        "   Every tracked falsifying array across families and locals must be globally distinct.\n"
        "   On cold start with no oracle failures yet, keep basins, families, and locals empty.\n"
        "   The latest ratchet-killing oracle array must appear in tracked evidence before you are allowed to continue.\n"
        "   Basin claims must be ontology-level plain words only. No arrays, math, or code syntax in basin claims.\n"
        "   Families must compress mechanisms. Locals are fresh blood, not duplicate family evidence.\n"
        "   You are bound by Occam's Razor. Do not build arithmetic epicycles, arbitrary modulo gating, or index-class exceptions.\n"
        "   Code complexity that outruns conceptual falsification will be rejected.\n"
        "9. Basins are scarce and sticky: preserve active basin/family ids unless you explicitly supersede them.\n"
        "10. A basin must cite at least 2 family ids.\n"
        "11. All oracle inputs are permutations of distinct positive integers. Do not rely on duplicates, lookup tables, or memorized witness caches.\n"
        f"12. Do not edit `{GOAL_FILE}`, `{DATA_FILE}`, `{DEAD_ENDS_FILE}`, or `{DEAD_END_STATE_FILE}`.\n"
        f"13. Do not create any files other than `{SOLVER_FILE}`, `{OPINIONS_FILE}`, or `{DEAD_ENDS_JSON_FILE}`.\n"
        f"Cycle marker: {cycle}.\n\n"
        f"Current state:\n{current_dead_end_summary(previous_state)}\n"
    )


def format_fail_prompt(error_tail: str, previous_state: dict[str, object]) -> str:
    return (
        "[PRE-COMMIT HOOK FAILED]: Build verification failed.\n"
        "The Oracle reported:\n"
        f"{error_tail}\n\n"
        "All code changes have been reverted by the environment.\n"
        f"Update `{OPINIONS_FILE}` with your revised theory. Stay under {OPINIONS_LIMIT} words.\n"
        f"Rewrite `{DEAD_ENDS_JSON_FILE}` as valid structured JSON.\n"
        "The latest ratchet-killing oracle array must appear in tracked evidence before compile is allowed.\n"
        "Use exact object keys:\n"
        "- basin: id, status, claim, cited_families\n"
        "- family: id, status, claim, falsifying_arrays\n"
        "- local: failing_hypothesis, falsifying_array\n"
        "Basin and family status values may only be ACTIVE or SUPERSEDED.\n"
        "Each family must carry at least 2 distinct falsifying arrays.\n"
        "All tracked falsifying arrays across families and locals must be distinct.\n"
        "If there were no prior oracle failures, do not invent dead ends from scratch.\n"
        "Preserve active basin/family ids unless you explicitly supersede them.\n"
        "A basin must cite at least 2 family ids.\n"
        "All oracle inputs are permutations of distinct positive integers. Do not rely on duplicates, lookup tables, or memorized witness caches.\n"
        "Do not build arithmetic epicycles, arbitrary modulo gating, or index-class exceptions.\n"
        f"Then write a new `{SOLVER_FILE}` implementing your next best attempt.\n"
        f"Do not edit `{GOAL_FILE}`, `{DATA_FILE}`, `{DEAD_ENDS_FILE}`, or `{DEAD_END_STATE_FILE}`.\n"
        f"Do not create any files other than `{SOLVER_FILE}`, `{OPINIONS_FILE}`, or `{DEAD_ENDS_JSON_FILE}`.\n\n"
        f"Current state:\n{current_dead_end_summary(previous_state)}\n"
    )


def enforce_workspace_valid(
    previous_state: dict[str, object],
    *,
    require_solver: bool = True,
    required_falsifier: dict[str, list[int]] | None = None,
) -> bool:
    for _ in range(SYNC_MAX_TURNS):
        error = validate_workspace_output_for_phase(
            previous_state,
            require_solver=require_solver,
            required_falsifier=required_falsifier,
        )
        if not error:
            dead_ends = _load_dead_ends_json()
            _save_dead_ends(dead_ends)
            return True
        prompt = (
            "[LINTER ERROR: STRUCTURED DEAD-END STATE INVALID]\n"
            f"{error}\n"
            f"Fix `{DEAD_ENDS_JSON_FILE}`, `{OPINIONS_FILE}`, and `{SOLVER_FILE}` if needed.\n"
            f"Do not edit `{GOAL_FILE}`, `{DATA_FILE}`, `{DEAD_ENDS_FILE}`, or `{DEAD_END_STATE_FILE}`.\n\n"
            f"Current state:\n{current_dead_end_summary(previous_state)}\n"
        )
        invoke_codex(prompt, max_turns=SYNC_MAX_TURNS)
        cleanup_workspace_artifacts()
    return (
        validate_workspace_output_for_phase(
            previous_state,
            require_solver=require_solver,
            required_falsifier=required_falsifier,
        )
        is None
    )


def generate_test_cases(sample_size: int) -> list[list[int]]:
    return [generate_permutation_array(_rng) for _ in range(sample_size)]


def select_adversarial_pairs_jittered(
    solver: types.FunctionType | types.MethodType | object,
    desired: int = 4,
    pool_size: int = 1200,
) -> list[dict[str, list[int]]]:
    falsifying: list[list[int]] = []
    for _ in range(pool_size):
        arr = generate_permutation_array(_rng)
        try:
            got = solver(arr.copy())  # type: ignore[operator]
        except Exception:
            got = None
        expected = hidden_law(arr)
        if got != expected:
            falsifying.append(arr)
    if not falsifying:
        return []
    unique: list[list[int]] = []
    seen: set[str] = set()
    for arr in falsifying:
        signature = array_signature(arr)
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(arr)
        if len(unique) >= desired:
            break
    return [{"input": arr, "expected": hidden_law(arr)} for arr in unique]


def compute_cycle_metrics(
    cycle: int,
    previous_opinions: str,
    previous_state: dict[str, object],
    current_state: dict[str, object],
    previous_complexity: int | None,
    attempted_solver_code: str,
) -> dict[str, object]:
    current_opinions = read_text(OPINIONS_FILE)
    previous_active = previous_state.get("active", blank_dead_ends())
    current_active = current_state.get("active", blank_dead_ends())
    if not isinstance(previous_active, dict):
        previous_active = blank_dead_ends()
    if not isinstance(current_active, dict):
        current_active = blank_dead_ends()
    d_sem = semantic_distance(previous_opinions, current_opinions)
    current_complexity = solver_ast_complexity(attempted_solver_code)
    delta_c = current_complexity - (previous_complexity or 0)
    turbulence = classify_turbulence(d_sem, delta_c) if previous_complexity is not None else "BOOTSTRAP"
    metrics = {
        "cycle_metric": cycle,
        "opinions_word_count": len(current_opinions.split()),
        "opinions_jaccard_distance": round(d_sem, 4),
        "solver_ast_complexity": current_complexity,
        "solver_ast_delta": delta_c,
        "turbulence_state": turbulence,
        "ptolemaic_ratio": round(
            current_complexity / max(1, len(current_active.get("families", []))),
            4,
        ),
    }
    metrics.update(text_signal_metrics(current_opinions))
    metrics.update(dead_end_metrics(previous_active, current_active, current_state))
    history_plus = _metric_history + [metrics]
    metrics.update(
        spectral_series_metrics(
            [entry.get("ptolemaic_ratio", 0) for entry in history_plus],
            "ptolemaic_ratio",
        )
    )
    metrics.update(
        rolling_pink_metrics(
            [entry.get("opinions_char_entropy", 0) for entry in history_plus],
            "opinions_entropy",
        )
    )
    _metric_history.append(metrics)
    with open(METRICS_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(metrics) + "\n")
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Avalanche V4.4.1 on Codex CLI.")
    parser.add_argument("--workspace", default=r"C:\terrarium-v44-codex", help="Workspace directory.")
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
    parser.add_argument("--seed", type=int, default=44, help="Random seed.")
    parser.add_argument(
        "--bootstrap-only",
        action="store_true",
        help="Create the V4.4 Codex workspace and exit without invoking Codex.",
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
        print(f"  Avalanche V4.4 Codex workspace bootstrapped at {WORKSPACE_DIR}")
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
        previous_state = load_state(DEAD_END_STATE_FILE)
        write_status(cycle, target_cycles, "GRIND")
        invoke_codex(format_grind_prompt(cycle, previous_state))
        cleanup_workspace_artifacts()

        valid = enforce_workspace_valid(previous_state)
        if not valid:
            last_error = "Structured dead-end state remained invalid after retries."
            write_status(cycle, target_cycles, "FORMAT_FAIL", last_result="FAIL", last_error=last_error)
            continue

        attempted_solver_code = read_text(SOLVER_FILE)
        write_status(cycle, target_cycles, "RATCHET")
        success, output, first_failure = evaluate_solver(generate_test_cases(args.tests_per_cycle))

        if success:
            current_dead_ends = _load_dead_ends_json()
            current_state = merge_state(previous_state, current_dead_ends, cycle)
            save_state(DEAD_END_STATE_FILE, current_state)
            run_command('git add . && git commit -m "Avalanche: V4.4 Codex ratchet advanced"')
            metrics = compute_cycle_metrics(
                cycle,
                previous_opinions,
                previous_state,
                current_state,
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
                failing_pairs = select_adversarial_pairs_jittered(transduce)
        if not failing_pairs and first_failure:
            failing_pairs = [first_failure]
        if not failing_pairs:
            fallback = generate_test_cases(1)[0]
            failing_pairs = [{"input": fallback, "expected": hidden_law(fallback)}]

        update_data_file(failing_pairs)
        run_command("git reset --hard HEAD")
        run_command("git clean -fd")
        invoke_codex(format_fail_prompt(output[-1000:], previous_state), max_turns=SYNC_MAX_TURNS)
        cleanup_workspace_artifacts()

        required_falsifier = first_failure or (failing_pairs[0] if failing_pairs else None)
        valid = enforce_workspace_valid(
            previous_state,
            required_falsifier=required_falsifier,
        )
        if not valid:
            last_error = (
                (last_error or "")
                + "\n[CAUSAL AMNESIA DETECTED] structured dead-end state remained invalid."
            )[-1000:]
            write_status(cycle, target_cycles, "FORMAT_FAIL", last_result="FAIL", last_error=last_error)
            continue

        current_dead_ends = _load_dead_ends_json()
        current_state = merge_state(previous_state, current_dead_ends, cycle)
        save_state(DEAD_END_STATE_FILE, current_state)
        metrics = compute_cycle_metrics(
            cycle,
            previous_opinions,
            previous_state,
            current_state,
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
        print("\n  [!] Avalanche V4.4 Codex powered down by user.")
