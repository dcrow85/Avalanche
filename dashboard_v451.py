#!/usr/bin/env python3
"""
V4.5.1 Apparatus Dashboard — Deep telemetry viewer for the gate machinery.

Single-branch (A-only) deep-telemetry dashboard with run selector and
9 chart panels covering E_ratio, oracle, reservoir, complexity decomposition,
theory lifecycle, token allocation, and mechanical health.

Zero external dependencies — stdlib only.

Usage: python3 dashboard_v451.py <workspace_root> [--port 8101]
Example: python3 dashboard_v451.py runs/assay-v451 --port 8101
"""
import json
import os
import sys
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

DEFAULT_PORT = 8101


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

def read_file_safe(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (FileNotFoundError, PermissionError, OSError):
        return ""


def read_json_safe(path):
    raw = read_file_safe(path)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def read_jsonl_safe(path):
    rows = []
    raw = read_file_safe(path)
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


# ---------------------------------------------------------------------------
# Field normalization
# ---------------------------------------------------------------------------

def normalize_log_entry(entry):
    """Normalize field names across all gate_decision types."""
    e = dict(entry)
    if "reservoir_remaining" not in e and "reservoir" in e:
        e["reservoir_remaining"] = e["reservoir"]
    elif "reservoir_remaining" not in e:
        e["reservoir_remaining"] = 0
    if "tokens_consumed_this_cycle" not in e and "tokens" in e:
        e["tokens_consumed_this_cycle"] = e["tokens"]
    elif "tokens_consumed_this_cycle" not in e:
        e["tokens_consumed_this_cycle"] = 0
    return e


# ---------------------------------------------------------------------------
# Workspace discovery
# ---------------------------------------------------------------------------

def discover_runs(root):
    """Find all branch-*-run-N directories under root."""
    runs = []
    root_path = Path(root)
    if not root_path.exists():
        return runs
    for entry in sorted(root_path.iterdir()):
        if entry.is_dir() and entry.name.startswith("branch-"):
            parts = entry.name.split("-")
            if len(parts) >= 4:
                try:
                    run_id = int(parts[3])
                except (ValueError, IndexError):
                    continue
                runs.append({"path": str(entry), "run_id": run_id, "name": entry.name})
    return runs


# ---------------------------------------------------------------------------
# Data reading
# ---------------------------------------------------------------------------

def read_run_data(ws, detailed=False):
    """Read all data for a single run workspace."""
    p = ws["path"]
    config = read_json_safe(os.path.join(p, "assay_config.json"))
    status = read_json_safe(os.path.join(p, "status.json"))
    log_raw = read_jsonl_safe(os.path.join(p, "assay_log.jsonl"))

    log = [normalize_log_entry(r) for r in log_raw]
    gated = [r for r in log if r.get("phase") == "gated"]

    accepted = sum(1 for r in gated if r.get("gate_decision") in ("accepted", "SURVIVED"))
    rejected = sum(1 for r in gated if r.get("gate_decision") == "rejected")
    quarantined = sum(1 for r in gated if r.get("gate_decision") == "quarantined")
    qr = sum(1 for r in gated if r.get("gate_decision") == "quarantine_resolved")
    qf = sum(1 for r in gated if r.get("gate_decision") == "quarantine_failed")
    ff = sum(1 for r in gated if r.get("gate_decision") == "format_fatal")

    gate_decisions = [r.get("gate_decision", "") for r in gated][-100:]

    phase = status.get("phase", "PENDING")
    cycle = status.get("cycle", 0)
    reservoir = gated[-1].get("reservoir_remaining", 0) if gated else config.get("token_reservoir", 0)
    max_reservoir = config.get("token_reservoir", 1)

    result = {
        "run_id": ws["run_id"],
        "name": ws["name"],
        "config": config,
        "phase": phase,
        "cycle": cycle,
        "reservoir": reservoir,
        "max_reservoir": max_reservoir,
        "total_accepted": accepted,
        "total_rejected": rejected,
        "total_quarantined": quarantined,
        "total_quarantine_resolved": qr,
        "total_quarantine_failed": qf,
        "total_format_fatals": ff,
        "total_gated": len(gated),
        "is_complete": phase in ("RESERVOIR_EXHAUSTED", "CYCLE_CAP"),
        "is_active": bool(status) and phase not in ("RESERVOIR_EXHAUSTED", "CYCLE_CAP", "PENDING"),
        "latest_e_ratio": gated[-1].get("e_ratio", 0) if gated else 0,
        "latest_oracle": gated[-1].get("oracle_score", 0) if gated else 0,
        "threshold": config.get("e_ratio_threshold", 0),
        "gate_decisions": gate_decisions,
        "reservoir_pct": round(reservoir / max_reservoir * 100, 1) if max_reservoir > 0 else 0,
        "hunches_enabled": config.get("hunches_enabled", False),
    }

    if detailed:
        result.update({
            "e_ratio_series": [r.get("e_ratio", 0) for r in gated if "e_ratio" in r][-100:],
            "oracle_series": [r.get("oracle_score", 0) for r in gated if "oracle_score" in r][-100:],
            "reservoir_series": [r.get("reservoir_remaining", 0) for r in gated][-100:],
            "delta_c_series": [r.get("delta_c", 0) for r in gated if "delta_c" in r][-100:],
            "flux_series": [r.get("flux", 0) for r in gated if "flux" in r][-100:],
            "ast_branch_series": [r.get("ast_branching_depth", 0) for r in gated if "ast_branching_depth" in r][-100:],
            "ast_alg_series": [r.get("ast_algebraic_nodes", 0) for r in gated if "ast_algebraic_nodes" in r][-100:],
            "active_theories_series": [r.get("active_theories", 0) for r in gated if "active_theories" in r][-100:],
            "archived_theories_series": [r.get("archived_theories", 0) for r in gated if "archived_theories" in r][-100:],
            "theory_tokens_series": [r.get("theory_tokens", 0) for r in gated if "theory_tokens" in r][-100:],
            "solver_tokens_series": [r.get("solver_tokens", 0) for r in gated if "solver_tokens" in r][-100:],
            "prompt_context_series": [r.get("prompt_context_tokens", 0) for r in gated if "prompt_context_tokens" in r][-100:],
            "format_retries_series": [r.get("format_retries", 0) for r in gated][-100:],
            "tokens_per_cycle_series": [r.get("tokens_consumed_this_cycle", 0) for r in gated][-100:],
            "log_tail": gated[-20:],
            "solver": read_file_safe(os.path.join(p, "solver.py"))[:3000],
            "dead_ends": read_file_safe(os.path.join(p, "dead-ends.md"))[:2000],
            "opinions": read_file_safe(os.path.join(p, "opinions.md"))[:1000],
            "hunches": read_file_safe(os.path.join(p, "hunches.md"))[:500],
            "hunches_enabled": config.get("hunches_enabled", False),
        })

    return result


def build_api_response(workspace_root, selected_run=None):
    """Build API response. selected_run picks which run gets detailed data."""
    workspaces = discover_runs(workspace_root)
    runs_summary = []
    selected_data = None

    for ws in workspaces:
        is_selected = (selected_run is not None and ws["run_id"] == selected_run)
        run = read_run_data(ws, detailed=is_selected)
        runs_summary.append(run)
        if is_selected:
            selected_data = run

    if selected_data is None and workspaces:
        active = [ws for ws in workspaces
                  if read_json_safe(os.path.join(ws["path"], "status.json")).get("phase", "")
                  not in ("RESERVOIR_EXHAUSTED", "CYCLE_CAP", "PENDING", "")]
        target = active[-1] if active else workspaces[-1]
        selected_data = read_run_data(target, detailed=True)
        for rs in runs_summary:
            if rs["run_id"] == target["run_id"]:
                rs.update(selected_data)

    return {
        "runs": runs_summary,
        "selected": selected_data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>V4.5.1 Apparatus — Deep Telemetry</title>
<style>
:root {
  --bg: #030405;
  --panel: rgba(8, 11, 12, 0.94);
  --panel-2: rgba(11, 16, 17, 0.92);
  --grid: rgba(124, 255, 191, 0.08);
  --line: rgba(125, 255, 210, 0.2);
  --lime: #7cffbf;
  --amber: #ffb347;
  --cyan: #86e7ff;
  --red: #ff655e;
  --acid: #c9ff62;
  --purple: #b47cff;
  --gray: #6b7b73;
  --text: #eef9f1;
  --muted: #7b9388;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  min-height: 100vh;
  padding: 16px;
  color: var(--text);
  font-family: "Bank Gothic", "Eurostile", "OCR A Extended", "Share Tech Mono", monospace;
  background:
    radial-gradient(circle at top right, rgba(180,124,255,0.08), transparent 18%),
    radial-gradient(circle at 14% 0%, rgba(201,255,98,0.08), transparent 24%),
    linear-gradient(transparent 35px, var(--grid) 36px),
    linear-gradient(90deg, transparent 35px, var(--grid) 36px),
    linear-gradient(180deg, #050708 0%, #090c0d 34%, #030405 100%);
  background-size: auto, auto, 36px 36px, 36px 36px, auto;
  overflow-x: hidden;
}
body::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.04) 2px, rgba(0,0,0,0.04) 4px);
  z-index: 9999;
}

/* Header */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  margin-bottom: 14px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
}
.header h1 {
  font-size: 17px;
  letter-spacing: 3px;
  text-transform: uppercase;
  color: var(--acid);
}
.header h1 span { color: var(--muted); font-size: 11px; letter-spacing: 1px; }
.header-stats {
  display: flex;
  gap: 20px;
  font-size: 11px;
  color: var(--muted);
}
.header-stats .val { color: var(--text); font-size: 13px; }
.conn-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--lime);
  display: inline-block;
  margin-right: 5px;
  animation: pulse 2s infinite;
}
.conn-dot.dead { background: var(--red); animation: none; }
@keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.4; } }

/* Layout */
.layout {
  display: flex;
  gap: 14px;
}
.sidebar {
  width: 200px;
  flex-shrink: 0;
}
.main-content {
  flex: 1;
  min-width: 0;
}

/* Sidebar */
.sidebar-panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  overflow: hidden;
}
.sidebar-header {
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
  font-size: 11px;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--acid);
}
.sidebar-runs { padding: 6px; }
.srun {
  background: var(--panel-2);
  border: 1px solid rgba(125,255,210,0.1);
  border-radius: 4px;
  padding: 8px 10px;
  margin-bottom: 5px;
  cursor: pointer;
  transition: border-color 0.2s;
}
.srun:hover { border-color: rgba(125,255,210,0.3); }
.srun.selected { border-left: 3px solid var(--lime); background: rgba(124,255,191,0.06); }
.srun.complete { border-left: 3px solid var(--cyan); }
.srun.pending { opacity: 0.5; }
.srun-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 3px;
}
.srun-label { font-size: 11px; letter-spacing: 1px; }
.phase-badge {
  font-size: 8px;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(125,255,210,0.1);
  color: var(--lime);
  letter-spacing: 0.5px;
}
.phase-badge.complete { background: rgba(134,231,255,0.15); color: var(--cyan); }
.phase-badge.pending { background: rgba(123,147,136,0.15); color: var(--muted); }
.srun-metrics {
  display: flex;
  gap: 8px;
  font-size: 9px;
  color: var(--muted);
}
.srun-metrics .val { color: var(--text); }
.res-gauge {
  height: 3px;
  background: rgba(255,255,255,0.06);
  border-radius: 2px;
  overflow: hidden;
  margin-top: 4px;
}
.res-gauge-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.5s;
}

/* Gate strip */
.gate-strip-panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px 14px;
  margin-bottom: 14px;
}
.gate-strip-label {
  font-size: 9px;
  color: var(--muted);
  letter-spacing: 1.5px;
  text-transform: uppercase;
  margin-bottom: 6px;
}
.gate-strip {
  display: flex;
  gap: 2px;
  flex-wrap: wrap;
  align-items: center;
}
.gate-tick {
  width: 4px;
  height: 14px;
  border-radius: 1px;
}
.gate-legend {
  display: flex;
  gap: 12px;
  margin-top: 6px;
  font-size: 8px;
  color: var(--muted);
}
.leg-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  display: inline-block;
  margin-right: 3px;
  vertical-align: middle;
}

/* Chart rows */
.chart-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 14px;
  margin-bottom: 14px;
}
.chart-panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px 12px;
}
.chart-title {
  font-size: 9px;
  color: var(--muted);
  letter-spacing: 1.5px;
  text-transform: uppercase;
  margin-bottom: 6px;
}
.chart-value {
  font-size: 18px;
  color: var(--text);
  margin-bottom: 4px;
}
.chart-value small { font-size: 10px; color: var(--muted); }
.chart-legend {
  display: flex;
  gap: 10px;
  margin-top: 4px;
  font-size: 8px;
  color: var(--muted);
}

/* Log table */
.log-panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 12px 14px;
  margin-bottom: 14px;
  overflow-x: auto;
}
.log-panel h3 {
  font-size: 10px;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--acid);
  margin-bottom: 8px;
}
.log-table {
  width: 100%;
  font-size: 10px;
  border-collapse: collapse;
  white-space: nowrap;
}
.log-table th {
  text-align: left;
  color: var(--muted);
  padding: 3px 6px;
  border-bottom: 1px solid var(--line);
  font-size: 8px;
  letter-spacing: 1px;
}
.log-table td {
  padding: 3px 6px;
  border-bottom: 1px solid rgba(125,255,210,0.04);
}
.log-table .accepted { color: var(--lime); }
.log-table .rejected { color: var(--red); }
.log-table .quarantined { color: var(--amber); }
.log-table .qresolved { color: var(--purple); }
.log-table .qfailed { color: var(--purple); opacity: 0.6; }
.log-table .ffatal { color: var(--gray); }

/* Artifact panels */
.artifacts {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 14px;
  margin-bottom: 14px;
}
.artifact-panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
}
.artifact-title {
  padding: 8px 12px;
  font-size: 10px;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--acid);
}
.artifact-pre {
  font-size: 10px;
  line-height: 1.4;
  background: rgba(0,0,0,0.3);
  padding: 8px;
  margin: 0 8px 8px 8px;
  border-radius: 3px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 250px;
  overflow-y: auto;
  color: var(--muted);
}

/* Empty state */
.empty-state {
  text-align: center;
  color: var(--muted);
  font-size: 12px;
  padding: 40px 20px;
  letter-spacing: 1px;
}

/* Responsive */
@media (max-width: 900px) {
  .layout { flex-direction: column; }
  .sidebar { width: 100%; }
  .sidebar-runs { display: flex; gap: 6px; overflow-x: auto; }
  .srun { min-width: 160px; }
}
@media (max-width: 700px) {
  .chart-row { grid-template-columns: 1fr; }
  .artifacts { grid-template-columns: 1fr; }
}
</style>
</head>
<body>

<div class="header">
  <h1>V4.5.1 APPARATUS <span>Deep Telemetry</span></h1>
  <div class="header-stats">
    <div><span class="conn-dot" id="connDot"></span><span id="connLabel">CONNECTING</span></div>
    <div>CYCLE <span class="val" id="hdrCycle">0</span></div>
    <div>RESERVOIR <span class="val" id="hdrRes">0%</span></div>
    <div>PHASE <span class="val" id="hdrPhase">—</span></div>
  </div>
</div>

<div class="layout">
  <div class="sidebar">
    <div class="sidebar-panel">
      <div class="sidebar-header">RUNS</div>
      <div class="sidebar-runs" id="sidebarRuns">
        <div class="empty-state">No runs</div>
      </div>
    </div>
  </div>

  <div class="main-content" id="mainContent">
    <div class="empty-state">Select a run or waiting for data...</div>
  </div>
</div>

<script>
const POLL_MS = 2000;
const GATE_COLORS = {
  'accepted': '#7cffbf',
  'SURVIVED': '#7cffbf',
  'rejected': '#ff655e',
  'quarantined': '#ffb347',
  'quarantine_resolved': '#b47cff',
  'quarantine_failed': '#b47cff',
  'format_fatal': '#6b7b73',
};
const GATE_OPACITY = { 'quarantine_failed': '0.5' };

let failCount = 0;
let selectedRun = null;
let lastData = null;

// --- SVG chart helpers ---

function renderLineChart(points, color, opts = {}) {
  const w = opts.width || 320;
  const h = opts.height || 70;
  const px = opts.padX || 14;
  const py = opts.padY || 8;
  if (!Array.isArray(points) || points.length < 2)
    return '<span style="color:var(--muted);font-size:10px">Awaiting data...</span>';
  const min = typeof opts.min === 'number' ? opts.min : Math.min(...points);
  const max = typeof opts.max === 'number' ? opts.max : Math.max(...points);
  const span = max - min || 1;
  const step = (w - px * 2) / (points.length - 1);
  const coords = points.map((v, i) => {
    const x = px + step * i;
    const y = h - py - ((v - min) / span) * (h - py * 2);
    return [x, y];
  });
  const polyline = coords.map(c => c.join(',')).join(' ');
  let extras = '';
  if (typeof opts.threshold === 'number') {
    const ty = h - py - ((opts.threshold - min) / span) * (h - py * 2);
    const clamped = Math.max(py, Math.min(h - py, ty));
    extras += `<line x1="${px}" y1="${clamped}" x2="${w - px}" y2="${clamped}" stroke="#ff655e" stroke-width="1" stroke-dasharray="4,3" opacity="0.6" />`;
  }
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    <rect width="${w}" height="${h}" fill="none" />
    ${extras}
    <polyline points="${polyline}" fill="none" stroke="${color}" stroke-width="1.5" opacity="0.8" />
    ${coords.map(([x, y]) => `<circle cx="${x}" cy="${y}" r="1.5" fill="${color}" />`).join('')}
  </svg>`;
}

function renderMultiLineChart(seriesArr, colors, opts = {}) {
  const w = opts.width || 320;
  const h = opts.height || 70;
  const px = opts.padX || 14;
  const py = opts.padY || 8;
  const allPts = seriesArr.flat();
  if (allPts.length === 0)
    return '<span style="color:var(--muted);font-size:10px">Awaiting data...</span>';
  const min = typeof opts.min === 'number' ? opts.min : Math.min(...allPts);
  const max = typeof opts.max === 'number' ? opts.max : Math.max(...allPts);
  const span = max - min || 1;
  let lines = '';
  seriesArr.forEach((pts, si) => {
    if (!pts || pts.length < 2) return;
    const step = (w - px * 2) / (pts.length - 1);
    const coords = pts.map((v, i) => {
      const x = px + step * i;
      const y = h - py - ((v - min) / span) * (h - py * 2);
      return `${x},${y}`;
    }).join(' ');
    lines += `<polyline points="${coords}" fill="none" stroke="${colors[si]}" stroke-width="1.5" opacity="0.7" />`;
  });
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${lines}</svg>`;
}

function renderGateStrip(decisions) {
  if (!decisions || !decisions.length) return '';
  return decisions.map(d => {
    const color = GATE_COLORS[d] || '#6b7b73';
    const opacity = GATE_OPACITY[d] || '1';
    return `<span class="gate-tick" style="background:${color};opacity:${opacity}" title="${d}"></span>`;
  }).join('');
}

function renderGauge(current, max, color) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (current / max) * 100)) : 0;
  const c = pct > 50 ? color : pct > 20 ? 'var(--amber)' : 'var(--red)';
  return `<div class="res-gauge"><div class="res-gauge-fill" style="width:${pct}%;background:${c}"></div></div>`;
}

function fmtNum(n) {
  if (typeof n !== 'number') return '—';
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return n.toFixed(1);
}

function escHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function gateClass(d) {
  if (d === 'accepted' || d === 'SURVIVED') return 'accepted';
  if (d === 'rejected') return 'rejected';
  if (d === 'quarantined') return 'quarantined';
  if (d === 'quarantine_resolved') return 'qresolved';
  if (d === 'quarantine_failed') return 'qfailed';
  if (d === 'format_fatal') return 'ffatal';
  return '';
}

// --- Render functions ---

function renderSidebar(runs) {
  if (!runs || !runs.length) return '<div class="empty-state">No runs discovered</div>';
  return runs.map(r => {
    let cls = '';
    if (selectedRun === r.run_id || (selectedRun === null && r.is_active)) cls = 'selected';
    else if (r.is_complete) cls = 'complete';
    else if (r.phase === 'PENDING') cls = 'pending';

    const pCls = r.is_complete ? 'complete' : r.phase === 'PENDING' ? 'pending' : '';
    const shortPhase = (r.phase || 'PENDING').replace('GATED_', '').replace('CALIBRATION_', 'CAL:');
    const rejRate = r.total_gated > 0 ? ((r.total_rejected / r.total_gated) * 100).toFixed(0) : '—';

    return `
      <div class="srun ${cls}" onclick="selectRun(${r.run_id})">
        <div class="srun-top">
          <span class="srun-label">RUN ${r.run_id}${r.hunches_enabled ? ' <span style="color:var(--purple);font-size:8px">H</span>' : ''}</span>
          <span class="phase-badge ${pCls}">${shortPhase}</span>
        </div>
        <div class="srun-metrics">
          <div>Cyc <span class="val">${r.cycle}</span></div>
          <div>Rej <span class="val">${rejRate}%</span></div>
        </div>
        ${renderGauge(r.reservoir, r.max_reservoir, 'var(--lime)')}
      </div>`;
  }).join('');
}

function renderMainContent(run) {
  if (!run) return '<div class="empty-state">Select a run from the sidebar</div>';

  const threshold = run.threshold || 0;

  // Gate strip
  let html = `
    <div class="gate-strip-panel">
      <div class="gate-strip-label">GATE HISTORY</div>
      <div class="gate-strip">${renderGateStrip(run.gate_decisions)}</div>
      <div class="gate-legend">
        <span><span class="leg-dot" style="background:#7cffbf"></span>Accepted</span>
        <span><span class="leg-dot" style="background:#ff655e"></span>Rejected</span>
        <span><span class="leg-dot" style="background:#ffb347"></span>Quarantined</span>
        <span><span class="leg-dot" style="background:#b47cff"></span>Q Resolved/Failed</span>
        <span><span class="leg-dot" style="background:#6b7b73"></span>Format Fatal</span>
      </div>
    </div>`;

  // Row 1: Core metrics
  html += `
    <div class="chart-row">
      <div class="chart-panel">
        <div class="chart-title">E_RATIO</div>
        <div class="chart-value">${fmtNum(run.latest_e_ratio)} <small>threshold: ${fmtNum(threshold)}</small></div>
        ${renderLineChart(run.e_ratio_series || [], '#7cffbf', {threshold: threshold})}
      </div>
      <div class="chart-panel">
        <div class="chart-title">ORACLE SCORE</div>
        <div class="chart-value">${((run.latest_oracle || 0) * 100).toFixed(0)}%</div>
        ${renderLineChart(run.oracle_series || [], '#86e7ff', {min: 0, max: 1})}
      </div>
      <div class="chart-panel">
        <div class="chart-title">RESERVOIR BURNDOWN</div>
        <div class="chart-value">${fmtNum(run.reservoir)} <small>/ ${fmtNum(run.max_reservoir)}</small></div>
        ${renderLineChart(run.reservoir_series || [], '#ffb347', {min: 0})}
      </div>
    </div>`;

  // Row 2: Complexity decomposition
  html += `
    <div class="chart-row">
      <div class="chart-panel">
        <div class="chart-title">TOPOLOGICAL ACTION (dC)</div>
        ${renderLineChart(run.delta_c_series || [], '#c9ff62')}
      </div>
      <div class="chart-panel">
        <div class="chart-title">EPISTEMIC FLUX</div>
        ${renderLineChart(run.flux_series || [], '#86e7ff')}
      </div>
      <div class="chart-panel">
        <div class="chart-title">AST COMPLEXITY</div>
        ${renderMultiLineChart([run.ast_branch_series || [], run.ast_alg_series || []], ['#7cffbf', '#ffb347'])}
        <div class="chart-legend">
          <span><span class="leg-dot" style="background:#7cffbf"></span>Branch Depth</span>
          <span><span class="leg-dot" style="background:#ffb347"></span>Algebraic Nodes</span>
        </div>
      </div>
    </div>`;

  // Row 3: V4.5.1 machinery
  html += `
    <div class="chart-row">
      <div class="chart-panel">
        <div class="chart-title">THEORY LIFECYCLE</div>
        ${renderMultiLineChart([run.active_theories_series || [], run.archived_theories_series || []], ['#7cffbf', '#86e7ff'])}
        <div class="chart-legend">
          <span><span class="leg-dot" style="background:#7cffbf"></span>Active</span>
          <span><span class="leg-dot" style="background:#86e7ff"></span>Archived</span>
        </div>
      </div>
      <div class="chart-panel">
        <div class="chart-title">TOKEN ALLOCATION</div>
        ${renderMultiLineChart(
          [run.theory_tokens_series || [], run.solver_tokens_series || [], run.prompt_context_series || []],
          ['#7cffbf', '#ffb347', '#86e7ff']
        )}
        <div class="chart-legend">
          <span><span class="leg-dot" style="background:#7cffbf"></span>Theory</span>
          <span><span class="leg-dot" style="background:#ffb347"></span>Solver</span>
          <span><span class="leg-dot" style="background:#86e7ff"></span>Prompt</span>
        </div>
      </div>
      <div class="chart-panel">
        <div class="chart-title">MECHANICAL HEALTH</div>
        ${renderLineChart(run.format_retries_series || [], '#ff655e')}
        <div class="chart-legend">
          <span><span class="leg-dot" style="background:#ff655e"></span>Format Retries</span>
          <span style="margin-left:auto">
            Q: ${run.total_quarantined || 0} |
            QR: ${run.total_quarantine_resolved || 0} |
            QF: ${run.total_quarantine_failed || 0} |
            FF: ${run.total_format_fatals || 0}
          </span>
        </div>
      </div>
    </div>`;

  // Cycle log table
  const logTail = run.log_tail || [];
  if (logTail.length > 0) {
    let rows = logTail.map(r => {
      const gc = gateClass(r.gate_decision || '');
      const oracleStr = typeof r.oracle_passed === 'number' && typeof r.oracle_total === 'number'
        ? `${r.oracle_passed}/${r.oracle_total}`
        : `${((r.oracle_score || 0) * 100).toFixed(0)}%`;
      return `<tr>
        <td>${r.cycle || ''}</td>
        <td class="${gc}">${(r.gate_decision || '').toUpperCase()}</td>
        <td>${fmtNum(r.e_ratio)}</td>
        <td>${fmtNum(r.delta_c)}</td>
        <td>${fmtNum(r.flux)}</td>
        <td>${oracleStr}</td>
        <td>${r.ast_branching_depth || 0}</td>
        <td>${r.ast_algebraic_nodes || 0}</td>
        <td>${fmtNum(r.tokens_consumed_this_cycle)}</td>
        <td>${fmtNum(r.reservoir_remaining)}</td>
        <td>${r.format_retries || 0}</td>
        <td>${r.quarantine_active ? 'Y' : ''}</td>
      </tr>`;
    }).join('');

    html += `
      <div class="log-panel">
        <h3>CYCLE LOG (LAST ${logTail.length})</h3>
        <table class="log-table">
          <tr>
            <th>CYC</th><th>GATE</th><th>E_RATIO</th><th>dC</th><th>FLUX</th>
            <th>ORACLE</th><th>AST_BD</th><th>AST_ALG</th><th>TOKENS</th>
            <th>RESERVOIR</th><th>FMT_R</th><th>Q</th>
          </tr>
          ${rows}
        </table>
      </div>`;
  }

  // Artifact panels
  html += `
    <div class="artifacts">
      <div class="artifact-panel">
        <div class="artifact-title">SOLVER</div>
        <pre class="artifact-pre">${escHtml(run.solver || 'No solver data')}</pre>
      </div>
      <div class="artifact-panel">
        <div class="artifact-title">DEAD ENDS</div>
        <pre class="artifact-pre">${escHtml(run.dead_ends || 'No dead-end data')}</pre>
      </div>
      <div class="artifact-panel">
        <div class="artifact-title">OPINIONS</div>
        <pre class="artifact-pre">${escHtml(run.opinions || 'No opinion data')}</pre>
      </div>
      ${run.hunches_enabled ? `<div class="artifact-panel" style="border-top:2px solid var(--purple)">
        <div class="artifact-title" style="color:var(--purple)">HUNCHES <span style="font-size:7px;color:var(--muted);letter-spacing:0">(subliminal ledger)</span></div>
        <pre class="artifact-pre">${escHtml(run.hunches || '(empty)')}</pre>
      </div>` : ''}
    </div>`;

  return html;
}

// --- Run selection ---

function selectRun(runId) {
  selectedRun = runId;
  poll();
}

// --- Polling ---

function update(data) {
  lastData = data;
  const sel = data.selected;

  // Header
  if (sel) {
    document.getElementById('hdrCycle').textContent = sel.cycle || 0;
    document.getElementById('hdrRes').textContent = (sel.reservoir_pct || 0) + '%';
    const ph = (sel.phase || 'PENDING').replace('GATED_', '');
    document.getElementById('hdrPhase').textContent = ph;
    if (selectedRun === null) selectedRun = sel.run_id;
  }

  // Sidebar
  document.getElementById('sidebarRuns').innerHTML = renderSidebar(data.runs || []);

  // Main content
  document.getElementById('mainContent').innerHTML = renderMainContent(sel);
}

function poll() {
  const url = selectedRun !== null ? `api/status?run=${selectedRun}` : 'api/status';
  fetch(url)
    .then(r => r.json())
    .then(data => {
      failCount = 0;
      document.getElementById('connDot').classList.remove('dead');
      document.getElementById('connLabel').textContent = 'LIVE';
      update(data);
    })
    .catch(() => {
      failCount++;
      if (failCount >= 3) {
        document.getElementById('connDot').classList.add('dead');
        document.getElementById('connLabel').textContent = 'DISCONNECTED';
      }
    })
    .finally(() => setTimeout(poll, POLL_MS));
}

poll();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class ApparatusHandler(BaseHTTPRequestHandler):
    workspace_root = "."

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/status":
            params = parse_qs(parsed.query)
            run_id = None
            if "run" in params:
                try:
                    run_id = int(params["run"][0])
                except (ValueError, IndexError):
                    pass
            self.send_json(build_api_response(self.workspace_root, run_id))
        elif path in ("", "/", "/index.html"):
            self.send_html(HTML_PAGE)
        else:
            self.send_error(404)

    def send_json(self, data):
        body = json.dumps(data, default=str).encode("utf-8")
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
        pass


def main():
    args = sys.argv[1:]
    port = DEFAULT_PORT

    if "--port" in args:
        idx = args.index("--port")
        port = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]

    if not args:
        print("Usage: python3 dashboard_v451.py <workspace_root> [--port 8101]")
        print("Example: python3 dashboard_v451.py runs/assay-v451 --port 8101")
        sys.exit(1)

    workspace_root = os.path.abspath(args[0])
    if not os.path.isdir(workspace_root):
        print(f"Error: {workspace_root} is not a directory")
        sys.exit(1)

    ApparatusHandler.workspace_root = workspace_root
    server = HTTPServer(("127.0.0.1", port), ApparatusHandler)
    print(f"  V4.5.1 Apparatus Dashboard on http://127.0.0.1:{port}")
    print(f"  Watching: {workspace_root}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
