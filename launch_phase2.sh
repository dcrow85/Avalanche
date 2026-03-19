#!/usr/bin/env bash
# V4.7 Phase 2: Altitude-Only Graveyard Reading
# Clean causal test of metacognitive reflection over existing graveyard.
# No gradient, no compression passes. Altitude only.
#
# Prompt style: "survey" — factual comparison, low-directiveness.
# The model compares its active theory against its dead-end families
# and proposes a new search direction. No hints about negative space,
# global structure, or cycles/graphs.
#
# Matrix:
#   run-50..51: altitude every 10 cycles (2 replicates)
#   run-52..53: altitude every 15 cycles (2 replicates)
#
# All runs: --no-gradient --no-passes --max-cycles 200
# Model: anthropic/claude-haiku-4-5 via Haimaker

set -euo pipefail
cd /opt/avalanche

: "${HAIMAKER_KEY:?HAIMAKER_KEY must be set in the environment before launching Phase 2.}"

WORKSPACE="/opt/avalanche/runs/v47-phase2"
SCRIPT="/opt/avalanche/compression_assay.py"
LOGDIR="$WORKSPACE/logs"
PIDDIR="$WORKSPACE/pids"
mkdir -p "$LOGDIR"
mkdir -p "$PIDDIR"

echo "=== V4.7 Phase 2: Altitude-Only Graveyard Reading ==="
echo "Workspace: $WORKSPACE"
echo ""

# Altitude every 10 cycles (2 replicates)
for RUN_ID in 50 51; do
    echo "Launching run-$RUN_ID (altitude every 10, survey prompt)..."
    nohup python3 -u "$SCRIPT" \
        --run-id "$RUN_ID" \
        --workspace-root "$WORKSPACE" \
        --max-cycles 200 \
        --no-gradient \
        --no-passes \
        --altitude-frequency 10 \
        --altitude-prompt survey \
        > "$LOGDIR/run-${RUN_ID}.log" 2>&1 &
    echo "$!" > "$PIDDIR/run-${RUN_ID}.pid"
    echo "  PID: $!"
    sleep 2
done

# Altitude every 15 cycles (2 replicates)
for RUN_ID in 52 53; do
    echo "Launching run-$RUN_ID (altitude every 15, survey prompt)..."
    nohup python3 -u "$SCRIPT" \
        --run-id "$RUN_ID" \
        --workspace-root "$WORKSPACE" \
        --max-cycles 200 \
        --no-gradient \
        --no-passes \
        --altitude-frequency 15 \
        --altitude-prompt survey \
        > "$LOGDIR/run-${RUN_ID}.log" 2>&1 &
    echo "$!" > "$PIDDIR/run-${RUN_ID}.pid"
    echo "  PID: $!"
    sleep 2
done

echo ""
echo "All 4 runs launched. Monitor with:"
echo "  tail -f $LOGDIR/run-*.log"
echo "  ps aux | grep compression_assay"
