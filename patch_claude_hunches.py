"""Add hunches.md support to the Claude Code hypervisor."""
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "hypervisor_v44_claude.py"

with open(path, "r") as f:
    content = f.read()

changes = 0

# 1. Add HUNCHES_FILE constant after SOLVER_FILE
old = 'SOLVER_FILE = "solver.py"'
new = 'SOLVER_FILE = "solver.py"\nHUNCHES_FILE = "hunches.md"\nHUNCHES_LIMIT = 15'
if old in content:
    content = content.replace(old, new, 1)
    changes += 1
    print("1. Added HUNCHES_FILE constant")

# 2. Add hunches.md to CLAUDE.md instructions
old_claude = (
    '            "Work only through opinions.md, dead-ends.json, and solver.py.\\n"'
)
new_claude = (
    '            "Work only through opinions.md, dead-ends.json, solver.py, and hunches.md.\\n"'
)
if old_claude in content:
    content = content.replace(old_claude, new_claude, 1)
    changes += 1
    print("2. Updated CLAUDE.md to mention hunches.md")

# 3. Add hunches.md to gitignore entries
old_gitignore = '        DEAD_END_STATE_FILE,'
new_gitignore = '        DEAD_END_STATE_FILE,\n        HUNCHES_FILE,'
if old_gitignore in content:
    content = content.replace(old_gitignore, new_gitignore, 1)
    changes += 1
    print("3. Added hunches.md to gitignore")

# 4. Seed hunches.md in workspace setup (after opinions.md creation)
old_opinions_setup = '    if not os.path.exists(OPINIONS_FILE):\n        write_text(OPINIONS_FILE, "# CURRENT THEORY\\n\\nNo theory yet.\\n")'
new_opinions_setup = (
    '    if not os.path.exists(OPINIONS_FILE):\n'
    '        write_text(OPINIONS_FILE, "# CURRENT THEORY\\n\\nNo theory yet.\\n")\n'
    '    if not os.path.exists(HUNCHES_FILE):\n'
    '        write_text(HUNCHES_FILE, "")'
)
if old_opinions_setup in content:
    content = content.replace(old_opinions_setup, new_opinions_setup, 1)
    changes += 1
    print("4. Added hunches.md workspace setup")

# 5. Add hunches instruction to grind prompt
old_grind_7 = '        f"7. Rewrite `{OPINIONS_FILE}` to state one specific hypothesis in under {OPINIONS_LIMIT} words.\\n"'
new_grind_7 = (
    '        f"7. Rewrite `{OPINIONS_FILE}` to state one specific hypothesis in under {OPINIONS_LIMIT} words.\\n"\n'
    '        f"7b. Rewrite `{HUNCHES_FILE}` with max {HUNCHES_LIMIT} words of raw gut feelings. Not theory summaries — fragments of what nags you before you can name it.\\n"'
)
if old_grind_7 in content:
    content = content.replace(old_grind_7, new_grind_7, 1)
    changes += 1
    print("5. Added hunches to grind prompt")

# 6. Add hunches to fail prompt allowed files
old_fail_files = (
    '        f"Do not create any files other than `{OPINIONS_FILE}` or `{DEAD_ENDS_JSON_FILE}`.\\n\\n"'
)
new_fail_files = (
    '        f"Do not create any files other than `{OPINIONS_FILE}`, `{DEAD_ENDS_JSON_FILE}`, or `{HUNCHES_FILE}`.\\n"\n'
    '        f"Also update `{HUNCHES_FILE}` with max {HUNCHES_LIMIT} words — raw intuitions, not theory.\\n\\n"'
)
if old_fail_files in content:
    content = content.replace(old_fail_files, new_fail_files, 1)
    changes += 1
    print("6. Added hunches to fail prompt")

# 7. Add hunches to grind allowed files (step 13)
old_grind_13 = '        f"13. Do not create any files other than `{SOLVER_FILE}`, `{OPINIONS_FILE}`, or `{DEAD_ENDS_JSON_FILE}`.\\n"'
new_grind_13 = '        f"13. Do not create any files other than `{SOLVER_FILE}`, `{OPINIONS_FILE}`, `{DEAD_ENDS_JSON_FILE}`, or `{HUNCHES_FILE}`.\\n"'
if old_grind_13 in content:
    content = content.replace(old_grind_13, new_grind_13, 1)
    changes += 1
    print("7. Updated allowed files list in grind")

# 8. Add hunches to PRESERVED_TOP_LEVEL if it exists
old_preserved = '    DEAD_END_STATE_FILE,'
# Already handled by gitignore entry above - PRESERVED_TOP_LEVEL might be a separate list
# Let's check for it
if 'PRESERVED_TOP_LEVEL' in content:
    old_pres = 'PRESERVED_TOP_LEVEL = {'
    # Find and add HUNCHES_FILE
    idx = content.find('PRESERVED_TOP_LEVEL')
    if idx != -1:
        # Find the closing brace
        end = content.find('}', idx)
        if end != -1:
            insert_pos = content.rfind(',', idx, end)
            if insert_pos != -1:
                content = content[:insert_pos+1] + '\n    HUNCHES_FILE,' + content[insert_pos+1:]
                changes += 1
                print("8. Added hunches to PRESERVED_TOP_LEVEL")

with open(path, "w") as f:
    f.write(content)

print(f"\nDone: {changes} patches applied")
