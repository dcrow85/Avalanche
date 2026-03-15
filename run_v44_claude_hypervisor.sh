#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${1:-/opt/avalanche/runs/terrarium-v44-claude}"
MODEL="${2:-${AVALANCHE_CLAUDE_MODEL:-sonnet}}"
MAX_CYCLES="${3:-${AVALANCHE_MAX_CYCLES:-10}}"
CONTINUE_CYCLES="${AVALANCHE_CONTINUE_CYCLES:-0}"

case "$MODEL" in
  opus)
    : "${AVALANCHE_CLAUDE_FAIL_SYNC_TIMEOUT:=1200}"
    ;;
  sonnet)
    : "${AVALANCHE_CLAUDE_FAIL_SYNC_TIMEOUT:=900}"
    ;;
  *)
    : "${AVALANCHE_CLAUDE_FAIL_SYNC_TIMEOUT:=900}"
    ;;
esac

# GRIND and LINTER timeouts are model-aware in Python — do not override here.
export AVALANCHE_CLAUDE_MODEL="$MODEL"
export AVALANCHE_CLAUDE_FAIL_SYNC_TIMEOUT

python3 /opt/avalanche/hypervisor_v44_claude.py \
  --workspace "$WORKSPACE" \
  --model "$MODEL" \
  --max-cycles "$MAX_CYCLES" \
  --continue-cycles "$CONTINUE_CYCLES"

