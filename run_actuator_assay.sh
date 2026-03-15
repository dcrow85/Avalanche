#!/bin/bash
# Three-Branch Actuator Assay — VPS batch launcher
#
# Usage: bash run_actuator_assay.sh [--model MODEL] [--calibration N] [--multiplier N]
#
# Runs all 15 experiments sequentially:
#   Phase 1: Branch A (5 runs) — must complete first to extract rejection rates
#   Phase 2: Branch B + C (5 runs each)

set -euo pipefail
cd /opt/avalanche

MODEL="${1:-anthropic/claude-haiku-4-5}"
API_BASE="https://api.haimaker.ai/v1"
API_KEY_ENV="HAIMAKER_KEY"
WORKSPACE_ROOT="runs/assay"
SEED_BASE=44
CALIBRATION=10
MULTIPLIER=150
TESTS=5

echo "=== Three-Branch Actuator Assay ==="
echo "Model: $MODEL"
echo "Workspace: $WORKSPACE_ROOT"
echo "Calibration cycles: $CALIBRATION"
echo "Reservoir multiplier: $MULTIPLIER"
echo ""

# --- Phase 1: Branch A (must run first) ---
echo "--- Phase 1: Branch A (informed gate, sterile) ---"
for RUN in 1 2 3 4 5; do
    echo ""
    echo ">>> Branch A, Run $RUN (seed=$((SEED_BASE + RUN)))"
    python3 actuator_assay.py \
        --branch A \
        --run-id "$RUN" \
        --workspace-root "$WORKSPACE_ROOT" \
        --model "$MODEL" \
        --api-base "$API_BASE" \
        --api-key-env "$API_KEY_ENV" \
        --seed "$SEED_BASE" \
        --calibration-cycles "$CALIBRATION" \
        --reservoir-multiplier "$MULTIPLIER" \
        --tests-per-cycle "$TESTS" \
        2>&1 | tee "${WORKSPACE_ROOT}/branch-A-run-${RUN}.log"
    echo "<<< Branch A, Run $RUN complete"
done

echo ""
echo "--- Phase 2: Branch B + C ---"

# --- Phase 2: Branch B (informed gate, dramatic) ---
for RUN in 1 2 3 4 5; do
    echo ""
    echo ">>> Branch B, Run $RUN (seed=$((SEED_BASE + RUN)))"
    python3 actuator_assay.py \
        --branch B \
        --run-id "$RUN" \
        --workspace-root "$WORKSPACE_ROOT" \
        --model "$MODEL" \
        --api-base "$API_BASE" \
        --api-key-env "$API_KEY_ENV" \
        --seed "$SEED_BASE" \
        --calibration-cycles "$CALIBRATION" \
        --reservoir-multiplier "$MULTIPLIER" \
        --tests-per-cycle "$TESTS" \
        2>&1 | tee "${WORKSPACE_ROOT}/branch-B-run-${RUN}.log"
    echo "<<< Branch B, Run $RUN complete"
done

# --- Phase 2: Branch C (random gate, null control) ---
# Rejection rate auto-extracted from paired Branch A runs.
for RUN in 1 2 3 4 5; do
    echo ""
    echo ">>> Branch C, Run $RUN (seed=$((SEED_BASE + RUN)))"
    python3 actuator_assay.py \
        --branch C \
        --run-id "$RUN" \
        --workspace-root "$WORKSPACE_ROOT" \
        --model "$MODEL" \
        --api-base "$API_BASE" \
        --api-key-env "$API_KEY_ENV" \
        --seed "$SEED_BASE" \
        --calibration-cycles "$CALIBRATION" \
        --reservoir-multiplier "$MULTIPLIER" \
        --tests-per-cycle "$TESTS" \
        2>&1 | tee "${WORKSPACE_ROOT}/branch-C-run-${RUN}.log"
    echo "<<< Branch C, Run $RUN complete"
done

echo ""
echo "=== All 15 runs complete. Running analysis... ==="
python3 analyze_assay.py --workspace-root "$WORKSPACE_ROOT"
echo "=== Done ==="
