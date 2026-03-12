#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${1:-/opt/avalanche/runs/terrarium-v44-codex}"
MODEL="${AVALANCHE_CODEX_MODEL:-gpt-5.3-codex}"
MAX_CYCLES="${AVALANCHE_MAX_CYCLES:-20}"
CONTINUE_CYCLES="${AVALANCHE_CONTINUE_CYCLES:-0}"
ORACLE_MODE="${AVALANCHE_ORACLE_MODE:-first-failure}"

export AVALANCHE_CODEX_MODEL="$MODEL"

python3 /opt/avalanche/hypervisor_v44_codex.py \
  --workspace "$WORKSPACE" \
  --model "$MODEL" \
  --max-cycles "$MAX_CYCLES" \
  --continue-cycles "$CONTINUE_CYCLES" \
  --oracle-mode "$ORACLE_MODE"
