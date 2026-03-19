#!/usr/bin/env bash
# V4.7 Phase 1b-v3: Slot-Based Compression Passes
# Compression passes return 4 structured slots instead of free prose.
# Harness renders opinions.md from slots. Centered on 75%.
#
# Matrix:
#   run-30..32: trigger=15, target=75%  (primary condition, 3 replicates)
#   run-33..34: trigger=10, target=75%  (early trigger variant)
#   run-35:     trigger=15, target=65%  (tighter compression test)
#
# All runs: --no-gradient --no-altitude --max-cycles 200
# Model: anthropic/claude-haiku-4-5 via Haimaker

set -euo pipefail
cd /opt/avalanche

export HAIMAKER_KEY=sk-OSrn0y2DNNgyVDZYj6m3Uw

WORKSPACE="/opt/avalanche/runs/v47-phase1b-v3"
SCRIPT="/opt/avalanche/compression_assay.py"
LOGDIR="$WORKSPACE/logs"
mkdir -p "$LOGDIR"

echo "=== V4.7 Phase 1b-v3: Slot-Based Compression ==="
echo "Workspace: $WORKSPACE"
echo ""

# Primary condition: trigger=15, target=75% (3 replicates)
for RUN_ID in 30 31 32; do
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

# Early trigger variant: trigger=10, target=75%
for RUN_ID in 33 34; do
    echo "Launching run-$RUN_ID (trigger=10, target=75%)..."
    nohup python3 "$SCRIPT" \
        --run-id "$RUN_ID" \
        --workspace-root "$WORKSPACE" \
        --max-cycles 200 \
        --no-gradient \
        --no-altitude \
        --stagnation-window 10 \
        --compression-target 0.75 \
        --max-passes 3 \
        > "$LOGDIR/run-${RUN_ID}.log" 2>&1 &
    echo "  PID: $!"
    sleep 2
done

# Tighter compression: trigger=15, target=65%
for RUN_ID in 35; do
    echo "Launching run-$RUN_ID (trigger=15, target=65%)..."
    nohup python3 "$SCRIPT" \
        --run-id "$RUN_ID" \
        --workspace-root "$WORKSPACE" \
        --max-cycles 200 \
        --no-gradient \
        --no-altitude \
        --stagnation-window 15 \
        --compression-target 0.65 \
        --max-passes 3 \
        > "$LOGDIR/run-${RUN_ID}.log" 2>&1 &
    echo "  PID: $!"
    sleep 2
done

echo ""
echo "All 6 runs launched. Monitor with:"
echo "  tail -f $LOGDIR/run-*.log"
echo "  ps aux | grep compression_assay"
