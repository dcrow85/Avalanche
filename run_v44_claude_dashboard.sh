#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${1:-/opt/avalanche/runs/terrarium-v44-claude}"
PORT="${2:-8988}"

python3 /opt/avalanche/dashboard.py "$WORKSPACE" --port "$PORT"
