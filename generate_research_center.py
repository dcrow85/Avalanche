#!/usr/bin/env python3
"""Generate public run summaries for the syntropy.city research center."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def read_json(path: Path, default):
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError:
        return default


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in read_text(path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-").lower()
    return slug or "run"


def classify_run(name: str) -> str:
    lowered = name.lower()
    if "qwen" in lowered:
        return "Qwen-Raw"
    if "haiku" in lowered or "claude" in lowered:
        return "Haiku-Raw"
    if "grok" in lowered or "xai" in lowered:
        return "Grok-Raw"
    if "perm-53" in lowered:
        return "Ava-53"
    if "perm-54" in lowered:
        return "Ava-54"
    if "53" in lowered:
        return "Ava-53"
    if "54" in lowered:
        return "Ava-54"
    return "Ava"


def load_run(run_dir: Path) -> dict | None:
    status = read_json(run_dir / "status.json", None)
    if not isinstance(status, dict):
        return None

    opinions = read_text(run_dir / "opinions.md")
    dead_ends = read_text(run_dir / "dead-ends.md")
    snapshots = read_jsonl(run_dir / "cycle_snapshots.jsonl")
    metrics_history = status.get("metrics_history", [])
    if not isinstance(metrics_history, list):
        metrics_history = []

    latest_metrics = metrics_history[-1] if metrics_history else {}
    if not isinstance(latest_metrics, dict):
        latest_metrics = {}

    if not snapshots:
        snapshots = [
            {
                "cycle": status.get("cycle", 0),
                "max_cycles": status.get("max_cycles", 0),
                "phase": status.get("phase", ""),
                "last_result": status.get("last_result", ""),
                "last_error": status.get("last_error", ""),
                "timestamp": status.get("timestamp", ""),
                "opinions_content": opinions,
                "dead_ends_content": dead_ends,
                "metrics": latest_metrics,
            }
        ]

    return {
        "name": run_dir.name,
        "slug": slugify(run_dir.name),
        "organism": classify_run(run_dir.name),
        "path": str(run_dir),
        "cycle": status.get("cycle", 0),
        "max_cycles": status.get("max_cycles", 0),
        "phase": status.get("phase", ""),
        "last_result": status.get("last_result", ""),
        "last_error": status.get("last_error", ""),
        "timestamp": status.get("timestamp", ""),
        "opinions_words": status.get("opinions_words", 0),
        "dead_ends_words": status.get("dead_ends_words", 0),
        "data_pairs": status.get("data_pairs", 0),
        "opinions_content": opinions,
        "dead_ends_content": dead_ends,
        "cycle_snapshots": snapshots,
        "metrics_history": metrics_history,
        "latest_metrics": latest_metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate syntropy.city run summaries.")
    parser.add_argument("--runs-root", required=True, help="Directory containing terrarium runs.")
    parser.add_argument("--out-dir", required=True, help="Public output directory for JSON.")
    args = parser.parse_args()

    runs_root = Path(args.runs_root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "runs").mkdir(parents=True, exist_ok=True)

    runs: list[dict] = []
    for candidate in sorted(runs_root.iterdir()):
        if not candidate.is_dir():
            continue
        loaded = load_run(candidate)
        if not loaded:
            continue
        runs.append(loaded)

    runs.sort(key=lambda item: item.get("timestamp", ""), reverse=True)

    index_payload = [
        {
            "name": run["name"],
            "slug": run["slug"],
            "organism": run["organism"],
            "cycle": run["cycle"],
            "max_cycles": run["max_cycles"],
            "phase": run["phase"],
            "last_result": run["last_result"],
            "timestamp": run["timestamp"],
            "latest_metrics": run["latest_metrics"],
        }
        for run in runs
    ]

    (out_dir / "runs.json").write_text(json.dumps(index_payload, indent=2), encoding="utf-8")
    for run in runs:
        (out_dir / "runs" / f"{run['slug']}.json").write_text(
            json.dumps(run, indent=2),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
