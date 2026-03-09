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


def get_api_response(terrarium):
    """Build the JSON response from terrarium files."""
    status_path = os.path.join(terrarium, "status.json")
    opinions_path = os.path.join(terrarium, "opinions.md")
    dead_ends_path = os.path.join(terrarium, "dead-ends.md")
    data_path = os.path.join(terrarium, "data.json")
    goal_path = os.path.join(terrarium, "goal.md")

    status_raw = read_file_safe(status_path)
    try:
        status = json.loads(status_raw) if status_raw else {}
    except json.JSONDecodeError:
        status = {}

    opinions = read_file_safe(opinions_path)
    dead_ends = read_file_safe(dead_ends_path)
    data_raw = read_file_safe(data_path)
    goal = read_file_safe(goal_path)

    try:
        data_parsed = json.loads(data_raw) if data_raw else []
    except json.JSONDecodeError:
        data_parsed = []

    return {
        **status,
        "opinions_content": opinions,
        "dead_ends_content": dead_ends,
        "data_content": json.dumps(data_parsed, indent=2) if data_parsed else "[]",
        "goal_content": goal,
    }


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Avalanche Hypervisor V4.1</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #0d1117;
    color: #c9d1d9;
    font-family: 'Cascadia Code', 'Fira Code', 'JetBrains Mono', monospace;
    font-size: 14px;
    padding: 20px;
  }
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
    padding-bottom: 16px;
    border-bottom: 1px solid #21262d;
  }
  .header h1 {
    font-size: 18px;
    font-weight: 600;
    color: #58a6ff;
    letter-spacing: 2px;
  }
  .header .connection {
    font-size: 12px;
    color: #484f58;
  }
  .header .connection.live { color: #3fb950; }
  .header .connection.dead { color: #f85149; }

  .status-bar {
    display: flex;
    gap: 16px;
    margin-bottom: 20px;
    flex-wrap: wrap;
  }
  .status-card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
    padding: 12px 20px;
    min-width: 130px;
  }
  .status-card .label {
    font-size: 11px;
    color: #484f58;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 4px;
  }
  .status-card .value {
    font-size: 22px;
    font-weight: 700;
  }
  .phase-grind { color: #d2a8ff; }
  .phase-ratchet { color: #79c0ff; }
  .phase-pass { color: #3fb950; }
  .phase-fail { color: #f85149; }
  .phase-sync { color: #ffa657; }
  .phase-idle { color: #484f58; }

  .panels {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 20px;
  }
  @media (max-width: 900px) {
    .panels { grid-template-columns: 1fr; }
  }
  .panel {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
    overflow: hidden;
  }
  .panel.full-width {
    grid-column: 1 / -1;
  }
  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 16px;
    background: #1c2128;
    border-bottom: 1px solid #21262d;
    font-size: 13px;
    font-weight: 600;
  }
  .word-count { font-weight: 400; color: #484f58; }
  .word-count.warn { color: #d29922; }
  .word-count.crit { color: #f85149; }
  .panel-body {
    padding: 16px;
    white-space: pre-wrap;
    word-wrap: break-word;
    font-size: 13px;
    line-height: 1.5;
    max-height: 400px;
    overflow-y: auto;
  }
  .progress-bar {
    height: 3px;
    background: #21262d;
  }
  .progress-fill {
    height: 100%;
    background: #3fb950;
    transition: width 0.5s ease;
  }
  .progress-fill.warn { background: #d29922; }
  .progress-fill.crit { background: #f85149; }

  .data-pair {
    background: #1c2128;
    border: 1px solid #21262d;
    border-radius: 4px;
    padding: 8px 12px;
    margin-bottom: 8px;
    font-size: 12px;
  }
  .data-pair .pair-label {
    color: #484f58;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 2px;
  }
  .data-pair .pair-input { color: #79c0ff; }
  .data-pair .pair-expected { color: #3fb950; }

  .error-panel {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
    margin-bottom: 20px;
    overflow: hidden;
  }
  .error-panel .panel-header {
    color: #f85149;
  }
  .error-panel .panel-body {
    color: #f0883e;
    font-size: 12px;
    max-height: 200px;
  }

  .timeline {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
    overflow: hidden;
  }
  .timeline .panel-header { color: #8b949e; }
  .timeline-body {
    padding: 12px 16px;
    max-height: 240px;
    overflow-y: auto;
    font-size: 12px;
  }
  .timeline-entry {
    display: flex;
    gap: 12px;
    padding: 3px 0;
    border-bottom: 1px solid #21262d10;
  }
  .timeline-entry .time { color: #484f58; min-width: 60px; }
  .timeline-entry .cycle-num { color: #8b949e; min-width: 30px; }
  .timeline-entry .event { }

  .no-data {
    color: #484f58;
    font-style: italic;
    text-align: center;
    padding: 40px;
  }
</style>
</head>
<body>
  <div class="header">
    <h1>AVALANCHE HYPERVISOR V4.1</h1>
    <span class="connection" id="conn">CONNECTING...</span>
  </div>

  <div class="status-bar">
    <div class="status-card">
      <div class="label">Cycle</div>
      <div class="value" id="cycle">-</div>
    </div>
    <div class="status-card">
      <div class="label">Phase</div>
      <div class="value" id="phase">-</div>
    </div>
    <div class="status-card">
      <div class="label">Result</div>
      <div class="value" id="result">-</div>
    </div>
    <div class="status-card">
      <div class="label">Opinions</div>
      <div class="value" id="op-words">-</div>
    </div>
    <div class="status-card">
      <div class="label">Dead Ends</div>
      <div class="value" id="de-words">-</div>
    </div>
    <div class="status-card">
      <div class="label">Data Pairs</div>
      <div class="value" id="dp-count">-</div>
    </div>
  </div>

  <div class="panels">
    <div class="panel">
      <div class="panel-header">
        <span>opinions.md</span>
        <span class="word-count" id="op-wc-label">-</span>
      </div>
      <div class="progress-bar"><div class="progress-fill" id="op-bar"></div></div>
      <div class="panel-body" id="op-content"><span class="no-data">Waiting for data...</span></div>
    </div>
    <div class="panel">
      <div class="panel-header">
        <span>dead-ends.md</span>
        <span class="word-count" id="de-wc-label">-</span>
      </div>
      <div class="progress-bar"><div class="progress-fill" id="de-bar"></div></div>
      <div class="panel-body" id="de-content"><span class="no-data">Waiting for data...</span></div>
    </div>
    <div class="panel full-width">
      <div class="panel-header">
        <span>data.json</span>
        <span class="word-count" id="dp-label">-</span>
      </div>
      <div class="panel-body" id="data-content"><span class="no-data">No failure data yet</span></div>
    </div>
  </div>

  <div class="error-panel" id="error-section" style="display:none">
    <div class="panel-header">LAST ERROR</div>
    <div class="panel-body" id="error-content"></div>
  </div>

  <div class="timeline">
    <div class="panel-header">EVENT LOG</div>
    <div class="timeline-body" id="timeline"><span class="no-data">Waiting for events...</span></div>
  </div>

<script>
const POLL_MS = 2000;
let lastTimestamp = null;
let failCount = 0;

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
  document.getElementById('op-wc-label').className = 'word-count ' + opWc;
  const opBar = document.getElementById('op-bar');
  opBar.style.width = Math.min(100, (opWords / opLimit) * 100) + '%';
  opBar.className = 'progress-fill ' + opWc;

  // Dead Ends
  const deWc = wcClass(deWords, deLimit);
  document.getElementById('de-words').textContent = deWords + '/' + deLimit;
  document.getElementById('de-wc-label').textContent = deWords + ' / ' + deLimit + ' words';
  document.getElementById('de-wc-label').className = 'word-count ' + deWc;
  const deBar = document.getElementById('de-bar');
  deBar.style.width = Math.min(100, (deWords / deLimit) * 100) + '%';
  deBar.className = 'progress-fill ' + deWc;

  // Data pairs
  document.getElementById('dp-count').textContent = dpCount + '/' + dpMax;
  document.getElementById('dp-label').textContent = dpCount + ' / ' + dpMax + ' pairs';

  // File contents
  const opContent = data.opinions_content || '';
  const deContent = data.dead_ends_content || '';
  const dataContent = data.data_content || '[]';
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

async function poll() {
  try {
    const resp = await fetch('/api/status');
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
