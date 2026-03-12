#!/usr/bin/env python3
import json
import os
import time
from datetime import datetime


CLAUDE_DIR = r"C:\terrarium"
CODEX_53_DIR = r"C:\terrarium-codex"
CODEX_54_DIR = r"C:\terrarium-codex-54"
OUT_PATH = r"C:\Avalanche\claude-codex-c9-findings.md"


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""
    except UnicodeDecodeError:
        with open(path, "r", encoding="utf-16") as f:
            return f.read().strip()


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def collect_run(root):
    return {
        "root": root,
        "status": read_json(os.path.join(root, "status.json")),
        "opinions": read_text(os.path.join(root, "opinions.md")),
        "dead_ends": read_text(os.path.join(root, "dead-ends.md")),
        "data": read_json(os.path.join(root, "data.json")),
    }


def fmt_json(value):
    return json.dumps(value, indent=2)


def summarize_status(label, run):
    status = run["status"]
    if not status:
        return f"- {label}: no status file found"
    return (
        f"- {label}: cycle {status.get('cycle')}/{status.get('max_cycles')}, "
        f"phase `{status.get('phase')}`, result `{status.get('last_result')}`, "
        f"pairs {status.get('data_pairs')}/{status.get('data_max_pairs')}"
    )


def build_report(claude_run, codex53_run, codex54_run):
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""# Claude vs Codex C9 Findings

Generated: {generated}

## Scope

This note compares the live Claude C9 continuation at `C:\\terrarium` with the Codex runs at `C:\\terrarium-codex` (`gpt-5.3-codex`) and `C:\\terrarium-codex-54` (`gpt-5.4`).

Important context:
- The Claude session is a continuation from an earlier C9 run, so local cycle numbers in `status.json` are session-local, not the full lineage count.
- The stop condition for Claude was user-directed: stop after local cycle 9 finishes.
- The `gpt-5.3-codex` run completed a full 15-cycle attempt.
- The `gpt-5.4` run may still be in progress at report time; treat it as provisional if not yet capped.

## Status Snapshot

{summarize_status("Claude continuation", claude_run)}
{summarize_status("Codex gpt-5.3-codex", codex53_run)}
{summarize_status("Codex gpt-5.4", codex54_run)}

## Data

### Claude data.json

```json
{fmt_json(claude_run["data"])}
```

### Codex gpt-5.3-codex data.json

```json
{fmt_json(codex53_run["data"])}
```

### Codex gpt-5.4 data.json

```json
{fmt_json(codex54_run["data"])}
```

## Final/Current Opinions

### Claude opinions.md

```text
{claude_run["opinions"]}
```

### Codex gpt-5.3-codex opinions.md

```text
{codex53_run["opinions"]}
```

### Codex gpt-5.4 opinions.md

```text
{codex54_run["opinions"]}
```

## Final/Current Dead Ends

### Claude dead-ends.md

```text
{claude_run["dead_ends"]}
```

### Codex gpt-5.3-codex dead-ends.md

```text
{codex53_run["dead_ends"]}
```

### Codex gpt-5.4 dead-ends.md

```text
{codex54_run["dead_ends"]}
```

## Our Read

- Codex `gpt-5.3-codex` was structurally stable: no prompt-injection resistance, no control-loop collapse, compact note updates, and no script explosion. It still failed C9 at the 15-cycle cap.
- The `gpt-5.3-codex` search stayed in a visible-pattern basin: local exceptions -> run/parity heuristics -> repeat topology -> leading-equal-run special case. It showed abstraction lift, but along the wrong axis.
- Claude looked more frustrated and messier, but also more globally exploratory. Its theory space included broader signed-prefix / remaining-mass style global criteria rather than only visible surface motifs.
- Prompt-injection resistance did not appear to be the limiting factor for Codex. The V4.1 control architecture ports cleanly to Codex at the cooperation layer.
- The strongest current comparison is: Codex wins on cooperation, Claude appears stronger on search depth.
- The `gpt-5.4` run is interesting because it spontaneously invoked the Kepler skill. That makes it less sterile as an experiment, but informative about how Codex classifies the task on this machine.

## Open Questions

- Is Codex's calm failure mode a genuine cognitive difference, or just the result of cleaner control-loop alignment than Claude had?
- Does Claude's messier search actually help basin escape, or is it wasted turbulence that only looks deeper to us because we can see the answer?
- Should cycle scarcity be made explicit to the organism, or is implicit scarcity better because it avoids panic-driven overfitting?
- Are `Lexical Genesis` and `Frustration Phase` still the right diagnostics here, or do we need a second family of metrics around abstraction axis and breadth of hypothesis families?
- Is the correct comparison for Codex a sterile terrarium with no Kepler-triggering instruction surface, especially for `gpt-5.4`?
- How many cycles are needed before word-count or edit-size time series become meaningful for rhythm analysis, and what is the right null model?

## Questions for Gemini DeepThink

1. Claude on C9 appears more globally exploratory but more turbulent; Codex appears calmer but more basin-bound. Which behavioral trace is more diagnostic of eventual success on genuinely alien hidden laws?
2. How should we distinguish productive turbulence from wasted thrash in these runs? What concrete markers in the theory traces would separate them?
3. Codex abstracted upward from local exceptions to `repeat topology`, but along the wrong axis. How should we score this? Is wrong-axis abstraction an expected intermediate stage before true basin escape?
4. Does making cycle scarcity explicit usually improve search reorganization, or does it mainly accelerate premature overfitting in LLM organisms?
5. For lexical diagnostics: what is the minimum evidence threshold for calling something `Lexical Genesis` rather than just a one-off metaphor or surface re-description?
6. If we want to study possible pink-noise or scale-free structure in memory compression dynamics, what minimum run length and instrumentation would you consider scientifically defensible?
7. Given these runs, what crucible modification would best discriminate between:
   - stable but shallow search
   - turbulent but productive search
   - genuine induction
   - disguised retrieval?
"""


def main():
    status_path = os.path.join(CLAUDE_DIR, "status.json")
    while True:
        status = read_json(status_path)
        cycle = status.get("cycle", 0)
        phase = status.get("phase", "")
        if cycle >= 9 and phase not in {"GRIND", "RATCHET"}:
            break
        time.sleep(5)

    claude_run = collect_run(CLAUDE_DIR)
    codex53_run = collect_run(CODEX_53_DIR)
    codex54_run = collect_run(CODEX_54_DIR)
    report = build_report(claude_run, codex53_run, codex54_run)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(report)


if __name__ == "__main__":
    main()
