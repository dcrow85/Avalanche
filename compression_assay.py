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
import signal
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Pop the recursion guard before importing the hypervisor as a library.
os.environ.pop("AVALANCHE_ACTIVE", None)

import hypervisor_v44 as hv
from actuator_metrics import evaluate_solver_fractional
from v43_metrics import semantic_distance
from v44_epistemics import (
    blank_state,
    detect_work_event,
    load_state,
    merge_state,
    save_state,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TELEMETRY_FILE = "telemetry.jsonl"
COMPRESSION_LOG_FILE = "compression_log.jsonl"
OPINIONS_HISTORY_FILE = "opinions_history.jsonl"
FORMAT_FAIL_MAX_RETRIES = 2
COMPRESSION_DATA_SLICE_ROWS = 2  # Rows from data.json shown during compression passes

# Compression pass slot schema — per-slot character budgets
COMPRESSION_SLOTS = {
    "core_rule":     120,  # Current best active rule, one sentence
    "alt_rule":      80,   # Structurally different approach, one sentence (may be empty)
    "key_exclusion": 95,   # One important falsified pattern, one sentence
    "uncertainty":   75,   # Main unresolved ambiguity, one sentence
}
COMPRESSION_SLOT_KEYS = set(COMPRESSION_SLOTS.keys())
COMPRESSION_MIN_RENDER_LEN = 220  # Smallest viable slot-rendered summary worth preserving
ALTITUDE_SURVEY_MIN_GRAVEYARD_ENTRIES = 12  # Let survey mode see enough fossils to compare structure

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
    """Tracks the shrinking prompt budget. Output budget stays fixed at 1200.

    The gradient compresses only the prompt side: fewer data pairs,
    shorter opinions, thinner graveyard. The model always has full
    output space to produce the JSON schema.
    """
    initial_prompt_budget: int = 1200
    floor: int = 400
    decay: str = "linear"  # "linear", "log", or "stepped"
    total_cycles: int = 200
    current_prompt_budget: int = 0  # set in __post_init__
    cycle_count: int = 0
    output_budget: int = 1200  # fixed — never shrinks

    def __post_init__(self):
        if self.current_prompt_budget == 0:
            self.current_prompt_budget = self.initial_prompt_budget

    def tick(self) -> int:
        """Advance one cycle, return new prompt budget."""
        self.cycle_count += 1
        span = self.initial_prompt_budget - self.floor

        if self.decay == "linear":
            progress = min(1.0, self.cycle_count / max(1, self.total_cycles))
            self.current_prompt_budget = max(self.floor, int(self.initial_prompt_budget - span * progress))

        elif self.decay == "log":
            # Logarithmic decay: fast initial drop, slow tail
            progress = min(1.0, self.cycle_count / max(1, self.total_cycles))
            log_progress = math.log(1.0 + progress * (math.e - 1.0))
            self.current_prompt_budget = max(self.floor, int(self.initial_prompt_budget - span * log_progress))

        elif self.decay == "stepped":
            # Plateau-drop: hold for 25% of cycles, then step down
            step_size = max(1, self.total_cycles // 4)
            steps_completed = self.cycle_count // step_size
            max_steps = 4
            steps_completed = min(steps_completed, max_steps)
            self.current_prompt_budget = max(self.floor, int(self.initial_prompt_budget - span * steps_completed / max_steps))

        return self.current_prompt_budget

    @property
    def prompt_budget(self) -> int:
        return self.current_prompt_budget

    @property
    def max_graveyard_entries(self) -> int:
        graveyard_budget = int(self.current_prompt_budget * 0.15)
        return max(3, graveyard_budget // 80)


@dataclass
class CompressionPassState:
    """Tracks oracle stagnation for compression pass triggering.

    Fires after stagnation_window consecutive working cycles with no
    improvement in oracle_fixed. Capped at max_passes per run.
    """
    stagnation_window: int = 15
    target_compression: float = 0.5
    max_passes: int = 3
    triggered_count: int = 0
    best_oracle_fixed: float | None = None
    best_oracle_cycle: int = 0
    stall_count: int = 0

    def record(self, oracle_fixed: float, cycle: int = 0) -> None:
        """Record an oracle_fixed score. Resets stall if score improves."""
        if self.best_oracle_fixed is None or oracle_fixed > self.best_oracle_fixed:
            self.best_oracle_fixed = oracle_fixed
            self.best_oracle_cycle = cycle
            self.stall_count = 0
        else:
            self.stall_count += 1

    def should_trigger(self) -> bool:
        """True if stalled for stagnation_window cycles and passes remain."""
        if self.triggered_count >= self.max_passes:
            return False
        return self.stall_count >= self.stagnation_window

    def mark_triggered(self) -> None:
        self.triggered_count += 1
        self.stall_count = 0


@dataclass
class AltitudeState:
    """Tracks periodic metacognitive survey cycles."""
    frequency: int = 10
    prompt_style: str = "survey"  # "survey", "negative-space", or "rotating" (low/medium/high)
    altitudes: list[str] = field(default_factory=lambda: ["low", "medium", "high"])
    current_index: int = 0
    last_map: str = ""

    def should_fire(self, cycle: int) -> bool:
        return cycle > 0 and cycle % self.frequency == 0

    def next_altitude(self) -> str:
        if self.prompt_style != "rotating":
            return self.prompt_style
        alt = self.altitudes[self.current_index % len(self.altitudes)]
        self.current_index += 1
        return alt


# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------

def _append_jsonl(path: str, record: dict) -> None:
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record) + "\n")


def _max_rendered_slot_len() -> int:
    """Maximum rendered opinions.md length if every slot uses its full budget."""
    max_slots = {key: ("x" * max_chars) for key, max_chars in COMPRESSION_SLOTS.items()}
    return len(_render_opinions_from_slots(max_slots))


def _compression_target_len(theory_len_before: int, target_compression: float) -> int:
    """Target rendered length for a compression pass.

    Keep the ratio-based target, but never set a rendered budget smaller than
    the calibrated minimum viable slot summary. This is intentionally lower
    than the full-cap slot ceiling so an accepted pass can still be genuinely
    shorter than the input theory.
    """
    ratio_target = int(theory_len_before * target_compression)
    return max(ratio_target, COMPRESSION_MIN_RENDER_LEN)


def _cycle_usage_aliases() -> dict[str, int]:
    """Mirror hypervisor token counters into shorter, assay-friendly names."""
    return {
        "call_count": int(hv._cycle_usage.get("api_call_count_cycle", 0)),
        "prompt_tokens": int(hv._cycle_usage.get("api_prompt_tokens_cycle", 0)),
        "completion_tokens": int(hv._cycle_usage.get("api_completion_tokens_cycle", 0)),
        "total_tokens": int(hv._cycle_usage.get("api_total_tokens_cycle", 0)),
        "reasoning_tokens": int(hv._cycle_usage.get("api_reasoning_tokens_cycle", 0)),
    }


def _hamming_distance(a: list[bool], b: list[bool]) -> int:
    """Hamming distance between two boolean vectors of equal length."""
    if len(a) != len(b):
        raise ValueError(f"Vectors must be same length: {len(a)} != {len(b)}")
    return sum(x != y for x, y in zip(a, b))


def _log_opinions_history(
    cycle: int,
    cycle_type: str,
    opinions_text: str,
    opinions_text_hash: str,
) -> None:
    """Append one row to opinions_history.jsonl."""
    _append_jsonl(OPINIONS_HISTORY_FILE, {
        "cycle": cycle,
        "cycle_type": cycle_type,
        "opinions_text": opinions_text,
        "opinions_text_hash": opinions_text_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def _dead_ends_claims_text(dead_ends: dict[str, object]) -> str:
    """Extract all claim/hypothesis text from dead-ends for Probe G distance."""
    parts: list[str] = []
    for tier in ("basins", "families", "locals"):
        for item in dead_ends.get(tier, []):
            claim = str(item.get("claim", "")).strip()
            if claim:
                parts.append(claim)
    return " ".join(parts)


def _snapshot_dead_ends(cycle: int, current_state: dict[str, object]) -> None:
    """Write dead_ends_snapshot_cycle_<N>.json on work events."""
    snapshot_path = f"dead_ends_snapshot_cycle_{cycle}.json"
    active_de = current_state.get("active", {})
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(active_de, f, indent=2)


def _persist_altitude_reorientation(opinions_md: str) -> None:
    """Persist altitude-driven opinions updates even though opinions.md is gitignored."""
    hv.write_text(hv.OPINIONS_FILE, opinions_md)
    hv.run_command('git add -f opinions.md && git commit -m "V4.7: altitude reorientation"')


def _effective_graveyard_entry_cap(base_cap: int, altitude_mode: str | None) -> int:
    """Raise the graveyard cap for survey altitude so the prompt can see recent fossils."""
    if altitude_mode in {"survey", "negative-space", "displace"}:
        return max(base_cap, ALTITUDE_SURVEY_MIN_GRAVEYARD_ENTRIES)
    return base_cap


def _load_status_progress(default_max_cycles: int) -> tuple[int, int]:
    """Best-effort read of the current cycle/max_cycles from status.json."""
    status_path = Path(hv.STATUS_FILE)
    if not status_path.exists():
        return 0, default_max_cycles
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0, default_max_cycles
    try:
        cycle = int(payload.get("cycle", 0) or 0)
    except (TypeError, ValueError):
        cycle = 0
    try:
        max_cycles = int(payload.get("max_cycles", default_max_cycles) or default_max_cycles)
    except (TypeError, ValueError):
        max_cycles = default_max_cycles
    return cycle, max_cycles


def _write_terminal_marker(
    phase: str,
    last_result: str,
    last_error: str,
    default_max_cycles: int,
) -> None:
    """Persist a terminal status/telemetry marker after an unexpected exit path."""
    cycle, max_cycles = _load_status_progress(default_max_cycles)
    hv.write_status(
        cycle,
        max_cycles,
        phase,
        last_result=last_result,
        last_error=last_error,
    )
    _append_jsonl(
        TELEMETRY_FILE,
        {
            "cycle": cycle,
            "event": "terminal_marker",
            "phase": phase,
            "last_result": last_result,
            "last_error": last_error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


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

def _render_opinions_from_slots(slots: dict[str, str]) -> str:
    """Render opinions.md from compression pass slot values."""
    lines = []
    if slots.get("core_rule"):
        lines.append(f"Core rule: {slots['core_rule']}")
    if slots.get("alt_rule"):
        lines.append(f"Alternative: {slots['alt_rule']}")
    if slots.get("key_exclusion"):
        lines.append(f"Key exclusion: {slots['key_exclusion']}")
    if slots.get("uncertainty"):
        lines.append(f"Uncertainty: {slots['uncertainty']}")
    return "\n".join(lines)


def _check_alt_rule_duplication(core: str, alt: str) -> bool:
    """Return True if alt_rule is trivially duplicative of core_rule."""
    if not core or not alt:
        return False
    c = core.lower().strip()
    a = alt.lower().strip()
    # Exact match
    if c == a:
        return True
    # One is a substring of the other
    if c in a or a in c:
        return True
    # High token overlap — tokenize on whitespace, reject if ≥80% overlap
    c_tokens = set(c.split())
    a_tokens = set(a.split())
    if not c_tokens or not a_tokens:
        return False
    overlap = len(c_tokens & a_tokens)
    smaller = min(len(c_tokens), len(a_tokens))
    if smaller > 0 and overlap / smaller >= 0.8:
        return True
    return False


def _validate_compression_slots(
    raw: dict[str, object], target_len: int, theory_len_before: int
) -> tuple[dict[str, str] | None, str]:
    """Validate compression pass slot output.

    Returns (slots, rejection_reason). slots is None if validation fails.
    """
    # Check exactly the required keys
    raw_keys = set(raw.keys())
    missing_keys = COMPRESSION_SLOT_KEYS - raw_keys
    if missing_keys:
        return None, f"missing_keys: {sorted(missing_keys)}"
    extra_keys = raw_keys - COMPRESSION_SLOT_KEYS
    if extra_keys:
        return None, f"extra_keys: {sorted(extra_keys)}"

    # Extract and validate types + per-slot budgets
    slots: dict[str, str] = {}
    for key, max_chars in COMPRESSION_SLOTS.items():
        val = raw[key]
        if not isinstance(val, str):
            return None, f"{key}_not_string: {type(val).__name__}"
        val = val.strip()
        slots[key] = val
        if len(val) > max_chars:
            return None, f"{key}_overflow: {len(val)}/{max_chars}"

    # Render and check total length
    rendered = _render_opinions_from_slots(slots)
    if len(rendered) > target_len:
        return None, f"rendered_overflow: {len(rendered)}/{target_len}"
    if len(rendered) >= theory_len_before:
        return None, f"not_shorter_than_input: {len(rendered)}/{theory_len_before}"

    # core_rule must not be empty
    if not slots.get("core_rule"):
        return None, "core_rule_empty"

    # alt_rule duplication check
    if slots.get("alt_rule") and _check_alt_rule_duplication(
        slots["core_rule"], slots["alt_rule"]
    ):
        return None, "alt_rule_duplicates_core"

    return slots, ""


def run_compression_pass(
    cycle: int,
    args: argparse.Namespace,
    gradient: GradientState,
    passes: CompressionPassState,
) -> None:
    """Slot-based working-memory compression pass (v3).

    The model fills exactly four slots instead of writing free prose.
    The harness renders opinions.md from those slots.  dead-ends.json
    stays frozen — this compresses working memory only.
    """
    current_theory = hv.read_text(hv.OPINIONS_FILE) or ""
    current_dead_ends = hv.read_text(hv.DEAD_ENDS_JSON_FILE) or "{}"
    theory_len_before = len(current_theory)
    pre_pass_theory_hash = hashlib.md5(current_theory.encode()).hexdigest()[:8]
    target_len = _compression_target_len(theory_len_before, passes.target_compression)

    # Most recent rows from data.json for stall context
    data_slice = ""
    try:
        data_raw = hv.read_text(hv.DATA_FILE) or "[]"
        data_rows = json.loads(data_raw)
        if isinstance(data_rows, list) and len(data_rows) >= COMPRESSION_DATA_SLICE_ROWS:
            data_slice = json.dumps(data_rows[-COMPRESSION_DATA_SLICE_ROWS:], indent=2)
        elif isinstance(data_rows, list):
            data_slice = json.dumps(data_rows, indent=2)
    except (json.JSONDecodeError, OSError):
        pass

    slot_spec = ", ".join(f'"{k}": max {v} chars' for k, v in COMPRESSION_SLOTS.items())

    prompt = (
        f"COMPRESSION PASS #{passes.triggered_count + 1} — Cycle {cycle}\n\n"
        f"Best oracle: {passes.best_oracle_fixed or 0:.4f} (cycle {passes.best_oracle_cycle}). "
        f"Stalled for {passes.stall_count} cycles.\n\n"
        f"Fill exactly four slots. Do not write an essay. Do not explain.\n"
        f"Output a JSON object with exactly these keys:\n"
        f"  {slot_spec}\n\n"
        f"Current opinions.md length is {theory_len_before} chars.\n"
        f"Slot rules:\n"
        f"- core_rule: your current best active rule. One sentence, max 120 chars.\n"
        f"- alt_rule: a STRUCTURALLY DIFFERENT approach — not a variant, threshold "
        f"tweak, or parameterization of core_rule. One sentence, max 80 chars. "
        f"Leave empty string if no genuinely different alternative exists.\n"
        f"- key_exclusion: one important falsified family or dead-end pattern. "
        f"One sentence, max 95 chars.\n"
        f"- uncertainty: the main unresolved ambiguity. One sentence, max 75 chars.\n\n"
        f"Constraints:\n"
        f"- Total rendered opinions.md budget is {target_len} chars including labels/newlines.\n"
        f"- The rendered opinions.md must be strictly shorter than the current {theory_len_before}-char opinions.md.\n"
        f"- Each slot must respect its character budget. Overflow = rejection.\n"
        f"- No extra keys. No extra text. Only the four slots.\n"
        f"- Shorter is better.\n"
        f"- Any non-compliant output will be rejected and your current theory preserved."
    )

    user_content = prompt + f"\n\n# Current opinions.md\n{current_theory}"
    user_content += f"\n\n# Current dead-ends.json\n{current_dead_ends}"
    if data_slice:
        user_content += (f"\n\n# Most recent {COMPRESSION_DATA_SLICE_ROWS} rows of data.json "
                         f"(recent contradictions)\n{data_slice}")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    # --- Call API and validate ---
    raw_result: dict[str, object] = {}
    accepted = False
    rejection_reason = ""
    rendered = ""
    slots: dict[str, str] = {}

    try:
        raw_result = hv.invoke_openai(
            messages, args.model, args.api_base,
            api_key_env=args.api_key_env,
            max_tokens=gradient.output_budget,
        )

        validated_slots, rejection_reason = _validate_compression_slots(
            raw_result, target_len, theory_len_before
        )

        if validated_slots is not None:
            slots = validated_slots
            rendered = _render_opinions_from_slots(slots)
            hv.write_text(hv.OPINIONS_FILE, rendered + "\n")
            hv.run_command('git add . && git commit -m "V4.7: compression pass (slot)"')
            accepted = True
            print(f"  [COMPRESS] Cycle {cycle}: ACCEPTED — {theory_len_before} -> "
                  f"{len(rendered)} chars (target {target_len})")
        else:
            # Rejection — preserve original
            rendered = ""
            slots = {k: str(raw_result.get(k, "")) for k in COMPRESSION_SLOT_KEYS}
            print(f"  [COMPRESS] Cycle {cycle}: REJECTED — {rejection_reason}. "
                  f"Original preserved.")

    except RuntimeError as exc:
        rejection_reason = f"api_error: {exc}"
        print(f"  [COMPRESS] Cycle {cycle}: FAILED: {exc}")

    # --- Telemetry (capture stall BEFORE mark_triggered zeroes it) ---
    stall_count_at_trigger = passes.stall_count
    passes.mark_triggered()

    theory_len_after = len(rendered) if accepted else theory_len_before
    post_pass_theory = hv.read_text(hv.OPINIONS_FILE).strip()
    post_pass_theory_hash = hashlib.md5(post_pass_theory.encode()).hexdigest()[:8]

    raw_slot_json = json.dumps(raw_result) if raw_result else ""
    rendered_attempt = _render_opinions_from_slots(slots) if slots else ""
    overshoot = max(0, len(rendered_attempt) - target_len) if rendered_attempt else 0

    log_entry = {
        "cycle": cycle,
        "event": "compression_pass",
        "accepted": accepted,
        "rejection_reason": rejection_reason,
        "pass_number": passes.triggered_count,
        "target_compression": passes.target_compression,
        "target_len": target_len,
        "theory_len_before": theory_len_before,
        "theory_len_rendered_attempt": len(rendered_attempt),
        "theory_len_after": theory_len_after,
        "raw_slot_json_len": len(raw_slot_json),
        "overshoot_chars": overshoot,
        "core_rule_len": len(slots.get("core_rule", "")),
        "alt_rule_len": len(slots.get("alt_rule", "")),
        "key_exclusion_len": len(slots.get("key_exclusion", "")),
        "uncertainty_len": len(slots.get("uncertainty", "")),
        "slot_values": slots,
        "rendered_preview": rendered_attempt[:300],
        "pre_pass_theory_hash": pre_pass_theory_hash,
        "post_pass_theory_hash": post_pass_theory_hash,
        "best_oracle_fixed": round(passes.best_oracle_fixed or 0, 4),
        "best_oracle_cycle": passes.best_oracle_cycle,
        "stall_count_at_trigger": stall_count_at_trigger,
        "triggered_count": passes.triggered_count,
        "data_slice_rows": COMPRESSION_DATA_SLICE_ROWS,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _append_jsonl(COMPRESSION_LOG_FILE, log_entry)

    # Log opinions history for compression pass
    _log_opinions_history(cycle, "compression_pass", post_pass_theory, post_pass_theory_hash)

    pass_telem = {
        "cycle": cycle,
        "prompt_budget": gradient.prompt_budget,
        "output_budget": gradient.output_budget,
        "cycle_type": "compression_pass",
        "compression_pass": True,
        "accepted": accepted,
        "rejection_reason": rejection_reason,
        "pass_number": passes.triggered_count,
        "target_compression": passes.target_compression,
        "target_len": target_len,
        "theory_len_before": theory_len_before,
        "theory_len_rendered_attempt": len(rendered_attempt),
        "theory_len_after": theory_len_after,
        "raw_slot_json_len": len(raw_slot_json),
        "overshoot_chars": overshoot,
        "core_rule_len": len(slots.get("core_rule", "")),
        "alt_rule_len": len(slots.get("alt_rule", "")),
        "key_exclusion_len": len(slots.get("key_exclusion", "")),
        "uncertainty_len": len(slots.get("uncertainty", "")),
        "compression_ratio_actual": round(theory_len_after / max(theory_len_before, 1), 4),
        "best_oracle_fixed": round(passes.best_oracle_fixed or 0, 4),
        "best_oracle_cycle": passes.best_oracle_cycle,
        "stall_count_at_trigger": stall_count_at_trigger,
        "pre_pass_theory_hash": pre_pass_theory_hash,
        "post_pass_theory_hash": post_pass_theory_hash,
        "theory_hash": post_pass_theory_hash,
        "opinions_text_hash": post_pass_theory_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    pass_telem.update(hv._cycle_usage)
    pass_telem.update(_cycle_usage_aliases())
    _append_jsonl(TELEMETRY_FILE, pass_telem)


def request_altitude_map(
    cycle: int,
    args: argparse.Namespace,
    gradient: GradientState,
    current_state: dict[str, object],
    altitude_mode: str,
    previous_map: str,
) -> dict[str, str]:
    """Run a metacognitive survey without invoking the solver schema.

    Returns dict with keys:
        "map": altitude map text (always present)
        "opinions_md": updated theory text (survey/negative-space modes only, may be empty)
    """
    prompt_messages = hv.format_cycle_prompt(
        cycle,
        args.max_cycles,
        "grind",
        current_state,
        altitude_mode=altitude_mode,
        context_window_hud=(
            f"Prompt budget: {gradient.prompt_budget}/{gradient.initial_prompt_budget} tokens. "
            f"Output budget: {gradient.output_budget} tokens (fixed)."
        ),
        altitude_map=previous_map or None,
        max_graveyard_entries=gradient.max_graveyard_entries,
        prompt_budget_tokens=gradient.prompt_budget,
    )

    if altitude_mode in {"survey", "negative-space", "displace"}:
        system_content = (
            "You are the metacognitive survey instrument of Avalanche V4.7.\n"
            "Output only a single raw JSON object with exactly two keys:\n"
            "  altitude_map: your structured comparison analysis (string)\n"
            "  opinions_md: your updated theory incorporating any new direction (string)\n"
            "No markdown fences. No extra keys."
        )
    else:
        system_content = (
            "You are the metacognitive survey instrument of Avalanche V4.7.\n"
            "Output only a single raw JSON object with exactly one key: altitude_map.\n"
            "The altitude_map value must be a plain string containing the survey text.\n"
            "No markdown fences. No extra keys."
        )

    altitude_messages = [
        {"role": "system", "content": system_content},
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

    result = {"map": altitude_text[:1200], "opinions_md": ""}
    if altitude_mode in {"survey", "negative-space", "displace"}:
        result["opinions_md"] = str(payload.get("opinions_md", "")).strip()
    return result


# ---------------------------------------------------------------------------
# Main compression loop
# ---------------------------------------------------------------------------

def run_compression_loop(args: argparse.Namespace) -> str:
    """Run the compression experiment loop. Returns final status string."""

    rng = random.Random(args.seed + args.run_id)
    hv._rng.seed(args.seed + args.run_id)

    gradient = GradientState(
        initial_prompt_budget=args.initial_window,
        floor=args.floor,
        decay=args.decay,
        total_cycles=args.max_cycles,
    )
    passes = CompressionPassState(
        stagnation_window=args.stagnation_window,
        target_compression=args.compression_target,
        max_passes=args.max_passes,
    )
    altitude = AltitudeState(
        frequency=args.altitude_frequency,
        prompt_style=args.altitude_prompt,
    )

    # Convergence state
    consecutive_perfect: int = 0
    previous_theory_hash: str | None = None
    best_oracle_score: float = 0.0
    previous_complexity: int = 0

    # Calorimeter state (V4.7.1)
    previous_fixed_vector: list[bool] | None = None
    previous_ast_node_count: int = 0
    previous_ast_structure_hash: str = ""

    print(f"\n  [V4.7] Starting compression loop")
    print(f"  [V4.7] Prompt gradient: {args.initial_window} -> {args.floor} ({args.decay})")
    print(f"  [V4.7] Output budget: {gradient.output_budget} (fixed)")
    print(f"  [V4.7] Features: gradient={'ON' if not args.no_gradient else 'OFF'}, "
          f"passes={'ON' if not args.no_passes else 'OFF'}, "
          f"altitude={'ON' if not args.no_altitude else 'OFF'}")
    if not args.no_altitude:
        print(f"  [V4.7] Altitude: every {args.altitude_frequency} cycles, "
              f"prompt={args.altitude_prompt}")
    if not args.no_passes:
        print(f"  [V4.7] Compression passes: stagnation={args.stagnation_window}, "
              f"target={args.compression_target:.0%}, max={args.max_passes}")
        print(f"  [V4.7] Compression input gate: min opinions len={args.compression_min_input_len}")

    for cycle in range(1, args.max_cycles + 1):
        hv.reset_cycle_usage()
        previous_opinions = hv.read_text(hv.OPINIONS_FILE)
        previous_state = load_state(hv.DEAD_END_STATE_FILE)

        # Advance gradient
        if not args.no_gradient:
            gradient.tick()
        else:
            gradient.cycle_count = cycle

        prompt_budget = gradient.prompt_budget
        output_budget = gradient.output_budget  # fixed at 1200

        # --- Compression pass check (before altitude, before normal cycle) ---
        if not args.no_passes and passes.should_trigger():
            current_theory_len = len(previous_opinions)
            if current_theory_len < args.compression_min_input_len:
                print(
                    f"  [V4.7] Cycle {cycle} — compression deferred "
                    f"(theory_len={current_theory_len} < min={args.compression_min_input_len})"
                )
                _append_jsonl(COMPRESSION_LOG_FILE, {
                    "cycle": cycle,
                    "event": "compression_deferred_short_input",
                    "theory_len_before": current_theory_len,
                    "compression_min_input_len": args.compression_min_input_len,
                    "stall_count": passes.stall_count,
                    "pass_number": passes.triggered_count + 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            else:
                print(f"  [V4.7] Cycle {cycle} — COMPRESSION PASS (prompt_budget={prompt_budget})")
                hv.write_status(cycle, args.max_cycles, "COMPRESSION_PASS")
                run_compression_pass(cycle, args, gradient, passes)
                continue

        # --- Altitude check ---
        altitude_mode = None
        if not args.no_altitude and altitude.should_fire(cycle):
            altitude_mode = altitude.next_altitude()

        mode_label = f"ALTITUDE_{altitude_mode.upper()}" if altitude_mode else "GRIND"
        hv.write_status(cycle, args.max_cycles, mode_label)
        print(f"  [V4.7] Cycle {cycle}/{args.max_cycles} — {mode_label} (prompt={prompt_budget}, output={output_budget})")

        # --- Build prompt kwargs ---
        prompt_kwargs: dict[str, Any] = {
            "context_window_hud": (
                f"Prompt budget: {prompt_budget}/{gradient.initial_prompt_budget} tokens. "
                f"Output budget: {output_budget} tokens (fixed)."
            ),
            "max_graveyard_entries": _effective_graveyard_entry_cap(
                gradient.max_graveyard_entries, altitude_mode
            ),
            "prompt_budget_tokens": prompt_budget,
        }
        if altitude_mode:
            prompt_kwargs["altitude_mode"] = altitude_mode
        if altitude.last_map:
            prompt_kwargs["altitude_map"] = altitude.last_map

        # --- Altitude cycle: extract map and skip oracle ---
        if altitude_mode:
            altitude_result = None
            for format_attempt in range(FORMAT_FAIL_MAX_RETRIES + 1):
                try:
                    altitude_result = request_altitude_map(
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
            if altitude_result is None:
                _append_jsonl(TELEMETRY_FILE, {
                    "cycle": cycle,
                    "prompt_budget": prompt_budget,
                    "output_budget": output_budget,
                    "altitude_mode": altitude_mode,
                    "event": "altitude_fatal",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                continue
            altitude.last_map = altitude_result["map"]
            opinions_before = previous_opinions
            opinions_updated = False

            # Survey mode: write updated opinions.md if the model produced one
            if altitude_result.get("opinions_md"):
                _persist_altitude_reorientation(altitude_result["opinions_md"])
                opinions_updated = True
                print(f"  [ALTITUDE] {altitude_mode}: map={len(altitude.last_map)} chars, "
                      f"opinions updated ({len(opinions_before)}->{len(altitude_result['opinions_md'])} chars)")
            else:
                print(f"  [ALTITUDE] {altitude_mode}: map={len(altitude.last_map)} chars")

            # Log opinions history for altitude cycle
            alt_opinions_text = hv.read_text(hv.OPINIONS_FILE).strip()
            alt_opinions_hash = hashlib.md5(alt_opinions_text.encode()).hexdigest()[:8]
            _log_opinions_history(cycle, f"altitude_{altitude_mode}", alt_opinions_text, alt_opinions_hash)

            # Probe G for altitude cycle
            alt_active_de = previous_state.get("active", {})
            if not isinstance(alt_active_de, dict):
                alt_active_de = {}
            alt_claims_text = _dead_ends_claims_text(alt_active_de)
            alt_probe_g = round(semantic_distance(alt_opinions_text, alt_claims_text), 4) if alt_claims_text else None

            altitude_telem = {
                "cycle": cycle, "prompt_budget": prompt_budget,
                "output_budget": output_budget,
                "cycle_type": f"altitude_{altitude_mode}",
                "altitude_mode": altitude_mode,
                "altitude_map_len": len(altitude.last_map),
                "altitude_map": altitude.last_map,
                "opinions_updated": opinions_updated,
                "opinions_len_before": len(opinions_before),
                "opinions_len_after": len(altitude_result.get("opinions_md", "")) if opinions_updated else len(opinions_before),
                "compression_pass": False,
                "theory_hash": alt_opinions_hash,
                "opinions_text_hash": alt_opinions_hash,
                "probe_g_distance": alt_probe_g,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            altitude_telem.update(hv._cycle_usage)
            altitude_telem.update(_cycle_usage_aliases())
            _append_jsonl(TELEMETRY_FILE, altitude_telem)
            _append_jsonl(COMPRESSION_LOG_FILE, {
                "cycle": cycle,
                "event": f"altitude_{altitude_mode}",
                "map_len": len(altitude.last_map),
                "altitude_map": altitude.last_map,
                "opinions_updated": opinions_updated,
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
                "cycle": cycle, "prompt_budget": prompt_budget,
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
        fixed_score, fixed_passed, fixed_total, _, fixed_vector, fixed_failure_cat = evaluate_solver_fractional(
            fixed_suite, hv.hidden_law, str(Path(hv.SOLVER_FILE))
        )

        # Oracle: combined (fixed + random) for ratchet/telemetry
        random_cases = [hv.generate_permutation_array(rng) for _ in range(args.tests_per_cycle)]
        all_cases = fixed_suite + random_cases
        oracle_score, passed, total, failure_report, _, _ = evaluate_solver_fractional(
            all_cases, hv.hidden_law, str(Path(hv.SOLVER_FILE))
        )

        # Record fixed score for compression pass trigger
        passes.record(fixed_score, cycle)

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
                hv.persist_dead_end_workspace(current_state)

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
                "cycle": cycle, "prompt_budget": prompt_budget,
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

        # --- Calorimeter sensors (V4.7.1) ---
        theory_len = len(current_theory)
        opinions_text_hash = current_hash[:8]
        dead_end_count = len(proposed_dead_ends.get("basins", [])) + \
                         len(proposed_dead_ends.get("families", [])) + \
                         len(proposed_dead_ends.get("locals", []))

        # S_t: Hamming surprise on fixed suite
        hamming = None
        if previous_fixed_vector is not None and len(fixed_vector) == len(previous_fixed_vector):
            hamming = _hamming_distance(previous_fixed_vector, fixed_vector)
        previous_fixed_vector = list(fixed_vector)

        # AST_t: code structure movement
        ast_node_count = hv.solver_ast_node_count(proposed_solver)
        ast_structure_hash = hv.solver_ast_structure_hash(proposed_solver)
        ast_node_delta = abs(ast_node_count - previous_ast_node_count) if previous_ast_node_count else 0
        ast_hash_changed = (ast_structure_hash != previous_ast_structure_hash) if previous_ast_structure_hash else False
        previous_ast_node_count = ast_node_count
        previous_ast_structure_hash = ast_structure_hash

        # W_t: work event proxy
        current_active = current_state.get("active", {})
        if not isinstance(current_active, dict):
            current_active = {}
        prev_active = previous_state.get("active", {})
        if not isinstance(prev_active, dict):
            prev_active = {}
        work_event = detect_work_event(prev_active, current_active)

        # Work-event snapshot (or every cycle if requested)
        if args.snapshot_every_cycle or work_event:
            _snapshot_dead_ends(cycle, current_state)

        # Opinions history
        _log_opinions_history(cycle, "grind", current_theory, opinions_text_hash)

        # Probe G: theory/graveyard semantic distance
        active_de = current_state.get("active", {})
        if not isinstance(active_de, dict):
            active_de = {}
        claims_text = _dead_ends_claims_text(active_de)
        probe_g_distance = round(semantic_distance(current_theory, claims_text), 4) if claims_text else None

        # --- Telemetry ---
        grind_telem = {
            "cycle": cycle,
            "prompt_budget": prompt_budget,
            "output_budget": output_budget,
            "cycle_type": "grind",
            "oracle_fixed": round(fixed_score, 4),
            "oracle_combined": round(oracle_score, 4),
            "altitude_mode": None,
            "compression_pass": False,
            "theory_hash": opinions_text_hash,
            "opinions_text_hash": opinions_text_hash,
            "theory_len": theory_len,
            "dead_end_count": dead_end_count,
            "graveyard_entries_shown": gradient.max_graveyard_entries if not args.no_gradient else None,
            "best_oracle_fixed": round(passes.best_oracle_fixed or 0, 4),
            "best_oracle": round(best_oracle_score, 4),
            "stall_count": passes.stall_count,
            "passes_triggered": passes.triggered_count,
            "passes_remaining": passes.max_passes - passes.triggered_count,
            "compression_input_eligible": theory_len >= args.compression_min_input_len,
            "compression_min_input_len": args.compression_min_input_len,
            # Calorimeter sensors
            "fixed_suite_vector": fixed_vector,
            "hamming_distance": hamming,
            "first_failure_category": fixed_failure_cat,
            "solver_ast_node_count": ast_node_count,
            "solver_ast_structure_hash": ast_structure_hash,
            "solver_ast_node_delta": ast_node_delta,
            "solver_ast_hash_changed": ast_hash_changed,
            "work_event": work_event,
            "probe_g_distance": probe_g_distance,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        grind_telem.update(hv._cycle_usage)
        grind_telem.update(_cycle_usage_aliases())
        _append_jsonl(TELEMETRY_FILE, grind_telem)

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
    parser.add_argument("--stagnation-window", type=int, default=15,
                        help="Consecutive cycles without oracle improvement to trigger compression pass")
    parser.add_argument("--compression-target", type=float, default=0.5,
                        help="Target compression ratio for compression passes (0.5 = compress to 50%%)")
    parser.add_argument("--max-passes", type=int, default=3,
                        help="Maximum compression passes per run")
    parser.add_argument("--compression-min-input-len", type=int, default=240,
                        help="Only trigger passes when opinions.md is at least this long")
    parser.add_argument("--no-passes", action="store_true",
                        help="Disable compression passes")

    # Altitude cycles
    parser.add_argument("--altitude-frequency", type=int, default=10,
                        help="Altitude survey every N cycles")
    parser.add_argument("--altitude-prompt", choices=["survey", "negative-space", "rotating", "displace"],
                        default="survey",
                        help="Altitude prompt style: 'survey' (factual comparison), 'negative-space' (untested direction), 'rotating' (low/medium/high), or 'displace' (graveyard-aware interaction surface)")
    parser.add_argument("--no-altitude", action="store_true",
                        help="Disable altitude cycles")

    # Fork / inject / snapshot
    parser.add_argument("--fork-snapshot", type=str, default=None,
                        help="Path to frozen snapshot directory to fork (copies opinions.md and dead-ends.json)")
    parser.add_argument("--inject-graveyard", type=str, default=None,
                        help="Path to synthetic dead-ends JSON to inject after forking")
    parser.add_argument("--snapshot-every-cycle", action="store_true",
                        help="Write graveyard snapshot every cycle (not just on work events)")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
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

        # Fork from frozen snapshot if requested
        if args.fork_snapshot:
            from v44_epistemics import render_dead_ends_md
            snap_dir = Path(args.fork_snapshot)
            snap_opinions = snap_dir / "opinions.md"
            snap_dead_ends = snap_dir / "dead-ends.json"
            if not snap_opinions.exists():
                raise FileNotFoundError(f"Fork snapshot missing opinions.md: {snap_opinions}")
            if not snap_dead_ends.exists():
                raise FileNotFoundError(f"Fork snapshot missing dead-ends.json: {snap_dead_ends}")
            # Copy opinions
            hv.write_text(hv.OPINIONS_FILE, snap_opinions.read_text(encoding="utf-8"))
            # Copy and render dead-ends
            de_data = json.loads(snap_dead_ends.read_text(encoding="utf-8"))
            hv.write_json(hv.DEAD_ENDS_JSON_FILE, de_data)
            hv.write_text(hv.DEAD_ENDS_FILE, render_dead_ends_md(de_data))
            # Initialize state with forked graveyard
            forked_state = merge_state(blank_state(), de_data, cycle=0)
            save_state(hv.DEAD_END_STATE_FILE, forked_state)
            hv.run_command(
                f'git add -f {hv.OPINIONS_FILE} {hv.DEAD_ENDS_JSON_FILE} '
                f'{hv.DEAD_ENDS_FILE} {hv.DEAD_END_STATE_FILE} && '
                f'git commit -m "V4.7: fork from snapshot {snap_dir.name}"'
            )
            print(f"  Forked from snapshot: {snap_dir}")

        # Inject synthetic graveyard if requested (overwrites fork)
        if args.inject_graveyard:
            from v44_epistemics import render_dead_ends_md
            inject_path = Path(args.inject_graveyard)
            if not inject_path.exists():
                raise FileNotFoundError(f"Inject graveyard file not found: {inject_path}")
            de_data = json.loads(inject_path.read_text(encoding="utf-8"))
            hv.write_json(hv.DEAD_ENDS_JSON_FILE, de_data)
            hv.write_text(hv.DEAD_ENDS_FILE, render_dead_ends_md(de_data))
            injected_state = merge_state(blank_state(), de_data, cycle=0)
            save_state(hv.DEAD_END_STATE_FILE, injected_state)
            hv.run_command(
                f'git add -f {hv.DEAD_ENDS_JSON_FILE} {hv.DEAD_ENDS_FILE} '
                f'{hv.DEAD_END_STATE_FILE} && '
                f'git commit -m "V4.7: inject synthetic graveyard {inject_path.name}"'
            )
            print(f"  Injected synthetic graveyard: {inject_path}")

        def _signal_exit(signum: int, _frame: object) -> None:
            signame = signal.Signals(signum).name
            _write_terminal_marker(
                phase=signame,
                last_result="FAIL",
                last_error=f"Process received {signame}",
                default_max_cycles=args.max_cycles,
            )
            raise SystemExit(128 + signum)

        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, _signal_exit)

        # Add assay-specific files to gitignore
        from v44_epistemics import SUPERSEDED_LOG_FILE
        assay_ignores = {TELEMETRY_FILE, COMPRESSION_LOG_FILE, OPINIONS_HISTORY_FILE, SUPERSEDED_LOG_FILE}
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
    except Exception as exc:
        traceback.print_exc()
        _write_terminal_marker(
            phase="CRASH",
            last_result="FAIL",
            last_error=f"{type(exc).__name__}: {exc}",
            default_max_cycles=args.max_cycles,
        )
        raise


if __name__ == "__main__":
    main()
