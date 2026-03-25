#!/usr/bin/env python3
"""Compute discrete hazard-rate summaries from dwell transition datasets."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


DEFAULT_DWELL_ROOT = Path(r"C:\Avalanche\local-runs\kramers-v472-mirror\kramers-dwell-v2")
DEFAULT_MIRROR_ROOT = Path(r"C:\Avalanche\local-runs\kramers-v472-mirror")
DEFAULT_OUTPUT = Path(r"C:\Avalanche\local-runs\kramers-v472-mirror\probe-hazard")
RUN_LABELS = ["haiku", "gpt54", "qwen", "displace"]


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    raise ValueError(f"Unsupported input format: {path}")


def load_max_cycle(status_path: Path) -> int:
    data = json.loads(status_path.read_text(encoding="utf-8"))
    cycle = data.get("cycle") or data.get("max_cycles") or 0
    return int(cycle)


def transition_cycles(dwell_rows: list[dict[str, Any]]) -> list[int]:
    return sorted(int(row["cycle"]) for row in dwell_rows)


def episode_lengths(dwell_rows: list[dict[str, Any]], max_cycle: int) -> tuple[list[int], list[int]]:
    transitions = transition_cycles(dwell_rows)
    events: list[int] = []
    censored: list[int] = []
    previous = 0
    for cycle in transitions:
        events.append(cycle - previous)
        previous = cycle
    trailing = max_cycle - previous
    if trailing > 0:
        censored.append(trailing)
    if not transitions:
        censored = [max_cycle] if max_cycle > 0 else []
    return events, censored


def hazard_rows(events: list[int], censored: list[int]) -> list[dict[str, Any]]:
    all_lengths = events + censored
    if not all_lengths:
        return []
    max_dwell = max(all_lengths)
    rows: list[dict[str, Any]] = []
    for t in range(1, max_dwell + 1):
        n_at_risk = sum(1 for length in all_lengths if length >= t)
        n_events = sum(1 for length in events if length == t)
        hazard = (n_events / n_at_risk) if n_at_risk else 0.0
        rows.append({
            "dwell_t": t,
            "n_at_risk": n_at_risk,
            "n_events": n_events,
            "hazard_rate": round(hazard, 6),
        })
    return rows


def linear_fit(xs: list[float], ys: list[float]) -> dict[str, Any] | None:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    ss_xx = sum((x - mean_x) ** 2 for x in xs)
    ss_yy = sum((y - mean_y) ** 2 for y in ys)
    if ss_xx <= 0:
        return None
    ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = ss_xy / ss_xx
    intercept = mean_y - slope * mean_x
    r = 0.0
    if ss_yy > 0:
        r = ss_xy / ((ss_xx * ss_yy) ** 0.5)
    return {
        "n": n,
        "slope": round(slope, 6),
        "intercept": round(intercept, 6),
        "r": round(r, 6),
    }


def summarize(label: str, hazard: list[dict[str, Any]], n_episodes: int, max_dwell: int) -> dict[str, Any]:
    xs = [float(row["dwell_t"]) for row in hazard]
    ys = [float(row["hazard_rate"]) for row in hazard]
    fit = linear_fit(xs, ys)
    mean_hazard = (sum(ys) / len(ys)) if ys else 0.0
    return {
        "label": label,
        "mean_hazard": round(mean_hazard, 6),
        "hazard_slope": fit["slope"] if fit else None,
        "hazard_slope_r": fit["r"] if fit else None,
        "n_episodes": n_episodes,
        "max_dwell": max_dwell,
        "low_power": n_episodes < 5,
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
    parser = argparse.ArgumentParser(description="Compute discrete hazard functions from dwell datasets.")
    parser.add_argument("--dwell-root", type=Path, default=DEFAULT_DWELL_ROOT)
    parser.add_argument("--mirror-root", type=Path, default=DEFAULT_MIRROR_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    summaries: list[dict[str, Any]] = []
    pooled_events: list[int] = []
    pooled_censored: list[int] = []

    for label in RUN_LABELS:
        dwell_path = args.dwell_root / f"{label}_dwell_dataset.jsonl"
        run_name = "v472-history-gpt54" if label == "gpt54" else (
            "v472-history-qwen" if label == "qwen" else (
                "v472-history-haiku" if label == "haiku" else "v472-displace-prompt"
            )
        )
        status_path = args.mirror_root / run_name / "run-1" / "status.json"
        rows = load_rows(dwell_path)
        max_cycle = load_max_cycle(status_path)
        events, censored = episode_lengths(rows, max_cycle)
        hazard = hazard_rows(events, censored)
        summary = summarize(label, hazard, len(events) + len(censored), max([0, *events, *censored]))
        summaries.append(summary)
        write_csv(args.output_dir / f"{label}_hazard.csv", hazard)
        (args.output_dir / f"{label}_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        if label in {"gpt54", "qwen"}:
            pooled_events.extend(events)
            pooled_censored.extend(censored)

    pooled_hazard = hazard_rows(pooled_events, pooled_censored)
    pooled_summary = summarize(
        "gpt54_qwen_pooled",
        pooled_hazard,
        len(pooled_events) + len(pooled_censored),
        max([0, *pooled_events, *pooled_censored]),
    )
    write_csv(args.output_dir / "gpt54_qwen_pooled_hazard.csv", pooled_hazard)
    (args.output_dir / "gpt54_qwen_pooled_summary.json").write_text(
        json.dumps(pooled_summary, indent=2),
        encoding="utf-8",
    )
    (args.output_dir / "hazard_manifest.json").write_text(
        json.dumps({"per_run": summaries, "pooled": pooled_summary}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"per_run": summaries, "pooled": pooled_summary}, indent=2))


if __name__ == "__main__":
    main()
