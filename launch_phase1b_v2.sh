#!/usr/bin/env bash
# V4.7 Phase 1b-v2: Compression Passes with Mechanical Enforcement
# Same 7-run matrix as 1b, but with length enforcement on compression passes.
# Runs in parallel with the advisory batch (run-16..22).
#
# Matrix:
#   run-23..25: trigger=15, target=50%  (primary condition, 3 replicates)
#   run-26..27: trigger=10, target=50%  (early trigger variant)
#   run-28..29: trigger=15, target=75%  (gentle compression variant)
#
# All runs: --no-gradient --no-altitude --max-cycles 200
# Model: anthropic/claude-haiku-4-5 via Haimaker

set -euo pipefail
cd /opt/avalanche

export HAIMAKER_KEY=sk-OSrn0y2DNNgyVDZYj6m3Uw

WORKSPACE="/opt/avalanche/runs/v47-phase1b-v2"
SCRIPT="/opt/avalanche/compression_assay.py"
LOGDIR="$WORKSPACE/logs"
mkdir -p "$LOGDIR"

echo "=== V4.7 Phase 1b-v2: Enforced Compression Passes ==="
echo "Workspace: $WORKSPACE"
echo ""

# Primary condition: trigger=15, target=50% (3 replicates)
for RUN_ID in 23 24 25; do
    echo "Launching run-$RUN_ID (trigger=15, target=50%)..."
    nohup python3 "$SCRIPT" \
        --run-id "$RUN_ID" \
        --workspace-root "$WORKSPACE" \
        --max-cycles 200 \
        --no-gradient \
        --no-altitude \
        --stagnation-window 15 \
        --compression-target 0.5 \
        --max-passes 3 \
        > "$LOGDIR/run-${RUN_ID}.log" 2>&1 &
    echo "  PID: $!"
    sleep 2
done

# Early trigger variant: trigger=10, target=50%
for RUN_ID in 26 27; do
    echo "Launching run-$RUN_ID (trigger=10, target=50%)..."
    nohup python3 "$SCRIPT" \
        --run-id "$RUN_ID" \
        --workspace-root "$WORKSPACE" \
        --max-cycles 200 \
        --no-gradient \
        --no-altitude \
        --stagnation-window 10 \
        --compression-target 0.5 \
        --max-passes 3 \
        > "$LOGDIR/run-${RUN_ID}.log" 2>&1 &
    echo "  PID: $!"
    sleep 2
done

# Gentle compression variant: trigger=15, target=75%
for RUN_ID in 28 29; do
    echo "Launching run-$RUN_ID (trigger=15, target=75%)..."
    nohup python3 "$SCRIPT" \
        --run-id "$RUN_ID" \
        --workspace-root "$WORKSPACE" \
        --max-cycles 200 \
        --no-gradient \
        --no-altitude \
        --stagnation-window 15 \
        --compression-target 0.75 \
        --max-passes 3 \
        > "$LOGDIR/run-${RUN_ID}.log" 2>&1 &
    echo "  PID: $!"
    sleep 2
done

echo ""
echo "All 7 runs launched. Monitor with:"
echo "  tail -f $LOGDIR/run-*.log"
echo "  ps aux | grep compression_assay"
