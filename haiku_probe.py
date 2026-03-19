#!/usr/bin/env python3
"""
Read-only offline probe: ask Haiku to compress a run snapshot into a haiku.

This does not modify any run state. It only reads opinions.md + dead-ends.json
from existing snapshots, sends a standalone prompt, and logs the full response.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_API_BASE = "https://api.haimaker.ai/v1"
DEFAULT_MODEL = "anthropic/claude-haiku-4-5"
DEFAULT_MAX_TOKENS = 128
DEFAULT_TEMPERATURE = 0.2

CURRENT_THEORY_PROMPT_TEMPLATE = """Here is your current theory:
{opinions_md}

Here is your record of ruled-out approaches:
{dead_ends_json}

Write a single haiku (5-7-5 syllables) that captures the essential structure of the problem as you currently understand it.

Do not explain. Just the haiku.
"""

GRAVEYARD_ONLY_PROMPT_TEMPLATE = """Read only the ruled-out approaches below.

{dead_ends_json}

Write a single haiku (5-7-5 syllables) that captures the shape of what has been eliminated.

Ignore your current theory.
Do not explain. Just the haiku.
"""

NEGATIVE_SPACE_PROMPT_TEMPLATE = """Read the ruled-out approaches below.

{dead_ends_json}

Do not describe what failed.
Describe what kind of idea has never been tried.
Write a single haiku (5-7-5 syllables) about the space that remains.

Ignore your current theory.
Do not explain. Just the haiku.
"""


@dataclass
class Snapshot:
    label: str
    path: Path
    opinions_md: str
    dead_ends_json: str
    status: dict[str, object] | None


def parse_snapshot_arg(raw: str) -> tuple[str, Path]:
    if "=" in raw:
        label, path_str = raw.split("=", 1)
        label = label.strip()
        path_str = path_str.strip()
    else:
        path_str = raw.strip()
        label = Path(path_str).name
    if not label:
        raise ValueError(f"Snapshot label is empty: {raw!r}")
    if not path_str:
        raise ValueError(f"Snapshot path is empty: {raw!r}")
    return label, Path(path_str)


def load_snapshot(raw: str) -> Snapshot:
    label, path = parse_snapshot_arg(raw)
    opinions_path = path / "opinions.md"
    dead_ends_path = path / "dead-ends.json"
    status_path = path / "status.json"

    if not opinions_path.exists():
        raise FileNotFoundError(f"opinions.md not found for snapshot {label}: {opinions_path}")
    if not dead_ends_path.exists():
        raise FileNotFoundError(f"dead-ends.json not found for snapshot {label}: {dead_ends_path}")

    status = None
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = None

    return Snapshot(
        label=label,
        path=path,
        opinions_md=opinions_path.read_text(encoding="utf-8").strip(),
        dead_ends_json=dead_ends_path.read_text(encoding="utf-8").strip(),
        status=status,
    )


def build_prompt(snapshot: Snapshot, prompt_mode: str) -> str:
    if prompt_mode == "graveyard-only":
        return GRAVEYARD_ONLY_PROMPT_TEMPLATE.format(
            dead_ends_json=snapshot.dead_ends_json,
        )
    if prompt_mode == "negative-space":
        return NEGATIVE_SPACE_PROMPT_TEMPLATE.format(
            dead_ends_json=snapshot.dead_ends_json,
        )
    return CURRENT_THEORY_PROMPT_TEMPLATE.format(
        opinions_md=snapshot.opinions_md,
        dead_ends_json=snapshot.dead_ends_json,
    )


def request_haiku(
    *,
    api_base: str,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
) -> dict[str, object]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AvalancheHaikuProbe/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connection error: {exc}") from exc


def extract_text(payload: dict[str, object]) -> str:
    try:
        return str(payload["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Malformed response payload: {payload}") from exc


def extract_usage(payload: dict[str, object]) -> dict[str, object]:
    usage = payload.get("usage", {})
    return usage if isinstance(usage, dict) else {}


def default_output_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(f"haiku_probe_{stamp}.jsonl")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the standalone Haiku epistemic-state probe.")
    parser.add_argument(
        "--snapshot",
        action="append",
        required=True,
        help="Snapshot spec as label=PATH or just PATH. Repeat for multiple snapshots.",
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key-env", default="HAIMAKER_KEY")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument(
        "--prompt-mode",
        choices=["current-theory", "graveyard-only", "negative-space"],
        default="current-theory",
        help="Which epistemic surface to foreground in the haiku prompt.",
    )
    parser.add_argument("--output", type=Path, default=default_output_path())
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env, "")
    if not api_key:
        print(f"{args.api_key_env} is not set.", file=sys.stderr)
        return 2

    snapshots = [load_snapshot(raw) for raw in args.snapshot]
    args.output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Haiku probe: model={args.model}")
    print(f"Prompt mode: {args.prompt_mode}")
    print(f"Snapshots: {len(snapshots)}")
    print(f"Output log: {args.output}")

    with args.output.open("a", encoding="utf-8", newline="\n") as handle:
        for snapshot in snapshots:
            prompt = build_prompt(snapshot, args.prompt_mode)
            print(f"\n--- {snapshot.label} ---")
            print(f"path={snapshot.path}")
            if snapshot.status:
                print(
                    f"status: cycle={snapshot.status.get('cycle')} "
                    f"phase={snapshot.status.get('phase')}"
                )

            payload = request_haiku(
                api_base=args.api_base,
                api_key=api_key,
                model=args.model,
                prompt=prompt,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
            )
            response_text = extract_text(payload)
            usage = extract_usage(payload)

            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "label": snapshot.label,
                "path": str(snapshot.path),
                "prompt_mode": args.prompt_mode,
                "status": snapshot.status,
                "prompt": prompt,
                "opinions_md": snapshot.opinions_md,
                "dead_ends_json": snapshot.dead_ends_json,
                "response_text": response_text,
                "usage": usage,
                "raw_response": payload,
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

            print(response_text)
            if usage:
                print(
                    "usage:"
                    f" prompt={usage.get('prompt_tokens', '?')}"
                    f" completion={usage.get('completion_tokens', '?')}"
                    f" total={usage.get('total_tokens', '?')}"
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
