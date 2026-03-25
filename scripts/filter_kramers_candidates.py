#!/usr/bin/env python3
"""Filter basin-transition candidates down to likely macrostate moves.

This consumes the outputs from `extract_basin_transitions.py` and adds one
more pass aimed at the Kramers fit:

- keep basin-id transitions by default
- keep basin-claim transitions when the active claim text changes
- reject support-only/citation-only rewires
- annotate every decision with an explicit reason
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"[a-z0-9]+")


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


def parse_run_arg(raw: str) -> tuple[str, Path]:
    if "=" in raw:
        label, path_str = raw.split("=", 1)
        return label.strip(), Path(path_str.strip())
    path = Path(raw.strip())
    return path.stem.replace("_transition_candidates", ""), path


def basin_map(basins: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(basin.get("id")): basin for basin in basins}


def claim_text(value: dict[str, Any] | None) -> str:
    if not value:
        return ""
    return str(value.get("claim") or "").strip()


def token_set(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def jaccard_distance(text_a: str, text_b: str) -> float:
    a = token_set(text_a)
    b = token_set(text_b)
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return 1.0 - (len(a & b) / len(union))


def abs_score_delta(row: dict[str, Any]) -> float:
    current = row.get("oracle_fixed")
    previous = row.get("oracle_fixed_prev")
    try:
        if current is None or previous is None:
            return 0.0
        return abs(float(current) - float(previous))
    except (TypeError, ValueError):
        return 0.0


def classify_candidate(row: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    category = row.get("category")
    from_basins = basin_map(row.get("from_basins") or [])
    to_basins = basin_map(row.get("to_basins") or [])

    if category == "basin_id_transition":
        return True, "basin_id_changed", {
            "score_delta": abs_score_delta(row),
            "claim_distance_max": None,
        }

    if category != "basin_content_transition":
        return False, "not_macrostate_category", {
            "score_delta": abs_score_delta(row),
            "claim_distance_max": None,
        }

    changed_ids = row.get("basin_changed") or []
    if not changed_ids:
        return False, "basin_content_without_changed_ids", {
            "score_delta": abs_score_delta(row),
            "claim_distance_max": None,
        }

    claim_changed = False
    claim_distance_max = 0.0
    for basin_id in changed_ids:
        before = claim_text(from_basins.get(basin_id))
        after = claim_text(to_basins.get(basin_id))
        if before != after:
            claim_changed = True
            claim_distance_max = max(claim_distance_max, jaccard_distance(before, after))

    if not claim_changed:
        return False, "support_only_basin_rewire", {
            "score_delta": abs_score_delta(row),
            "claim_distance_max": round(claim_distance_max, 6),
        }

    score_delta = abs_score_delta(row)
    hamming = row.get("hamming_distance")
    family_structure = bool(
        (row.get("family_added") or [])
        or (row.get("family_removed") or [])
        or (row.get("family_changed") or [])
    )
    local_structure = bool(
        (row.get("local_added") or [])
        or (row.get("local_removed") or [])
        or (row.get("local_changed") or [])
    )
    work_event = bool(row.get("work_event"))

    dynamic_support = (
        work_event
        or score_delta >= 0.0833
        or (isinstance(hamming, (int, float)) and hamming > 0)
        or family_structure
        or local_structure
    )

    if dynamic_support:
        return True, "claim_changed_with_support", {
            "score_delta": round(score_delta, 6),
            "claim_distance_max": round(claim_distance_max, 6),
        }

    if claim_distance_max >= 0.5:
        return True, "claim_changed_large_distance", {
            "score_delta": round(score_delta, 6),
            "claim_distance_max": round(claim_distance_max, 6),
        }

    return False, "claim_changed_but_weak_support", {
        "score_delta": round(score_delta, 6),
        "claim_distance_max": round(claim_distance_max, 6),
    }


def run_filter(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = load_jsonl(path)
    kept: list[dict[str, Any]] = []
    decision_counts: dict[str, int] = {}
    kept_counts: dict[str, int] = {}

    for row in rows:
        keep, reason, evidence = classify_candidate(row)
        enriched = dict(row)
        enriched["kramers_keep"] = keep
        enriched["kramers_reason"] = reason
        enriched["kramers_evidence"] = evidence
        decision_counts[reason] = decision_counts.get(reason, 0) + 1
        if keep:
            kept_counts[row.get("category", "unknown")] = kept_counts.get(row.get("category", "unknown"), 0) + 1
            kept.append(enriched)

    summary = {
        "source": str(path),
        "total_rows": len(rows),
        "kept_rows": len(kept),
        "decision_counts": decision_counts,
        "kept_category_counts": kept_counts,
    }
    return kept, summary


def write_outputs(output_dir: Path, label: str, kept: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{label}_kramers_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    with (output_dir / f"{label}_kramers_candidates.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in kept:
            handle.write(json.dumps(row) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter transition candidates down to likely Kramers macrostates.")
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        help="Candidate spec as label=PATH or just PATH. Repeat for multiple runs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output directory for filtered artifacts.",
    )
    args = parser.parse_args()

    for raw in args.run:
        label, path = parse_run_arg(raw)
        kept, summary = run_filter(path)
        if args.output_dir:
            write_outputs(args.output_dir, label, kept, summary)
        print(json.dumps({
            "label": label,
            "summary": summary,
        }))


if __name__ == "__main__":
    main()
