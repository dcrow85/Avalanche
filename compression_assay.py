#!/usr/bin/env python3
"""
Compression Assay (V4.7).

Three metacognitive pressure mechanisms replacing the E_ratio gate:
  1. Compression Gradient — shrinking context window over time
  2. Compression Pass — directed distillation when oracle stagnates
  3. Altitude Cycles — periodic metacognitive surveys at three zoom levels

No gate. No quarantine. No branches. Simple loop with three orthogonal
interventions, each independently togglable for isolation experiments.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Pop the recursion guard before importing the hypervisor as a library.
os.environ.pop("AVALANCHE_ACTIVE", None)

import hypervisor_v44 as hv
from actuator_metrics import evaluate_solver_fractional
from v44_epistemics import (
    load_state,
    merge_state,
    save_state,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TELEMETRY_FILE = "telemetry.jsonl"
COMPRESSION_LOG_FILE = "compression_log.jsonl"
FORMAT_FAIL_MAX_RETRIES = 2

# Decay functions expect total_cycles to be set; we compute it from
# the gradient floor, initial window, and max_cycles.

SYSTEM_PROMPT = (
    "You are the combinatorial engine of the Avalanche V4.7 system.\n"
    "Output only the JSON object matching the provided schema.\n"
    "No conversational filler. No markdown fences. No extra keys.\n"
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class GradientState:
    """Tracks the shrinking context window."""
    initial_window: int = 1200
    floor: int = 400
    decay: str = "linear"  # "linear", "log", or "stepped"
    total_cycles: int = 200
    current_window: int = 0  # set in __post_init__
    cycle_count: int = 0

    def __post_init__(self):
        if self.current_window == 0:
            self.current_window = self.initial_window

    def tick(self) -> int:
        """Advance one cycle, return new window size."""
        self.cycle_count += 1
        span = self.initial_window - self.floor

        if self.decay == "linear":
            progress = min(1.0, self.cycle_count / max(1, self.total_cycles))
            self.current_window = max(self.floor, int(self.initial_window - span * progress))

        elif self.decay == "log":
            # Logarithmic decay: fast initial drop, slow tail
            progress = min(1.0, self.cycle_count / max(1, self.total_cycles))
            # log(1 + progress * (e-1)) / log(e) = log(1 + progress * (e-1))
            log_progress = math.log(1.0 + progress * (math.e - 1.0))
            self.current_window = max(self.floor, int(self.initial_window - span * log_progress))

        elif self.decay == "stepped":
            # Plateau-drop: hold for 25% of cycles, drop linearly over 10%, repeat
            step_size = max(1, self.total_cycles // 4)
            steps_completed = self.cycle_count // step_size
            max_steps = 4
            steps_completed = min(steps_completed, max_steps)
            self.current_window = max(self.floor, int(self.initial_window - span * steps_completed / max_steps))

        return self.current_window

    @property
    def prompt_budget(self) -> int:
        return int(self.current_window * 0.6)

    @property
    def output_budget(self) -> int:
        return self.current_window - self.prompt_budget

    @property
    def max_graveyard_entries(self) -> int:
        graveyard_budget = int(self.current_window * 0.15)
        return max(3, graveyard_budget // 80)


@dataclass
class CompressionPassState:
    """Tracks oracle stagnation for compression pass triggering."""
    stagnation_window: int = 8
    target_compression: float = 0.5
    recent_scores: list[float] = field(default_factory=list)
    triggered_count: int = 0

    def record(self, oracle_score: float) -> None:
        """Append score, keep last stagnation_window entries."""
        self.recent_scores.append(round(oracle_score, 4))
        if len(self.recent_scores) > self.stagnation_window:
            self.recent_scores.pop(0)

    def should_trigger(self) -> bool:
        """True if last stagnation_window scores are all identical (stagnant)."""
        if len(self.recent_scores) < self.stagnation_window:
            return False
        return len(set(self.recent_scores)) == 1

    def mark_triggered(self) -> None:
        self.triggered_count += 1
        self.recent_scores.clear()


@dataclass
class AltitudeState:
    """Tracks periodic metacognitive survey cycles."""
    frequency: int = 10
    altitudes: list[str] = field(default_factory=lambda: ["low", "medium", "high"])
    current_index: int = 0
    last_map: str = ""

    def should_fire(self, cycle: int) -> bool:
        return cycle > 0 and cycle % self.frequency == 0

    def next_altitude(self) -> str:
        alt = self.altitudes[self.current_index % len(self.altitudes)]
        self.current_index += 1
        return alt


# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------

def _append_jsonl(path: str, record: dict) -> None:
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------

def _snapshot_workspace() -> dict[str, str]:
    return {
        "opinions_md": hv.read_text(hv.OPINIONS_FILE),
        "dead_ends_json": hv.read_text(hv.DEAD_ENDS_JSON_FILE),
        "solver_py": hv.read_text(hv.SOLVER_FILE),
    }


def _restore_workspace(snapshot: dict[str, str]) -> None:
    hv.write_text(hv.OPINIONS_FILE, snapshot["opinions_md"])
    de = json.loads(snapshot["dead_ends_json"]) if snapshot["dead_ends_json"] else {}
    hv.write_json(hv.DEAD_ENDS_JSON_FILE, de)
    from v44_epistemics import render_dead_ends_md
    hv.write_text(hv.DEAD_ENDS_FILE, render_dead_ends_md(de))
    hv.write_text(hv.SOLVER_FILE, snapshot["solver_py"])


# ---------------------------------------------------------------------------
# Altitude map extraction
# ---------------------------------------------------------------------------

def extract_altitude_map(payload: dict[str, object]) -> str:
    """Extract the ## Altitude Map section from model output."""
    opinions = str(payload.get("opinions_md", ""))
    # Look for ## Altitude Map section
    match = re.search(r'## Altitude Map\s*\n(.*?)(?=\n##|\Z)', opinions, re.DOTALL)
    if match:
        return match.group(0).strip()[:1200]  # Cap at 300 tokens ~ 1200 chars
    # Fallback: use the full opinions as the map if short enough
    if len(opinions) <= 1200:
        return opinions.strip()
    return opinions[:1200].strip()


# ---------------------------------------------------------------------------
# Compression pass
# ---------------------------------------------------------------------------

def run_compression_pass(
    cycle: int,
    args: argparse.Namespace,
    gradient: GradientState,
    passes: CompressionPassState,
) -> None:
    """Directed distillation cycle. Model compresses its theory."""
    current_theory = hv.read_text(hv.OPINIONS_FILE) or ""
    current_dead_ends = hv.read_text(hv.DEAD_ENDS_JSON_FILE) or "{}"
    target_len = int(len(current_theory) * passes.target_compression)

    prompt = (
        f"COMPRESSION PASS: Your theory has grown too large for the shrinking context window.\n\n"
        f"Current theory length: {len(current_theory)} characters\n"
        f"Target length: {target_len} characters\n\n"
        f"Rewrite your theory to fit within {target_len} characters. Preserve your strongest hypotheses "
        f"and most important dead-end exclusions. Drop speculative content and redundant phrasing.\n"
        f"Output ONLY the JSON object with a single key 'opinions_md' containing the compressed theory text."
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                prompt
                + f"\n\n# Current opinions.md\n{current_theory}"
                + f"\n\n# Current dead-ends.json\n{current_dead_ends}"
            ),
        },
    ]

    try:
        result = hv.invoke_openai(
            messages, args.model, args.api_base,
            api_key_env=args.api_key_env,
            max_tokens=gradient.output_budget,
        )
        compressed = str(result.get("opinions_md", "")).strip()
        if compressed:
            hv.write_text(hv.OPINIONS_FILE, compressed + "\n")
            hv.run_command('git add . && git commit -m "V4.7: compression pass"')
            print(f"  [COMPRESS] Cycle {cycle}: {len(current_theory)} -> {len(compressed)} chars")
        else:
            print(f"  [COMPRESS] Cycle {cycle}: empty result, skipping")
    except RuntimeError as exc:
        print(f"  [COMPRESS] Cycle {cycle}: FAILED: {exc}")

    passes.mark_triggered()

    _append_jsonl(COMPRESSION_LOG_FILE, {
        "cycle": cycle,
        "event": "compression_pass",
        "theory_len_before": len(current_theory),
        "target_len": target_len,
        "triggered_count": passes.triggered_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def request_altitude_map(
    cycle: int,
    args: argparse.Namespace,
    gradient: GradientState,
    current_state: dict[str, object],
    altitude_mode: str,
    previous_map: str,
) -> str:
    """Run a metacognitive survey without invoking the solver schema."""
    prompt_messages = hv.format_cycle_prompt(
        cycle,
        args.max_cycles,
        "grind",
        current_state,
        altitude_mode=altitude_mode,
        context_window_hud=(
            f"Context budget: {gradient.output_budget} tokens (output limit). "
            f"Window: {gradient.current_window}/{gradient.initial_window}."
        ),
        altitude_map=previous_map or None,
        max_graveyard_entries=gradient.max_graveyard_entries,
        prompt_budget_tokens=gradient.prompt_budget,
    )
    altitude_messages = [
        {
            "role": "system",
            "content": (
                "You are the metacognitive survey instrument of Avalanche V4.7.\n"
                "Output only a single raw JSON object with exactly one key: altitude_map.\n"
                "The altitude_map value must be a plain string containing the survey text.\n"
                "No markdown fences. No extra keys."
            ),
        },
        prompt_messages[-1],
    ]
    payload = hv.invoke_openai(
        altitude_messages,
        args.model,
        args.api_base,
        api_key_env=args.api_key_env,
        max_tokens=gradient.output_budget,
        response_format_override="json_object",
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Altitude response must be a JSON object.")
    altitude_text = str(payload.get("altitude_map", "")).strip()
    if not altitude_text:
        altitude_text = extract_altitude_map(payload)
    altitude_text = altitude_text.strip()
    if not altitude_text:
        raise RuntimeError("Altitude response did not include altitude_map.")
    return altitude_text[:1200]


# ---------------------------------------------------------------------------
# Main compression loop
# ---------------------------------------------------------------------------

def run_compression_loop(args: argparse.Namespace) -> str:
    """Run the compression experiment loop. Returns final status string."""

    rng = random.Random(args.seed + args.run_id)
    hv._rng.seed(args.seed + args.run_id)

    gradient = GradientState(
        initial_window=args.initial_window,
        floor=args.floor,
        decay=args.decay,
        total_cycles=args.max_cycles,
    )
    passes = CompressionPassState(stagnation_window=args.stagnation_window)
    altitude = AltitudeState(frequency=args.altitude_frequency)

    # Convergence state
    consecutive_perfect: int = 0
    previous_theory_hash: str | None = None
    best_oracle_score: float = 0.0
    previous_complexity: int = 0

    print(f"\n  [V4.7] Starting compression loop")
    print(f"  [V4.7] Gradient: {args.initial_window} -> {args.floor} ({args.decay})")
    print(f"  [V4.7] Features: gradient={'ON' if not args.no_gradient else 'OFF'}, "
          f"passes={'ON' if not args.no_passes else 'OFF'}, "
          f"altitude={'ON' if not args.no_altitude else 'OFF'}")

    for cycle in range(1, args.max_cycles + 1):
        hv.reset_cycle_usage()
        previous_opinions = hv.read_text(hv.OPINIONS_FILE)
        previous_state = load_state(hv.DEAD_END_STATE_FILE)

        # Advance gradient
        if not args.no_gradient:
            gradient.tick()
        else:
            gradient.cycle_count = cycle

        current_window = gradient.current_window
        output_budget = gradient.output_budget

        # --- Compression pass check (before altitude, before normal cycle) ---
        if not args.no_passes and passes.should_trigger():
            print(f"  [V4.7] Cycle {cycle} — COMPRESSION PASS (window={current_window})")
            hv.write_status(cycle, args.max_cycles, "COMPRESSION_PASS")
            run_compression_pass(cycle, args, gradient, passes)
            continue

        # --- Altitude check ---
        altitude_mode = None
        if not args.no_altitude and altitude.should_fire(cycle):
            altitude_mode = altitude.next_altitude()

        mode_label = f"ALTITUDE_{altitude_mode.upper()}" if altitude_mode else "GRIND"
        hv.write_status(cycle, args.max_cycles, mode_label)
        print(f"  [V4.7] Cycle {cycle}/{args.max_cycles} — {mode_label} (window={current_window}, budget={output_budget})")

        # --- Build prompt kwargs ---
        prompt_kwargs: dict[str, Any] = {
            "context_window_hud": (
                f"Context budget: {output_budget} tokens (output limit). "
                f"Window: {current_window}/{gradient.initial_window}."
            ),
            "max_graveyard_entries": gradient.max_graveyard_entries,
            "prompt_budget_tokens": gradient.prompt_budget,
        }
        if altitude_mode:
            prompt_kwargs["altitude_mode"] = altitude_mode
        if altitude.last_map:
            prompt_kwargs["altitude_map"] = altitude.last_map

        # --- Altitude cycle: extract map and skip oracle ---
        if altitude_mode:
            altitude_text = None
            for format_attempt in range(FORMAT_FAIL_MAX_RETRIES + 1):
                try:
                    altitude_text = request_altitude_map(
                        cycle, args, gradient, previous_state, altitude_mode, altitude.last_map
                    )
                    break
                except RuntimeError as exc:
                    if format_attempt < FORMAT_FAIL_MAX_RETRIES:
                        print(f"  [V4.7] ALTITUDE_FAIL (retry {format_attempt + 1}): {exc}")
                        hv.reset_cycle_usage()
                        continue
                    print(f"  [V4.7] ALTITUDE_FATAL: {exc}")
                    hv.write_status(
                        cycle,
                        args.max_cycles,
                        "FORMAT_FATAL",
                        last_result="FAIL",
                        last_error=str(exc),
                    )
            if altitude_text is None:
                _append_jsonl(TELEMETRY_FILE, {
                    "cycle": cycle,
                    "window": current_window,
                    "prompt_budget": gradient.prompt_budget,
                    "output_budget": output_budget,
                    "altitude_mode": altitude_mode,
                    "event": "altitude_fatal",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                continue
            altitude.last_map = altitude_text
            print(f"  [ALTITUDE] {altitude_mode}: map={len(altitude.last_map)} chars")

            _append_jsonl(TELEMETRY_FILE, {
                "cycle": cycle, "window": current_window,
                "prompt_budget": gradient.prompt_budget,
                "output_budget": output_budget,
                "altitude_mode": altitude_mode,
                "altitude_map_len": len(altitude.last_map),
                "altitude_map": altitude.last_map,
                "compression_pass": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            _append_jsonl(COMPRESSION_LOG_FILE, {
                "cycle": cycle,
                "event": f"altitude_{altitude_mode}",
                "map_len": len(altitude.last_map),
                "altitude_map": altitude.last_map,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            continue

        # --- Request cycle output ---
        workspace_snapshot = _snapshot_workspace()
        grind_payload = None

        for format_attempt in range(FORMAT_FAIL_MAX_RETRIES + 1):
            try:
                grind_payload = hv.request_cycle_output(
                    cycle, args.max_cycles, args.model, args.api_base,
                    mode="grind", current_state=previous_state,
                    api_key_env=args.api_key_env,
                    max_tokens=output_budget,
                    **prompt_kwargs,
                )
                break
            except RuntimeError as exc:
                if format_attempt < FORMAT_FAIL_MAX_RETRIES:
                    print(f"  [V4.7] FORMAT_FAIL (retry {format_attempt + 1}): {exc}")
                    hv.reset_cycle_usage()
                    continue
                else:
                    print(f"  [V4.7] FORMAT_FATAL: {exc}")
                    hv.write_status(cycle, args.max_cycles, "FORMAT_FATAL",
                                    last_result="FAIL", last_error=str(exc))
                    break

        if grind_payload is None:
            _append_jsonl(TELEMETRY_FILE, {
                "cycle": cycle, "window": current_window,
                "prompt_budget": gradient.prompt_budget,
                "output_budget": output_budget,
                "event": "format_fatal",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            continue

        # --- Normal cycle: persist, evaluate, ratchet ---
        proposed_solver = str(grind_payload.get("solver_py", ""))
        proposed_dead_ends = grind_payload.get("dead_ends", {})

        # Temporarily write solver for fractional oracle evaluation
        hv.write_text(hv.SOLVER_FILE, proposed_solver + "\n")

        # Oracle: fixed suite for compression pass trigger
        fixed_suite = hv.build_fixed_oracle_suite()
        fixed_score, fixed_passed, fixed_total, _ = evaluate_solver_fractional(
            fixed_suite, hv.hidden_law, str(Path(hv.SOLVER_FILE))
        )

        # Oracle: combined (fixed + random) for ratchet/telemetry
        random_cases = [hv.generate_permutation_array(rng) for _ in range(args.tests_per_cycle)]
        all_cases = fixed_suite + random_cases
        oracle_score, passed, total, failure_report = evaluate_solver_fractional(
            all_cases, hv.hidden_law, str(Path(hv.SOLVER_FILE))
        )

        # Record fixed score for compression pass trigger
        passes.record(fixed_score)

        # Restore solver, then do full persist + ratchet
        hv.write_text(hv.SOLVER_FILE, workspace_snapshot["solver_py"])

        # Now persist and run standard ratchet
        hv.persist_model_output(grind_payload)
        hv.write_status(cycle, args.max_cycles, "RATCHET")

        ratchet_cases = [hv.generate_permutation_array(rng) for _ in range(args.tests_per_cycle)]
        success, output, first_failure = hv.evaluate_solver(ratchet_cases)

        if success:
            current_state = merge_state(previous_state, grind_payload["dead_ends"], cycle)
            save_state(hv.DEAD_END_STATE_FILE, current_state)
            hv.run_command('git add . && git commit -m "V4.7: ratchet advanced"')
            metrics = hv.compute_cycle_metrics(
                cycle, previous_opinions, previous_state,
                current_state, proposed_solver, previous_complexity,
            )
            previous_complexity = int(metrics.get("solver_ast_complexity", 0))
            hv.write_status(cycle, args.max_cycles, "PASS", last_result="PASS", metrics=metrics)
            print(f"  [V4.7] PASS cycle {cycle}: oracle={oracle_score:.2f} ({passed}/{total})")
        else:
            # Fail-sync path
            failing_pairs = [first_failure] if first_failure else []
            if not failing_pairs:
                fallback = hv.generate_permutation_array(rng)
                failing_pairs = [{"input": fallback, "expected": hv.hidden_law(fallback)}]
            hv.update_data_file(failing_pairs)
            hv.run_command("git reset --hard HEAD")
            hv.run_command("git clean -fd")

            try:
                fail_payload = hv.request_cycle_output(
                    cycle, args.max_cycles, args.model, args.api_base,
                    mode="sync-fail", current_state=previous_state,
                    failure_report=output, required_falsifier=failing_pairs[0],
                    api_key_env=args.api_key_env,
                    max_tokens=output_budget,
                    **{k: v for k, v in prompt_kwargs.items() if k != "altitude_mode"},
                )
                hv.persist_model_output(fail_payload)
                current_state = merge_state(previous_state, fail_payload["dead_ends"], cycle)
            except RuntimeError as exc:
                print(f"  [V4.7] SYNC FORMAT_FAIL: {exc}")
                current_state = previous_state

            save_state(hv.DEAD_END_STATE_FILE, current_state)
            metrics = hv.compute_cycle_metrics(
                cycle, previous_opinions, previous_state,
                current_state, proposed_solver, previous_complexity,
            )
            previous_complexity = int(metrics.get("solver_ast_complexity", 0))
            hv.write_status(cycle, args.max_cycles, "SYNC_FAIL", last_result="FAIL",
                            last_error=output[-500:] if output else "", metrics=metrics)
            print(f"  [V4.7] FAIL cycle {cycle}: oracle={oracle_score:.2f} ({passed}/{total})")

        # --- Convergence detection ---
        current_theory = hv.read_text(hv.OPINIONS_FILE).strip()
        current_hash = hashlib.md5(current_theory.encode()).hexdigest()
        if oracle_score >= 1.0 and current_hash == previous_theory_hash:
            consecutive_perfect += 1
        else:
            consecutive_perfect = 0 if oracle_score < 1.0 else 1
        previous_theory_hash = current_hash

        if consecutive_perfect >= 5:
            print(f"\n  [CONVERGED] 5 consecutive perfect oracle cycles with stable theory.")
            print(f"  [CONVERGED] Final oracle: {oracle_score:.2f} ({passed}/{total})")
            _append_jsonl(TELEMETRY_FILE, {
                "cycle": cycle, "window": current_window,
                "prompt_budget": gradient.prompt_budget,
                "output_budget": output_budget,
                "oracle_fixed": round(fixed_score, 4),
                "oracle_combined": round(oracle_score, 4),
                "event": "converged",
                "consecutive_perfect": consecutive_perfect,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            hv.write_status(cycle, args.max_cycles, "CONVERGED", last_result="SOLVED")
            return "CONVERGED"

        best_oracle_score = max(best_oracle_score, oracle_score)

        # --- Telemetry ---
        theory_len = len(current_theory)
        dead_end_count = len(proposed_dead_ends.get("basins", [])) + \
                         len(proposed_dead_ends.get("families", [])) + \
                         len(proposed_dead_ends.get("locals", []))

        _append_jsonl(TELEMETRY_FILE, {
            "cycle": cycle,
            "window": current_window,
            "prompt_budget": gradient.prompt_budget,
            "output_budget": output_budget,
            "oracle_fixed": round(fixed_score, 4),
            "oracle_combined": round(oracle_score, 4),
            "altitude_mode": None,
            "compression_pass": False,
            "theory_hash": current_hash[:8],
            "theory_len": theory_len,
            "dead_end_count": dead_end_count,
            "graveyard_entries_shown": gradient.max_graveyard_entries if not args.no_gradient else None,
            "best_oracle": round(best_oracle_score, 4),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # Max cycles reached
    hv.write_status(args.max_cycles, args.max_cycles, "MAX_CYCLES", last_result="COMPLETE")
    print(f"\n  [V4.7] Max cycles ({args.max_cycles}) reached. Best oracle: {best_oracle_score:.2f}")
    return "MAX_CYCLES"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compression Assay (V4.7) — metacognitive pressure experiment"
    )

    # Core args
    parser.add_argument("--run-id", type=int, required=True, help="Run index")
    parser.add_argument("--workspace-root", type=str, default="runs/v47",
                        help="Parent directory for all V4.7 workspaces")
    parser.add_argument("--max-cycles", type=int, default=200,
                        help="Maximum cycles before stopping")
    parser.add_argument("--seed", type=int, default=47, help="RNG seed base")

    # Model/API
    parser.add_argument("--model", default="anthropic/claude-haiku-4-5",
                        help="Model slug for Haimaker/OpenAI-compatible API")
    parser.add_argument("--api-base", default="https://api.haimaker.ai/v1",
                        help="OpenAI-compatible API base URL")
    parser.add_argument("--api-key-env", default="HAIMAKER_KEY",
                        help="Environment variable name for API key")
    parser.add_argument("--tests-per-cycle", type=int, default=5,
                        help="Random oracle test cases per cycle (in addition to fixed suite)")
    parser.add_argument("--response-format", choices=["json_schema", "json_object"],
                        default=None, help="Override API response format")
    parser.add_argument("--hunches", action="store_true",
                        help="Enable subliminal ledger (hunches.md)")

    # Compression gradient
    parser.add_argument("--initial-window", type=int, default=1200,
                        help="Starting max_tokens")
    parser.add_argument("--floor", type=int, default=400,
                        help="Minimum max_tokens")
    parser.add_argument("--decay", choices=["linear", "log", "stepped"], default="linear",
                        help="Gradient decay curve")
    parser.add_argument("--no-gradient", action="store_true",
                        help="Disable compression gradient (fixed window)")

    # Compression passes
    parser.add_argument("--stagnation-window", type=int, default=8,
                        help="Consecutive identical oracle scores to trigger compression pass")
    parser.add_argument("--no-passes", action="store_true",
                        help="Disable compression passes")

    # Altitude cycles
    parser.add_argument("--altitude-frequency", type=int, default=10,
                        help="Altitude survey every N cycles")
    parser.add_argument("--no-altitude", action="store_true",
                        help="Disable altitude cycles")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Set response format if overridden
    if args.response_format:
        hv.DEFAULT_RESPONSE_FORMAT = args.response_format

    # Enable hunches if requested
    if args.hunches:
        hv.HUNCHES_ENABLED = True

    # Set up workspace
    workspace_root = Path(args.workspace_root).resolve()
    workspace = workspace_root / f"run-{args.run_id}"
    workspace.mkdir(parents=True, exist_ok=True)
    os.chdir(workspace)

    hv.setup_workspace()

    # Add assay-specific files to gitignore
    from v44_epistemics import SUPERSEDED_LOG_FILE
    assay_ignores = {TELEMETRY_FILE, COMPRESSION_LOG_FILE, SUPERSEDED_LOG_FILE}
    if args.hunches:
        assay_ignores.add(hv.HUNCHES_FILE)
    gitignore_path = ".gitignore"
    existing = set()
    if os.path.exists(gitignore_path):
        existing = {line.strip() for line in hv.read_text(gitignore_path).splitlines() if line.strip()}
    new_entries = assay_ignores - existing
    if new_entries:
        hv.write_text(gitignore_path, "\n".join(sorted(existing | assay_ignores)) + "\n")
        hv.run_command('git add .gitignore && git commit -m "V4.7: add telemetry files to gitignore"')

    # Load any existing metric history (for continuation support)
    hv._metric_history, _ = hv.load_existing_metric_history()

    print(f"\n  === COMPRESSION ASSAY V4.7: Run {args.run_id} ===")
    print(f"  Workspace: {workspace}")
    print(f"  Model: {args.model}")
    print(f"  Seed: {args.seed + args.run_id}")

    status = run_compression_loop(args)

    print(f"\n  === V4.7 COMPLETE: {status} ===")


if __name__ == "__main__":
    main()
