"""Fix Opus format issues: stronger prompt + smarter normalizer."""
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "hypervisor_v44.py"

with open(path, "r") as f:
    content = f.read()

# 1. Strengthen system prompt to suppress reasoning
old_prompt = (
    '    system_prompt = (\n'
    '        "You are the combinatorial engine of the Avalanche V4.4.1 system.\\n"\n'
    '        "Output only the JSON object matching the provided schema.\\n"\n'
    '        "No conversational filler. No markdown fences. No extra keys.\\n"\n'
    '    )'
)
new_prompt = (
    '    system_prompt = (\n'
    '        "You are the combinatorial engine of the Avalanche V4.4.1 system.\\n"\n'
    '        "RESPOND WITH ONLY A SINGLE RAW JSON OBJECT. No reasoning, no analysis, no prose, no markdown fences, no code blocks.\\n"\n'
    '        "Your entire response must be parseable by json.loads() with zero preprocessing.\\n"\n'
    '        "The JSON object must have exactly three keys: opinions_md, dead_ends, solver_py.\\n"\n'
    '    )'
)

if old_prompt in content:
    content = content.replace(old_prompt, new_prompt)
    print("OK: system prompt strengthened")
else:
    print("WARNING: system prompt text not found, skipping")

# 2. Make normalizer find JSON by key signature as last resort
old_norm = '''    if normalized and normalized[0] != "{":
        start = normalized.find("{")
        end = normalized.rfind("}")
        if start != -1 and end > start:
            normalized = normalized[start:end + 1]
    return normalized'''

new_norm = '''    if normalized and normalized[0] != "{":
        # Try to find JSON by key signature — look for {"opinions_md"
        sig_idx = normalized.find('"opinions_md"')
        if sig_idx != -1:
            # Walk backwards to find the opening brace
            brace_idx = normalized.rfind("{", 0, sig_idx)
            if brace_idx != -1:
                end = normalized.rfind("}")
                if end > brace_idx:
                    normalized = normalized[brace_idx:end + 1]
        else:
            # Generic fallback: first { to last }
            start = normalized.find("{")
            end = normalized.rfind("}")
            if start != -1 and end > start:
                normalized = normalized[start:end + 1]
    return normalized'''

if old_norm in content:
    content = content.replace(old_norm, new_norm)
    print("OK: normalizer updated with key-signature extraction")
else:
    print("WARNING: normalizer text not found, skipping")

with open(path, "w") as f:
    f.write(content)
