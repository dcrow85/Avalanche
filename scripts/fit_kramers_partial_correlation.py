#!/usr/bin/env python3
"""Compute raw and partial-correlation diagnostics for dwell barriers.

This keeps the oracle dwell barrier fixed and tests whether a normalized
structure dwell barrier adds signal beyond dwell length.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


BARRIERS = [
    "oracle_dwell_barrier",
    "structure_dwell_barrier_normalized",
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


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    ss_xx = sum((x - mean_x) ** 2 for x in xs)
    ss_yy = sum((y - mean_y) ** 2 for y in ys)
    if ss_xx <= 0 or ss_yy <= 0:
        return None
    ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return ss_xy / math.sqrt(ss_xx * ss_yy)


def linear_fit(xs: list[float], ys: list[float]) -> dict[str, Any] | None:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    ss_xx = sum((x - mean_x) ** 2 for x in xs)
    if ss_xx <= 0:
        return None
    ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = ss_xy / ss_xx
    intercept = mean_y - slope * mean_x
    r = pearson(xs, ys)
    return {
        "n": n,
        "slope": round(slope, 6),
        "intercept": round(intercept, 6),
        "r": round(r, 6) if r is not None else None,
    }


def partial_corr(x: list[float], y: list[float], z: list[float]) -> float | None:
    r_xy = pearson(x, y)
    r_xz = pearson(x, z)
    r_yz = pearson(y, z)
    if r_xy is None or r_xz is None or r_yz is None:
        return None
    denom = math.sqrt(max(1e-12, (1 - r_xz**2) * (1 - r_yz**2)))
    if denom <= 1e-12:
        return None
    value = (r_xy - (r_xz * r_yz)) / denom
    return value


def usable_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        waiting = row.get("waiting_time_since_previous_transition")
        dwell = row.get("dwell_cycle_count")
        if waiting in (None, 0) or dwell in (None, 0):
            continue
        try:
            waiting_f = float(waiting)
            dwell_f = float(dwell)
        except (TypeError, ValueError):
            continue
        if waiting_f <= 0 or dwell_f <= 0:
            continue
        enriched = dict(row)
        enriched["_log_waiting"] = math.log(waiting_f)
        enriched["_dwell"] = dwell_f
        result.append(enriched)
    return result


def barrier_summary(rows: list[dict[str, Any]], barrier_key: str) -> dict[str, Any]:
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for row in rows:
        try:
            barrier = float(row.get(barrier_key))
        except (TypeError, ValueError):
            continue
        xs.append(barrier)
        ys.append(float(row["_log_waiting"]))
        zs.append(float(row["_dwell"]))
    return {
        "raw_fit": linear_fit(xs, ys),
        "corr_barrier_vs_dwell": _round_or_none(pearson(xs, zs)),
        "partial_corr_log_wait_given_dwell": _round_or_none(partial_corr(xs, ys, zs)),
    }


def _round_or_none(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def build_summary(label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable = usable_rows(rows)
    summary = {
        "label": label,
        "rows": len(rows),
        "usable_rows": len(usable),
        "dwell_fit": linear_fit(
            [float(row["_dwell"]) for row in usable],
            [float(row["_log_waiting"]) for row in usable],
        ),
        "barriers": {},
    }
    for barrier in BARRIERS:
        summary["barriers"][barrier] = barrier_summary(usable, barrier)
    return summary


def write_outputs(output_dir: Path, summaries: list[dict[str, Any]], pooled: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "partial_correlation_summary.json").write_text(
        json.dumps({"per_run": summaries, "pooled": pooled}, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run partial-correlation diagnostics for dwell barriers.")
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
