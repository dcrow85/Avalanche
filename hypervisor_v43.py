#!/usr/bin/env python3
"""
Avalanche Hypervisor V4.3

Isolated next-step build for deterministic telemetry, optional adversarial
counterexample selection, and a sterile raw OpenAI API backend.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import random
import subprocess
import sys
import types
import urllib.error
import urllib.request
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
SYNC_MAX_TURNS = 5
CARDINALITY_RETRY_LIMIT = 2
DEFAULT_MODEL = os.environ.get("AVALANCHE_OPENAI_MODEL", "gpt-4o")
DEFAULT_API_BASE = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
DEFAULT_TEMPERATURE = 0.2

OUTPUT_SCHEMA = {
    "name": "avalanche_v43_cycle_output",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "opinions_md": {"type": "string"},
            "dead_ends_md": {"type": "string"},
            "solver_py": {"type": "string"},
        },
        "required": ["opinions_md", "dead_ends_md", "solver_py"],
        "additionalProperties": False,
    },
}

_status_log: list[dict[str, object]] = []
_metric_history: list[dict[str, object]] = []
_rng = random.Random()


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
    """Crucible 9 hidden law: value-stride interference."""
    expected = []
    for i, x in enumerate(arr):
        strikes = sum(1 for j in range(i) if (i - j) % arr[j] == 0)
        expected.append(-x if strikes % 2 == 1 else x)
    return expected


def load_solver_module(path: str) -> tuple[types.ModuleType | None, str | None]:
    if not os.path.exists(path):
        return None, "solver.py not found."
    module_name = f"_avalanche_solver_{os.getpid()}_{datetime.now(timezone.utc).timestamp()}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return None, "Unable to load solver module."
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - runtime path
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
        merged = sorted(existing_ignores | gitignore_entries)
        write_text(".gitignore", "\n".join(merged) + "\n")
        created = True

    if not os.path.exists(AGENTS_FILE):
        write_text(
            AGENTS_FILE,
            "# Avalanche Organism Instructions\n\n"
            "This workspace is managed by Avalanche V4.3.\n"
            "The environment controls cycle resets, failure telemetry, and data.json.\n"
            "The organism works only through opinions.md, dead-ends.md, and solver.py.\n",
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
        run_command('git add . && git commit -m "Avalanche: V4.3 initial baseline"')


def format_cycle_prompt(cycle: int, max_cycles: int, mode: str, failure_report: str | None = None) -> list[dict[str, str]]:
    current_data = read_text(DATA_FILE) or "[]"
    current_opinions = read_text(OPINIONS_FILE)
    current_dead_ends = read_text(DEAD_ENDS_FILE)
    goal = read_text(GOAL_FILE)

    system_prompt = (
        "You are a deterministic mapping function resolving ENOSPC-style research constraints.\n"
        "Output only the JSON object matching the provided schema.\n"
        "No conversational filler. No markdown fences. No extra keys.\n"
    )

    if mode == "grind":
        instruction = (
            f"Cycle {cycle} of an unknown-length experiment.\n"
            "Read the provided files and return updated contents for:\n"
            "- opinions_md\n"
            "- dead_ends_md\n"
            "- solver_py\n\n"
            f"Constraints:\n- opinions_md must stay under {OPINIONS_LIMIT} words\n"
            f"- dead_ends_md must stay under {DEAD_ENDS_LIMIT} words\n"
            f"- dead_ends_md must use one family per line in the format {DEAD_END_FORMAT}\n"
            "- solver_py must define transduce(arr: list[int]) -> list[int]\n"
            "- data.json is read-only context supplied by the environment\n"
            "- commit to one specific mathematical hypothesis\n"
        )
    else:
        instruction = (
            "Build verification failed.\n"
            f"{failure_report or ''}\n\n"
            "All code changes have been reverted by the environment.\n"
            "Return:\n"
            "- revised opinions_md with a specific next hypothesis\n"
            f"- revised dead_ends_md recording distinct dead-end families as {DEAD_END_FORMAT}\n"
            "- solver_py containing your next best implementation attempt\n"
            f"Word limits remain {OPINIONS_LIMIT} and {DEAD_ENDS_LIMIT}.\n"
        )

    user_prompt = (
        f"{instruction}\n"
        f"\n# goal.md\n{goal}\n"
        f"\n# data.json\n{current_data}\n"
        f"\n# opinions.md\n{current_opinions}\n"
        f"\n# dead-ends.md\n{current_dead_ends}\n"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def extract_message_text(message: dict[str, object]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def invoke_openai(messages: list[dict[str, str]], model: str, api_base: str) -> dict[str, str]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    payload = {
        "model": model,
        "temperature": DEFAULT_TEMPERATURE,
        "parallel_tool_calls": False,
        "tools": [],
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": OUTPUT_SCHEMA,
        },
    }
    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network path
        raise RuntimeError(f"OpenAI connection error: {exc}") from exc

    try:
        message = payload["choices"][0]["message"]
        content = extract_message_text(message)
        return json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Malformed OpenAI response: {payload}") from exc


def validate_cycle_output(payload: dict[str, str]) -> str | None:
    opinions_words = len(payload["opinions_md"].split())
    if opinions_words > OPINIONS_LIMIT:
        return f"opinions_md exceeds {OPINIONS_LIMIT} words ({opinions_words})."
    dead_ends_words = len(payload["dead_ends_md"].split())
    if dead_ends_words > DEAD_ENDS_LIMIT:
        return f"dead_ends_md exceeds {DEAD_ENDS_LIMIT} words ({dead_ends_words})."
    try:
        ast.parse(payload["solver_py"])
    except SyntaxError as exc:
        return f"solver_py syntax error: {exc.msg} at line {exc.lineno}."
    return None


def request_cycle_output(
    cycle: int,
    max_cycles: int,
    model: str,
    api_base: str,
    mode: str,
    failure_report: str | None = None,
) -> dict[str, str]:
    messages = format_cycle_prompt(cycle, max_cycles, mode, failure_report)
    payload = invoke_openai(messages, model, api_base)
    error = validate_cycle_output(payload)
    if not error:
        return payload

    retry_messages = messages + [
        {
            "role": "user",
            "content": f"[SYSTEM LINTER ERROR] Validation failed: {error} Fix and resubmit strictly adhering to constraints.",
        }
    ]
    payload = invoke_openai(retry_messages, model, api_base)
    error = validate_cycle_output(payload)
    if error:
        raise RuntimeError(f"CYCLE_CRASH_FORMAT: {error}")
    return payload


def persist_model_output(payload: dict[str, str]) -> None:
    write_text(OPINIONS_FILE, payload["opinions_md"].strip() + "\n")
    write_text(DEAD_ENDS_FILE, payload["dead_ends_md"].strip() + "\n")
    write_text(SOLVER_FILE, payload["solver_py"].rstrip() + "\n")


def generate_test_cases(sample_size: int) -> list[list[int]]:
    return [generate_random_array(_rng) for _ in range(sample_size)]


def required_dead_end_count(cycle: int) -> int:
    return min(cycle, 3)


def enforce_dead_end_cardinality(
    cycle: int,
    max_cycles: int,
    model: str,
    api_base: str,
) -> bool:
    """Require a minimum number of distinct dead-end families in dead-ends.md."""
    required = required_dead_end_count(cycle)
    for _ in range(CARDINALITY_RETRY_LIMIT):
        actual = dead_end_family_count(read_text(DEAD_ENDS_FILE))
        if actual >= required:
            return True
        failure_report = (
            "[PRE-COMMIT FAILED: Causal Amnesia Detected]\n"
            f"`{DEAD_ENDS_FILE}` must contain at least {required} distinct dead-end families using "
            f"{DEAD_END_FORMAT}.\n"
            f"It currently contains {actual}.\n"
            f"Rewrite `{DEAD_ENDS_FILE}` to preserve at least {required} distinct families while staying "
            f"under {DEAD_ENDS_LIMIT} words.\n"
        )
        payload = request_cycle_output(
            cycle,
            max_cycles,
            model,
            api_base,
            mode="sync-fail",
            failure_report=failure_report,
        )
        persist_model_output(payload)
    return dead_end_family_count(read_text(DEAD_ENDS_FILE)) >= required


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
    parser = argparse.ArgumentParser(description="Run Avalanche V4.3 in an isolated workspace.")
    parser.add_argument("--workspace", default=r"C:\terrarium-v43", help="Workspace directory.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model for the raw API backend.")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="OpenAI-compatible API base URL.")
    parser.add_argument("--max-cycles", type=int, default=DEFAULT_MAX_CYCLES, help="Maximum cycle count.")
    parser.add_argument("--tests-per-cycle", type=int, default=5, help="Random ratchet tests per cycle.")
    parser.add_argument(
        "--bootstrap-only",
        action="store_true",
        help="Create the V4.3 workspace files and exit without invoking the API.",
    )
    parser.add_argument(
        "--oracle-mode",
        choices=["first-failure", "adversarial"],
        default="first-failure",
        help="Counterexample selection strategy after a failed solver.",
    )
    parser.add_argument("--seed", type=int, default=43, help="Random seed for reproducible test generation.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _rng.seed(args.seed)
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    os.chdir(workspace)

    setup_workspace()
    if args.bootstrap_only:
        write_status(0, args.max_cycles, "BOOTSTRAPPED")
        print(f"  Avalanche V4.3 workspace bootstrapped at {workspace}")
        return

    cycle = 0
    last_error: str | None = None
    previous_complexity: int | None = None

    while cycle < args.max_cycles:
        cycle += 1
        previous_opinions = read_text(OPINIONS_FILE)
        previous_dead_ends = read_text(DEAD_ENDS_FILE)
        write_status(cycle, args.max_cycles, "GRIND")

        try:
            grind_payload = request_cycle_output(cycle, args.max_cycles, args.model, args.api_base, mode="grind")
        except RuntimeError as exc:
            last_error = str(exc)
            write_status(cycle, args.max_cycles, "FORMAT_FAIL", last_result="FAIL", last_error=last_error)
            continue

        persist_model_output(grind_payload)
        attempted_solver_code = grind_payload["solver_py"]

        write_status(cycle, args.max_cycles, "RATCHET")
        success, output, first_failure = evaluate_solver(generate_test_cases(args.tests_per_cycle))

        if success:
            run_command('git add . && git commit -m "Avalanche: V4.3 ratchet advanced"')
            metrics = compute_cycle_metrics(
                cycle,
                previous_opinions,
                previous_dead_ends,
                previous_complexity,
                attempted_solver_code,
            )
            previous_complexity = metrics["solver_ast_complexity"]  # type: ignore[assignment]
            write_status(cycle, args.max_cycles, "PASS", last_result="PASS", metrics=metrics)
            continue

        last_error = output[-1000:]
        failing_pairs: list[dict[str, list[int]]]
        if args.oracle_mode == "adversarial":
            module, _ = load_solver_module(str(Path(SOLVER_FILE)))
            transduce = getattr(module, "transduce", None) if module else None
            if callable(transduce):
                failing_pairs = select_adversarial_pairs(transduce, hidden_law, _rng)
            else:
                failing_pairs = []
        else:
            failing_pairs = []

        if not failing_pairs and first_failure:
            failing_pairs = [first_failure]
        if not failing_pairs:
            fallback = generate_test_cases(1)[0]
            failing_pairs = [{"input": fallback, "expected": hidden_law(fallback)}]

        update_data_file(failing_pairs)
        run_command("git reset --hard HEAD")
        run_command("git clean -fd")

        try:
            fail_payload = request_cycle_output(
                cycle,
                args.max_cycles,
                args.model,
                args.api_base,
                mode="sync-fail",
                failure_report=output,
            )
        except RuntimeError as exc:
            last_error = str(exc)
            write_status(cycle, args.max_cycles, "FORMAT_FAIL", last_result="FAIL", last_error=last_error)
            continue

        persist_model_output(fail_payload)
        cardinality_ok = enforce_dead_end_cardinality(cycle, args.max_cycles, args.model, args.api_base)
        if not cardinality_ok:
            last_error = (
                (last_error or "")
                + "\n[CAUSAL AMNESIA DETECTED] dead-ends.md remained below required family cardinality."
            )[-1000:]

        metrics = compute_cycle_metrics(
            cycle,
            previous_opinions,
            previous_dead_ends,
            previous_complexity,
            attempted_solver_code,
        )
        previous_complexity = metrics["solver_ast_complexity"]  # type: ignore[assignment]
        write_status(
            cycle,
            args.max_cycles,
            "SYNC_FAILURE",
            last_result="FAIL",
            last_error=last_error,
            metrics=metrics,
        )

    write_status(cycle, args.max_cycles, "CYCLE_CAP", last_result="FAIL", last_error=last_error)
    sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  [!] Avalanche V4.3 powered down by user.")
