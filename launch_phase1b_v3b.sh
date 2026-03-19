#!/usr/bin/env bash
# V4.7 Phase 1b-v3b: Slot-Based Compression Calibration
# Same slot-based pass mechanism as v3, but with loosened slot budgets to test
# the acceptance boundary without making the pass fully comfortable.
#
# Matrix:
#   run-36..38: trigger=15, target=75%  (primary condition, 3 replicates)
#   run-39..40: trigger=10, target=75%  (early trigger variant)
#   run-41:     trigger=15, target=65%  (tighter compression probe)
#
# All runs: --no-gradient --no-altitude --max-cycles 200
# Model: anthropic/claude-haiku-4-5 via Haimaker

set -euo pipefail
cd /opt/avalanche

export HAIMAKER_KEY=sk-OSrn0y2DNNgyVDZYj6m3Uw

WORKSPACE="/opt/avalanche/runs/v47-phase1b-v3b"
SCRIPT="/opt/avalanche/compression_assay.py"
LOGDIR="$WORKSPACE/logs"
PIDDIR="$WORKSPACE/pids"
mkdir -p "$LOGDIR"
mkdir -p "$PIDDIR"

echo "=== V4.7 Phase 1b-v3b: Slot Budget Calibration ==="
echo "Workspace: $WORKSPACE"
echo ""

# Primary condition: trigger=15, target=75% (3 replicates)
for RUN_ID in 36 37 38; do
    echo "Launching run-$RUN_ID (trigger=15, target=75%)..."
    nohup python3 -u "$SCRIPT" \
        --run-id "$RUN_ID" \
        --workspace-root "$WORKSPACE" \
        --max-cycles 200 \
        --no-gradient \
        --no-altitude \
        --stagnation-window 15 \
        --compression-target 0.75 \
        --max-passes 3 \
        > "$LOGDIR/run-${RUN_ID}.log" 2>&1 &
    echo "$!" > "$PIDDIR/run-${RUN_ID}.pid"
    echo "  PID: $!"
    sleep 2
done

# Early trigger variant: trigger=10, target=75%
for RUN_ID in 39 40; do
    echo "Launching run-$RUN_ID (trigger=10, target=75%)..."
    nohup python3 -u "$SCRIPT" \
        --run-id "$RUN_ID" \
        --workspace-root "$WORKSPACE" \
        --max-cycles 200 \
        --no-gradient \
        --no-altitude \
        --stagnation-window 10 \
        --compression-target 0.75 \
        --max-passes 3 \
        > "$LOGDIR/run-${RUN_ID}.log" 2>&1 &
    echo "$!" > "$PIDDIR/run-${RUN_ID}.pid"
    echo "  PID: $!"
    sleep 2
done

# Tighter compression probe: trigger=15, target=65%
for RUN_ID in 41; do
    echo "Launching run-$RUN_ID (trigger=15, target=65%)..."
    nohup python3 -u "$SCRIPT" \
        --run-id "$RUN_ID" \
        --workspace-root "$WORKSPACE" \
        --max-cycles 200 \
        --no-gradient \
        --no-altitude \
        --stagnation-window 15 \
        --compression-target 0.65 \
        --max-passes 3 \
        > "$LOGDIR/run-${RUN_ID}.log" 2>&1 &
    echo "$!" > "$PIDDIR/run-${RUN_ID}.pid"
    echo "  PID: $!"
    sleep 2
done

echo ""
echo "All 6 runs launched. Monitor with:"
echo "  tail -f $LOGDIR/run-*.log"
echo "  ps aux | grep compression_assay"
