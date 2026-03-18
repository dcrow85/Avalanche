#!/usr/bin/env bash
# V4.7 Reconciliation Batch — post dead-end-state fix
# 6 targeted runs to test whether Phase 1a patterns survive clean state sync.
#
# Run 10: no-gradient baseline (anchor)
# Run 11-12: f300/linear (replicating run-7 broadening condition)
# Run 13-14: f300/stepped (replicating run-9 regression condition)
# Run 15: f600/stepped (calmer control from healthy pack)

set -euo pipefail
cd /opt/avalanche

export HAIMAKER_KEY=sk-OSrn0y2DNNgyVDZYj6m3Uw

COMMON="--max-cycles 200 --no-passes --no-altitude --model anthropic/claude-haiku-4-5 --api-base https://api.haimaker.ai/v1 --api-key-env HAIMAKER_KEY --workspace-root runs/v47-reconcile"

echo "=== Launching V4.7 Reconciliation Batch ==="

# Run 10: no-gradient baseline
nohup python3 compression_assay.py --run-id 10 --no-gradient --seed 100 $COMMON \
  > runs/v47-reconcile/run-10.log 2>&1 &
echo "  run-10: no-gradient baseline (pid=$!)"

# Run 11: f300/linear (run-7 replicate A)
nohup python3 compression_assay.py --run-id 11 --floor 300 --decay linear --seed 111 $COMMON \
  > runs/v47-reconcile/run-11.log 2>&1 &
echo "  run-11: f300/linear seed=111 (pid=$!)"

# Run 12: f300/linear (run-7 replicate B)
nohup python3 compression_assay.py --run-id 12 --floor 300 --decay linear --seed 112 $COMMON \
  > runs/v47-reconcile/run-12.log 2>&1 &
echo "  run-12: f300/linear seed=112 (pid=$!)"

# Run 13: f300/stepped (run-9 replicate A)
nohup python3 compression_assay.py --run-id 13 --floor 300 --decay stepped --seed 113 $COMMON \
  > runs/v47-reconcile/run-13.log 2>&1 &
echo "  run-13: f300/stepped seed=113 (pid=$!)"

# Run 14: f300/stepped (run-9 replicate B)
nohup python3 compression_assay.py --run-id 14 --floor 300 --decay stepped --seed 114 $COMMON \
  > runs/v47-reconcile/run-14.log 2>&1 &
echo "  run-14: f300/stepped seed=114 (pid=$!)"

# Run 15: f600/stepped (healthy control)
nohup python3 compression_assay.py --run-id 15 --floor 600 --decay stepped --seed 115 $COMMON \
  > runs/v47-reconcile/run-15.log 2>&1 &
echo "  run-15: f600/stepped seed=115 (pid=$!)"

echo ""
echo "=== All 6 runs launched ==="
echo "Monitor: for d in runs/v47-reconcile/run-*/; do echo \$(basename \$d): \$(wc -l < \$d/telemetry.jsonl 2>/dev/null || echo 0) cycles; done"
