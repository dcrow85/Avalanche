"""Patch Claude hypervisor to write full dead-end graveyard (active + superseded) to dead-ends.json after merge."""
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "hypervisor_v44_claude.py"

with open(path, "r") as f:
    content = f.read()

changes = 0

# 1. Add a function to reconstruct full dead-ends from registry
# Insert after _save_dead_ends function
old_save = '''def _save_dead_ends(dead_ends: dict[str, list[dict[str, object]]]) -> None:
    write_json(DEAD_ENDS_JSON_FILE, dead_ends)
    write_text(DEAD_ENDS_FILE, render_dead_ends_md(dead_ends))'''

new_save = '''def _save_dead_ends(dead_ends: dict[str, list[dict[str, object]]]) -> None:
    write_json(DEAD_ENDS_JSON_FILE, dead_ends)
    write_text(DEAD_ENDS_FILE, render_dead_ends_md(dead_ends))


def _full_dead_ends_from_state(state: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    """Reconstruct dead-ends.json with active + superseded entries from registry.

    Without this, the agent only sees active entries and loses memory of
    superseded families, making it impossible to build basin-level hierarchy.
    """
    active = state.get("active", {})
    if not isinstance(active, dict):
        active = blank_dead_ends()

    # Start with active entries
    full_basins = list(active.get("basins", []))
    full_families = list(active.get("families", []))
    full_locals = list(active.get("locals", []))

    # Collect IDs already present
    active_basin_ids = {str(b.get("id", "")) for b in full_basins}
    active_family_ids = {str(f.get("id", "")) for f in full_families}

    # Add superseded entries from registry
    registry = state.get("registry", {})
    if isinstance(registry, dict):
        for tier, active_ids, target_list in [
            ("basins", active_basin_ids, full_basins),
            ("families", active_family_ids, full_families),
        ]:
            tier_map = registry.get(tier, {})
            if isinstance(tier_map, dict):
                for item_id, record in tier_map.items():
                    if item_id not in active_ids and isinstance(record, dict):
                        item = record.get("item", {})
                        if isinstance(item, dict) and item.get("status") == "SUPERSEDED":
                            target_list.append(item)

    return {"basins": full_basins, "families": full_families, "locals": full_locals}


def _persist_full_dead_ends(state: dict[str, object]) -> None:
    """Write dead-ends.json with full graveyard visibility."""
    full = _full_dead_ends_from_state(state)
    _save_dead_ends(full)'''

if old_save in content:
    content = content.replace(old_save, new_save, 1)
    changes += 1
    print("1. Added _full_dead_ends_from_state and _persist_full_dead_ends functions")

# 2. After merge_state + save_state in the PASS path, persist full dead ends
old_pass = '''            current_state = merge_state(previous_state, current_dead_ends, cycle)
            save_state(DEAD_END_STATE_FILE, current_state)
            run_command('git add . && git commit -m "Avalanche: V4.4 Claude ratchet advanced"')'''

new_pass = '''            current_state = merge_state(previous_state, current_dead_ends, cycle)
            save_state(DEAD_END_STATE_FILE, current_state)
            _persist_full_dead_ends(current_state)
            run_command('git add . && git commit -m "Avalanche: V4.4 Claude ratchet advanced"')'''

if old_pass in content:
    content = content.replace(old_pass, new_pass, 1)
    changes += 1
    print("2. Added full dead-end persist after PASS merge")

# 3. After merge_state + save_state in the FAIL path, persist full dead ends
old_fail = '''        current_dead_ends = _load_dead_ends_json()
        current_state = merge_state(previous_state, current_dead_ends, cycle)
        save_state(DEAD_END_STATE_FILE, current_state)
        metrics = compute_cycle_metrics(
            cycle,
            previous_opinions,
            previous_state,
            current_state,'''

new_fail = '''        current_dead_ends = _load_dead_ends_json()
        current_state = merge_state(previous_state, current_dead_ends, cycle)
        save_state(DEAD_END_STATE_FILE, current_state)
        _persist_full_dead_ends(current_state)
        metrics = compute_cycle_metrics(
            cycle,
            previous_opinions,
            previous_state,
            current_state,'''

if old_fail in content:
    content = content.replace(old_fail, new_fail, 1)
    changes += 1
    print("3. Added full dead-end persist after FAIL merge")

with open(path, "w") as f:
    f.write(content)

print(f"\nDone: {changes}/3 patches applied")
