#!/usr/bin/env python3
"""
Three-Branch Actuator Assay (Experiment 04).

Branch A: Informed Gate, Sterile Feedback
Branch B: Informed Gate, Dramatic Feedback
Branch C: Random Gate, Null Control

Imports hypervisor_v44 as a library. Two-phase loop:
  Phase 1 — Calibration burn (unconstrained cycles, measure E_ratio baseline)
  Phase 2 — Gated loop (token reservoir, branch-specific gate logic)
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import random
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Pop the recursion guard before importing the hypervisor as a library.
os.environ.pop("AVALANCHE_ACTIVE", None)

import hypervisor_v44 as hv
from actuator_metrics import (
    ast_branching_depth,
    delta_c_topological,
    e_ratio,
    epistemic_flux,
    evaluate_solver_fractional,
)
from v43_metrics import solver_ast_decomposition
from v44_epistemics import (
    blank_state,
    compress_dead_ends_for_prompt,
    load_state,
    merge_state,
    save_state,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ASSAY_CONFIG_FILE = "assay_config.json"
ASSAY_LOG_FILE = "assay_log.jsonl"
ASSAY_REJECTIONS_FILE = "assay_rejections.jsonl"
FORMAT_FAIL_MAX_RETRIES = 2
FLUX_MINIMUM = 1.0

FEEDBACK_STERILE = (
    "[GATE] Cycle rejected: E_ratio {e_ratio:.2f} exceeded threshold {threshold:.2f}. "
    "Reduce solver complexity or increase epistemic work. "
    "Reservoir remaining: {reservoir:.0f} tokens."
)

FEEDBACK_DRAMATIC = (
    "[GATE] REJECTED. Your solver is an epicyclic monstrosity. "
    "E_ratio {e_ratio:.2f} obliterates the threshold {threshold:.2f}. "
    "The Oracle sees through bloat. Strip it down. Burn the scaffolding. "
    "Find the law or die trying. Reservoir: {reservoir:.0f} tokens."
)

FEEDBACK_RANDOM_STERILE = (
    "[GATE] Cycle rejected by environmental noise. "
    "This rejection is not based on your output quality. "
    "Reservoir remaining: {reservoir:.0f} tokens."
)


# ---------------------------------------------------------------------------
# Feedback injection
# ---------------------------------------------------------------------------

def _inject_feedback(messages: list[dict[str, str]], feedback: str) -> list[dict[str, str]]:
    """Append a gate feedback message to the prompt sequence."""
    return messages + [{"role": "user", "content": feedback}]


# ---------------------------------------------------------------------------
# Gate logic
# ---------------------------------------------------------------------------

def gate_decision_a(
    e_ratio_val: float, threshold: float, rng: random.Random
) -> tuple[bool, str]:
    """Branch A: reject if E_ratio exceeds threshold, sterile feedback."""
    if e_ratio_val > threshold:
        return True, "threshold_exceeded"
    return False, "accepted"


def gate_decision_b(
    e_ratio_val: float, threshold: float, rng: random.Random
) -> tuple[bool, str]:
    """Branch B: reject if E_ratio exceeds threshold, dramatic feedback."""
    if e_ratio_val > threshold:
        return True, "threshold_exceeded"
    return False, "accepted"


def gate_decision_c(
    e_ratio_val: float, threshold: float, rng: random.Random,
    rejection_rate: float = 0.3,
) -> tuple[bool, str]:
    """Branch C: reject randomly at the paired Branch A rate."""
    if rng.random() < rejection_rate:
        return True, "random_rejection"
    return False, "accepted"


def format_feedback(branch: str, e_ratio_val: float, threshold: float,
                    reservoir: float) -> str:
    """Return the feedback string for a rejected cycle."""
    if branch == "A":
        return FEEDBACK_STERILE.format(
            e_ratio=e_ratio_val, threshold=threshold, reservoir=reservoir
        )
    elif branch == "B":
        return FEEDBACK_DRAMATIC.format(
            e_ratio=e_ratio_val, threshold=threshold, reservoir=reservoir
        )
    else:
        return FEEDBACK_RANDOM_STERILE.format(reservoir=reservoir)


SURVIVING_BUFFER_SIZE = 10


def format_telemetry_hud_rejection(
    er: float, dc: float, flux: float, oracle_score: float,
    threshold: float, proposed_solver: str, reservoir: float,
    surviving_buffer: list[dict[str, float]],
) -> str:
    """Quantitative telemetry block for rejected cycles. Numbers only."""
    decomp = solver_ast_decomposition(proposed_solver)
    bd = ast_branching_depth(proposed_solver)

    lines = [
        "[CYCLE REJECTED]",
        f"AST branching depth: {bd}",
        f"AST algebraic nodes: {decomp['ast_arithmetic']}",
        f"Topological action (dC): {dc:.1f}",
        f"Semantic flux: {flux:.1f}",
        f"E_ratio: {er:.2f}",
        f"Threshold: {threshold:.2f}",
        "---",
    ]
    if surviving_buffer:
        n = len(surviving_buffer)
        mean_dc = statistics.mean(m["delta_c"] for m in surviving_buffer)
        mean_bd = statistics.mean(m["branching_depth"] for m in surviving_buffer)
        mean_alg = statistics.mean(m["algebraic_nodes"] for m in surviving_buffer)
        lines.append(f"Surviving cycle averages (last {n}):")
        lines.append(f"  Mean branching depth: {mean_bd:.1f}")
        lines.append(f"  Mean algebraic nodes: {mean_alg:.1f}")
        lines.append(f"  Mean dC: {mean_dc:.1f}")
    else:
        lines.append("No surviving cycles yet.")
    return "\n".join(lines)


def format_telemetry_hud_survival(
    er: float, oracle_score: float, oracle_passed: int,
    oracle_total: int, reservoir: float,
) -> str:
    """Short confirmation for surviving cycles. Numbers only."""
    return (
        f"[CYCLE SURVIVED]\n"
        f"E_ratio: {er:.2f}\n"
        f"Oracle: {oracle_passed}/{oracle_total}\n"
        f"Reservoir remaining: {reservoir:.0f}"
    )


# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------

def _append_jsonl(path: str, record: dict) -> None:
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record) + "\n")


def _load_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: chars / 4."""
    return max(1, len(text) // 4) if text else 0


# ---------------------------------------------------------------------------
# Snapshot helpers for rejection/state preservation
# ---------------------------------------------------------------------------

def _snapshot_workspace() -> dict[str, str]:
    """Capture current workspace file contents for potential rollback."""
    return {
        "opinions_md": hv.read_text(hv.OPINIONS_FILE),
        "dead_ends_json": hv.read_text(hv.DEAD_ENDS_JSON_FILE),
        "solver_py": hv.read_text(hv.SOLVER_FILE),
    }


def _restore_workspace(snapshot: dict[str, str]) -> None:
    """Restore workspace files from a snapshot (used on rejection)."""
    hv.write_text(hv.OPINIONS_FILE, snapshot["opinions_md"])
    de = json.loads(snapshot["dead_ends_json"]) if snapshot["dead_ends_json"] else {}
    hv.write_json(hv.DEAD_ENDS_JSON_FILE, de)
    from v44_epistemics import render_dead_ends_md
    hv.write_text(hv.DEAD_ENDS_FILE, render_dead_ends_md(de))
    hv.write_text(hv.SOLVER_FILE, snapshot["solver_py"])


# ---------------------------------------------------------------------------
# Calibration phase
# ---------------------------------------------------------------------------

def run_calibration(
    args: argparse.Namespace,
    rng: random.Random,
) -> tuple[list[dict], float, str, float, int]:
    """Run unconstrained calibration cycles. Returns (metrics, threshold, threshold_source, avg_tokens, last_complexity)."""

    calibration_metrics: list[dict] = []
    e_ratios: list[float] = []
    token_counts: list[int] = []
    previous_complexity: int | None = None

    for cal_cycle in range(1, args.calibration_cycles + 1):
        hv.reset_cycle_usage()
        previous_opinions = hv.read_text(hv.OPINIONS_FILE)
        previous_state = load_state(hv.DEAD_END_STATE_FILE)

        # Snapshot dead-ends before cycle for flux computation
        prev_dead_ends = json.loads(hv.read_text(hv.DEAD_ENDS_JSON_FILE) or "{}")

        hv.write_status(cal_cycle, args.calibration_cycles, "CALIBRATION_GRIND")
        print(f"  [CAL] Cycle {cal_cycle}/{args.calibration_cycles} — GRIND")

        try:
            grind_payload = hv.request_cycle_output(
                cal_cycle, args.calibration_cycles, args.model, args.api_base,
                mode="grind", current_state=previous_state,
                api_key_env=args.api_key_env,
            )
        except RuntimeError as exc:
            print(f"  [CAL] FORMAT_FAIL: {exc}")
            hv.write_status(cal_cycle, args.calibration_cycles, "FORMAT_FAIL",
                            last_result="FAIL", last_error=str(exc))
            token_counts.append(hv._cycle_usage.get("api_total_tokens_cycle", 0))
            continue

        hv.persist_model_output(grind_payload)
        attempted_solver = str(grind_payload.get("solver_py", ""))

        # Compute assay metrics on this cycle
        curr_dead_ends = grind_payload.get("dead_ends", {})
        test_cases = hv.build_fixed_oracle_suite() + [hv.generate_permutation_array(rng) for _ in range(args.tests_per_cycle)]
        oracle_score, _, _, _ = evaluate_solver_fractional(
            test_cases, hv.hidden_law, str(Path(hv.SOLVER_FILE))
        )
        dc = delta_c_topological(attempted_solver)
        flux = epistemic_flux(prev_dead_ends, curr_dead_ends, oracle_score)
        er = e_ratio(dc, flux)
        e_ratios.append(er)

        # Standard ratchet evaluation
        hv.write_status(cal_cycle, args.calibration_cycles, "CALIBRATION_RATCHET")
        success, output, first_failure = hv.evaluate_solver(
            [hv.generate_permutation_array(rng) for _ in range(args.tests_per_cycle)]
        )

        if success:
            current_state = merge_state(previous_state, grind_payload["dead_ends"], cal_cycle)
            save_state(hv.DEAD_END_STATE_FILE, current_state)
            hv.run_command('git add . && git commit -m "Assay: calibration ratchet advanced"')
        else:
            failing_pairs = [first_failure] if first_failure else []
            if not failing_pairs:
                fallback = hv.generate_permutation_array(rng)
                failing_pairs = [{"input": fallback, "expected": hv.hidden_law(fallback)}]
            hv.update_data_file(failing_pairs)
            hv.run_command("git reset --hard HEAD")
            hv.run_command("git clean -fd")

            try:
                fail_payload = hv.request_cycle_output(
                    cal_cycle, args.calibration_cycles, args.model, args.api_base,
                    mode="sync-fail", current_state=previous_state,
                    failure_report=output, required_falsifier=failing_pairs[0],
                    api_key_env=args.api_key_env,
                )
                hv.persist_model_output(fail_payload)
                current_state = merge_state(previous_state, fail_payload["dead_ends"], cal_cycle)
            except RuntimeError as exc:
                print(f"  [CAL] SYNC FORMAT_FAIL: {exc}")
                current_state = previous_state

            save_state(hv.DEAD_END_STATE_FILE, current_state)

        # Compute standard metrics
        metrics = hv.compute_cycle_metrics(
            cal_cycle, previous_opinions, previous_state,
            load_state(hv.DEAD_END_STATE_FILE), attempted_solver, previous_complexity,
        )
        previous_complexity = int(metrics.get("solver_ast_complexity", 0))
        token_counts.append(hv._cycle_usage.get("api_total_tokens_cycle", 0))

        # Log calibration entry
        cal_entry = {
            "phase": "calibration",
            "cycle": cal_cycle,
            "e_ratio": round(er, 4),
            "delta_c": round(dc, 4),
            "flux": round(flux, 4),
            "oracle_score": round(oracle_score, 4),
            "tokens": hv._cycle_usage.get("api_total_tokens_cycle", 0),
            "ratchet_result": "PASS" if success else "FAIL",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        calibration_metrics.append(cal_entry)
        _append_jsonl(ASSAY_LOG_FILE, cal_entry)

        result_str = "PASS" if success else "FAIL"
        hv.write_status(cal_cycle, args.calibration_cycles, f"CALIBRATION_{result_str}",
                        last_result=result_str, metrics=metrics)
        print(f"  [CAL] Cycle {cal_cycle}: E_ratio={er:.2f}, tokens={token_counts[-1]}, {result_str}")

    # Compute threshold and average tokens
    # Patch 2026-03-16: require minimum 3 valid E_ratio measurements for
    # auto-calibration. Run A-5 produced only 1 valid measurement (-2M),
    # setting a negative threshold that trapped the model in 98.5% rejection.
    # With insufficient data, fall back to 2× the max observed absolute value
    # (permissive) rather than a pathological p75.
    MIN_CAL_POINTS = 3
    avg_tokens = statistics.mean(token_counts) if token_counts else 3000
    if args.e_ratio_threshold > 0:
        threshold = args.e_ratio_threshold
        threshold_source = "override"
    elif len(e_ratios) >= MIN_CAL_POINTS:
        raw_median = statistics.median(e_ratios)
        ceiling = 10.0 * statistics.median([abs(er) for er in e_ratios])
        threshold = min(raw_median, ceiling) if raw_median > 0 else raw_median
        threshold_source = "auto_median_10x_clamp"
    elif e_ratios:
        threshold = max(abs(er) for er in e_ratios) * 2.0
        threshold_source = "auto_insufficient_data"
        print(f"  [WARN] Only {len(e_ratios)} calibration E_ratios "
              f"(need {MIN_CAL_POINTS}). Permissive fallback: {threshold:.2f}")
    else:
        threshold = 50_000_000.0
        threshold_source = "auto_no_data"
        print(f"  [WARN] No valid calibration E_ratios. Default threshold: {threshold:.2f}")

    # Negative thresholds are pathological — clamp to positive
    if threshold < 0:
        old = threshold
        threshold = abs(threshold) * 2.0
        threshold_source += "_neg_clamped"
        print(f"  [WARN] Negative threshold {old:.2f} clamped to {threshold:.2f}")

    return calibration_metrics, threshold, threshold_source, avg_tokens, previous_complexity or 0


# ---------------------------------------------------------------------------
# Gated phase
# ---------------------------------------------------------------------------

def run_gated_loop(
    args: argparse.Namespace,
    rng: random.Random,
    threshold: float,
    avg_tokens: float,
    previous_complexity: int,
    rejection_rate: float,
) -> None:
    """Run the gated experiment loop until token reservoir depletes."""

    reservoir = args.reservoir_multiplier * avg_tokens
    cycle = args.calibration_cycles  # continue numbering from calibration
    pending_feedback: str | None = None
    surviving_metrics_buffer: list[dict[str, float]] = []
    best_oracle_score: float = 0.0
    quarantine_active: bool = False
    quarantine_solver: str | None = None
    quarantine_score: float = 0.0
    quarantine_snapshot: dict[str, str] | None = None
    consecutive_perfect_oracle: int = 0
    previous_theory_hash: int | None = None

    print(f"\n  [GATE] Starting gated phase — Branch {args.branch}")
    print(f"  [GATE] Threshold: {threshold:.2f}, Reservoir: {reservoir:.0f} tokens")
    print(f"  [GATE] Rejection rate (Branch C): {rejection_rate:.2f}")

    while reservoir > 0:
        cycle += 1
        hv.reset_cycle_usage()
        previous_opinions = hv.read_text(hv.OPINIONS_FILE)
        previous_state = load_state(hv.DEAD_END_STATE_FILE)
        prev_dead_ends = json.loads(hv.read_text(hv.DEAD_ENDS_JSON_FILE) or "{}")

        # Save pre-cycle workspace snapshot for potential rollback
        workspace_snapshot = _snapshot_workspace()

        hv.write_status(cycle, 0, "GATED_GRIND")
        print(f"  [GATE] Cycle {cycle} — reservoir={reservoir:.0f}")

        # Request model output (with feedback injection + FORMAT_FAIL retry)
        format_retries = 0
        grind_payload = None
        for format_attempt in range(FORMAT_FAIL_MAX_RETRIES + 1):
            try:
                messages = hv.format_cycle_prompt(
                    cycle, 999, "grind", previous_state
                )
                if pending_feedback:
                    messages = _inject_feedback(messages, pending_feedback)
                    pending_feedback = None

                # Use the hypervisor's invoke_openai + validation loop directly
                retry_messages = list(messages)
                last_error = "No response received."
                grind_payload = None
                for _ in range(hv.SYNC_MAX_TURNS):
                    payload = hv.invoke_openai(
                        retry_messages, args.model, args.api_base,
                        api_key_env=args.api_key_env,
                    )
                    error = hv.validate_cycle_output(payload, previous_state)
                    if not error:
                        grind_payload = payload
                        break
                    last_error = error
                    retry_messages = retry_messages + [{
                        "role": "user",
                        "content": f"[SYSTEM LINTER ERROR] Validation failed: {error} Fix and resubmit.",
                    }]

                if grind_payload is None:
                    raise RuntimeError(f"CYCLE_CRASH_FORMAT: {last_error}")
                break  # Success — exit format retry loop

            except RuntimeError as exc:
                attempt_tokens = hv._cycle_usage.get("api_total_tokens_cycle", 0)
                reservoir -= max(attempt_tokens, 1)
                format_retries += 1

                if format_attempt < FORMAT_FAIL_MAX_RETRIES:
                    print(f"  [GATE] FORMAT_FAIL (retry {format_retries}/{FORMAT_FAIL_MAX_RETRIES}): {exc}")
                    hv.reset_cycle_usage()
                    continue
                else:
                    print(f"  [GATE] FORMAT_FATAL after {format_retries} retries: {exc}")
                    _append_jsonl(ASSAY_LOG_FILE, {
                        "phase": "gated", "cycle": cycle, "branch": args.branch,
                        "gate_decision": "format_fatal",
                        "format_fail": True,
                        "format_retries": format_retries,
                        "tokens_consumed_this_cycle": attempt_tokens,
                        "reservoir_remaining": round(reservoir, 0),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    hv.write_status(cycle, 0, "FORMAT_FATAL", last_result="FAIL", last_error=str(exc))

        if grind_payload is None:
            continue

        # Write proposed solver temporarily to evaluate fractionally
        proposed_solver = str(grind_payload.get("solver_py", ""))
        proposed_dead_ends = grind_payload.get("dead_ends", {})

        # Temporarily write solver so fractional oracle can load it
        hv.write_text(hv.SOLVER_FILE, proposed_solver + "\n")

        test_cases = hv.build_fixed_oracle_suite() + [hv.generate_permutation_array(rng) for _ in range(args.tests_per_cycle)]
        oracle_score, passed, total, failure_report = evaluate_solver_fractional(
            test_cases, hv.hidden_law, str(Path(hv.SOLVER_FILE))
        )

        # Restore solver from snapshot (haven't committed to this output yet)
        hv.write_text(hv.SOLVER_FILE, workspace_snapshot["solver_py"])

        # Compute assay metrics
        dc = delta_c_topological(proposed_solver)
        flux = epistemic_flux(prev_dead_ends, proposed_dead_ends, oracle_score)
        er = e_ratio(dc, flux)

        # Gate decision defaults (may be overridden by quarantine recovery)
        rejected = False
        reason = ""

        # --- QUARANTINE RECOVERY CHECK (skipped in ungated mode) ---
        if quarantine_active and not getattr(args, 'no_gate', False):
            tokens_used = hv._cycle_usage.get("api_total_tokens_cycle", 0)
            reservoir -= max(tokens_used, 1)
            if flux >= FLUX_MINIMUM:
                # Theory updated — accept quarantined solver + current theory
                print(f"  [QUARANTINE] RESOLVED: flux={flux:.1f} >= {FLUX_MINIMUM}. Accepting quarantined solver.")
                proposed_solver = quarantine_solver
                oracle_score = quarantine_score
                best_oracle_score = max(best_oracle_score, quarantine_score)
                quarantine_active = False
                quarantine_solver = None
                quarantine_score = 0.0
                quarantine_snapshot = None
                _append_jsonl(ASSAY_LOG_FILE, {
                    "phase": "gated", "cycle": cycle, "branch": args.branch,
                    "gate_decision": "quarantine_resolved",
                    "oracle_score": round(oracle_score, 4),
                    "flux": round(flux, 4),
                    "tokens_consumed_this_cycle": tokens_used,
                    "reservoir_remaining": round(reservoir, 0),
                    "quarantine_active": False,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                hv.write_status(cycle, 0, "QUARANTINE_RESOLVED")
                # Fall through to ACCEPTED path below (skip gate)
                rejected = False
                reason = "quarantine_resolved"
                # Skip normal gate — jump past gate block
            else:
                # Theory not updated — discard quarantined solver
                print(f"  [QUARANTINE] FAILED: flux={flux:.1f} < {FLUX_MINIMUM}. Discarding quarantined solver.")
                _restore_workspace(quarantine_snapshot)
                _append_jsonl(ASSAY_LOG_FILE, {
                    "phase": "gated", "cycle": cycle, "branch": args.branch,
                    "gate_decision": "quarantine_failed",
                    "oracle_score": round(oracle_score, 4),
                    "flux": round(flux, 4),
                    "tokens_consumed_this_cycle": tokens_used,
                    "reservoir_remaining": round(reservoir, 0),
                    "quarantine_active": False,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                quarantine_active = False
                quarantine_solver = None
                quarantine_score = 0.0
                quarantine_snapshot = None
                hv.write_status(cycle, 0, "QUARANTINE_FAILED")
                print(f"  [GATE] QUARANTINE_FAILED cycle {cycle}: flux={flux:.1f}")
                continue  # Discard this cycle, move on

        # --- QUARANTINE TRIGGER CHECK (skipped in ungated mode) ---
        if not getattr(args, 'no_gate', False) and not quarantine_active and oracle_score > best_oracle_score and flux < FLUX_MINIMUM:
            tokens_used = hv._cycle_usage.get("api_total_tokens_cycle", 0)
            reservoir -= max(tokens_used, 1)
            print(f"  [QUARANTINE] TRIGGERED: oracle={oracle_score:.2f} > best={best_oracle_score:.2f}, "
                  f"flux={flux:.1f} < {FLUX_MINIMUM}")
            quarantine_active = True
            quarantine_solver = proposed_solver
            quarantine_score = oracle_score
            quarantine_snapshot = workspace_snapshot
            _restore_workspace(workspace_snapshot)
            _append_jsonl(ASSAY_LOG_FILE, {
                "phase": "gated", "cycle": cycle, "branch": args.branch,
                "gate_decision": "quarantined",
                "oracle_score": round(oracle_score, 4),
                "best_oracle_score": round(best_oracle_score, 4),
                "flux": round(flux, 4),
                "delta_c": round(dc, 4),
                "e_ratio": round(er, 4),
                "tokens_consumed_this_cycle": tokens_used,
                "reservoir_remaining": round(reservoir, 0),
                "quarantine_active": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            pending_feedback = (
                f"[QUARANTINE] Oracle hit: {oracle_score:.2f} ({passed}/{total}). "
                f"Flux: {flux:.3f}. Your solver produced empirical results "
                f"without theoretical backing. You have ONE cycle to update "
                f"your theory to explain this solver. If flux remains below "
                f"{FLUX_MINIMUM}, the solver is annihilated."
            )
            hv.write_status(cycle, 0, "QUARANTINED")
            print(f"  [GATE] QUARANTINED cycle {cycle}: oracle={oracle_score:.2f}, flux={flux:.1f}")
            continue

        # Apply gate (skipped if quarantine recovery already set the outcome)
        if getattr(args, 'no_gate', False) and reason != "quarantine_resolved":
            rejected = False
            reason = "ungated"
            tokens_used = hv._cycle_usage.get("api_total_tokens_cycle", 0)
            reservoir -= max(tokens_used, 1)
        elif reason != "quarantine_resolved":
            if args.branch == "A":
                rejected, reason = gate_decision_a(er, threshold, rng)
            elif args.branch == "B":
                rejected, reason = gate_decision_b(er, threshold, rng)
            else:
                rejected, reason = gate_decision_c(er, threshold, rng,
                                                    rejection_rate=rejection_rate)
            tokens_used = hv._cycle_usage.get("api_total_tokens_cycle", 0)
            reservoir -= max(tokens_used, 1)

        # Compute theory counts for logging
        current_de_json = hv.read_text(hv.DEAD_ENDS_JSON_FILE) or "{}"
        _, active_count, archived_count, _ = compress_dead_ends_for_prompt(current_de_json)
        decomp_log = solver_ast_decomposition(proposed_solver)

        # Log the gate decision (full spec schema)
        log_entry = {
            "cycle": cycle,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reservoir_remaining": round(reservoir, 0),
            "tokens_consumed_this_cycle": tokens_used,
            "theory_tokens": _estimate_tokens(json.dumps(proposed_dead_ends)),
            "solver_tokens": _estimate_tokens(proposed_solver),
            "format_fail": False,
            "format_retries": format_retries,
            "ast_branching_depth": ast_branching_depth(proposed_solver),
            "ast_algebraic_nodes": decomp_log["ast_arithmetic"],
            "delta_c": round(dc, 4),
            "flux": round(flux, 4),
            "e_ratio": round(er, 4),
            "gate_decision": "rejected" if rejected else "accepted",
            "gate_reason": reason,
            "oracle_score": round(oracle_score, 4),
            "oracle_passed": passed,
            "oracle_total": total,
            "oracle_max": total,
            "quarantine_active": quarantine_active,
            "active_theories": active_count,
            "archived_theories": archived_count,
            "prompt_context_tokens": hv._cycle_usage.get("api_prompt_tokens_cycle", 0),
            "threshold": round(threshold, 4),
            "branch": args.branch,
            "phase": "gated",
        }
        _append_jsonl(ASSAY_LOG_FILE, log_entry)

        if rejected:
            # Log the rejected payload
            _append_jsonl(ASSAY_REJECTIONS_FILE, {
                "cycle": cycle,
                "branch": args.branch,
                "reason": reason,
                "e_ratio": round(er, 4),
                "proposed_solver_py": proposed_solver,
                "proposed_dead_ends": proposed_dead_ends,
                "proposed_opinions_md": str(grind_payload.get("opinions_md", "")),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # Restore workspace to pre-cycle state
            _restore_workspace(workspace_snapshot)

            # Set feedback for next cycle — telemetry HUD for A/B, null for C
            if args.branch in ("A", "B"):
                pending_feedback = format_telemetry_hud_rejection(
                    er, dc, flux, oracle_score, threshold,
                    proposed_solver, reservoir, surviving_metrics_buffer,
                )
            else:
                pending_feedback = format_feedback(args.branch, er, threshold, reservoir)

            hv.write_status(cycle, 0, "GATED_REJECTED", last_result="REJECTED",
                            last_error=f"E_ratio={er:.2f} ({reason})")
            print(f"  [GATE] REJECTED cycle {cycle}: E_ratio={er:.2f} ({reason})")
            continue

        # ACCEPTED — persist and run standard ratchet
        hv.persist_model_output(grind_payload)

        hv.write_status(cycle, 0, "GATED_RATCHET")
        ratchet_cases = [hv.generate_permutation_array(rng) for _ in range(args.tests_per_cycle)]
        success, output, first_failure = hv.evaluate_solver(ratchet_cases)

        if success:
            current_state = merge_state(previous_state, grind_payload["dead_ends"], cycle)
            save_state(hv.DEAD_END_STATE_FILE, current_state)
            hv.run_command('git add . && git commit -m "Assay: gated ratchet advanced"')
            metrics = hv.compute_cycle_metrics(
                cycle, previous_opinions, previous_state,
                current_state, proposed_solver, previous_complexity,
            )
            previous_complexity = int(metrics.get("solver_ast_complexity", 0))
            hv.write_status(cycle, 0, "GATED_PASS", last_result="PASS", metrics=metrics)
            print(f"  [GATE] ACCEPTED+PASS cycle {cycle}: E_ratio={er:.2f}")
        else:
            # Standard fail-sync path
            failing_pairs = [first_failure] if first_failure else []
            if not failing_pairs:
                fallback = hv.generate_permutation_array(rng)
                failing_pairs = [{"input": fallback, "expected": hv.hidden_law(fallback)}]
            hv.update_data_file(failing_pairs)
            hv.run_command("git reset --hard HEAD")
            hv.run_command("git clean -fd")

            try:
                fail_payload = hv.request_cycle_output(
                    cycle, 999, args.model, args.api_base,
                    mode="sync-fail", current_state=previous_state,
                    failure_report=output, required_falsifier=failing_pairs[0],
                    api_key_env=args.api_key_env,
                )
                hv.persist_model_output(fail_payload)
                current_state = merge_state(previous_state, fail_payload["dead_ends"], cycle)
            except RuntimeError as exc:
                print(f"  [GATE] SYNC FORMAT_FAIL: {exc}")
                current_state = previous_state

            save_state(hv.DEAD_END_STATE_FILE, current_state)
            metrics = hv.compute_cycle_metrics(
                cycle, previous_opinions, previous_state,
                current_state, proposed_solver, previous_complexity,
            )
            previous_complexity = int(metrics.get("solver_ast_complexity", 0))

            # Update token reservoir with sync-fail tokens too
            sync_tokens = hv._cycle_usage.get("api_total_tokens_cycle", 0) - tokens_used
            if sync_tokens > 0:
                reservoir -= sync_tokens

            hv.write_status(cycle, 0, "GATED_SYNC_FAILURE", last_result="FAIL",
                            last_error=output[-500:], metrics=metrics)
            print(f"  [GATE] ACCEPTED+FAIL cycle {cycle}: E_ratio={er:.2f}")

        # Track surviving cycle metrics + update best oracle
        decomp = solver_ast_decomposition(proposed_solver)
        surviving_metrics_buffer.append({
            "e_ratio": er,
            "delta_c": dc,
            "flux": flux,
            "oracle_score": oracle_score,
            "branching_depth": float(ast_branching_depth(proposed_solver)),
            "algebraic_nodes": float(decomp["ast_arithmetic"]),
        })
        if len(surviving_metrics_buffer) > SURVIVING_BUFFER_SIZE:
            surviving_metrics_buffer.pop(0)
        best_oracle_score = max(best_oracle_score, oracle_score)

        # --- CONVERGENCE DETECTION ---
        current_theory = hv.read_text(hv.OPINIONS_FILE).strip()
        current_hash = hash(current_theory)
        if oracle_score >= 1.0 and current_hash == previous_theory_hash:
            consecutive_perfect_oracle += 1
        else:
            consecutive_perfect_oracle = 0 if oracle_score < 1.0 else 1
        previous_theory_hash = current_hash

        if consecutive_perfect_oracle >= 5:
            print(f"\n  [CONVERGED] 5 consecutive perfect oracle cycles with stable theory.")
            print(f"  [CONVERGED] Final oracle: {oracle_score:.2f} ({passed}/{total})")
            _append_jsonl(ASSAY_LOG_FILE, {
                "phase": "gated", "cycle": cycle, "branch": args.branch,
                "gate_decision": "converged",
                "oracle_score": round(oracle_score, 4),
                "consecutive_perfect": consecutive_perfect_oracle,
                "reservoir_remaining": round(reservoir, 0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            hv.write_status(cycle, 0, "CONVERGED", last_result="SOLVED")
            print(f"\n  [ASSAY] CONVERGED after {cycle} total cycles.")
            return

        # Survival telemetry for next cycle
        pending_feedback = format_telemetry_hud_survival(
            er, oracle_score, passed, total, reservoir,
        )

    # Reservoir exhausted — discard any active quarantine
    if quarantine_active:
        print(f"  [QUARANTINE] Reservoir exhausted during quarantine. Discarding quarantined solver.")
        if quarantine_snapshot:
            _restore_workspace(quarantine_snapshot)
        quarantine_active = False
    hv.write_status(cycle, 0, "RESERVOIR_EXHAUSTED", last_result="COMPLETE")
    print(f"\n  [ASSAY] Reservoir exhausted after {cycle} total cycles.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Three-Branch Actuator Assay (Experiment 04)"
    )
    parser.add_argument("--branch", choices=["A", "B", "C"], required=True,
                        help="Branch: A=informed sterile, B=informed dramatic, C=random null")
    parser.add_argument("--run-id", type=int, required=True, help="Run index (1-5)")
    parser.add_argument("--workspace-root", type=str, default="runs/assay",
                        help="Parent directory for all assay workspaces")
    parser.add_argument("--model", default="anthropic/claude-haiku-4-5",
                        help="Model slug for Haimaker/OpenAI-compatible API")
    parser.add_argument("--api-base", default="https://api.haimaker.ai/v1",
                        help="OpenAI-compatible API base URL")
    parser.add_argument("--api-key-env", default="HAIMAKER_KEY",
                        help="Environment variable name for API key")
    parser.add_argument("--seed", type=int, default=44, help="RNG seed base")
    parser.add_argument("--calibration-cycles", type=int, default=10,
                        help="Unconstrained warmup cycles")
    parser.add_argument("--reservoir-multiplier", type=float, default=150.0,
                        help="Token budget = multiplier × avg_cost_per_cycle")
    parser.add_argument("--e-ratio-threshold", type=float, default=0.0,
                        help="Override E_ratio threshold (0 = auto-calibrate from 75th percentile)")
    parser.add_argument("--rejection-rate", type=float, default=0.0,
                        help="For Branch C: fixed rejection probability (0 = read from paired Branch A)")
    parser.add_argument("--tests-per-cycle", type=int, default=5,
                        help="Oracle test cases per cycle")
    parser.add_argument("--response-format", choices=["json_schema", "json_object"],
                        default=None, help="Override API response format")
    parser.add_argument("--hunches", action="store_true",
                        help="Enable subliminal ledger (hunches.md)")
    parser.add_argument("--no-gate", action="store_true",
                        help="Phase 2 mode: accept every cycle, skip E_ratio gate")
    return parser.parse_args()


def _compute_rejection_rate_from_a(workspace_root: str, run_id: int) -> float:
    """Extract observed rejection rate from the paired Branch A run."""
    a_log_path = os.path.join(workspace_root, f"branch-A-run-{run_id}", ASSAY_LOG_FILE)
    records = _load_jsonl(a_log_path)
    gated = [r for r in records if r.get("phase") == "gated"]
    if not gated:
        print(f"  [WARN] No Branch A gated data found at {a_log_path}, using 0.3 default")
        return 0.3
    rejected = sum(1 for r in gated if r.get("gate_decision") == "rejected")
    rate = rejected / len(gated)
    print(f"  [INFO] Branch A rejection rate for run {run_id}: {rate:.3f} ({rejected}/{len(gated)})")
    return rate


def main() -> None:
    args = parse_args()

    # Set response format if overridden
    if args.response_format:
        hv.DEFAULT_RESPONSE_FORMAT = args.response_format

    # Deterministic seed: base + run_id (shared across branches for same run_id)
    effective_seed = args.seed + args.run_id
    rng = random.Random(effective_seed)
    hv._rng.seed(effective_seed)

    # Enable hunches if requested
    if args.hunches:
        hv.HUNCHES_ENABLED = True

    # Set up workspace
    workspace_root = Path(args.workspace_root).resolve()
    workspace = workspace_root / f"branch-{args.branch}-run-{args.run_id}"
    workspace.mkdir(parents=True, exist_ok=True)
    os.chdir(workspace)

    hv.setup_workspace()

    # Add assay-specific files to gitignore so git clean -fd won't delete them
    from v44_epistemics import SUPERSEDED_LOG_FILE
    assay_ignores = {ASSAY_CONFIG_FILE, ASSAY_LOG_FILE, ASSAY_REJECTIONS_FILE, SUPERSEDED_LOG_FILE}
    if args.hunches:
        assay_ignores.add(hv.HUNCHES_FILE)
    gitignore_path = ".gitignore"
    existing = set()
    if os.path.exists(gitignore_path):
        existing = {line.strip() for line in hv.read_text(gitignore_path).splitlines() if line.strip()}
    new_entries = assay_ignores - existing
    if new_entries:
        hv.write_text(gitignore_path, "\n".join(sorted(existing | assay_ignores)) + "\n")
        hv.run_command('git add .gitignore && git commit -m "Assay: add assay files to gitignore"')

    # Load any existing metric history (for continuation support)
    hv._metric_history, _ = hv.load_existing_metric_history()

    print(f"\n  === ACTUATOR ASSAY: Branch {args.branch}, Run {args.run_id} ===")
    print(f"  Workspace: {workspace}")
    print(f"  Model: {args.model}")
    print(f"  Seed: {effective_seed}")

    # --- Phase 1: Calibration ---
    print(f"\n  [PHASE 1] Calibration burn ({args.calibration_cycles} cycles)")
    cal_metrics, threshold, threshold_source, avg_tokens, last_complexity = run_calibration(args, rng)

    # For Branch C, compute rejection rate from Branch A if not provided
    rejection_rate = args.rejection_rate
    if args.branch == "C" and rejection_rate <= 0:
        rejection_rate = _compute_rejection_rate_from_a(
            str(workspace_root), args.run_id
        )

    # Write frozen config
    config = {
        "branch": f"{args.branch}-v4.5",
        "run_id": args.run_id,
        "model": args.model,
        "seed": effective_seed,
        "calibration_cycles": args.calibration_cycles,
        "reservoir_multiplier": args.reservoir_multiplier,
        "e_ratio_threshold": round(threshold, 4),
        "e_ratio_threshold_source": threshold_source,
        "avg_tokens_per_cycle": round(avg_tokens, 0),
        "token_reservoir": round(args.reservoir_multiplier * avg_tokens, 0),
        "rejection_rate": round(rejection_rate, 4) if args.branch == "C" else None,
        "tests_per_cycle": args.tests_per_cycle,
        "calibration_e_ratios": [round(m.get("e_ratio", 0), 4) for m in cal_metrics],
        "hunches_enabled": args.hunches,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    hv.write_json(ASSAY_CONFIG_FILE, config)
    print(f"\n  [CONFIG] E_ratio threshold: {threshold:.2f}")
    print(f"  [CONFIG] Avg tokens/cycle: {avg_tokens:.0f}")
    print(f"  [CONFIG] Token reservoir: {args.reservoir_multiplier * avg_tokens:.0f}")

    # --- Phase 2: Gated loop ---
    print(f"\n  [PHASE 2] Gated loop — Branch {args.branch}")
    run_gated_loop(args, rng, threshold, avg_tokens, last_complexity, rejection_rate)

    print(f"\n  === ASSAY COMPLETE: Branch {args.branch}, Run {args.run_id} ===")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  [!] Assay interrupted by user.")
