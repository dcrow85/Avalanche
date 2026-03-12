#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${1:-/opt/avalanche/runs/terrarium-v44-codex}"
PORT="${2:-8981}"

python3 /opt/avalanche/dashboard_v44_codex.py "$WORKSPACE" --port "$PORT"
