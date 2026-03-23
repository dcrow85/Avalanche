#!/usr/bin/env python3
"""Compute PE_t-v2: three-surface narrative/code/graveyard coupling states.

PE_t-v1 compared only opinions drift against code drift. With exact
`dead_ends_history.jsonl`, we can now distinguish:

- pattern_eater: narrative high, code low, graveyard static
- bow_shock_advance: narrative high, code low, graveyard moved
- genuine_coupled_advance: narrative high, code high, graveyard moved
- silent_structural_work: narrative low, code high, graveyard moved
- administrative_or_stasis: nothing moved

Additional fallback classes are emitted for combinations that do occur but do
not fit the core five-way interpretation cleanly.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def jaccard_distance(text_a: str, text_b: str) -> float:
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a and not words_b:
        return 0.0
    union = words_a | words_b
    if not union:
        return 0.0
    return 1.0 - len(words_a & words_b) / len(union)


def ast_structure_distance(
    hash_changed: bool,
    node_delta: int,
    node_count: int,
) -> float:
    if not hash_changed:
        return 0.0
    if node_count > 0:
        return 1.0 + (node_delta / max(node_count, 1))
    return 1.0


def positive_median(values: list[float], default: float) -> float:
    positives = [v for v in values if v > 0]
    if not positives:
        return default
    return float(statistics.median(positives))


def positive_quantile(values: list[float], default: float, q: float) -> float:
    positives = sorted(v for v in values if v > 0)
    if not positives:
        return default
    if len(positives) == 1:
        return float(positives[0])
    idx = max(0, min(len(positives) - 1, round((len(positives) - 1) * q)))
    return float(positives[idx])


def classify_state(
    narrative_high: bool,
    code_high: bool,
    graveyard_drift: bool,
) -> str:
    if narrative_high and not code_high and not graveyard_drift:
        return "pattern_eater"
    if narrative_high and not code_high and graveyard_drift:
        return "bow_shock_advance"
    if narrative_high and code_high and graveyard_drift:
        return "genuine_coupled_advance"
    if not narrative_high and code_high and graveyard_drift:
        return "silent_structural_work"
    if not narrative_high and not code_high and not graveyard_drift:
        return "administrative_or_stasis"
    if narrative_high and code_high and not graveyard_drift:
        return "code_narrative_without_graveyard"
    if not narrative_high and not code_high and graveyard_drift:
        return "graveyard_only_shift"
    if not narrative_high and code_high and not graveyard_drift:
        return "code_only_wobble"
    return "mixed_transition"


def latest_cycle_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse retries to the last row seen for each cycle.

    Telemetry can contain multiple grind rows for the same cycle when the assay
    retries after sync turbulence. The last row is the canonical end-of-cycle
    state and is the one we want for step-to-step classification.
    """
    latest: dict[int, dict[str, Any]] = {}
    order: list[int] = []
    for row in rows:
        if "cycle" not in row:
            continue
        cycle = int(row["cycle"])
        if cycle not in latest:
            order.append(cycle)
        latest[cycle] = row
    return [latest[cycle] for cycle in order]


def build_step_rows(
    telemetry: list[dict[str, Any]],
    opinions_history: list[dict[str, Any]],
    dead_ends_history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    opinion_rows = latest_cycle_rows([
        row for row in opinions_history
        if row.get("cycle_type") in (None, "grind") and "cycle" in row
    ])
    dead_rows = latest_cycle_rows([
        row for row in dead_ends_history
        if row.get("cycle_type") in (None, "grind") and "cycle" in row
    ])
    opinions_by_cycle = {
        int(row["cycle"]): row.get("opinions_text", "")
        for row in opinion_rows
    }
    dead_by_cycle = {
        int(row["cycle"]): row
        for row in dead_rows
    }
    grind_rows = latest_cycle_rows([
        row for row in telemetry
        if row.get("cycle_type") in (None, "grind") and "oracle_fixed" in row
    ])

    results: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for row in grind_rows:
        cycle = int(row.get("cycle"))
        if previous is None:
            previous = row
            continue

        prev_cycle = int(previous.get("cycle"))
        opinions_now = opinions_by_cycle.get(cycle, "")
        opinions_prev = opinions_by_cycle.get(prev_cycle, "")
        narrative_drift = jaccard_distance(opinions_prev, opinions_now)

        code_drift = ast_structure_distance(
            bool(row.get("solver_ast_hash_changed")),
            int(row.get("solver_ast_node_delta") or 0),
            int(row.get("solver_ast_node_count") or 0),
        )

        dead_now = dead_by_cycle.get(cycle, {})
        dead_prev = dead_by_cycle.get(prev_cycle, {})
        graveyard_drift = (
            dead_now.get("dead_ends_hash") is not None
            and dead_now.get("dead_ends_hash") != dead_prev.get("dead_ends_hash")
        )

        results.append({
            "cycle": cycle,
            "previous_cycle": prev_cycle,
            "oracle_fixed": row.get("oracle_fixed"),
            "work_event": row.get("work_event"),
            "hamming_distance": row.get("hamming_distance"),
            "probe_g_distance": row.get("probe_g_distance"),
            "solver_ast_structure_hash": row.get("solver_ast_structure_hash"),
            "narrative_drift": round(narrative_drift, 6),
            "code_drift": round(code_drift, 6),
            "graveyard_drift": graveyard_drift,
            "dead_ends_hash": dead_now.get("dead_ends_hash"),
        })
        previous = row
    return results


def classify_steps(
    steps: list[dict[str, Any]],
    *,
    narrative_threshold: float | None = None,
    code_threshold: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not steps:
        summary = {
            "narrative_threshold": narrative_threshold,
            "code_threshold": code_threshold,
            "class_counts": {},
            "total_steps": 0,
        }
        return [], summary

    narrative_values = [float(step["narrative_drift"]) for step in steps]
    code_values = [float(step["code_drift"]) for step in steps]

    n_thresh = narrative_threshold if narrative_threshold is not None else positive_quantile(narrative_values, 0.25, 0.35)
    c_thresh = code_threshold if code_threshold is not None else positive_median(code_values, 1.0)

    class_counts: dict[str, int] = {}
    classified: list[dict[str, Any]] = []
    for step in steps:
        narrative_high = float(step["narrative_drift"]) >= n_thresh and float(step["narrative_drift"]) > 0
        code_high = float(step["code_drift"]) >= c_thresh and float(step["code_drift"]) > 0
        klass = classify_state(narrative_high, code_high, bool(step["graveyard_drift"]))
        class_counts[klass] = class_counts.get(klass, 0) + 1
        enriched = dict(step)
        enriched["narrative_high"] = narrative_high
        enriched["code_high"] = code_high
        enriched["classification"] = klass
        classified.append(enriched)

    summary = {
        "narrative_threshold": round(n_thresh, 6),
        "code_threshold": round(c_thresh, 6),
        "class_counts": class_counts,
        "total_steps": len(classified),
    }
    return classified, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute PE_t-v2 coupling-state classifications.")
    parser.add_argument("--telemetry", required=True, help="Path to telemetry.jsonl")
    parser.add_argument("--opinions", required=True, help="Path to opinions_history.jsonl")
    parser.add_argument("--dead-ends", required=True, help="Path to dead_ends_history.jsonl")
    parser.add_argument("--output", default=None, help="Optional output JSONL path")
    parser.add_argument("--summary-output", default=None, help="Optional summary JSON path")
    parser.add_argument("--narrative-threshold", type=float, default=None, help="Override narrative-drift threshold")
    parser.add_argument("--code-threshold", type=float, default=None, help="Override code-drift threshold")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    telemetry = load_jsonl(Path(args.telemetry))
    opinions = load_jsonl(Path(args.opinions))
    dead_ends = load_jsonl(Path(args.dead_ends))
    steps = build_step_rows(telemetry, opinions, dead_ends)
    classified, summary = classify_steps(
        steps,
        narrative_threshold=args.narrative_threshold,
        code_threshold=args.code_threshold,
    )

    if args.output:
        out_path = Path(args.output)
        with out_path.open("w", encoding="utf-8", newline="\n") as f:
            for row in classified:
                f.write(json.dumps(row) + "\n")
    else:
        for row in classified:
            print(json.dumps(row))

    if args.summary_output:
        Path(args.summary_output).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    else:
        print(json.dumps({"summary": summary}))


if __name__ == "__main__":
    main()
