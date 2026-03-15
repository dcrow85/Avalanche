"""Add JSON-only reinforcement to sync-fail mode instruction."""
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "hypervisor_v44.py"

with open(path, "r") as f:
    content = f.read()

old = '''    else:
        instruction = (
            "Build verification failed.\\n"
            f"{failure_report or ''}\\n\\n"
            "All code changes have been reverted by the environment.\\n"
            "Return:\\n"
            "- revised opinions_md with a specific next hypothesis\\n"
            "- revised dead_ends preserving active basin/family ids or explicitly superseding them\\n"
            "- solver_py containing your next best implementation attempt\\n"
            f"Constraints remain:\\n{common_constraints}"
        )'''

new = '''    else:
        instruction = (
            "Build verification failed.\\n"
            f"{failure_report or ''}\\n\\n"
            "All code changes have been reverted by the environment.\\n"
            "IMPORTANT: Respond with ONLY a raw JSON object. No analysis, no reasoning, no markdown.\\n"
            "Return the JSON object with keys opinions_md, dead_ends, solver_py containing:\\n"
            "- revised opinions_md with a specific next hypothesis\\n"
            "- revised dead_ends preserving active basin/family ids or explicitly superseding them\\n"
            "- solver_py containing your next best implementation attempt\\n"
            f"Constraints remain:\\n{common_constraints}"
        )'''

if old in content:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    print("OK: sync-fail prompt reinforced")
else:
    print("ERROR: target text not found")
    sys.exit(1)
