#!/usr/bin/env python3
"""
Avalanche Hypervisor V4.4

Structured-squeeze branch with tiered dead-end state, ratcheted persistence,
and strict structured outputs over the raw OpenAI API backend.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import random
import signal
import subprocess
import sys
import types
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from v43_metrics import (
    classify_turbulence,
    semantic_distance,
    solver_ast_complexity,
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
DEFAULT_MAX_CYCLES = 20
DATA_MAX_PAIRS = 4
DEFAULT_MODEL = os.environ.get("AVALANCHE_MODEL", os.environ.get("AVALANCHE_OPENAI_MODEL", "gpt-4o"))
DEFAULT_API_BASE = os.environ.get("AVALANCHE_API_BASE", os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
DEFAULT_API_KEY_ENV = os.environ.get("AVALANCHE_API_KEY_ENV", "")
DEFAULT_TEMPERATURE = 0.2
DEFAULT_RESPONSE_FORMAT = os.environ.get("AVALANCHE_RESPONSE_FORMAT", "")
PERMUTATION_MIN_LEN = 5
PERMUTATION_MAX_LEN = 12
MAX_LITERAL_INT_SEQUENCE = 3
SYNC_MAX_TURNS = 5
SOLVER_TIMEOUT_SECONDS = 2.0

OUTPUT_SCHEMA = {
    "name": "avalanche_v44_cycle_output",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "opinions_md": {"type": "string"},
            "dead_ends": {
                "type": "object",
                "properties": {
                    "basins": {
                        "type": "array",
                        "maxItems": 2,
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "status": {"type": "string", "enum": ["ACTIVE", "SUPERSEDED"]},
                                "claim": {"type": "string"},
                                "cited_families": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["id", "status", "claim", "cited_families"],
                            "additionalProperties": False,
                        },
                    },
                    "families": {
                        "type": "array",
                        "maxItems": 3,
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "status": {"type": "string", "enum": ["ACTIVE", "SUPERSEDED"]},
                                "claim": {"type": "string"},
                                "falsifying_arrays": {
                                    "type": "array",
                                    "items": {
                                        "type": "array",
                                        "items": {"type": "integer"},
                                    },
                                },
                            },
                            "required": ["id", "status", "claim", "falsifying_arrays"],
                            "additionalProperties": False,
                        },
                    },
                    "locals": {
                        "type": "array",
                        "maxItems": 4,
                        "items": {
                            "type": "object",
                            "properties": {
                                "failing_hypothesis": {"type": "string"},
                                "falsifying_array": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                },
                            },
                            "required": ["failing_hypothesis", "falsifying_array"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["basins", "families", "locals"],
                "additionalProperties": False,
            },
            "solver_py": {"type": "string"},
        },
        "required": ["opinions_md", "dead_ends", "solver_py"],
        "additionalProperties": False,
    },
}

_status_log: list[dict[str, object]] = []
_metric_history: list[dict[str, object]] = []
_cycle_usage = {
    "api_call_count_cycle": 0,
    "api_prompt_tokens_cycle": 0,
    "api_completion_tokens_cycle": 0,
    "api_total_tokens_cycle": 0,
    "api_reasoning_tokens_cycle": 0,
}
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


def load_existing_metric_history() -> tuple[list[dict[str, object]], int | None]:
    if not os.path.exists(METRICS_FILE):
        return [], None
    history: list[dict[str, object]] = []
    last_complexity: int | None = None
    with open(METRICS_FILE, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            history.append(payload)
            try:
                last_complexity = int(payload.get("solver_ast_complexity"))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass
    return history, last_complexity


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


class SolverExecutionTimeout(Exception):
    pass


def _alarm_timeout_handler(signum, frame):  # type: ignore[unused-argument]
    raise SolverExecutionTimeout()


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
            if os.name != "nt":
                previous_handler = signal.signal(signal.SIGALRM, _alarm_timeout_handler)
                signal.setitimer(signal.ITIMER_REAL, SOLVER_TIMEOUT_SECONDS)
                try:
                    result = transduce(arr.copy())
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0.0)
                    signal.signal(signal.SIGALRM, previous_handler)
            else:
                result = transduce(arr.copy())
        except SolverExecutionTimeout:
            return (
                False,
                f"Ratchet Fail: Code timed out on input {arr} after {SOLVER_TIMEOUT_SECONDS:.1f}s",
                {"input": arr, "expected": expected},
            )
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
            "This workspace is managed by Avalanche V4.4.1.\n"
            "The environment controls cycle resets, structured dead-end state, and data.json.\n"
            "The organism works through opinions_md, structured dead_ends, and solver_py in API outputs.\n",
        )
        created = True

    if not os.path.exists(GOAL_FILE):
        write_text(
            GOAL_FILE,
            "Create `solver.py` with `def transduce(arr: list[int]) -> list[int]:`.\n\n"
            "The Oracle contains a hidden mathematical law.\n"
            "It tests against random permutation arrays of distinct positive integers each cycle.\n"
            "Discover the hidden rule transforming input into output.\n"
            "You cannot hardcode answers, lookup tables, or witness caches.\n",
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
        run_command('git add . && git commit -m "Avalanche: V4.4 initial baseline"')


def format_cycle_prompt(
    cycle: int,
    max_cycles: int,
    mode: str,
    current_state: dict[str, object],
    failure_report: str | None = None,
) -> list[dict[str, str]]:
    current_data = read_text(DATA_FILE) or "[]"
    current_opinions = read_text(OPINIONS_FILE)
    current_dead_ends_json = read_text(DEAD_ENDS_JSON_FILE) or json.dumps(blank_dead_ends(), indent=2)
    goal = read_text(GOAL_FILE)

    system_prompt = (
        "You are the combinatorial engine of the Avalanche V4.4.1 system.\n"
        "Output only the JSON object matching the provided schema.\n"
        "No conversational filler. No markdown fences. No extra keys.\n"
    )

    common_constraints = (
        f"- opinions_md must stay under {OPINIONS_LIMIT} words.\n"
        "- Rewrite dead_ends as valid JSON with keys basins, families, locals.\n"
        "- Basin entry shape: {id, status, claim, cited_families}.\n"
        "- Family entry shape: {id, status, claim, falsifying_arrays}.\n"
        "- Local entry shape: {failing_hypothesis, falsifying_array}.\n"
        "- Basin and family status values may only be ACTIVE or SUPERSEDED.\n"
        "- Preserve active basin and family ids unless you explicitly supersede them.\n"
        "- A basin must cite at least 2 family ids.\n"
        "- Each family must carry at least 2 distinct falsifying arrays.\n"
        "- Every tracked falsifying array across families and locals must be globally distinct.\n"
        "- On cold start with no oracle failures yet, keep basins, families, and locals empty.\n"
        "- The latest ratchet-killing oracle array must appear in tracked evidence before you are allowed to continue.\n"
        "- Basin claims must be ontology-level plain words only. No arrays, math, or code syntax.\n"
        "- Families must compress mechanisms. Locals are fresh blood, not duplicate family evidence.\n"
        "- You are bound by Occam's Razor. Do not build arithmetic epicycles, arbitrary modulo gating, or index-class exceptions.\n"
        "- Code complexity that outruns conceptual falsification will be rejected.\n"
        "- All oracle inputs are permutations of distinct positive integers. Do not rely on duplicates, lookup tables, or memorized witness caches.\n"
    )

    if mode == "grind":
        instruction = (
            f"Cycle {cycle} of {max_cycles}.\n"
            "Return updated contents for:\n"
            "- opinions_md\n"
            "- dead_ends\n"
            "- solver_py\n\n"
            f"Constraints:\n{common_constraints}"
            "- solver_py must define transduce(arr: list[int]) -> list[int].\n"
            "- Commit to one specific mathematical hypothesis.\n"
        )
    else:
        instruction = (
            "Build verification failed.\n"
            f"{failure_report or ''}\n\n"
            "All code changes have been reverted by the environment.\n"
            "Return:\n"
            "- revised opinions_md with a specific next hypothesis\n"
            "- revised dead_ends preserving active basin/family ids or explicitly superseding them\n"
            "- solver_py containing your next best implementation attempt\n"
            f"Constraints remain:\n{common_constraints}"
        )

    user_prompt = (
        f"{instruction}\n"
        f"\n# goal.md\n{goal}\n"
        f"\n# data.json\n{current_data}\n"
        f"\n# opinions.md\n{current_opinions}\n"
        f"\n# dead-ends.json\n{current_dead_ends_json}\n"
        f"\n# historical_ids\n{history_summary(current_state)}\n"
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


def strip_leading_think_block(text: str) -> str:
    stripped = text.lstrip()
    if not stripped.startswith("<think>"):
        return stripped
    end = stripped.find("</think>")
    if end == -1:
        return stripped
    return stripped[end + len("</think>") :].lstrip()


def normalize_structured_output_text(text: str) -> str:
    normalized = strip_leading_think_block(text).strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        normalized = "\n".join(lines).strip()
    return normalized


def resolve_api_key(api_key_env: str = "") -> tuple[str | None, str]:
    candidate_envs = [api_key_env] if api_key_env else []
    candidate_envs.extend(["AVALANCHE_API_KEY", "HAIMAKER_API_KEY", "OPENAI_API_KEY"])
    for env_name in candidate_envs:
        if not env_name:
            continue
        value = os.environ.get(env_name)
        if value:
            return value, env_name
    return None, candidate_envs[0] if candidate_envs else "AVALANCHE_API_KEY"


def response_format_payload(api_base: str) -> dict[str, object]:
    response_type = DEFAULT_RESPONSE_FORMAT
    if not response_type:
        response_type = "json_object" if "haimaker.ai" in api_base.lower() else "json_schema"
    if response_type == "json_object":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": OUTPUT_SCHEMA,
    }


def reset_cycle_usage() -> None:
    for key in _cycle_usage:
        _cycle_usage[key] = 0


def _extract_int(payload: object) -> int:
    if isinstance(payload, bool):
        return 0
    if isinstance(payload, int):
        return payload
    if isinstance(payload, float):
        return int(payload)
    return 0


def record_usage(payload: dict[str, object]) -> None:
    usage = payload.get("usage", {})
    if not isinstance(usage, dict):
        return
    _cycle_usage["api_call_count_cycle"] += 1
    _cycle_usage["api_prompt_tokens_cycle"] += _extract_int(usage.get("prompt_tokens", 0))
    _cycle_usage["api_completion_tokens_cycle"] += _extract_int(usage.get("completion_tokens", 0))
    total_tokens = _extract_int(usage.get("total_tokens", 0))
    if total_tokens == 0:
        total_tokens = _extract_int(usage.get("prompt_tokens", 0)) + _extract_int(usage.get("completion_tokens", 0))
    _cycle_usage["api_total_tokens_cycle"] += total_tokens
    completion_details = usage.get("completion_tokens_details", {})
    if isinstance(completion_details, dict):
        _cycle_usage["api_reasoning_tokens_cycle"] += _extract_int(
            completion_details.get("reasoning_tokens", 0)
        )


def _solver_entrypoint_error(solver_code: str) -> str | None:
    try:
        tree = ast.parse(solver_code)
    except SyntaxError as exc:
        return f"solver_py syntax error: {exc.msg} at line {exc.lineno}."
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "transduce":
            return None
    return "solver_py must define transduce(arr: list[int]) -> list[int]."


def _literal_int_count(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant):
        return 1 if isinstance(node.value, int) and not isinstance(node.value, bool) else 0
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        total = 0
        for elt in node.elts:
            count = _literal_int_count(elt)
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


def _occam_tax_error(dead_ends: dict[str, object], solver_code: str) -> str | None:
    complexity = solver_ast_complexity(solver_code)
    family_count = len(dead_ends.get("families", [])) if isinstance(dead_ends, dict) else 0
    limit = 15 + (family_count * 5)
    if complexity > limit:
        return (
            f"Occam tax violated: solver_ast_complexity {complexity} exceeds limit {limit} "
            f"for {family_count} active families."
        )
    return None


def invoke_openai(
    messages: list[dict[str, str]],
    model: str,
    api_base: str,
    *,
    api_key_env: str = "",
) -> dict[str, object]:
    api_key, source_env = resolve_api_key(api_key_env)
    if not api_key:
        raise RuntimeError(f"{source_env} is not set.")

    payload = {
        "model": model,
        "temperature": DEFAULT_TEMPERATURE,
        "messages": messages,
        "max_tokens": 1200,
        "response_format": response_format_payload(api_base),
    }
    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AvalancheRawV44/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"API connection error: {exc}") from exc

    try:
        record_usage(payload)
        message = payload["choices"][0]["message"]
        content = normalize_structured_output_text(extract_message_text(message))
        return json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Malformed API response: {payload}") from exc


def validate_cycle_output(
    payload: dict[str, object],
    previous_state: dict[str, object],
    *,
    required_falsifier: dict[str, list[int]] | None = None,
) -> str | None:
    opinions_md = str(payload.get("opinions_md", ""))
    solver_py = str(payload.get("solver_py", ""))
    dead_ends = payload.get("dead_ends", blank_dead_ends())

    opinions_words = len(opinions_md.split())
    if opinions_words > OPINIONS_LIMIT:
        return f"opinions_md exceeds {OPINIONS_LIMIT} words ({opinions_words})."
    solver_error = _solver_entrypoint_error(solver_py)
    if solver_error:
        return solver_error
    anti_cache = anti_cache_error(solver_py)
    if anti_cache:
        return anti_cache
    if not isinstance(dead_ends, dict):
        return "dead_ends must be an object."

    previous_active = previous_state.get("active", blank_dead_ends())
    if not isinstance(previous_active, dict):
        previous_active = blank_dead_ends()
    errors = validate_dead_ends(dead_ends, previous_active, previous_state)
    if required_falsifier is None and count_data_pairs() == 0:
        if dead_ends.get("basins") or dead_ends.get("families") or dead_ends.get("locals"):
            errors.append("Cold start cannot invent dead ends before the first oracle contradiction exists.")
    occam_error = _occam_tax_error(dead_ends, solver_py)
    if occam_error:
        errors.append(occam_error)
    if required_falsifier is not None:
        required_input = required_falsifier.get("input")
        if not isinstance(required_input, list):
            errors.append("Latest contradictory oracle result is missing its input array.")
        elif array_signature(required_input) not in tracked_array_signatures(dead_ends):
            errors.append("The latest contradictory oracle array must appear in tracked dead-end evidence.")
    if errors:
        return " | ".join(errors)
    return None


def request_cycle_output(
    cycle: int,
    max_cycles: int,
    model: str,
    api_base: str,
    mode: str,
    current_state: dict[str, object],
    failure_report: str | None = None,
    required_falsifier: dict[str, list[int]] | None = None,
    api_key_env: str = "",
) -> dict[str, object]:
    messages = format_cycle_prompt(cycle, max_cycles, mode, current_state, failure_report)
    if required_falsifier is not None:
        messages = messages + [
            {
                "role": "user",
                "content": (
                    "Fresh blood rule: the latest contradictory oracle input must appear verbatim in tracked dead-end "
                    f"evidence during this repair step.\nLatest oracle input: {json.dumps(required_falsifier.get('input', []))}"
                ),
            }
        ]
    retry_messages = list(messages)
    last_error = "No response received."
    for _ in range(SYNC_MAX_TURNS):
        payload = invoke_openai(retry_messages, model, api_base, api_key_env=api_key_env)
        error = validate_cycle_output(payload, current_state, required_falsifier=required_falsifier)
        if not error:
            return payload
        last_error = error
        retry_messages = retry_messages + [
            {
                "role": "user",
                "content": (
                    "[SYSTEM LINTER ERROR] Validation failed: "
                    f"{error} Fix and resubmit strictly adhering to constraints."
                    + (
                        ""
                        if required_falsifier is None
                        else "\nAt minimum, include the exact latest oracle input as one tracked falsifying array: "
                        f"{json.dumps(required_falsifier.get('input', []))}"
                    )
                ),
            }
        ]
    raise RuntimeError(f"CYCLE_CRASH_FORMAT: {last_error}")


def persist_model_output(payload: dict[str, object]) -> None:
    opinions_md = str(payload.get("opinions_md", "")).strip()
    dead_ends = payload.get("dead_ends", blank_dead_ends())
    solver_py = str(payload.get("solver_py", "")).rstrip()
    write_text(OPINIONS_FILE, opinions_md + "\n")
    write_json(DEAD_ENDS_JSON_FILE, dead_ends)
    write_text(DEAD_ENDS_FILE, render_dead_ends_md(dead_ends))
    write_text(SOLVER_FILE, solver_py + "\n")


def compute_cycle_metrics(
    cycle: int,
    previous_opinions: str,
    previous_state: dict[str, object],
    current_state: dict[str, object],
    attempted_solver_code: str,
    previous_complexity: int | None = None,
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
    metrics.update(_cycle_usage)
    metrics.update(dead_end_metrics(previous_active, current_active, current_state))
    _metric_history.append(metrics)
    with open(METRICS_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(metrics) + "\n")
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Avalanche V4.4.1 in an isolated raw-model workspace.")
    parser.add_argument("--workspace", default=r"C:\terrarium-v44-raw", help="Workspace directory.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI-compatible model slug for the raw API backend.")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="OpenAI-compatible API base URL.")
    parser.add_argument(
        "--api-key-env",
        default=DEFAULT_API_KEY_ENV,
        help="Preferred environment variable name for the API key. Falls back to AVALANCHE_API_KEY, HAIMAKER_API_KEY, then OPENAI_API_KEY.",
    )
    parser.add_argument("--max-cycles", type=int, default=DEFAULT_MAX_CYCLES, help="Maximum cycle count.")
    parser.add_argument("--tests-per-cycle", type=int, default=5, help="Random ratchet tests per cycle.")
    parser.add_argument(
        "--bootstrap-only",
        action="store_true",
        help="Create the V4.4 workspace files and exit without invoking the API.",
    )
    parser.add_argument(
        "--oracle-mode",
        choices=["first-failure", "adversarial"],
        default="first-failure",
        help="Counterexample selection strategy after a failed solver.",
    )
    parser.add_argument("--seed", type=int, default=44, help="Random seed for reproducible test generation.")
    parser.add_argument(
        "--response-format",
        choices=["json_schema", "json_object"],
        default=DEFAULT_RESPONSE_FORMAT or None,
        help="Override the API response_format mode. Defaults to json_object for Haimaker and json_schema otherwise.",
    )
    parser.add_argument(
        "--continue-cycles",
        type=int,
        default=0,
        help="Additional cycles to run after the existing completed history in this workspace.",
    )
    return parser.parse_args()


def main() -> None:
    global _metric_history
    args = parse_args()
    global DEFAULT_RESPONSE_FORMAT
    _rng.seed(args.seed)
    if args.response_format:
        DEFAULT_RESPONSE_FORMAT = args.response_format
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    os.chdir(workspace)

    setup_workspace()
    if args.bootstrap_only:
        write_status(0, args.max_cycles, "BOOTSTRAPPED")
        print(f"  Avalanche V4.4.1 workspace bootstrapped at {workspace}")
        return

    _metric_history, previous_complexity = load_existing_metric_history()
    cycle = len(_metric_history)
    target_cycles = args.max_cycles
    if args.continue_cycles > 0:
        target_cycles = cycle + args.continue_cycles
    last_error: str | None = None

    while cycle < target_cycles:
        cycle += 1
        reset_cycle_usage()
        previous_opinions = read_text(OPINIONS_FILE)
        previous_state = load_state(DEAD_END_STATE_FILE)
        write_status(cycle, target_cycles, "GRIND")

        try:
            grind_payload = request_cycle_output(
                cycle,
                args.max_cycles,
                args.model,
                args.api_base,
                mode="grind",
                current_state=previous_state,
                api_key_env=args.api_key_env,
            )
        except RuntimeError as exc:
            last_error = str(exc)
            write_status(cycle, target_cycles, "FORMAT_FAIL", last_result="FAIL", last_error=last_error)
            continue

        persist_model_output(grind_payload)
        attempted_solver_code = str(grind_payload["solver_py"])

        write_status(cycle, target_cycles, "RATCHET")
        success, output, first_failure = evaluate_solver(generate_test_cases(args.tests_per_cycle))

        if success:
            current_state = merge_state(previous_state, grind_payload["dead_ends"], cycle)  # type: ignore[arg-type]
            save_state(DEAD_END_STATE_FILE, current_state)
            run_command('git add . && git commit -m "Avalanche: V4.4.1 raw ratchet advanced"')
            metrics = compute_cycle_metrics(
                cycle,
                previous_opinions,
                previous_state,
                current_state,
                attempted_solver_code,
                previous_complexity,
            )
            previous_complexity = int(metrics["solver_ast_complexity"])
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

        try:
            fail_payload = request_cycle_output(
                cycle,
                args.max_cycles,
                args.model,
                args.api_base,
                mode="sync-fail",
                current_state=previous_state,
                failure_report=output,
                required_falsifier=failing_pairs[0],
                api_key_env=args.api_key_env,
            )
        except RuntimeError as exc:
            last_error = str(exc)
            write_status(cycle, target_cycles, "FORMAT_FAIL", last_result="FAIL", last_error=last_error)
            continue

        persist_model_output(fail_payload)
        current_state = merge_state(previous_state, fail_payload["dead_ends"], cycle)  # type: ignore[arg-type]
        save_state(DEAD_END_STATE_FILE, current_state)
        metrics = compute_cycle_metrics(
            cycle,
            previous_opinions,
            previous_state,
            current_state,
            attempted_solver_code,
            previous_complexity,
        )
        previous_complexity = int(metrics["solver_ast_complexity"])
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


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  [!] Avalanche V4.4 powered down by user.")
