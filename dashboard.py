#!/usr/bin/env python3
"""
Avalanche Dashboard — Live web viewer for the Hypervisor V4.1.

Serves a single-page dashboard that polls the terrarium for status.
Zero external dependencies — stdlib only.

Usage: python dashboard.py <terrarium_path> [--port 8080]
Example: python dashboard.py C:\terrarium
"""
import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

DEFAULT_PORT = 8080


def read_file_safe(path):
    """Read a file, return empty string if missing or error."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (FileNotFoundError, PermissionError):
        return ""


def read_jsonl_safe(path):
    rows = []
    raw = read_file_safe(path)
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def get_api_response(terrarium):
    """Build the JSON response from terrarium files."""
    status_path = os.path.join(terrarium, "status.json")
    opinions_path = os.path.join(terrarium, "opinions.md")
    dead_ends_path = os.path.join(terrarium, "dead-ends.md")
    snapshots_path = os.path.join(terrarium, "cycle_snapshots.jsonl")
    data_path = os.path.join(terrarium, "data.json")
    goal_path = os.path.join(terrarium, "goal.md")

    status_raw = read_file_safe(status_path)
    try:
        status = json.loads(status_raw) if status_raw else {}
    except json.JSONDecodeError:
        status = {}

    opinions = read_file_safe(opinions_path)
    dead_ends = read_file_safe(dead_ends_path)
    snapshots = read_jsonl_safe(snapshots_path)
    data_raw = read_file_safe(data_path)
    goal = read_file_safe(goal_path)

    try:
        data_parsed = json.loads(data_raw) if data_raw else []
    except json.JSONDecodeError:
        data_parsed = []

    latest_metrics = status.get("metrics_history", [])
    if isinstance(latest_metrics, list) and latest_metrics:
        latest_metrics = latest_metrics[-1]
    if not isinstance(latest_metrics, dict):
        latest_metrics = {}

    if not snapshots:
        snapshots = [{
            "cycle": status.get("cycle", 0),
            "max_cycles": status.get("max_cycles", 0),
            "phase": status.get("phase", ""),
            "last_result": status.get("last_result", ""),
            "last_error": status.get("last_error", ""),
            "timestamp": status.get("timestamp", ""),
            "opinions_content": opinions,
            "dead_ends_content": dead_ends,
            "metrics": latest_metrics,
        }]

    return {
        **status,
        "opinions_content": opinions,
        "dead_ends_content": dead_ends,
        "cycle_snapshots": snapshots,
        "data_content": json.dumps(data_parsed, indent=2) if data_parsed else "[]",
        "goal_content": goal,
    }


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Avalanche Telemetry Feed</title>
<style>
  :root {
    --bg: #030405;
    --panel: rgba(8, 11, 12, 0.94);
    --panel-2: rgba(11, 16, 17, 0.92);
    --grid: rgba(124, 255, 191, 0.08);
    --line: rgba(125, 255, 210, 0.2);
    --line-strong: rgba(255, 179, 71, 0.35);
    --acid: #c9ff62;
    --lime: #7cffbf;
    --cyan: #86e7ff;
    --amber: #ffb347;
    --amber-2: #ff8d45;
    --red: #ff655e;
    --text: #eef9f1;
    --muted: #7b9388;
    --shadow: 0 26px 70px rgba(0, 0, 0, 0.42);
  }

  * { box-sizing: border-box; }

  body {
    margin: 0;
    min-height: 100vh;
    padding: 18px;
    color: var(--text);
    font-family: "Bank Gothic", "Eurostile", "OCR A Extended", "Share Tech Mono", monospace;
    background:
      radial-gradient(circle at top right, rgba(255,101,94,0.12), transparent 18%),
      radial-gradient(circle at 14% 0%, rgba(201,255,98,0.1), transparent 24%),
      linear-gradient(transparent 35px, var(--grid) 36px),
      linear-gradient(90deg, transparent 35px, var(--grid) 36px),
      linear-gradient(180deg, #050708 0%, #090c0d 34%, #030405 100%);
    background-size: auto, auto, 36px 36px, 36px 36px, auto;
    overflow-x: hidden;
  }

  body::before,
  body::after {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
  }

  body::before {
    background:
      linear-gradient(to bottom, rgba(255,255,255,0.04), transparent 12%),
      repeating-linear-gradient(
        to bottom,
        rgba(255,255,255,0.028) 0,
        rgba(255,255,255,0.028) 1px,
        transparent 1px,
        transparent 4px
      );
    mix-blend-mode: screen;
    opacity: 0.28;
  }

  body::after {
    background:
      linear-gradient(125deg, transparent 0 62%, rgba(255,179,71,0.05) 62% 66%, transparent 66%),
      linear-gradient(300deg, transparent 0 68%, rgba(124,255,191,0.05) 68% 71%, transparent 71%);
    animation: sweep 12s linear infinite;
  }

  @keyframes sweep {
    from { transform: translateX(-2%); }
    50% { transform: translateX(2%); }
    to { transform: translateX(-2%); }
  }

  .shell {
    width: min(1480px, calc(100vw - 4px));
    margin: 0 auto;
    position: relative;
    z-index: 1;
  }

  .header,
  .telemetry-shell,
  .telemetry-charts,
  .timeline,
  .error-panel {
    position: relative;
    border: 1px solid var(--line);
    background:
      linear-gradient(180deg, rgba(255,255,255,0.03), transparent 38%),
      var(--panel);
    box-shadow: var(--shadow), 0 0 0 1px rgba(255,255,255,0.03) inset;
    overflow: hidden;
  }

  .header::before,
  .telemetry-shell::before,
  .telemetry-charts::before,
  .timeline::before,
  .error-panel::before {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgba(255,255,255,0.03), transparent 34%);
    pointer-events: none;
  }

  .header {
    clip-path: polygon(0 0, calc(100% - 28px) 0, 100% 28px, 100% 100%, 22px 100%, 0 calc(100% - 22px));
    margin-bottom: 18px;
  }

  .header-top {
    display: grid;
    grid-template-columns: 200px 1fr 200px;
    gap: 18px;
    align-items: center;
    padding: 18px 22px;
    border-bottom: 1px solid var(--line);
    background:
      linear-gradient(90deg, rgba(255,179,71,0.08), transparent 20%, transparent 80%, rgba(124,255,191,0.05));
  }

  .header-code,
  .header-status {
    font-size: 11px;
    line-height: 1.65;
    letter-spacing: 0.28em;
    text-transform: uppercase;
    color: var(--muted);
  }

  .header-code::before,
  .header-status::before {
    content: "";
    display: block;
    width: 44px;
    height: 3px;
    margin-bottom: 10px;
    background: linear-gradient(90deg, var(--amber), transparent);
  }

  .header-copy {
    text-align: center;
  }

  .header-copy h1 {
    margin: 0;
    font-size: clamp(26px, 3.5vw, 54px);
    line-height: 0.9;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--acid);
    text-shadow: 0 0 22px rgba(201,255,98,0.14);
  }

  .header-copy p {
    margin: 10px 0 0;
    color: var(--amber);
    font-size: 11px;
    letter-spacing: 0.36em;
    text-transform: uppercase;
  }

  .header-bottom {
    display: grid;
    grid-template-columns: 1.2fr 0.8fr;
    gap: 18px;
    padding: 20px 22px 22px;
  }

  .brief,
  .signal-board {
    border: 1px solid var(--line);
    background: linear-gradient(180deg, rgba(255,255,255,0.02), transparent 70%), var(--panel-2);
    padding: 16px 18px;
    position: relative;
  }

  .brief-label {
    display: inline-block;
    margin-bottom: 12px;
    padding: 4px 8px 4px 10px;
    border-left: 3px solid var(--amber);
    background: rgba(255, 179, 71, 0.08);
    color: var(--amber);
    font-size: 10px;
    letter-spacing: 0.24em;
    text-transform: uppercase;
  }

  .brief p {
    margin: 0;
    max-width: 62ch;
    line-height: 1.7;
    font-size: 14px;
  }

  .signal-board {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    align-content: start;
  }

  .signal-cell,
  .status-card,
  .panel,
  .chart-block {
    position: relative;
    border: 1px solid var(--line);
    background: linear-gradient(180deg, rgba(255,255,255,0.02), transparent 72%), var(--panel-2);
    box-shadow: 0 0 0 1px rgba(255,255,255,0.025) inset;
  }

  .signal-cell,
  .status-card {
    clip-path: polygon(0 0, calc(100% - 14px) 0, 100% 14px, 100% 100%, 0 100%);
    padding: 12px 12px 14px 14px;
  }

  .signal-cell::after,
  .status-card::after,
  .panel::after,
  .chart-block::after {
    content: "";
    position: absolute;
    top: 0;
    right: 0;
    width: 16px;
    height: 16px;
    background: linear-gradient(135deg, rgba(255,179,71,0.42), rgba(255,179,71,0.08));
    clip-path: polygon(100% 0, 0 0, 100% 100%);
  }

  .signal-label,
  .label,
  .panel-header,
  .chart-label {
    letter-spacing: 0.24em;
    text-transform: uppercase;
  }

  .signal-label,
  .label {
    color: var(--muted);
    font-size: 10px;
  }

  .signal-value,
  .value {
    margin-top: 8px;
    font-size: 22px;
    line-height: 0.95;
  }

  .signal-value {
    color: var(--lime);
  }

  .telemetry-shell {
    padding: 18px;
  }

  .status-bar,
  .telemetry-bar {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
  }

  .telemetry-bar {
    display: none;
    margin-top: 12px;
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .telemetry-bar.live {
    display: grid;
  }

  .phase-grind { color: #d9b3ff; }
  .phase-ratchet { color: var(--cyan); }
  .phase-pass { color: var(--lime); }
  .phase-fail { color: var(--red); }
  .phase-sync { color: var(--amber); }
  .phase-idle { color: var(--muted); }
  .phase-telemetry { color: var(--lime); }
  .phase-turbulence { color: var(--red); }
  .phase-ontology { color: var(--cyan); }
  .phase-epicycle { color: var(--amber); }

  .panels {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-top: 18px;
    margin-bottom: 18px;
  }

  .snapshot-shell {
    margin-top: 18px;
    margin-bottom: 18px;
    border: 1px solid var(--line);
    background: linear-gradient(180deg, rgba(255,255,255,0.03), transparent 72%), var(--panel-2);
    box-shadow: 0 0 0 1px rgba(255,255,255,0.025) inset;
    padding: 14px 16px;
  }

  .snapshot-row {
    display: grid;
    grid-template-columns: 190px 1fr auto;
    gap: 14px;
    align-items: center;
  }

  .snapshot-label {
    font-size: 11px;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    color: var(--amber);
  }

  .snapshot-meta {
    font-size: 11px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--muted);
  }

  .snapshot-controls {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .snapshot-controls button {
    border: 1px solid var(--line);
    background: rgba(0, 0, 0, 0.32);
    color: var(--text);
    padding: 7px 10px;
    font: inherit;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    cursor: pointer;
  }

  .snapshot-controls button.live {
    color: var(--acid);
    border-color: var(--line-strong);
  }

  .snapshot-controls input[type="range"] {
    width: min(420px, 34vw);
    accent-color: var(--amber);
  }

  .panel {
    overflow: hidden;
  }

  .panel.full-width {
    grid-column: 1 / -1;
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    border-bottom: 1px solid var(--line);
    background:
      linear-gradient(90deg, rgba(255,179,71,0.08), transparent 22%, transparent 80%, rgba(124,255,191,0.05));
    color: var(--acid);
    font-size: 11px;
  }

  .word-count {
    font-size: 10px;
    color: var(--muted);
  }
  .word-count.warn { color: var(--amber); }
  .word-count.crit { color: var(--red); }

  .progress-bar {
    height: 4px;
    background: rgba(255,255,255,0.05);
  }

  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--lime), var(--acid));
    transition: width 0.4s ease;
  }
  .progress-fill.warn { background: linear-gradient(90deg, var(--amber), var(--amber-2)); }
  .progress-fill.crit { background: linear-gradient(90deg, var(--red), #ff9276); }

  .panel-body {
    padding: 16px 18px;
    white-space: pre-wrap;
    word-wrap: break-word;
    font-size: 13px;
    line-height: 1.6;
    max-height: 420px;
    overflow-y: auto;
  }

  .panel-subchart {
    position: relative;
    border-top: 1px solid var(--line);
    background:
      linear-gradient(90deg, rgba(255, 179, 71, 0.08), transparent 18%, transparent 82%, rgba(124,255,191,0.05)),
      repeating-linear-gradient(
        135deg,
        rgba(255,179,71,0.045) 0,
        rgba(255,179,71,0.045) 8px,
        transparent 8px,
        transparent 16px
      ),
      rgba(0, 0, 0, 0.22);
    padding: 12px 16px 14px;
  }

  .panel-subchart::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: linear-gradient(180deg, rgba(255,255,255,0.03), transparent 52%);
  }

  .subchart-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
  }

  .subchart-label {
    color: var(--amber);
    font-size: 10px;
    letter-spacing: 0.24em;
    text-transform: uppercase;
  }

  .subchart-meta {
    color: var(--muted);
    font-size: 10px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
  }

  .subchart-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .oscillator-card {
    position: relative;
    border: 1px solid var(--line);
    background:
      linear-gradient(180deg, rgba(255,255,255,0.025), transparent 62%),
      rgba(0, 0, 0, 0.22);
    padding: 10px 12px 12px;
    min-width: 0;
  }

  .oscillator-card::after {
    content: "";
    position: absolute;
    top: 0;
    right: 0;
    width: 14px;
    height: 14px;
    background: linear-gradient(135deg, rgba(255,179,71,0.42), rgba(255,179,71,0.08));
    clip-path: polygon(100% 0, 0 0, 100% 100%);
  }

  .oscillator-frame {
    display: grid;
    grid-template-columns: 28px 1fr;
    grid-template-rows: 1fr auto;
    gap: 6px 8px;
    align-items: stretch;
  }

  .axis-y,
  .axis-x {
    color: var(--muted);
    font-size: 9px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
  }

  .axis-y {
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    text-align: center;
    align-self: center;
  }

  .axis-x {
    grid-column: 2;
    text-align: right;
  }

  .subchart-svg {
    width: 100%;
    height: 120px;
    display: block;
  }

  .data-pair {
    margin-bottom: 10px;
    padding: 10px 12px;
    border: 1px solid var(--line);
    background: rgba(0, 0, 0, 0.26);
  }

  .pair-label {
    margin-bottom: 4px;
    color: var(--amber);
    font-size: 10px;
    letter-spacing: 0.2em;
    text-transform: uppercase;
  }

  .pair-input { color: var(--cyan); }
  .pair-expected { color: var(--lime); margin-top: 4px; }

  .error-panel,
  .telemetry-charts,
  .timeline {
    margin-bottom: 18px;
  }

  .error-panel .panel-header {
    color: var(--red);
  }

  .error-panel .panel-body {
    color: #ffb07b;
    max-height: 220px;
  }

  body.alert-ratchet .header,
  body.alert-ratchet .telemetry-shell,
  body.alert-ratchet .snapshot-shell {
    box-shadow: var(--shadow), 0 0 0 1px rgba(255,255,255,0.03) inset, 0 0 28px rgba(134, 231, 255, 0.12);
  }

  body.alert-ontology .header,
  body.alert-ontology .telemetry-shell,
  body.alert-ontology .panel {
    box-shadow: var(--shadow), 0 0 0 1px rgba(255,255,255,0.03) inset, 0 0 30px rgba(255, 179, 71, 0.12);
  }

  body.alert-edge::after {
    opacity: 1;
    animation-duration: 5s;
  }

  body.alert-edge .signal-cell,
  body.alert-edge .status-card,
  body.alert-edge .panel,
  body.alert-edge .chart-block {
    border-color: rgba(255, 95, 89, 0.28);
  }

  body.alert-edge .panel::before,
  body.alert-edge .telemetry-shell::before {
    background: linear-gradient(135deg, rgba(255,95,89,0.08), transparent 34%);
  }

  .telemetry-charts {
    display: none;
  }

  .telemetry-charts.live {
    display: block;
  }

  .telemetry-grid {
    padding: 16px;
    display: grid;
    gap: 12px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chart-block {
    padding: 10px 12px 12px;
  }

  .chart-label {
    color: var(--muted);
    font-size: 10px;
    margin-bottom: 8px;
  }

  .chart-svg {
    width: 100%;
    height: 92px;
    display: block;
  }

  .chart-meta {
    margin-top: 6px;
    font-size: 10px;
    color: var(--muted);
    display: flex;
    justify-content: space-between;
  }

  .timeline-band {
    display: grid;
    grid-auto-flow: column;
    grid-auto-columns: 1fr;
    gap: 4px;
    height: 22px;
  }

  .timeline-band .slot {
    min-width: 10px;
    border-radius: 0;
  }

  .slot.bootstrap { background: #5c6468; }
  .slot.stable { background: var(--lime); }
  .slot.epicycle { background: var(--amber); }
  .slot.ontology { background: var(--cyan); }
  .slot.turbulence { background: var(--red); }

  .timeline-body {
    padding: 12px 16px;
    max-height: 260px;
    overflow-y: auto;
    font-size: 12px;
  }

  .timeline-entry {
    display: grid;
    grid-template-columns: 72px 48px 1fr auto;
    gap: 10px;
    padding: 5px 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
  }

  .timeline-entry .time,
  .timeline-entry .cycle-num {
    color: var(--muted);
  }

  .no-data {
    color: var(--muted);
    text-align: center;
    padding: 36px;
    font-size: 11px;
    letter-spacing: 0.2em;
    text-transform: uppercase;
  }

  @media (max-width: 980px) {
    .header-top,
    .header-bottom,
    .status-bar,
    .telemetry-bar,
    .panels,
    .subchart-grid,
    .telemetry-grid {
      grid-template-columns: 1fr;
    }

    .shell {
      width: min(100vw - 8px, 1480px);
    }

    .header-top {
      text-align: center;
    }
  }
</style>
</head>
<body>
  <main class="shell">
    <section class="header">
      <div class="header-top">
        <div class="header-code">Feed Designation<br>Live Telemetry</div>
        <div class="header-copy">
          <h1>Avalanche Feed</h1>
          <p>Research Control Surface</p>
        </div>
        <div class="header-status"><span id="conn">CONNECTING...</span><br>Signal State</div>
      </div>
      <div class="header-bottom">
        <div class="brief">
          <span class="brief-label">Telemetry Brief</span>
          <p>
            This feed shows one organism inside the Avalanche pressure chamber:
            active cycle phase, dead-end compression, ratchet contradictions, and
            theory drift across the structured Basin / Family / Local stack.
          </p>
        </div>
        <div class="signal-board">
          <div class="signal-cell">
            <div class="signal-label">Cycle Envelope</div>
            <div class="signal-value" id="cycle">-</div>
          </div>
          <div class="signal-cell">
            <div class="signal-label">Phase Gate</div>
            <div class="signal-value" id="phase">-</div>
          </div>
          <div class="signal-cell">
            <div class="signal-label">Last Result</div>
            <div class="signal-value" id="result">-</div>
          </div>
          <div class="signal-cell">
            <div class="signal-label">Failure Pairs</div>
            <div class="signal-value" id="dp-count">-</div>
          </div>
        </div>
      </div>
    </section>

    <section class="telemetry-shell">
      <div class="status-bar">
        <div class="status-card">
          <div class="label">Opinions</div>
          <div class="value" id="op-words">-</div>
        </div>
        <div class="status-card">
          <div class="label">Dead Ends</div>
          <div class="value" id="de-words">-</div>
        </div>
        <div class="status-card">
          <div class="label">Theory Cap</div>
          <div class="value phase-telemetry" id="op-summary">-</div>
        </div>
        <div class="status-card">
          <div class="label">Constraint Cap</div>
          <div class="value phase-telemetry" id="de-summary">-</div>
        </div>
      </div>

      <div class="telemetry-bar" id="telemetry-bar">
        <div class="status-card">
          <div class="label">D_sem</div>
          <div class="value phase-telemetry" id="d-sem">-</div>
        </div>
        <div class="status-card">
          <div class="label">C_ast</div>
          <div class="value phase-telemetry" id="c-ast">-</div>
        </div>
        <div class="status-card">
          <div class="label">Delta C</div>
          <div class="value phase-telemetry" id="c-delta">-</div>
        </div>
        <div class="status-card">
          <div class="label">Dead Ends #</div>
          <div class="value phase-telemetry" id="de-count">-</div>
        </div>
        <div class="status-card">
          <div class="label">Tokens</div>
          <div class="value phase-telemetry" id="api-tokens">-</div>
        </div>
        <div class="status-card">
          <div class="label">DE Families</div>
          <div class="value phase-telemetry" id="de-families">-</div>
        </div>
        <div class="status-card">
          <div class="label">H_char</div>
          <div class="value phase-telemetry" id="op-entropy">-</div>
        </div>
        <div class="status-card">
          <div class="label">Retention</div>
          <div class="value phase-telemetry" id="de-retain">-</div>
        </div>
        <div class="status-card">
          <div class="label">Ontology #</div>
          <div class="value phase-telemetry" id="de-ontology">-</div>
        </div>
        <div class="status-card">
          <div class="label">P_beta</div>
          <div class="value phase-telemetry" id="ptolemy-beta">-</div>
        </div>
        <div class="status-card">
          <div class="label">OpPink</div>
          <div class="value phase-telemetry" id="opinions-pink">-</div>
        </div>
        <div class="status-card">
          <div class="label">TokPink</div>
          <div class="value phase-telemetry" id="token-pink">-</div>
        </div>
        <div class="status-card">
          <div class="label">Turbulence</div>
          <div class="value" id="turbulence-state">-</div>
        </div>
      </div>
    </section>

    <section class="snapshot-shell">
      <div class="snapshot-row">
        <div class="snapshot-label">Cycle Playback</div>
        <div class="snapshot-meta" id="snapshot-meta">Latest visible state</div>
        <div class="snapshot-controls">
          <button id="snapshot-prev">Prev</button>
          <input type="range" id="snapshot-range" min="0" max="0" value="0">
          <button id="snapshot-next">Next</button>
          <button id="snapshot-live" class="live">Latest</button>
        </div>
      </div>
    </section>

    <div class="panels">
      <section class="panel">
        <div class="panel-header">
          <span>opinions.md</span>
          <span class="word-count" id="op-wc-label">-</span>
        </div>
        <div class="progress-bar"><div class="progress-fill" id="op-bar"></div></div>
        <div class="panel-body" id="op-content"><span class="no-data">Waiting for data...</span></div>
        <div class="panel-subchart">
          <div class="subchart-head">
            <div class="subchart-label">Rolling Noise Spectrometer</div>
            <div class="subchart-meta" id="opinions-pink-meta">window -</div>
          </div>
          <div class="subchart-grid">
            <div class="oscillator-card">
              <div class="subchart-head">
                <div class="subchart-label">Opinions Spectrometer</div>
                <div class="subchart-meta" id="opinions-pink-latest">beta -</div>
              </div>
              <div class="oscillator-frame">
                <div class="axis-y">Beta</div>
                <svg class="subchart-svg" id="opinions-pink-chart" viewBox="0 0 420 120" preserveAspectRatio="none"></svg>
                <div class="axis-x">Cycle / Regime</div>
              </div>
            </div>
            <div class="oscillator-card">
              <div class="subchart-head">
                <div class="subchart-label">Token Spectrometer</div>
                <div class="subchart-meta" id="token-pink-latest">beta -</div>
              </div>
              <div class="oscillator-frame">
                <div class="axis-y">Beta</div>
                <svg class="subchart-svg" id="token-pink-chart" viewBox="0 0 420 120" preserveAspectRatio="none"></svg>
                <div class="axis-x">Cycle / Regime</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <span>dead-ends.md</span>
          <span class="word-count" id="de-wc-label">-</span>
        </div>
        <div class="progress-bar"><div class="progress-fill" id="de-bar"></div></div>
        <div class="panel-body" id="de-content"><span class="no-data">Waiting for data...</span></div>
      </section>

      <section class="panel full-width">
        <div class="panel-header">
          <span>data.json</span>
          <span class="word-count" id="dp-label">-</span>
        </div>
        <div class="panel-body" id="data-content"><span class="no-data">No failure data yet</span></div>
      </section>
    </div>

    <section class="error-panel" id="error-section" style="display:none">
      <div class="panel-header">Last Contradiction</div>
      <div class="panel-body" id="error-content"></div>
    </section>

    <section class="telemetry-charts" id="telemetry-charts">
      <div class="panel-header">Telemetry Trends</div>
      <div class="telemetry-grid">
        <div class="chart-block">
          <div class="chart-label">D_sem</div>
          <svg class="chart-svg" id="dsem-chart" viewBox="0 0 420 92" preserveAspectRatio="none"></svg>
          <div class="chart-meta">
            <span id="dsem-min">min -</span>
            <span id="dsem-max">max -</span>
          </div>
        </div>
        <div class="chart-block">
          <div class="chart-label">C_ast</div>
          <svg class="chart-svg" id="cast-chart" viewBox="0 0 420 92" preserveAspectRatio="none"></svg>
          <div class="chart-meta">
            <span id="cast-min">min -</span>
            <span id="cast-max">max -</span>
          </div>
        </div>
        <div class="chart-block">
          <div class="chart-label">Dead-End Families</div>
          <svg class="chart-svg" id="defam-chart" viewBox="0 0 420 92" preserveAspectRatio="none"></svg>
          <div class="chart-meta">
            <span id="defam-min">min -</span>
            <span id="defam-max">max -</span>
          </div>
        </div>
        <div class="chart-block">
          <div class="chart-label">Ptolemaic Ratio</div>
          <svg class="chart-svg" id="ptolemy-chart" viewBox="0 0 420 92" preserveAspectRatio="none"></svg>
          <div class="chart-meta">
            <span id="ptolemy-min">min -</span>
            <span id="ptolemy-max">max -</span>
          </div>
        </div>
        <div class="chart-block">
          <div class="chart-label">Turbulence Timeline</div>
          <div class="timeline-band" id="turbulence-band"></div>
          <div class="chart-meta">
            <span id="timeline-start">cycle -</span>
            <span id="timeline-end">cycle -</span>
          </div>
        </div>
      </div>
    </section>

    <section class="timeline">
      <div class="panel-header">Event Log</div>
      <div class="timeline-body" id="timeline"><span class="no-data">Waiting for events...</span></div>
    </section>
  </main>

<script>
const POLL_MS = 2000;
let lastTimestamp = null;
let failCount = 0;
let lastDataPayload = null;
let snapshotIndex = -1;
let snapshotPinned = false;

const phaseClass = {
  'GRIND': 'phase-grind',
  'RATCHET': 'phase-ratchet',
  'PASS': 'phase-pass',
  'FAIL': 'phase-fail',
  'SYNC_SUCCESS': 'phase-sync',
  'SYNC_FAILURE': 'phase-sync',
  'CYCLE_CAP': 'phase-fail',
};

const phaseLabel = {
  'GRIND': 'GRIND',
  'RATCHET': 'RATCHET',
  'PASS': 'PASS',
  'FAIL': 'FAIL',
  'SYNC_SUCCESS': 'SYNC',
  'SYNC_FAILURE': 'SYNC',
  'CYCLE_CAP': 'CAP',
};

const turbulenceClass = {
  'BOOTSTRAP': 'phase-idle',
  'STABLE_PATCHING': 'phase-telemetry',
  'EPICYCLE_ACCUMULATION': 'phase-epicycle',
  'ONTOLOGY_CHANGE': 'phase-ontology',
  'PRODUCTIVE_TURBULENCE': 'phase-turbulence',
};

const turbulenceSlotClass = {
  'BOOTSTRAP': 'bootstrap',
  'STABLE_PATCHING': 'stable',
  'EPICYCLE_ACCUMULATION': 'epicycle',
  'ONTOLOGY_CHANGE': 'ontology',
  'PRODUCTIVE_TURBULENCE': 'turbulence',
};

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function wcClass(words, limit) {
  if (words >= limit) return 'crit';
  if (words >= limit * 0.8) return 'warn';
  return '';
}

function renderLineChart(points, color, options = {}) {
  const width = 420;
  const height = options.height || 92;
  const padX = options.padX || 22;
  const padY = options.padY || 10;
  if (!Array.isArray(points) || points.length === 0) {
    return '';
  }
  const min = typeof options.min === 'number' ? options.min : Math.min(...points);
  const max = typeof options.max === 'number' ? options.max : Math.max(...points);
  const span = max - min || 1;
  const step = points.length === 1 ? 0 : (width - padX * 2) / (points.length - 1);
  const coords = points.map((value, idx) => {
    const x = padX + step * idx;
    const y = height - padY - (((value - min) / span) * (height - padY * 2));
    return [x, y];
  });
  const polyline = coords.map(([x, y]) => `${x},${y}`).join(' ');
  const dots = coords.map(([x, y]) =>
    `<circle cx="${x}" cy="${y}" r="2.5" fill="${color}" />`
  ).join('');
  const baseY = height - padY;
  const axisX = `<line x1="${padX}" y1="${baseY}" x2="${width - padX}" y2="${baseY}" stroke="#2d383a" stroke-width="1" />`;
  const axisY = `<line x1="${padX}" y1="${padY}" x2="${padX}" y2="${baseY}" stroke="#2d383a" stroke-width="1" />`;
  const midY = padY + ((baseY - padY) / 2);
  const guides = `
    <line x1="${padX}" y1="${padY}" x2="${width - padX}" y2="${padY}" stroke="rgba(255,255,255,0.06)" stroke-width="1" />
    <line x1="${padX}" y1="${midY}" x2="${width - padX}" y2="${midY}" stroke="rgba(255,255,255,0.05)" stroke-width="1" />
  `;
  const bands = Array.isArray(options.bandLines) ? options.bandLines.map((band) => {
    const value = Number(band.value);
    const clamped = Math.min(max, Math.max(min, value));
    const y = height - padY - (((clamped - min) / span) * (height - padY * 2));
    const label = escapeHtml(String(band.label || value));
    const stroke = band.stroke || 'rgba(255,255,255,0.08)';
    return `
      <line x1="${padX}" y1="${y}" x2="${width - padX}" y2="${y}" stroke="${stroke}" stroke-width="1" stroke-dasharray="5 4" />
      <text x="${width - padX + 6}" y="${y + 3}" fill="#7b9388" font-size="9" text-anchor="start">${label}</text>
    `;
  }).join('') : '';
  const yTickValues = Array.isArray(options.yTickValues) ? options.yTickValues : [];
  const yTicks = yTickValues.map((value) => {
    const clamped = Math.min(max, Math.max(min, Number(value)));
    const y = height - padY - (((clamped - min) / span) * (height - padY * 2));
    const label = typeof options.yTickFormat === 'function'
      ? options.yTickFormat(clamped)
      : String(clamped);
    return `
      <line x1="${padX - 4}" y1="${y}" x2="${padX}" y2="${y}" stroke="rgba(255,255,255,0.16)" stroke-width="1" />
      <text x="${padX - 8}" y="${y + 3}" fill="#7b9388" font-size="9" text-anchor="end">${label}</text>
    `;
  }).join('');
  const xStart = options.xStart;
  const xEnd = options.xEnd;
  const xLabels = (typeof xStart !== 'undefined' && typeof xEnd !== 'undefined')
    ? `
      <text x="${padX}" y="${height - 1}" fill="#7b9388" font-size="9" text-anchor="start">${xStart}</text>
      <text x="${width - padX}" y="${height - 1}" fill="#7b9388" font-size="9" text-anchor="end">${xEnd}</text>
    `
    : '';
  return `${guides}${bands}${axisX}${axisY}${yTicks}${xLabels}<polyline fill="none" stroke="${color}" stroke-width="2.5" points="${polyline}" />${dots}`;
}

function renderTelemetryCharts(history) {
  const chartSection = document.getElementById('telemetry-charts');
  if (!Array.isArray(history) || history.length === 0) {
    chartSection.className = 'telemetry-charts';
    return;
  }
  chartSection.className = 'telemetry-charts live';

  const dsem = history.map(item => Number(item.opinions_jaccard_distance || 0));
  const cast = history.map(item => Number(item.solver_ast_complexity || 0));
  const defam = history.map(item => Number(item.dead_end_family_count || 0));
  const ptolemy = history.map(item => Number(item.ptolemaic_ratio || 0));
  const opinionsPink = history.map(item => Number(item.opinions_entropy_pink_closeness || 0));
  const tokenPink = history.map(item => Number(item.token_pink_closeness || 0));
  const opinionsBeta = history.map(item => Number(item.opinions_entropy_pink_beta || 0));
  const tokenBeta = history.map(item => Number(item.token_pink_beta || 0));
  const opinionsWindows = history.map(item => Number(item.opinions_entropy_pink_window || 0));
  const tokenWindows = history.map(item => Number(item.token_pink_window || 0));
  const cycleStart = history[0].cycle_metric || 1;
  const cycleEnd = history[history.length - 1].cycle_metric || history.length;

  document.getElementById('dsem-chart').innerHTML = renderLineChart(dsem, '#79c0ff');
  document.getElementById('cast-chart').innerHTML = renderLineChart(cast, '#56d364');
  document.getElementById('defam-chart').innerHTML = renderLineChart(defam, '#d2a8ff');
  document.getElementById('ptolemy-chart').innerHTML = renderLineChart(ptolemy, '#ffb347');
  const spectrometerBands = [
    { value: 2.0, label: 'BROWN', stroke: 'rgba(255,127,77,0.18)' },
    { value: 1.0, label: 'PINK', stroke: 'rgba(201,255,98,0.2)' },
    { value: 0.0, label: 'WHITE', stroke: 'rgba(134,231,255,0.18)' },
    { value: -1.0, label: 'BLUE', stroke: 'rgba(121,192,255,0.16)' },
  ];
  document.getElementById('opinions-pink-chart').innerHTML = renderLineChart(opinionsBeta, '#c8ff63', {
    height: 120,
    padX: 40,
    padY: 12,
    min: -1,
    max: 2.5,
    yTickValues: [2.0, 1.0, 0.0, -1.0],
    yTickFormat: value => Number(value).toFixed(1),
    xStart: cycleStart,
    xEnd: cycleEnd,
    bandLines: spectrometerBands,
  });
  document.getElementById('token-pink-chart').innerHTML = renderLineChart(tokenBeta, '#ff7f4d', {
    height: 120,
    padX: 40,
    padY: 12,
    min: -1,
    max: 2.5,
    yTickValues: [2.0, 1.0, 0.0, -1.0],
    yTickFormat: value => Number(value).toFixed(1),
    xStart: cycleStart,
    xEnd: cycleEnd,
    bandLines: spectrometerBands,
  });
  document.getElementById('dsem-min').textContent = 'min ' + Math.min(...dsem).toFixed(4);
  document.getElementById('dsem-max').textContent = 'max ' + Math.max(...dsem).toFixed(4);
  document.getElementById('cast-min').textContent = 'min ' + Math.min(...cast);
  document.getElementById('cast-max').textContent = 'max ' + Math.max(...cast);
  document.getElementById('defam-min').textContent = 'min ' + Math.min(...defam);
  document.getElementById('defam-max').textContent = 'max ' + Math.max(...defam);
  document.getElementById('ptolemy-min').textContent = 'min ' + Math.min(...ptolemy).toFixed(2);
  document.getElementById('ptolemy-max').textContent = 'max ' + Math.max(...ptolemy).toFixed(2);
  document.getElementById('opinions-pink-meta').textContent =
    'opinions ' + Math.max(...opinionsWindows, 0) + ' // token ' + Math.max(...tokenWindows, 0);
  document.getElementById('opinions-pink-latest').textContent =
    'beta ' + opinionsBeta[opinionsBeta.length - 1].toFixed(2) + ' // closeness ' + opinionsPink[opinionsPink.length - 1].toFixed(2);
  document.getElementById('token-pink-latest').textContent =
    'beta ' + tokenBeta[tokenBeta.length - 1].toFixed(2) + ' // closeness ' + tokenPink[tokenPink.length - 1].toFixed(2);

  const band = document.getElementById('turbulence-band');
  band.innerHTML = history.map(item => {
    const label = item.turbulence_state || 'BOOTSTRAP';
    const cls = turbulenceSlotClass[label] || 'bootstrap';
    const cycle = item.cycle_metric || '?';
    return `<div class="slot ${cls}" title="Cycle ${cycle}: ${label}"></div>`;
  }).join('');
  document.getElementById('timeline-start').textContent = 'cycle ' + (history[0].cycle_metric || '-');
  document.getElementById('timeline-end').textContent = 'cycle ' + (history[history.length - 1].cycle_metric || '-');
}

function renderDataPairs(contentStr) {
  try {
    const pairs = JSON.parse(contentStr);
    if (!Array.isArray(pairs) || pairs.length === 0) {
      return '<span class="no-data">No failure data yet</span>';
    }
    let html = '';
    pairs.forEach((pair, i) => {
      html += '<div class="data-pair">';
      html += '<div class="pair-label">Pair ' + (i + 1) + '</div>';
      html += '<div class="pair-input">Input:    ' + escapeHtml(JSON.stringify(pair.input)) + '</div>';
      html += '<div class="pair-expected">Expected: ' + escapeHtml(JSON.stringify(pair.expected)) + '</div>';
      html += '</div>';
    });
    return html;
  } catch (e) {
    return '<span class="no-data">Invalid data</span>';
  }
}

function update(data) {
  lastDataPayload = data;
  const conn = document.getElementById('conn');
  conn.textContent = 'LIVE';
  conn.className = 'connection live';

  const cycle = data.cycle || 0;
  const maxCycles = data.max_cycles || 15;
  const phase = data.phase || 'IDLE';
  const result = data.last_result || '-';
  const opWords = data.opinions_words || 0;
  const opLimit = data.opinions_limit || 75;
  const deWords = data.dead_ends_words || 0;
  const deLimit = data.dead_ends_limit || 50;
  const dpCount = data.data_pairs || 0;
  const dpMax = data.data_max_pairs || 4;

  document.getElementById('cycle').textContent = cycle + '/' + maxCycles;

  const phaseEl = document.getElementById('phase');
  phaseEl.textContent = phaseLabel[phase] || phase;
  phaseEl.className = 'value ' + (phaseClass[phase] || 'phase-idle');

  const resultEl = document.getElementById('result');
  resultEl.textContent = result;
  resultEl.className = 'value ' + (result === 'PASS' ? 'phase-pass' : result === 'FAIL' ? 'phase-fail' : 'phase-idle');

  // Opinions
  const opWc = wcClass(opWords, opLimit);
  document.getElementById('op-words').textContent = opWords + '/' + opLimit;
  document.getElementById('op-wc-label').textContent = opWords + ' / ' + opLimit + ' words';
  document.getElementById('op-summary').textContent = opWords + '/' + opLimit;
  document.getElementById('op-wc-label').className = 'word-count ' + opWc;
  const opBar = document.getElementById('op-bar');
  opBar.style.width = Math.min(100, (opWords / opLimit) * 100) + '%';
  opBar.className = 'progress-fill ' + opWc;

  // Dead Ends
  const deWc = wcClass(deWords, deLimit);
  document.getElementById('de-words').textContent = deWords + '/' + deLimit;
  document.getElementById('de-wc-label').textContent = deWords + ' / ' + deLimit + ' words';
  document.getElementById('de-summary').textContent = deWords + '/' + deLimit;
  document.getElementById('de-wc-label').className = 'word-count ' + deWc;
  const deBar = document.getElementById('de-bar');
  deBar.style.width = Math.min(100, (deWords / deLimit) * 100) + '%';
  deBar.className = 'progress-fill ' + deWc;

  // Data pairs
  document.getElementById('dp-count').textContent = dpCount + '/' + dpMax;
  document.getElementById('dp-label').textContent = dpCount + ' / ' + dpMax + ' pairs';

  // Optional telemetry
  const telemetryBar = document.getElementById('telemetry-bar');
  const latestMetrics = Array.isArray(data.metrics_history) && data.metrics_history.length > 0
    ? data.metrics_history[data.metrics_history.length - 1]
    : null;
  const telemetry = (typeof data.solver_ast_complexity !== 'undefined') ? data : latestMetrics;
  const hasTelemetry = telemetry !== null && typeof telemetry.solver_ast_complexity !== 'undefined';
  telemetryBar.className = hasTelemetry ? 'telemetry-bar live' : 'telemetry-bar';
  if (hasTelemetry) {
    document.getElementById('d-sem').textContent = Number(telemetry.opinions_jaccard_distance || 0).toFixed(4);
    document.getElementById('c-ast').textContent = telemetry.solver_ast_complexity ?? '-';
    document.getElementById('c-delta').textContent = telemetry.solver_ast_delta ?? '-';
    document.getElementById('de-count').textContent = telemetry.dead_ends_count ?? '-';
    document.getElementById('api-tokens').textContent = telemetry.api_total_tokens_cycle ?? '-';
    document.getElementById('de-families').textContent = telemetry.dead_end_family_count ?? '-';
    document.getElementById('op-entropy').textContent =
      typeof telemetry.opinions_char_entropy === 'undefined' ? '-' : Number(telemetry.opinions_char_entropy).toFixed(3);
    document.getElementById('de-retain').textContent = Math.round(Number(telemetry.dead_end_family_retention || 0) * 100) + '%';
    document.getElementById('de-ontology').textContent = telemetry.dead_end_ontology_count ?? '-';
    document.getElementById('ptolemy-beta').textContent =
      typeof telemetry.ptolemaic_ratio_pink_beta === 'undefined' ? '-' : Number(telemetry.ptolemaic_ratio_pink_beta).toFixed(2);
    document.getElementById('opinions-pink').textContent =
      typeof telemetry.opinions_entropy_pink_closeness === 'undefined' ? '-' : Number(telemetry.opinions_entropy_pink_closeness).toFixed(2);
    document.getElementById('token-pink').textContent =
      typeof telemetry.token_pink_closeness === 'undefined' ? '-' : Number(telemetry.token_pink_closeness).toFixed(2);
    const turbulence = telemetry.turbulence_state || 'BOOTSTRAP';
    const turbulenceEl = document.getElementById('turbulence-state');
    turbulenceEl.textContent = turbulence;
    turbulenceEl.className = 'value ' + (turbulenceClass[turbulence] || 'phase-idle');
  }
  renderTelemetryCharts(Array.isArray(data.metrics_history) ? data.metrics_history : []);
  updateAlertState(phase, result, telemetry);

  // File contents / snapshots
  const snapshots = normalizeSnapshots(data);
  syncSnapshotControls(snapshots);
  const activeSnapshot = snapshots[snapshotIndex] || snapshots[snapshots.length - 1];
  const opContent = activeSnapshot.opinions_content || data.opinions_content || '';
  const deContent = activeSnapshot.dead_ends_content || data.dead_ends_content || '';
  const dataContent = data.data_content || '[]';
  const activeCycle = activeSnapshot.cycle || cycle;
  const activePhase = activeSnapshot.phase || phase;
  const activeResult = activeSnapshot.last_result || result;
  document.getElementById('snapshot-meta').textContent =
    'Cycle ' + activeCycle + ' / ' + maxCycles + ' // ' + activePhase + ' // ' + (activeResult || 'IN-FLIGHT');
  document.getElementById('op-content').innerHTML = opContent
    ? escapeHtml(opContent) : '<span class="no-data">File not found</span>';
  document.getElementById('de-content').innerHTML = deContent
    ? escapeHtml(deContent) : '<span class="no-data">File not found</span>';
  document.getElementById('data-content').innerHTML = renderDataPairs(dataContent);

  // Error
  const errSection = document.getElementById('error-section');
  const errContent = document.getElementById('error-content');
  if (data.last_error && data.last_error.trim()) {
    errSection.style.display = 'block';
    errContent.textContent = data.last_error;
  } else {
    errSection.style.display = 'none';
  }

  // Timeline
  const log = data.log || [];
  if (log.length > 0) {
    const timelineEl = document.getElementById('timeline');
    let html = '';
    for (let i = log.length - 1; i >= 0; i--) {
      const e = log[i];
      const cls = phaseClass[e.phase] || 'phase-idle';
      html += '<div class="timeline-entry">';
      html += '<span class="time">' + escapeHtml(e.time || '') + '</span>';
      html += '<span class="cycle-num">C' + (e.cycle || 0) + '</span>';
      html += '<span class="event ' + cls + '">' + escapeHtml(e.phase || '') + '</span>';
      if (e.result) {
        html += '<span class="event ' + (e.result === 'PASS' ? 'phase-pass' : 'phase-fail') + '"> ' + escapeHtml(e.result) + '</span>';
      }
      html += '</div>';
    }
    timelineEl.innerHTML = html;
  }

  lastTimestamp = data.timestamp;
}

function normalizeSnapshots(data) {
  const snapshots = Array.isArray(data.cycle_snapshots) && data.cycle_snapshots.length
    ? data.cycle_snapshots
    : [{
        cycle: data.cycle || 0,
        max_cycles: data.max_cycles || 0,
        phase: data.phase || 'IDLE',
        last_result: data.last_result || '',
        opinions_content: data.opinions_content || '',
        dead_ends_content: data.dead_ends_content || '',
        metrics: Array.isArray(data.metrics_history) && data.metrics_history.length ? data.metrics_history[data.metrics_history.length - 1] : {},
      }];
  return snapshots;
}

function syncSnapshotControls(snapshots) {
  const range = document.getElementById('snapshot-range');
  range.max = String(Math.max(0, snapshots.length - 1));
  if (!snapshotPinned || snapshotIndex >= snapshots.length || snapshotIndex < 0) {
    snapshotIndex = snapshots.length - 1;
  }
  range.value = String(snapshotIndex);
}

function updateAlertState(phase, result, telemetry) {
  const body = document.body;
  body.classList.remove('alert-ratchet', 'alert-ontology', 'alert-edge');
  if (phase === 'RATCHET') {
    body.classList.add('alert-ratchet');
  }
  const turbulence = telemetry && telemetry.turbulence_state ? telemetry.turbulence_state : '';
  if (turbulence === 'ONTOLOGY_CHANGE' || turbulence === 'EPICYCLE_ACCUMULATION' || turbulence === 'PRODUCTIVE_TURBULENCE') {
    body.classList.add('alert-ontology');
  }
  const edge =
    phase === 'RATCHET' ||
    result === 'FAIL' ||
    turbulence === 'EPICYCLE_ACCUMULATION' ||
    (telemetry && typeof telemetry.solver_ast_delta !== 'undefined' && Math.abs(Number(telemetry.solver_ast_delta || 0)) >= 3);
  if (edge) {
    body.classList.add('alert-edge');
  }
}

document.getElementById('snapshot-prev').addEventListener('click', () => {
  if (!lastDataPayload) return;
  const snapshots = normalizeSnapshots(lastDataPayload);
  snapshotPinned = true;
  snapshotIndex = Math.max(0, snapshotIndex - 1);
  update(lastDataPayload);
});

document.getElementById('snapshot-next').addEventListener('click', () => {
  if (!lastDataPayload) return;
  const snapshots = normalizeSnapshots(lastDataPayload);
  snapshotPinned = true;
  snapshotIndex = Math.min(snapshots.length - 1, snapshotIndex + 1);
  update(lastDataPayload);
});

document.getElementById('snapshot-range').addEventListener('input', (event) => {
  if (!lastDataPayload) return;
  snapshotPinned = true;
  snapshotIndex = Number(event.target.value || 0);
  update(lastDataPayload);
});

document.getElementById('snapshot-live').addEventListener('click', () => {
  snapshotPinned = false;
  if (lastDataPayload) update(lastDataPayload);
});

async function poll() {
  try {
    const resp = await fetch('api/status');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    update(data);
    failCount = 0;
  } catch (e) {
    failCount++;
    if (failCount > 3) {
      const conn = document.getElementById('conn');
      conn.textContent = 'DISCONNECTED';
      conn.className = 'connection dead';
    }
  }
  setTimeout(poll, POLL_MS);
}

poll();
</script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    terrarium = "."

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/status":
            self.send_json(get_api_response(self.terrarium))
        elif path == "/" or path == "/index.html":
            self.send_html(HTML_PAGE)
        else:
            self.send_error(404)

    def send_json(self, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Suppress request logging


def main():
    args = sys.argv[1:]
    port = DEFAULT_PORT

    if "--port" in args:
        idx = args.index("--port")
        port = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]

    if not args:
        print("Usage: python dashboard.py <terrarium_path> [--port 8080]")
        print("Example: python dashboard.py C:\\terrarium")
        sys.exit(1)

    terrarium = os.path.abspath(args[0])
    if not os.path.isdir(terrarium):
        print(f"Error: '{terrarium}' is not a directory.")
        sys.exit(1)

    DashboardHandler.terrarium = terrarium

    server = HTTPServer(("127.0.0.1", port), DashboardHandler)
    print(f"  Avalanche Dashboard: http://127.0.0.1:{port}")
    print(f"  Watching: {terrarium}")
    print(f"  Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
