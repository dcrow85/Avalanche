#!/usr/bin/env bash
# V4.7 Phase 1b-v3c: Actual Compression Gate
# Same slot-based schema as v3b, but passes only fire when opinions.md is long
# enough to be meaningfully compressible, and accepted passes must be strictly
# shorter than the input working-memory state.
#
# Matrix:
#   run-42..44: trigger=15, target=75%  (primary condition, 3 replicates)
#   run-45..46: trigger=10, target=75%  (early trigger variant)
#   run-47:     trigger=15, target=65%  (tighter compression probe)
#
# All runs: --no-gradient --no-altitude --max-cycles 200
# Additional gate: --compression-min-input-len 240

set -euo pipefail
cd /opt/avalanche

export HAIMAKER_KEY=sk-OSrn0y2DNNgyVDZYj6m3Uw

WORKSPACE="/opt/avalanche/runs/v47-phase1b-v3c"
SCRIPT="/opt/avalanche/compression_assay.py"
LOGDIR="$WORKSPACE/logs"
PIDDIR="$WORKSPACE/pids"
mkdir -p "$LOGDIR"
mkdir -p "$PIDDIR"

echo "=== V4.7 Phase 1b-v3c: Actual Compression Gate ==="
echo "Workspace: $WORKSPACE"
echo ""

common_args=(
    --workspace-root "$WORKSPACE"
    --max-cycles 200
    --no-gradient
    --no-altitude
    --max-passes 3
    --compression-min-input-len 240
)

# Primary condition: trigger=15, target=75% (3 replicates)
for RUN_ID in 42 43 44; do
    echo "Launching run-$RUN_ID (trigger=15, target=75%, min-input=240)..."
    nohup python3 -u "$SCRIPT" \
        --run-id "$RUN_ID" \
        "${common_args[@]}" \
        --stagnation-window 15 \
        --compression-target 0.75 \
        > "$LOGDIR/run-${RUN_ID}.log" 2>&1 &
    echo "$!" > "$PIDDIR/run-${RUN_ID}.pid"
    echo "  PID: $!"
    sleep 2
done

# Early trigger variant: trigger=10, target=75%
for RUN_ID in 45 46; do
    echo "Launching run-$RUN_ID (trigger=10, target=75%, min-input=240)..."
    nohup python3 -u "$SCRIPT" \
        --run-id "$RUN_ID" \
        "${common_args[@]}" \
        --stagnation-window 10 \
        --compression-target 0.75 \
        > "$LOGDIR/run-${RUN_ID}.log" 2>&1 &
    echo "$!" > "$PIDDIR/run-${RUN_ID}.pid"
    echo "  PID: $!"
    sleep 2
done

# Tighter compression probe: trigger=15, target=65%
for RUN_ID in 47; do
    echo "Launching run-$RUN_ID (trigger=15, target=65%, min-input=240)..."
    nohup python3 -u "$SCRIPT" \
        --run-id "$RUN_ID" \
        "${common_args[@]}" \
        --stagnation-window 15 \
        --compression-target 0.65 \
        > "$LOGDIR/run-${RUN_ID}.log" 2>&1 &
    echo "$!" > "$PIDDIR/run-${RUN_ID}.pid"
    echo "  PID: $!"
    sleep 2
done

echo ""
echo "All 6 runs launched. Monitor with:"
echo "  tail -f $LOGDIR/run-*.log"
echo "  ps aux | grep compression_assay"
