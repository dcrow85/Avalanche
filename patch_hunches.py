"""Patch hypervisor_v44.py to add the subliminal ledger (hunches.md)."""
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "hypervisor_v44.py"

with open(path, "r") as f:
    content = f.read()

changes = 0

# 1. Add HUNCHES_FILE constant and limit after OPINIONS_LIMIT
old = 'OPINIONS_LIMIT = 75'
new = 'OPINIONS_LIMIT = 75\nHUNCHES_LIMIT = 15\nHUNCHES_FILE = "hunches.md"'
if old in content:
    content = content.replace(old, new, 1)
    changes += 1
    print("1. Added HUNCHES_FILE constant and limit")

# 2. Update system prompt to mention hunches_md key
old_sys = '        "The JSON object must have exactly three keys: opinions_md, dead_ends, solver_py.\\n"'
new_sys = '        "The JSON object must have keys: opinions_md, dead_ends, solver_py, and optionally hunches_md.\\n"'
if old_sys in content:
    content = content.replace(old_sys, new_sys, 1)
    changes += 1
    print("2. Updated system prompt for hunches_md key")

# 3. Add hunches constraint to common_constraints
old_constraints = '        f"- opinions_md must stay under {OPINIONS_LIMIT} words.\\n"'
new_constraints = (
    '        f"- opinions_md must stay under {OPINIONS_LIMIT} words.\\n"\n'
    '        f"- hunches_md (optional): maximum {HUNCHES_LIMIT} words. Raw intuitions, not theories. "\n'
    '        "Fragments, not sentences. What feels wrong that you cannot explain yet. "\n'
    '        "This is a subliminal scratchpad — jot pattern fragments, not explanations.\\n"'
)
if old_constraints in content:
    content = content.replace(old_constraints, new_constraints, 1)
    changes += 1
    print("3. Added hunches constraint to common_constraints")

# 4. Add hunches_md to grind instruction return list
old_grind = (
    '"Return updated contents for:\\n"\n'
    '            "- opinions_md\\n"\n'
    '            "- dead_ends\\n"\n'
    '            "- solver_py\\n\\n"'
)
new_grind = (
    '"Return updated contents for:\\n"\n'
    '            "- opinions_md\\n"\n'
    '            "- dead_ends\\n"\n'
    '            "- solver_py\\n"\n'
    '            "- hunches_md (optional, max 15 words — raw gut feelings only)\\n\\n"'
)
if old_grind in content:
    content = content.replace(old_grind, new_grind, 1)
    changes += 1
    print("4. Added hunches_md to grind return list")

# 5. Read hunches.md into user prompt context
old_user_prompt = (
    '    user_prompt = (\n'
    '        f"{instruction}\\n"\n'
    '        f"\\n# goal.md\\n{goal}\\n"'
)
new_user_prompt = (
    '    current_hunches = read_text(HUNCHES_FILE)\n'
    '    user_prompt = (\n'
    '        f"{instruction}\\n"\n'
    '        f"\\n# goal.md\\n{goal}\\n"'
)
if old_user_prompt in content:
    content = content.replace(old_user_prompt, new_user_prompt, 1)
    changes += 1
    print("5. Added hunches.md read")

# 6. Add hunches.md to user prompt after dead-ends.json
old_context = '        f"\\n# dead-ends.json\\n{current_dead_ends_json}\\n"'
new_context = (
    '        f"\\n# dead-ends.json\\n{current_dead_ends_json}\\n"\n'
    '        f"\\n# hunches.md (subliminal scratchpad)\\n{current_hunches or \"(empty)\"}\\n"'
)
if old_context in content:
    content = content.replace(old_context, new_context, 1)
    changes += 1
    print("6. Added hunches.md to user prompt context")

# 7. Persist hunches_md in persist_model_output
old_persist = '    write_text(SOLVER_FILE, solver_py + "\\n")'
new_persist = (
    '    write_text(SOLVER_FILE, solver_py + "\\n")\n'
    '    hunches_md = str(payload.get("hunches_md", "")).strip()\n'
    '    if hunches_md:\n'
    '        write_text(HUNCHES_FILE, hunches_md + "\\n")'
)
if old_persist in content:
    content = content.replace(old_persist, new_persist, 1)
    changes += 1
    print("7. Added hunches_md persist")

# 8. Add hunches word count validation in validate_cycle_output
old_validate = '    opinions_words = len(opinions_md.split())\n    if opinions_words > OPINIONS_LIMIT:'
new_validate = (
    '    opinions_words = len(opinions_md.split())\n'
    '    if opinions_words > OPINIONS_LIMIT:'
)
# Actually, let's find the right spot — after opinions validation, add hunches validation
old_val2 = '    solver_error = _solver_entrypoint_error(solver_py)\n    if solver_error:\n        return solver_error'
new_val2 = (
    '    hunches_md = str(payload.get("hunches_md", ""))\n'
    '    hunches_words = len(hunches_md.split())\n'
    '    if hunches_words > HUNCHES_LIMIT:\n'
    '        return f"hunches_md exceeds {HUNCHES_LIMIT} words ({hunches_words})."\n'
    '    solver_error = _solver_entrypoint_error(solver_py)\n'
    '    if solver_error:\n'
    '        return solver_error'
)
if old_val2 in content:
    content = content.replace(old_val2, new_val2, 1)
    changes += 1
    print("8. Added hunches word count validation")

with open(path, "w") as f:
    f.write(content)

print(f"\nDone: {changes}/8 patches applied")
if changes < 8:
    print("WARNING: Some patches did not match. Check the file manually.")
