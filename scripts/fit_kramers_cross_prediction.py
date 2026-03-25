#!/usr/bin/env python3
"""Fit log(waiting time) against oracle and structure dwell barriers by run."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


BARRIERS = [
    "oracle_dwell_barrier",
    "structure_dwell_barrier",
]


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
    return path.stem.replace("_dwell_dataset", ""), path


def linear_fit(xs: list[float], ys: list[float]) -> dict[str, Any] | None:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    ss_xx = sum((x - mean_x) ** 2 for x in xs)
    if ss_xx == 0:
        return None
    ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    ss_yy = sum((y - mean_y) ** 2 for y in ys)
    slope = ss_xy / ss_xx
    intercept = mean_y - slope * mean_x
    r = 0.0
    if ss_yy > 0:
        r = ss_xy / math.sqrt(ss_xx * ss_yy)
    return {
        "n": n,
        "slope": round(slope, 6),
        "intercept": round(intercept, 6),
        "r": round(r, 6),
    }


def fit_barrier(rows: list[dict[str, Any]], barrier_key: str) -> dict[str, Any] | None:
    xs: list[float] = []
    ys: list[float] = []
    for row in rows:
        waiting = row.get("waiting_time_since_previous_transition")
        barrier = row.get(barrier_key)
        if waiting in (None, 0) or barrier in (None,):
            continue
        try:
            waiting_f = float(waiting)
            barrier_f = float(barrier)
        except (TypeError, ValueError):
            continue
        if waiting_f <= 0 or barrier_f < 0:
            continue
        xs.append(barrier_f)
        ys.append(math.log(waiting_f))
    return linear_fit(xs, ys)


def build_summary(label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        "label": label,
        "rows": len(rows),
        "rows_with_waiting_time": sum(
            1 for row in rows if row.get("waiting_time_since_previous_transition") not in (None, 0)
        ),
        "fits": {},
    }
    for barrier in BARRIERS:
        summary["fits"][barrier] = fit_barrier(rows, barrier)
    return summary


def write_outputs(output_dir: Path, summaries: list[dict[str, Any]], pooled: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cross_prediction_summary.json").write_text(
        json.dumps({"per_run": summaries, "pooled": pooled}, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit oracle and structure dwell barriers by run.")
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        help="Run spec as label=PATH or just PATH. Repeat for multiple runs.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    per_run: list[dict[str, Any]] = []
    pooled_rows: list[dict[str, Any]] = []
    for raw in args.run:
        label, path = parse_run_arg(raw)
        rows = load_jsonl(path)
        per_run.append(build_summary(label, rows))
        pooled_rows.extend(rows)

    pooled = build_summary("pooled", pooled_rows)
    write_outputs(args.output_dir, per_run, pooled)
    print(json.dumps({"per_run": per_run, "pooled": pooled}, indent=2))


if __name__ == "__main__":
    main()
