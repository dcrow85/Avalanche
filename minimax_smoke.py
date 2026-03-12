#!/usr/bin/env python3
"""
Minimal smoke tests for the Haimaker MiniMax M2.5 endpoint.

This is intentionally separate from Avalanche hypervisors so we can answer:
- Does the key work?
- Is the endpoint OpenAI-compatible enough for chat completions?
- Can we coerce deterministic short text?
- Can we get clean machine-readable JSON without visible reasoning text?
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


DEFAULT_API_BASE = "https://api.haimaker.ai/v1"
DEFAULT_MODEL = "minimax/MiniMax-M2.5"


def request_json(method: str, url: str, api_key: str, payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AvalancheMiniMaxSmoke/1.0",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connection error: {exc}") from exc


def extract_text(payload: dict) -> str:
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Malformed chat payload: {payload}") from exc


def usage_summary(payload: dict) -> str:
    usage = payload.get("usage", {})
    if not isinstance(usage, dict):
        return "usage=?"
    prompt = usage.get("prompt_tokens", "?")
    completion = usage.get("completion_tokens", "?")
    total = usage.get("total_tokens", "?")
    return f"usage prompt={prompt} completion={completion} total={total}"


def chat(api_base: str, api_key: str, model: str, prompt: str, *, max_tokens: int = 128, temperature: int = 0,
         response_format: dict | None = None) -> dict:
    payload: dict[str, object] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format is not None:
        payload["response_format"] = response_format
    return request_json("POST", f"{api_base.rstrip('/')}/chat/completions", api_key, payload)


def report_case(name: str, payload: dict, *, expect_json: bool = False) -> None:
    text = extract_text(payload)
    print(f"\n== {name} ==")
    print(usage_summary(payload))
    print(f"finish_reason={payload.get('choices', [{}])[0].get('finish_reason')}")
    print(f"contains_think={'<think>' in text}")
    if expect_json:
        try:
            parsed = json.loads(text)
            print("json_parse=ok")
            print(json.dumps(parsed, indent=2))
        except json.JSONDecodeError:
            print("json_parse=fail")
            print(text)
    else:
        print(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Haimaker MiniMax M2.5.")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key", default=os.environ.get("HAIMAKER_API_KEY", ""))
    args = parser.parse_args()

    if not args.api_key:
        print("HAIMAKER_API_KEY is not set and --api-key was not provided.", file=sys.stderr)
        return 2

    print("== MODELS ==")
    models = request_json("GET", f"{args.api_base.rstrip('/')}/models", args.api_key)
    print(json.dumps(models, indent=2))

    exact = chat(
        args.api_base,
        args.api_key,
        args.model,
        "Reply with exactly MINIMAX_OK. No reasoning. No tags. No punctuation.",
        max_tokens=64,
    )
    report_case("EXACT_TEXT", exact)

    longer = chat(
        args.api_base,
        args.api_key,
        args.model,
        "Reply with exactly MINIMAX_OK. No reasoning. No tags. No punctuation.",
        max_tokens=256,
    )
    report_case("EXACT_TEXT_LONGER", longer)

    json_probe = chat(
        args.api_base,
        args.api_key,
        args.model,
        'Return valid JSON only: {"ok": true, "value": "MINIMAX_OK"}',
        max_tokens=128,
        response_format={"type": "json_object"},
    )
    report_case("JSON_OBJECT", json_probe, expect_json=True)

    anti_think = chat(
        args.api_base,
        args.api_key,
        args.model,
        "Return exactly one JSON object with keys ok and value. Do not think aloud. Do not include <think> tags.",
        max_tokens=256,
        response_format={"type": "json_object"},
    )
    report_case("JSON_NO_THINK", anti_think, expect_json=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
