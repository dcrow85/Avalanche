import json
import shutil
import uuid
from pathlib import Path

import dashboard
import generate_research_center


TEST_ROOT = Path(r"C:\Users\howar\.codex\memories\test-run-metrics-history")


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_jsonl(path, rows):
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def make_run_dir() -> Path:
    run_dir = TEST_ROOT / str(uuid.uuid4())
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def test_dashboard_prefers_cycle_metrics_history():
    run_dir = make_run_dir()
    try:
        write_json(
            run_dir / "status.json",
            {
                "cycle": 100,
                "max_cycles": 100,
                "phase": "CYCLE_CAP",
                "metrics_history": [{"cycle_metric": 97, "ptolemaic_ratio": 999}],
            },
        )
        write_jsonl(
            run_dir / "cycle_metrics.jsonl",
            [
                {"cycle_metric": 48, "ptolemaic_ratio": 1.5},
                {"cycle_metric": 97, "ptolemaic_ratio": 2.6667},
            ],
        )

        payload = dashboard.get_api_response(str(run_dir))

        assert [row["cycle_metric"] for row in payload["metrics_history"]] == [48, 97]
        assert payload["cycle_snapshots"][0]["metrics"]["ptolemaic_ratio"] == 2.6667
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_archive_generator_prefers_cycle_metrics_history():
    run_dir = make_run_dir()
    try:
        write_json(
            run_dir / "status.json",
            {
                "cycle": 50,
                "max_cycles": 50,
                "phase": "CYCLE_CAP",
                "last_result": "FAIL",
                "metrics_history": [{"cycle_metric": 10, "dead_end_family_count": 99}],
            },
        )
        write_jsonl(
            run_dir / "cycle_metrics.jsonl",
            [
                {"cycle_metric": 1, "dead_end_family_count": 1},
                {"cycle_metric": 10, "dead_end_family_count": 3},
            ],
        )

        payload = generate_research_center.load_run(run_dir)

        assert payload is not None
        assert [row["cycle_metric"] for row in payload["metrics_history"]] == [1, 10]
        assert payload["latest_metrics"]["dead_end_family_count"] == 3
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
