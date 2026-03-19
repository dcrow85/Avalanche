#!/usr/bin/env bash
# V4.7 Phase 2b: Negative-Space Altitude Pilot
#
# Prompt style: "negative-space" — ask what the pattern of elimination
# has left untested, then propose one actionable search direction.
#
# Conservative pilot matrix:
#   run-54..55: altitude every 10 cycles (2 replicates)
#   run-56:    altitude every 15 cycles (1 replicate)
#
# Keep this small. Phase 2 v1 already established the baseline; this batch is
# testing prompt shape, not schedule breadth.

set -euo pipefail
cd /opt/avalanche

: "${HAIMAKER_KEY:?HAIMAKER_KEY must be set in the environment before launching Phase 2b.}"

WORKSPACE="/opt/avalanche/runs/v47-phase2b"
SCRIPT="/opt/avalanche/compression_assay.py"
LOGDIR="$WORKSPACE/logs"
PIDDIR="$WORKSPACE/pids"
mkdir -p "$LOGDIR"
mkdir -p "$PIDDIR"

echo "=== V4.7 Phase 2b: Negative-Space Altitude Pilot ==="
echo "Workspace: $WORKSPACE"
echo ""

for RUN_ID in 54 55; do
    echo "Launching run-$RUN_ID (altitude every 10, negative-space prompt)..."
    nohup python3 -u "$SCRIPT" \
        --run-id "$RUN_ID" \
        --workspace-root "$WORKSPACE" \
        --max-cycles 200 \
        --no-gradient \
        --no-passes \
        --altitude-frequency 10 \
        --altitude-prompt negative-space \
        > "$LOGDIR/run-${RUN_ID}.log" 2>&1 &
    echo "$!" > "$PIDDIR/run-${RUN_ID}.pid"
    echo "  PID: $!"
    sleep 2
done

echo "Launching run-56 (altitude every 15, negative-space prompt)..."
nohup python3 -u "$SCRIPT" \
    --run-id 56 \
    --workspace-root "$WORKSPACE" \
    --max-cycles 200 \
    --no-gradient \
    --no-passes \
    --altitude-frequency 15 \
    --altitude-prompt negative-space \
    > "$LOGDIR/run-56.log" 2>&1 &
echo "$!" > "$PIDDIR/run-56.pid"
echo "  PID: $!"

echo ""
echo "All Phase 2b pilot runs launched. Monitor with:"
echo "  tail -f $LOGDIR/run-*.log"
echo "  ps aux | grep compression_assay"
