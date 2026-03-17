#!/usr/bin/env python3
"""
The Assayer Dashboard — V4.5 Three-Branch Actuator Experiment viewer.

Aggregates all branch-X-run-N workspaces and serves a live comparison dashboard.
Zero external dependencies — stdlib only.

Usage: python3 dashboard_assay.py <workspace_root> [--port 8100]
Example: python3 dashboard_assay.py runs/assay --port 8100
"""
import json
import os
import statistics
import sys
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_PORT = 8100

BRANCH_LABELS = {
    "A": "Informed Gate / Sterile",
    "B": "Informed Gate / Dramatic",
    "C": "Random Gate / Null Control",
}


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
# Workspace discovery and data aggregation
# ---------------------------------------------------------------------------

def discover_workspaces(root):
    """Find all branch-X-run-N directories."""
    workspaces = []
    root_path = Path(root)
    if not root_path.exists():
        return workspaces
    for entry in sorted(root_path.iterdir()):
        if entry.is_dir() and entry.name.startswith("branch-"):
            parts = entry.name.split("-")
            if len(parts) >= 4:
                branch = parts[1]
                try:
                    run_id = int(parts[3])
                except (ValueError, IndexError):
                    continue
                workspaces.append({
                    "path": str(entry),
                    "branch": branch,
                    "run_id": run_id,
                    "name": entry.name,
                })
    return workspaces


def read_run_data(ws):
    """Read all data for a single run workspace."""
    p = ws["path"]
    config = read_json_safe(os.path.join(p, "assay_config.json"))
    status = read_json_safe(os.path.join(p, "status.json"))
    log = read_jsonl_safe(os.path.join(p, "assay_log.jsonl"))
    rejections = read_jsonl_safe(os.path.join(p, "assay_rejections.jsonl"))
    opinions = read_file_safe(os.path.join(p, "opinions.md"))
    solver = read_file_safe(os.path.join(p, "solver.py"))
    dead_ends = read_file_safe(os.path.join(p, "dead-ends.md"))

    gated = [r for r in log if r.get("phase") == "gated"]
    calibration = [r for r in log if r.get("phase") == "calibration"]

    accepted = sum(1 for r in gated if r.get("gate_decision") == "accepted")
    rejected = sum(1 for r in gated if r.get("gate_decision") == "rejected")
    format_fails = sum(1 for r in gated if r.get("gate_decision") == "format_fail")

    e_ratio_series = [r.get("e_ratio", 0) for r in gated if "e_ratio" in r]
    oracle_series = [r.get("oracle_score", 0) for r in gated if "oracle_score" in r]
    gate_series = [1 if r.get("gate_decision") == "rejected" else 0 for r in gated
                   if r.get("gate_decision") in ("accepted", "rejected")]
    reservoir_series = [r.get("reservoir", 0) for r in gated if "reservoir" in r]
    delta_c_series = [r.get("delta_c", 0) for r in gated if "delta_c" in r]
    flux_series = [r.get("flux", 0) for r in gated if "flux" in r]

    phase = status.get("phase", "PENDING")
    cycle = status.get("cycle", 0)
    reservoir = gated[-1].get("reservoir", 0) if gated else config.get("token_reservoir", 0)
    max_reservoir = config.get("token_reservoir", 1)

    is_complete = phase in ("RESERVOIR_EXHAUSTED", "CYCLE_CAP")
    is_active = bool(status) and not is_complete and phase != "PENDING"

    return {
        "run_id": ws["run_id"],
        "branch": ws["branch"],
        "name": ws["name"],
        "config": config,
        "phase": phase,
        "cycle": cycle,
        "reservoir": reservoir,
        "max_reservoir": max_reservoir,
        "total_accepted": accepted,
        "total_rejected": rejected,
        "total_format_fails": format_fails,
        "total_gated": len(gated),
        "total_calibration": len(calibration),
        "is_complete": is_complete,
        "is_active": is_active,
        "latest_e_ratio": e_ratio_series[-1] if e_ratio_series else 0,
        "latest_oracle_score": oracle_series[-1] if oracle_series else 0,
        "threshold": config.get("e_ratio_threshold", 0),
        "e_ratio_series": e_ratio_series[-100:],
        "oracle_series": oracle_series[-100:],
        "gate_series": gate_series[-100:],
        "reservoir_series": reservoir_series[-100:],
        "delta_c_series": delta_c_series[-100:],
        "flux_series": flux_series[-100:],
        "log": log[-30:],
        "rejection_count": len(rejections),
        "opinions": opinions[:500],
        "solver": solver[:2000],
        "dead_ends": dead_ends[:1000],
    }


def build_api_response(workspace_root):
    """Build the full API response aggregating all runs."""
    workspaces = discover_workspaces(workspace_root)
    branches = {}

    for branch_key in ("A", "B", "C"):
        branch_ws = [ws for ws in workspaces if ws["branch"] == branch_key]
        runs = [read_run_data(ws) for ws in branch_ws]
        runs.sort(key=lambda r: r["run_id"])

        complete = sum(1 for r in runs if r["is_complete"])
        active = sum(1 for r in runs if r["is_active"])
        e_ratios = [r["latest_e_ratio"] for r in runs if r["total_gated"] > 0]
        rejection_rates = [
            r["total_rejected"] / max(r["total_gated"], 1)
            for r in runs if r["total_gated"] > 0
        ]
        total_tokens = sum(
            r["config"].get("token_reservoir", 0) - r["reservoir"]
            for r in runs
        )

        branches[branch_key] = {
            "label": BRANCH_LABELS.get(branch_key, ""),
            "runs": runs,
            "aggregate": {
                "runs_complete": complete,
                "runs_active": active,
                "runs_total": len(runs),
                "mean_rejection_rate": round(statistics.mean(rejection_rates), 4) if rejection_rates else 0,
                "mean_e_ratio": round(statistics.mean(e_ratios), 2) if e_ratios else 0,
                "total_tokens_consumed": total_tokens,
            },
        }

    total_complete = sum(b["aggregate"]["runs_complete"] for b in branches.values())
    total_runs = sum(b["aggregate"]["runs_total"] for b in branches.values())
    total_tokens = sum(b["aggregate"]["total_tokens_consumed"] for b in branches.values())

    return {
        "branches": branches,
        "total_complete": total_complete,
        "total_runs": total_runs,
        "total_tokens": total_tokens,
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
<title>The Assayer — V4.5</title>
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
  --text: #eef9f1;
  --muted: #7b9388;
  --shadow: 0 26px 70px rgba(0, 0, 0, 0.42);
  --branch-a: #7cffbf;
  --branch-b: #ffb347;
  --branch-c: #86e7ff;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  min-height: 100vh;
  padding: 16px;
  color: var(--text);
  font-family: "Bank Gothic", "Eurostile", "OCR A Extended", "Share Tech Mono", monospace;
  background:
    radial-gradient(circle at top right, rgba(255,101,94,0.10), transparent 18%),
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
  margin-bottom: 16px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
}
.header h1 {
  font-size: 18px;
  letter-spacing: 3px;
  text-transform: uppercase;
  color: var(--acid);
}
.header h1 span { color: var(--muted); font-size: 12px; letter-spacing: 1px; }
.header-stats {
  display: flex;
  gap: 24px;
  font-size: 12px;
  color: var(--muted);
}
.header-stats .val { color: var(--text); font-size: 14px; }
.conn-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--lime);
  display: inline-block;
  margin-right: 6px;
  animation: pulse 2s infinite;
}
.conn-dot.dead { background: var(--red); animation: none; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

/* Branch columns */
.branch-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 14px;
  margin-bottom: 16px;
}
.branch-col {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  overflow: hidden;
}
.branch-header {
  padding: 10px 14px;
  border-bottom: 1px solid var(--line);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.branch-header h2 {
  font-size: 13px;
  letter-spacing: 2px;
  text-transform: uppercase;
}
.branch-header .branch-label {
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.5px;
}
.branch-header .agg-stats {
  font-size: 10px;
  color: var(--muted);
  text-align: right;
}
.branch-header .agg-stats .val { color: var(--text); }
.branch-a .branch-header { border-top: 2px solid var(--branch-a); }
.branch-b .branch-header { border-top: 2px solid var(--branch-b); }
.branch-c .branch-header { border-top: 2px solid var(--branch-c); }

/* Run cards */
.run-cards { padding: 8px; }
.run-card {
  background: var(--panel-2);
  border: 1px solid rgba(125, 255, 210, 0.1);
  border-radius: 4px;
  padding: 8px 10px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: border-color 0.2s;
}
.run-card:hover { border-color: rgba(125, 255, 210, 0.3); }
.run-card.active { border-left: 3px solid var(--lime); }
.run-card.calibrating { border-left: 3px solid var(--amber); }
.run-card.complete { border-left: 3px solid var(--cyan); }
.run-card.pending { border-left: 3px solid var(--muted); opacity: 0.5; }
.run-card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.run-card-top .run-label { font-size: 11px; letter-spacing: 1px; }
.run-card-top .phase-badge {
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(125, 255, 210, 0.1);
  color: var(--lime);
  letter-spacing: 0.5px;
}
.phase-badge.rejected { background: rgba(255, 101, 94, 0.15); color: var(--red); }
.phase-badge.calibrating { background: rgba(255, 179, 71, 0.15); color: var(--amber); }
.phase-badge.complete { background: rgba(134, 231, 255, 0.15); color: var(--cyan); }
.phase-badge.pending { background: rgba(123, 147, 136, 0.15); color: var(--muted); }
.run-card-metrics {
  display: flex;
  gap: 12px;
  font-size: 10px;
  color: var(--muted);
  margin-bottom: 4px;
}
.run-card-metrics .val { color: var(--text); }

/* Reservoir gauge */
.reservoir-gauge {
  height: 4px;
  background: rgba(255,255,255,0.06);
  border-radius: 2px;
  overflow: hidden;
  margin-top: 4px;
}
.reservoir-gauge-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.5s;
}

/* Gate ticks */
.gate-ticks {
  display: flex;
  gap: 1px;
  margin-top: 4px;
  height: 6px;
  align-items: center;
}
.gate-tick {
  width: 3px;
  height: 6px;
  border-radius: 1px;
}

/* Expanded detail */
.run-detail {
  display: none;
  padding: 8px 0 4px 0;
  border-top: 1px solid rgba(125, 255, 210, 0.08);
  margin-top: 6px;
}
.run-detail.open { display: block; }
.run-detail .chart-area { margin-bottom: 6px; }
.chart-label { font-size: 9px; color: var(--muted); letter-spacing: 1px; margin-bottom: 2px; }

/* Comparison section */
.comparison {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 14px;
  margin-bottom: 16px;
}
.comparison h3 {
  font-size: 12px;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--acid);
  margin-bottom: 12px;
}
.comparison-charts {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 14px;
}
.comp-chart {
  background: var(--panel-2);
  border: 1px solid rgba(125, 255, 210, 0.08);
  border-radius: 4px;
  padding: 10px;
}
.comp-chart h4 {
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 1px;
  margin-bottom: 8px;
}
.comp-legend {
  display: flex;
  gap: 12px;
  font-size: 9px;
  color: var(--muted);
  margin-top: 6px;
}
.comp-legend .leg-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  display: inline-block;
  margin-right: 3px;
  vertical-align: middle;
}

/* Detail drawer */
.drawer-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  z-index: 100;
}
.drawer-overlay.open { display: block; }
.drawer {
  position: fixed;
  top: 0;
  right: -520px;
  width: 500px;
  height: 100vh;
  background: var(--panel);
  border-left: 1px solid var(--line);
  z-index: 101;
  overflow-y: auto;
  padding: 16px;
  transition: right 0.3s;
}
.drawer.open { right: 0; }
.drawer h3 {
  font-size: 14px;
  letter-spacing: 2px;
  color: var(--acid);
  margin-bottom: 12px;
}
.drawer .close-btn {
  position: absolute;
  top: 12px;
  right: 14px;
  background: none;
  border: 1px solid var(--line);
  color: var(--muted);
  font-size: 14px;
  padding: 4px 10px;
  cursor: pointer;
  border-radius: 3px;
}
.drawer .close-btn:hover { color: var(--text); border-color: var(--text); }
.drawer-section {
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(125, 255, 210, 0.08);
}
.drawer-section h4 {
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 1px;
  margin-bottom: 6px;
}
.drawer-table {
  width: 100%;
  font-size: 10px;
  border-collapse: collapse;
}
.drawer-table th {
  text-align: left;
  color: var(--muted);
  padding: 3px 6px;
  border-bottom: 1px solid var(--line);
}
.drawer-table td {
  padding: 3px 6px;
  border-bottom: 1px solid rgba(125, 255, 210, 0.04);
}
.drawer-table .rej { color: var(--red); }
.drawer-table .acc { color: var(--lime); }
.drawer-pre {
  font-size: 10px;
  line-height: 1.4;
  background: rgba(0,0,0,0.3);
  padding: 8px;
  border-radius: 3px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
  color: var(--muted);
}

/* Responsive */
@media (max-width: 1000px) {
  .branch-grid { grid-template-columns: 1fr; }
  .comparison-charts { grid-template-columns: 1fr; }
}
</style>
</head>
<body>

<div class="header">
  <h1>THE ASSAYER <span>V4.5 Actuator Experiment</span></h1>
  <div class="header-stats">
    <div><span class="conn-dot" id="connDot"></span><span id="connLabel">CONNECTING</span></div>
    <div>RUNS <span class="val" id="hdrRuns">0/0</span></div>
    <div>TOKENS <span class="val" id="hdrTokens">0</span></div>
  </div>
</div>

<div class="branch-grid" id="branchGrid"></div>

<div class="comparison" id="comparison">
  <h3>Cross-Branch Comparison</h3>
  <div class="comparison-charts" id="compCharts"></div>
</div>

<div class="drawer-overlay" id="drawerOverlay"></div>
<div class="drawer" id="drawer">
  <button class="close-btn" id="drawerClose">X</button>
  <div id="drawerContent"></div>
</div>

<script>
const POLL_MS = 2000;
const BRANCH_COLORS = { A: '#7cffbf', B: '#ffb347', C: '#86e7ff' };
const BRANCH_KEYS = ['A', 'B', 'C'];
let failCount = 0;
let lastData = null;

// --- SVG chart helpers ---

function renderLineChart(points, color, opts = {}) {
  const w = opts.width || 380;
  const h = opts.height || 70;
  const px = opts.padX || 16;
  const py = opts.padY || 8;
  if (!Array.isArray(points) || points.length < 2) return '';
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
  const w = opts.width || 380;
  const h = opts.height || 80;
  const px = opts.padX || 16;
  const py = opts.padY || 8;
  const allPts = seriesArr.flat();
  if (allPts.length === 0) return '<span style="color:var(--muted);font-size:10px">No data</span>';
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

function renderGateTicks(series, branchColor) {
  if (!series || series.length === 0) return '';
  return series.map(v =>
    `<span class="gate-tick" style="background:${v === 1 ? '#ff655e' : branchColor}"></span>`
  ).join('');
}

function renderGaugeBar(current, max, branchColor) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (current / max) * 100)) : 0;
  const color = pct > 50 ? branchColor : pct > 20 ? 'var(--amber)' : 'var(--red)';
  return `<div class="reservoir-gauge"><div class="reservoir-gauge-fill" style="width:${pct}%;background:${color}"></div></div>`;
}

function fmtNum(n) {
  if (typeof n !== 'number') return '—';
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return n.toFixed(1);
}

function phaseClass(phase) {
  if (!phase || phase === 'PENDING') return 'pending';
  if (phase.startsWith('CALIBRATION')) return 'calibrating';
  if (phase === 'RESERVOIR_EXHAUSTED' || phase === 'CYCLE_CAP') return 'complete';
  if (phase === 'GATED_REJECTED') return 'rejected';
  return '';
}

function cardStateClass(run) {
  if (!run.phase || run.phase === 'PENDING') return 'pending';
  if (run.phase.startsWith('CALIBRATION')) return 'calibrating';
  if (run.is_complete) return 'complete';
  return 'active';
}

// --- Render functions ---

function renderBranch(key, branch) {
  const bc = BRANCH_COLORS[key];
  const agg = branch.aggregate || {};
  const runs = branch.runs || [];
  const runsHtml = runs.map(r => renderRunCard(r, key, bc)).join('');

  return `
    <div class="branch-col branch-${key.toLowerCase()}">
      <div class="branch-header">
        <div>
          <h2 style="color:${bc}">BRANCH ${key}</h2>
          <div class="branch-label">${branch.label}</div>
        </div>
        <div class="agg-stats">
          <div>Rej rate <span class="val">${(agg.mean_rejection_rate * 100).toFixed(0)}%</span></div>
          <div>Runs <span class="val">${agg.runs_complete}/${agg.runs_total}</span></div>
        </div>
      </div>
      <div class="run-cards">${runsHtml}</div>
    </div>`;
}

function renderRunCard(run, branchKey, bc) {
  const stateClass = cardStateClass(run);
  const pClass = phaseClass(run.phase);
  const shortPhase = (run.phase || 'PENDING').replace('GATED_', '').replace('CALIBRATION_', 'CAL:');
  const rejRate = run.total_gated > 0 ? ((run.total_rejected / run.total_gated) * 100).toFixed(0) : '—';
  const gauge = renderGaugeBar(run.reservoir, run.max_reservoir, bc);
  const ticks = renderGateTicks(run.gate_series, bc);

  return `
    <div class="run-card ${stateClass}" data-branch="${branchKey}" data-run="${run.run_id}" onclick="toggleDetail(this)">
      <div class="run-card-top">
        <span class="run-label">RUN ${run.run_id}</span>
        <span class="phase-badge ${pClass}">${shortPhase}</span>
      </div>
      <div class="run-card-metrics">
        <div>Cycle <span class="val">${run.cycle}</span></div>
        <div>E_ratio <span class="val">${fmtNum(run.latest_e_ratio)}</span></div>
        <div>Oracle <span class="val">${(run.latest_oracle_score * 100).toFixed(0)}%</span></div>
        <div>Rej <span class="val">${rejRate}%</span></div>
      </div>
      ${gauge}
      <div class="gate-ticks">${ticks}</div>
      <div class="run-detail" id="detail-${branchKey}-${run.run_id}">
        <div class="chart-area">
          <div class="chart-label">E_RATIO (threshold: ${fmtNum(run.threshold)})</div>
          ${renderLineChart(run.e_ratio_series, bc, {threshold: run.threshold})}
        </div>
        <div class="chart-area">
          <div class="chart-label">ORACLE SCORE</div>
          ${renderLineChart(run.oracle_series, bc, {min: 0, max: 1})}
        </div>
      </div>
    </div>`;
}

function renderComparison(data) {
  const branches = data.branches || {};
  // Average E_ratio series per branch
  const eSeries = BRANCH_KEYS.map(k => {
    const runs = (branches[k] || {}).runs || [];
    const maxLen = Math.max(...runs.map(r => (r.e_ratio_series || []).length), 0);
    if (maxLen === 0) return [];
    const avg = [];
    for (let i = 0; i < maxLen; i++) {
      let sum = 0, count = 0;
      runs.forEach(r => {
        const s = r.e_ratio_series || [];
        if (i < s.length) { sum += s[i]; count++; }
      });
      avg.push(count > 0 ? sum / count : 0);
    }
    return avg;
  });

  // Average reservoir series per branch
  const rSeries = BRANCH_KEYS.map(k => {
    const runs = (branches[k] || {}).runs || [];
    const maxLen = Math.max(...runs.map(r => (r.reservoir_series || []).length), 0);
    if (maxLen === 0) return [];
    const avg = [];
    for (let i = 0; i < maxLen; i++) {
      let sum = 0, count = 0;
      runs.forEach(r => {
        const s = r.reservoir_series || [];
        if (i < s.length) { sum += s[i]; count++; }
      });
      avg.push(count > 0 ? sum / count : 0);
    }
    return avg;
  });

  // Aggregate gate series per branch (concatenated)
  const gSeries = BRANCH_KEYS.map(k => {
    const runs = (branches[k] || {}).runs || [];
    const all = [];
    runs.forEach(r => { (r.gate_series || []).forEach(v => all.push(v)); });
    return all;
  });

  const colors = BRANCH_KEYS.map(k => BRANCH_COLORS[k]);
  const legend = `<div class="comp-legend">
    <span><span class="leg-dot" style="background:${BRANCH_COLORS.A}"></span>A Sterile</span>
    <span><span class="leg-dot" style="background:${BRANCH_COLORS.B}"></span>B Dramatic</span>
    <span><span class="leg-dot" style="background:${BRANCH_COLORS.C}"></span>C Random</span>
  </div>`;

  return `
    <div class="comp-chart">
      <h4>E_RATIO (AVERAGED)</h4>
      ${renderMultiLineChart(eSeries, colors)}
      ${legend}
    </div>
    <div class="comp-chart">
      <h4>RESERVOIR BURNDOWN</h4>
      ${renderMultiLineChart(rSeries, colors, {min: 0})}
      ${legend}
    </div>
    <div class="comp-chart">
      <h4>GATE DECISIONS (ALL RUNS)</h4>
      ${BRANCH_KEYS.map((k, i) => {
        const ticks = renderGateTicks(gSeries[i], BRANCH_COLORS[k]);
        return `<div style="margin-bottom:4px"><span style="font-size:9px;color:var(--muted);margin-right:6px">${k}</span><span class="gate-ticks" style="display:inline-flex">${ticks}</span></div>`;
      }).join('')}
    </div>`;
}

// --- Drawer ---

function openDrawer(branchKey, runId) {
  const data = lastData;
  if (!data) return;
  const branch = (data.branches || {})[branchKey];
  if (!branch) return;
  const run = (branch.runs || []).find(r => r.run_id === runId);
  if (!run) return;

  const bc = BRANCH_COLORS[branchKey];
  const log = run.log || [];
  const gated = log.filter(r => r.phase === 'gated');

  let tableRows = gated.slice(-20).map(r => {
    const cls = r.gate_decision === 'rejected' ? 'rej' : 'acc';
    return `<tr>
      <td>${r.cycle || ''}</td>
      <td>${fmtNum(r.e_ratio)}</td>
      <td>${fmtNum(r.delta_c)}</td>
      <td>${fmtNum(r.flux)}</td>
      <td>${((r.oracle_score || 0) * 100).toFixed(0)}%</td>
      <td class="${cls}">${(r.gate_decision || '').toUpperCase()}</td>
    </tr>`;
  }).join('');

  document.getElementById('drawerContent').innerHTML = `
    <h3 style="color:${bc}">BRANCH ${branchKey} / RUN ${runId}</h3>
    <div class="drawer-section">
      <h4>CONFIG</h4>
      <div style="font-size:10px;color:var(--muted)">
        Model: ${run.config.model || '—'} | Seed: ${run.config.seed || '—'} |
        Threshold: ${fmtNum(run.threshold)} (${run.config.e_ratio_threshold_source || '?'}) |
        Reservoir: ${fmtNum(run.max_reservoir)} tokens
      </div>
    </div>
    <div class="drawer-section">
      <h4>E_RATIO</h4>
      ${renderLineChart(run.e_ratio_series, bc, {width: 460, height: 90, threshold: run.threshold})}
    </div>
    <div class="drawer-section">
      <h4>ORACLE SCORE</h4>
      ${renderLineChart(run.oracle_series, bc, {width: 460, height: 70, min: 0, max: 1})}
    </div>
    <div class="drawer-section">
      <h4>CYCLE LOG (LAST 20)</h4>
      <table class="drawer-table">
        <tr><th>CYC</th><th>E_RATIO</th><th>DC</th><th>FLUX</th><th>ORACLE</th><th>GATE</th></tr>
        ${tableRows}
      </table>
    </div>
    <div class="drawer-section">
      <h4>OPINIONS</h4>
      <div class="drawer-pre">${escHtml(run.opinions || 'No data')}</div>
    </div>
    <div class="drawer-section">
      <h4>SOLVER</h4>
      <div class="drawer-pre">${escHtml(run.solver || 'No data')}</div>
    </div>
    <div class="drawer-section">
      <h4>DEAD ENDS</h4>
      <div class="drawer-pre">${escHtml(run.dead_ends || 'No data')}</div>
    </div>`;

  document.getElementById('drawerOverlay').classList.add('open');
  document.getElementById('drawer').classList.add('open');
}

function closeDrawer() {
  document.getElementById('drawerOverlay').classList.remove('open');
  document.getElementById('drawer').classList.remove('open');
}

function escHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// --- Card expand/collapse ---

function toggleDetail(card) {
  const branch = card.dataset.branch;
  const runId = card.dataset.run;
  const detail = document.getElementById('detail-' + branch + '-' + runId);
  if (detail) {
    if (detail.classList.contains('open')) {
      detail.classList.remove('open');
    } else {
      // Close all others first
      document.querySelectorAll('.run-detail.open').forEach(d => d.classList.remove('open'));
      detail.classList.add('open');
    }
  }
  // Double-click opens drawer
  if (card._lastClick && Date.now() - card._lastClick < 400) {
    openDrawer(branch, parseInt(runId));
  }
  card._lastClick = Date.now();
}

// --- Polling ---

function update(data) {
  lastData = data;

  // Header
  document.getElementById('hdrRuns').textContent = `${data.total_complete}/${data.total_runs}`;
  document.getElementById('hdrTokens').textContent = fmtNum(data.total_tokens);

  // Branch grid
  const grid = document.getElementById('branchGrid');
  grid.innerHTML = BRANCH_KEYS.map(k => renderBranch(k, data.branches[k] || {label: '', runs: [], aggregate: {}})).join('');

  // Comparison
  document.getElementById('compCharts').innerHTML = renderComparison(data);
}

function poll() {
  fetch('api/status')
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

document.getElementById('drawerOverlay').addEventListener('click', closeDrawer);
document.getElementById('drawerClose').addEventListener('click', closeDrawer);
poll();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class AssayHandler(BaseHTTPRequestHandler):
    workspace_root = "."

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/status":
            self.send_json(build_api_response(self.workspace_root))
        elif path in ("/", "/index.html"):
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
        print("Usage: python3 dashboard_assay.py <workspace_root> [--port 8100]")
        print("Example: python3 dashboard_assay.py runs/assay --port 8100")
        sys.exit(1)

    workspace_root = os.path.abspath(args[0])
    if not os.path.isdir(workspace_root):
        print(f"Error: {workspace_root} is not a directory")
        sys.exit(1)

    AssayHandler.workspace_root = workspace_root
    server = HTTPServer(("127.0.0.1", port), AssayHandler)
    print(f"  The Assayer Dashboard on http://127.0.0.1:{port}")
    print(f"  Watching: {workspace_root}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
