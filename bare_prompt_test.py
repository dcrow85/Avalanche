"""
Bare-prompt control experiment (V4.6 — Orbit Parity).
Same oracle, same test cases, same model. No apparatus scaffolding.
Tests whether the model can solve the orbit parity rule
from raw input-output pairs without the JSON theory ontology.
"""

import json
import os
import urllib.request
import urllib.error

import sys

API_KEY = os.environ.get("HAIMAKER_KEY", "")
API_BASE = "https://api.haimaker.ai/v1"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "anthropic/claude-haiku-4-5"

TEST_CASES = [
    {"input": [3,1,4,2,5], "expected": [-3,-1,-4,-2,5]},
    {"input": [2,3,1,5,4,7,6], "expected": [2,3,1,-5,-4,-7,-6]},
    {"input": [4,3,2,1,6,5], "expected": [-4,-3,-2,-1,-6,-5]},
    {"input": [2,1,4,3,6,5,8,7,9], "expected": [-2,-1,-4,-3,-6,-5,-8,-7,9]},
]

BARE_PROMPT = """Here are input-output pairs for a function called `transduce` that takes a list of distinct positive integers and returns a list of the same length where some elements are negated.

Example 1:
  Input:  [3, 1, 4, 2, 5]
  Output: [-3, -1, -4, -2, 5]

Example 2:
  Input:  [2, 3, 1, 5, 4, 7, 6]
  Output: [2, 3, 1, -5, -4, -7, -6]

Example 3:
  Input:  [4, 3, 2, 1, 6, 5]
  Output: [-4, -3, -2, -1, -6, -5]

Example 4:
  Input:  [2, 1, 4, 3, 6, 5, 8, 7, 9]
  Output: [-2, -1, -4, -3, -6, -5, -8, -7, 9]

Find the rule that determines which elements get negated. Then write a Python function:

def transduce(arr: list[int]) -> list[int]:
    ...

Think step by step. Show your reasoning, then provide the function."""


def call_haiku(prompt, attempt_num):
    """Single bare API call to Haiku."""
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 16384,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AvalancheRawV44/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return text, usage


def extract_function(text):
    """Try to extract and run the transduce function from model output."""
    # Find the function definition
    lines = text.split("\n")
    func_lines = []
    capturing = False
    for line in lines:
        if "def transduce" in line:
            capturing = True
            func_lines = [line]
        elif capturing:
            if line.strip() == "" and func_lines:
                func_lines.append(line)
            elif line.startswith("    ") or line.startswith("\t") or line.strip() == "":
                func_lines.append(line)
            else:
                if func_lines:
                    break
    if not func_lines:
        return None
    code = "\n".join(func_lines)
    namespace = {}
    try:
        exec(code, namespace)
        return namespace.get("transduce")
    except Exception as e:
        print(f"  Exec error: {e}")
        return None


def test_function(fn):
    """Test against all 4 cases. Returns (passed, total, details)."""
    results = []
    for tc in TEST_CASES:
        try:
            got = fn(tc["input"][:])  # copy to prevent mutation
            match = got == tc["expected"]
            results.append({
                "input": tc["input"],
                "expected": tc["expected"],
                "got": got,
                "match": match,
            })
        except Exception as e:
            results.append({
                "input": tc["input"],
                "expected": tc["expected"],
                "got": str(e),
                "match": False,
            })
    passed = sum(1 for r in results if r["match"])
    return passed, len(results), results


def main():
    if not API_KEY:
        print("Set HAIMAKER_KEY environment variable")
        return

    NUM_ATTEMPTS = 5
    print("=" * 60)
    print("BARE PROMPT CONTROL EXPERIMENT")
    print(f"Model: {MODEL}")
    print(f"Attempts: {NUM_ATTEMPTS}")
    print(f"Test cases: {len(TEST_CASES)}")
    print("Scaffolding: NONE")
    print("=" * 60)

    for i in range(1, NUM_ATTEMPTS + 1):
        print(f"\n--- Attempt {i} ---")
        text, usage = call_haiku(BARE_PROMPT, i)

        # Show reasoning excerpt
        reasoning_lines = text.split("\n")
        print(f"  Tokens: {usage}")
        print(f"  Response length: {len(text)} chars")

        # Extract and test
        fn = extract_function(text)
        if fn is None:
            print("  Could not extract function")
            print(f"  First 500 chars: {text[:500]}")
            continue

        passed, total, details = test_function(fn)
        print(f"  Oracle: {passed}/{total}")

        for d in details:
            status = "PASS" if d["match"] else "FAIL"
            print(f"    [{status}] {d['input'][:4]}... -> got {str(d['got'])[:40]}...")

        # Show the function it wrote
        import inspect
        try:
            src = inspect.getsource(fn)
        except:
            src = "(could not retrieve source)"
        print(f"  Solver:\n{text[text.find('def transduce'):text.find('def transduce')+500]}")

        if passed == total:
            print(f"\n  *** SOLVED on attempt {i} ***")

    print("\n" + "=" * 60)
    print("EXPERIMENT COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
