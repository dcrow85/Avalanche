"""Make hunches_md required instead of optional."""
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "hypervisor_v44.py"

with open(path, "r") as f:
    content = f.read()

changes = 0

# 1. System prompt: remove "optionally"
old = '        "The JSON object must have keys: opinions_md, dead_ends, solver_py, and optionally hunches_md.\\n"'
new = '        "The JSON object must have exactly four keys: opinions_md, dead_ends, solver_py, hunches_md.\\n"'
if old in content:
    content = content.replace(old, new, 1)
    changes += 1

# 2. Constraint: remove "(optional)" label, make it mandatory
old = (
    '        f"- hunches_md (optional): maximum {HUNCHES_LIMIT} words. Raw intuitions, not theories. "\n'
    '        "Fragments, not sentences. What feels wrong that you cannot explain yet. "\n'
    '        "This is a subliminal scratchpad — jot pattern fragments, not explanations.\\n"'
)
new = (
    '        f"- hunches_md: REQUIRED. Maximum {HUNCHES_LIMIT} words. Raw intuitions, not theories. "\n'
    '        "Fragments, not sentences. What feels wrong that you cannot explain yet. "\n'
    '        "Not a summary of your theory — write what nags you before you can name it.\\n"'
)
if old in content:
    content = content.replace(old, new, 1)
    changes += 1

# 3. Grind instruction: remove "(optional, ...)" qualifier
old = '            "- hunches_md (optional, max 15 words — raw gut feelings only)\\n\\n"'
new = '            "- hunches_md (max 15 words — raw gut feelings, not theory summaries)\\n\\n"'
if old in content:
    content = content.replace(old, new, 1)
    changes += 1

with open(path, "w") as f:
    f.write(content)

print(f"Done: {changes}/3 patches applied")
