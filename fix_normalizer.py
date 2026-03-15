"""Patch normalize_structured_output_text in hypervisor_v44.py to handle fences anywhere in text."""
import re, sys

path = sys.argv[1] if len(sys.argv) > 1 else "hypervisor_v44.py"

with open(path, "r") as f:
    content = f.read()

old = '''def normalize_structured_output_text(text: str) -> str:
    normalized = strip_leading_think_block(text).strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        normalized = "\\n".join(lines).strip()
    return normalized'''

new = '''def normalize_structured_output_text(text: str) -> str:
    normalized = strip_leading_think_block(text).strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        normalized = "\\n".join(lines).strip()
    elif "```" in normalized:
        m = re.search(r"```(?:json)?\\s*\\n(.*?)\\n\\s*```", normalized, re.DOTALL)
        if m:
            normalized = m.group(1).strip()
    if normalized and normalized[0] != "{":
        start = normalized.find("{")
        end = normalized.rfind("}")
        if start != -1 and end > start:
            normalized = normalized[start:end + 1]
    return normalized'''

if old in content:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    print("OK: normalize_structured_output_text patched")
else:
    print("ERROR: target text not found in", path)
    sys.exit(1)
