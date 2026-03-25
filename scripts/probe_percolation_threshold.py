#!/usr/bin/env python3
"""Probe for a percolation-like oracle-evidence threshold by dwell episode."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

from scipy.optimize import curve_fit


DEFAULT_DWELL_ROOT = Path(r"C:\Avalanche\local-runs\kramers-v472-mirror\kramers-dwell-v2")
DEFAULT_MIRROR_ROOT = Path(r"C:\Avalanche\local-runs\kramers-v472-mirror")
DEFAULT_OUTPUT = Path(r"C:\Avalanche\local-runs\kramers-v472-mirror\probe-percolation")
RUN_LABELS = ["haiku", "gpt54", "qwen", "displace"]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def latest_cycle_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def canonical_grind_telemetry(path: Path) -> list[dict[str, Any]]:
    rows = load_jsonl(path)
    return latest_cycle_rows([
        row for row in rows
        if row.get("cycle_type") in (None, "grind") and "oracle_fixed" in row
    ])


def parse_bool_vector(value: Any) -> tuple[bool, ...] | None:
    if isinstance(value, list) and all(isinstance(item, bool) for item in value):
        return tuple(value)
    return None


def load_max_cycle(status_path: Path) -> int:
    data = json.loads(status_path.read_text(encoding="utf-8"))
    cycle = data.get("cycle") or data.get("max_cycles") or 0
    return int(cycle)


def run_name_for_label(label: str) -> str:
    if label == "gpt54":
        return "v472-history-gpt54"
    if label == "qwen":
        return "v472-history-qwen"
    if label == "haiku":
        return "v472-history-haiku"
    return "v472-displace-prompt"


def sigmoid(x: float, x_c: float, k: float) -> float:
    z = max(-60.0, min(60.0, -k * (x - x_c)))
    return 1.0 / (1.0 + math.exp(z))


def episode_rows(
    dwell_rows: list[dict[str, Any]],
    telemetry_rows: list[dict[str, Any]],
    max_cycle: int,
) -> list[dict[str, Any]]:
    telemetry_by_cycle = {int(row["cycle"]): row for row in telemetry_rows}
    cycles = sorted(telemetry_by_cycle)
    transition_cycles = sorted(int(row["cycle"]) for row in dwell_rows)

    episodes: list[dict[str, Any]] = []
    previous_transition = 0
    for idx, transition_cycle in enumerate(transition_cycles):
        start = previous_transition if previous_transition > 0 else 1
        dwell_cycles = [c for c in cycles if start <= c < transition_cycle]
        episode = build_episode(dwell_cycles, telemetry_by_cycle, transitioned=True, end_cycle=transition_cycle)
        episode["episode_index"] = idx + 1
        episodes.append(episode)
        previous_transition = transition_cycle

    if previous_transition < max_cycle:
        start = previous_transition if previous_transition > 0 else 1
        dwell_cycles = [c for c in cycles if start <= c <= max_cycle]
        censored = build_episode(dwell_cycles, telemetry_by_cycle, transitioned=False, end_cycle=max_cycle)
        censored["episode_index"] = len(episodes) + 1
        episodes.append(censored)

    return episodes


def build_episode(
    dwell_cycles: list[int],
    telemetry_by_cycle: dict[int, dict[str, Any]],
    *,
    transitioned: bool,
    end_cycle: int,
) -> dict[str, Any]:
    positive_gain = 0.0
    improvements = 0
    vectors: set[tuple[bool, ...]] = set()
    distinct_scores: set[float] = set()
    previous_score: float | None = None

    for cycle in dwell_cycles:
        row = telemetry_by_cycle[cycle]
        score = float(row.get("oracle_fixed") or 0.0)
        distinct_scores.add(score)
        vector = parse_bool_vector(row.get("fixed_suite_vector"))
        if vector is not None:
            vectors.add(vector)
        if previous_score is not None and score > previous_score:
            positive_gain += score - previous_score
            improvements += 1
        previous_score = score

    return {
        "episode_start_cycle": dwell_cycles[0] if dwell_cycles else None,
        "episode_end_cycle": end_cycle,
        "dwell_length": len(dwell_cycles) if dwell_cycles else 0,
        "transitioned": transitioned,
        "cum_oracle_delta": round(positive_gain, 6),
        "cum_oracle_unique_vectors": len(vectors) if vectors else len(distinct_scores),
        "cum_oracle_improvements": improvements,
        "oracle_evidence": round(positive_gain, 6),
    }


def equal_count_bins(values: list[dict[str, Any]], min_bin_size: int = 3) -> list[list[dict[str, Any]]]:
    if not values:
        return []
    ordered = sorted(values, key=lambda row: (float(row["oracle_evidence"]), int(row["episode_end_cycle"])))
    n = len(ordered)
    target_bins = max(1, n // min_bin_size)
    if target_bins == 1:
        return [ordered]
    bins: list[list[dict[str, Any]]] = []
    start = 0
    for remaining_bins in range(target_bins, 0, -1):
        remaining = n - start
        size = max(min_bin_size, math.ceil(remaining / remaining_bins))
        bins.append(ordered[start:start + size])
        start += size
    bins = [bucket for bucket in bins if bucket]
    while len(bins) > 1 and len(bins[-1]) < min_bin_size:
        bins[-2].extend(bins[-1])
        bins.pop()
    return bins


def bin_rows(episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bins = equal_count_bins(episodes, min_bin_size=3)
    rows: list[dict[str, Any]] = []
    for idx, bucket in enumerate(bins, start=1):
        evidences = [float(row["oracle_evidence"]) for row in bucket]
        n_episodes = len(bucket)
        n_transitions = sum(1 for row in bucket if row["transitioned"])
        probability = (n_transitions / n_episodes) if n_episodes else 0.0
        rows.append({
            "oracle_evidence_bin": idx,
            "oracle_evidence_min": round(min(evidences), 6),
            "oracle_evidence_max": round(max(evidences), 6),
            "oracle_evidence_mean": round(sum(evidences) / n_episodes, 6),
            "n_episodes": n_episodes,
            "n_transitions": n_transitions,
            "transition_prob": round(probability, 6),
        })
    return rows


def fit_sigmoid(bin_rows_data: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(bin_rows_data) < 3:
        return None
    xs = [float(row["oracle_evidence_mean"]) for row in bin_rows_data]
    ys = [float(row["transition_prob"]) for row in bin_rows_data]
    if max(xs) == min(xs):
        return None
    x0 = sum(xs) / len(xs)
    try:
        params, _ = curve_fit(
            lambda x, x_c, k: 1.0 / (1.0 + __import__("numpy").exp(-k * (x - x_c))),
            xs,
            ys,
            p0=[x0, 5.0],
            maxfev=20000,
        )
    except Exception:
        return None
    x_c, k = float(params[0]), float(params[1])
    preds = [sigmoid(x, x_c, k) for x in xs]
    mean_y = sum(ys) / len(ys)
    ss_res = sum((y - p) ** 2 for y, p in zip(ys, preds))
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0
    width = (2.0 * math.log(9.0) / abs(k)) if abs(k) > 1e-9 else None
    return {
        "x_c": round(x_c, 6),
        "k": round(k, 6),
        "sigmoid_r2": round(r2, 6),
        "transition_width": round(width, 6) if width is not None else None,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe for percolation-like oracle evidence thresholds.")
    parser.add_argument("--dwell-root", type=Path, default=DEFAULT_DWELL_ROOT)
    parser.add_argument("--mirror-root", type=Path, default=DEFAULT_MIRROR_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    summaries: list[dict[str, Any]] = []
    xcs: list[float] = []

    for label in RUN_LABELS:
        run_name = run_name_for_label(label)
        dwell_path = args.dwell_root / f"{label}_dwell_dataset.jsonl"
        telemetry_path = args.mirror_root / run_name / "run-1" / "telemetry.jsonl"
        status_path = args.mirror_root / run_name / "run-1" / "status.json"

        dwell_rows = load_jsonl(dwell_path)
        telemetry_rows = canonical_grind_telemetry(telemetry_path)
        max_cycle = load_max_cycle(status_path)

        episodes = episode_rows(dwell_rows, telemetry_rows, max_cycle)
        bins = bin_rows(episodes)
        fit = fit_sigmoid(bins)

        summary = {
            "label": label,
            "oracle_evidence_metric": "cum_oracle_delta",
            "n_episodes": len(episodes),
            "low_power": len(episodes) < 5,
        }
        if fit is not None:
            summary.update(fit)
            xcs.append(float(fit["x_c"]))
        else:
            summary.update({
                "x_c": None,
                "k": None,
                "sigmoid_r2": None,
                "transition_width": None,
            })

        write_csv(args.output_dir / f"{label}_episodes.csv", episodes)
        write_csv(args.output_dir / f"{label}_bins.csv", bins)
        (args.output_dir / f"{label}_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        summaries.append(summary)

    cv = None
    if len(xcs) >= 2:
        mean_xc = sum(xcs) / len(xcs)
        if abs(mean_xc) > 1e-9:
            variance = sum((x - mean_xc) ** 2 for x in xcs) / len(xcs)
            cv = math.sqrt(variance) / abs(mean_xc)

    comparison = {
        "oracle_evidence_metric": "cum_oracle_delta",
        "x_c_values": {row["label"]: row["x_c"] for row in summaries},
        "x_c_coefficient_of_variation": round(cv, 6) if cv is not None else None,
    }
    (args.output_dir / "comparison_summary.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    (args.output_dir / "percolation_manifest.json").write_text(
        json.dumps({"per_run": summaries, "comparison": comparison}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"per_run": summaries, "comparison": comparison}, indent=2))


if __name__ == "__main__":
    main()
