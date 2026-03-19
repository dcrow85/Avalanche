#!/usr/bin/env bash
# V4.7 Phase 1b-v3c probe: slightly loosened true-compression smoke
#
# Goal:
#   Determine whether a small slot loosening is enough to land a true
#   compression pass under the actual-compression gate.
#
# Matrix:
#   run-48: trigger=10, target=75%, max-cycles=25, max-passes=1
#   run-49: trigger=15, target=75%, max-cycles=25, max-passes=1

set -euo pipefail
cd /opt/avalanche

export HAIMAKER_KEY=sk-OSrn0y2DNNgyVDZYj6m3Uw

WORKSPACE="/opt/avalanche/runs/v47-phase1b-v3c-probe"
SCRIPT="/opt/avalanche/compression_assay.py"
LOGDIR="$WORKSPACE/logs"
PIDDIR="$WORKSPACE/pids"
mkdir -p "$LOGDIR"
mkdir -p "$PIDDIR"

echo "=== V4.7 Phase 1b-v3c Probe ==="
echo "Workspace: $WORKSPACE"
echo ""

common_args=(
    --workspace-root "$WORKSPACE"
    --max-cycles 25
    --no-gradient
    --no-altitude
    --max-passes 1
    --compression-target 0.75
    --compression-min-input-len 240
)

echo "Launching run-48 (trigger=10)..."
nohup python3 -u "$SCRIPT" \
    --run-id 48 \
    "${common_args[@]}" \
    --stagnation-window 10 \
    > "$LOGDIR/run-48.log" 2>&1 &
echo "$!" > "$PIDDIR/run-48.pid"
echo "  PID: $!"
sleep 2

echo "Launching run-49 (trigger=15)..."
nohup python3 -u "$SCRIPT" \
    --run-id 49 \
    "${common_args[@]}" \
    --stagnation-window 15 \
    > "$LOGDIR/run-49.log" 2>&1 &
echo "$!" > "$PIDDIR/run-49.pid"
echo "  PID: $!"

echo ""
echo "Probe launched. Monitor with:"
echo "  tail -f $LOGDIR/run-48.log $LOGDIR/run-49.log"
