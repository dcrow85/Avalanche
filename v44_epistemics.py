#!/usr/bin/env python3
"""Structured dead-end state helpers for Avalanche V4.4.1."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

STATUS_VALUES = {"ACTIVE", "SUPERSEDED"}
ACTIVEISH_STATUS = {"ACTIVE"}
FORBIDDEN_BASIN_CHARS = set("<>=[]+*/%(){}0123456789")
MAX_BASINS = 2
MAX_FAMILIES = 3
MAX_LOCALS = 4
MAX_BASIN_WORDS = 15
MAX_FAMILY_WORDS = 25
MAX_LOCAL_HYPOTHESIS_WORDS = 15
ANCHOR_REPLACEMENT_SYNONYMS = {
    "rank": {"rank", "sorted", "order"},
    "cycle": {"cycle", "orbit"},
    "inversion": {"inversion"},
    "adjacent": {"adjacent", "neighbor", "next"},
    "minimum": {"minimum", "min"},
    "threshold": {"threshold"},
    "value": {"value"},
}
ANCHOR_GENERIC_KEYWORDS = {
    "based",
    "negation",
    "determines",
    "comparison",
    "theory",
    "replacement",
    "basin",
    "element",
}


def blank_dead_ends() -> dict[str, list[dict[str, object]]]:
    return {"basins": [], "families": [], "locals": []}


def blank_anchor_lock() -> dict[str, object]:
    return {
        "active": False,
        "locked_basin_id": None,
        "locked_basin_hash": None,
        "replacement_theory_type": None,
        "lock_activated_cycle": None,
        "lock_cleared_cycle": None,
    }


def blank_anchor_ledger() -> dict[str, object]:
    return {
        "active": False,
        "baseline_cycle": None,
        "baseline_fixed_vector": [],
        "baseline_fixed_score": None,
        "last_cycle": None,
        "last_fixed_vector": [],
        "last_fixed_score": None,
        "positive_flip_counts": {},
        "negative_flip_counts": {},
        "coverage_cases": [],
        "recurring_positive_cases": [],
        "recurring_negative_cases": [],
        "ready_for_replacement": False,
    }


def blank_state() -> dict[str, object]:
    return {
        "active": blank_dead_ends(),
        "registry": {"basins": {}, "families": {}, "arrays": {}},
        "anchor_lock": blank_anchor_lock(),
        "anchor_ledger": blank_anchor_ledger(),
    }


def load_state(path: str) -> dict[str, object]:
    file_path = Path(path)
    if not file_path.exists():
        return blank_state()
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return blank_state()
    if not isinstance(payload, dict):
        return blank_state()
    state = blank_state()
    state.update(payload)
    registry = state.setdefault("registry", {})
    if isinstance(registry, dict):
        registry.setdefault("basins", {})
        registry.setdefault("families", {})
        registry.setdefault("arrays", {})
    anchor_lock = state.setdefault("anchor_lock", blank_anchor_lock())
    if isinstance(anchor_lock, dict):
        for key, value in blank_anchor_lock().items():
            anchor_lock.setdefault(key, value)
    else:
        state["anchor_lock"] = blank_anchor_lock()
    anchor_ledger = state.setdefault("anchor_ledger", blank_anchor_ledger())
    if isinstance(anchor_ledger, dict):
        for key, value in blank_anchor_ledger().items():
            anchor_ledger.setdefault(key, value)
    else:
        state["anchor_ledger"] = blank_anchor_ledger()
    return state


def save_state(path: str, state: dict[str, object]) -> None:
    Path(path).write_text(json.dumps(state, indent=2), encoding="utf-8")


def _word_count(text: str) -> int:
    return len((text or "").split())


def _collect_ids(items: list[dict[str, object]]) -> set[str]:
    return {str(item.get("id")) for item in items if item.get("id")}


def _normalize_id_list(payload: object) -> list[str]:
    if not isinstance(payload, list):
        return []
    normalized: list[str] = []
    for item in payload:
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _normalize_array(payload: object) -> list[int] | None:
    if not isinstance(payload, list) or not payload:
        return None
    normalized: list[int] = []
    for item in payload:
        if not isinstance(item, int):
            return None
        normalized.append(item)
    return normalized


def array_signature(arr: list[int]) -> str:
    return json.dumps(arr, separators=(",", ":"))


def _family_arrays(family: dict[str, object]) -> list[list[int]]:
    arrays = family.get("falsifying_arrays", [])
    if not isinstance(arrays, list):
        return []
    normalized: list[list[int]] = []
    for payload in arrays:
        arr = _normalize_array(payload)
        if arr is not None:
            normalized.append(arr)
    return normalized


def _local_array(local: dict[str, object]) -> list[int] | None:
    return _normalize_array(local.get("falsifying_array"))


def tracked_array_signatures(dead_ends: dict[str, list[dict[str, object]]]) -> set[str]:
    signatures: set[str] = set()
    for family in dead_ends.get("families", []):
        signatures.update(array_signature(arr) for arr in _family_arrays(family))
    for local in dead_ends.get("locals", []):
        arr = _local_array(local)
        if arr is not None:
            signatures.add(array_signature(arr))
    return signatures


def _find_item_by_id(items: list[dict[str, object]], item_id: str) -> dict[str, object] | None:
    for item in items:
        if str(item.get("id", "")) == item_id:
            return copy.deepcopy(item)
    return None


def _locked_basin_bundle(
    dead_ends: dict[str, list[dict[str, object]]],
    basin_id: str,
) -> dict[str, object] | None:
    basin = _find_item_by_id(dead_ends.get("basins", []), basin_id)
    if basin is None:
        return None
    cited_ids = _normalize_id_list(basin.get("cited_families", []))
    families = [
        family
        for family_id in sorted(cited_ids)
        if (family := _find_item_by_id(dead_ends.get("families", []), family_id)) is not None
    ]
    return {
        "basin": basin,
        "families": families,
    }


def compute_basin_lock_hash_from_dead_ends(
    dead_ends: dict[str, list[dict[str, object]]],
    basin_id: str,
) -> str | None:
    bundle = _locked_basin_bundle(dead_ends, basin_id)
    if bundle is None:
        return None
    canonical = json.dumps(bundle, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def activate_anchor_lock(
    state: dict[str, object],
    *,
    locked_basin_id: str,
    replacement_theory_type: str,
    cycle: int,
) -> dict[str, object]:
    merged = copy.deepcopy(state)
    anchor_lock = merged.setdefault("anchor_lock", blank_anchor_lock())
    if not isinstance(anchor_lock, dict):
        anchor_lock = blank_anchor_lock()
        merged["anchor_lock"] = anchor_lock
    if anchor_lock.get("active"):
        return merged
    active = merged.get("active", blank_dead_ends())
    if not isinstance(active, dict):
        active = blank_dead_ends()
        merged["active"] = active
    locked_hash = compute_basin_lock_hash_from_dead_ends(active, locked_basin_id)
    if locked_hash is None:
        raise ValueError(f"Cannot activate anchor lock: basin `{locked_basin_id}` is not present.")
    anchor_lock.update(
        {
            "active": True,
            "locked_basin_id": locked_basin_id,
            "locked_basin_hash": locked_hash,
            "replacement_theory_type": replacement_theory_type,
            "lock_activated_cycle": cycle,
            "lock_cleared_cycle": None,
        }
    )
    return merged


def anchor_lock_status_fields(state: dict[str, object]) -> dict[str, object]:
    anchor_lock = state.get("anchor_lock", {})
    if not isinstance(anchor_lock, dict):
        anchor_lock = blank_anchor_lock()
    if anchor_lock.get("active"):
        status = "unclosed"
    elif anchor_lock.get("lock_cleared_cycle") is not None:
        status = "cleared"
    else:
        status = "inactive"
    return {
        "anchor_lock_status": status,
        "locked_basin_id": anchor_lock.get("locked_basin_id"),
        "replacement_theory_type": anchor_lock.get("replacement_theory_type"),
        "lock_activated_cycle": anchor_lock.get("lock_activated_cycle"),
        "lock_cleared_cycle": anchor_lock.get("lock_cleared_cycle"),
    }


def _anchor_lock_content_snippet(previous_active: dict[str, list[dict[str, object]]], basin_id: str) -> str:
    bundle = _locked_basin_bundle(previous_active, basin_id)
    if bundle is None:
        return "{}"
    return json.dumps(bundle, sort_keys=True, ensure_ascii=True)


def _replacement_keywords(replacement_theory_type: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[a-z]+", replacement_theory_type.lower())
        if token and token not in ANCHOR_GENERIC_KEYWORDS
    }
    keywords: set[str] = set()
    for token in tokens:
        keywords.update(ANCHOR_REPLACEMENT_SYNONYMS.get(token, {token}))
    return keywords or tokens


def _replacement_matches_theory_type(
    dead_ends: dict[str, list[dict[str, object]]],
    replacement_basins: list[dict[str, object]],
    replacement_theory_type: str,
) -> bool:
    keywords = _replacement_keywords(replacement_theory_type)
    if not keywords:
        return True
    text_parts: list[str] = []
    for basin in replacement_basins:
        text_parts.append(str(basin.get("claim", "")))
        for family_id in _normalize_id_list(basin.get("cited_families", [])):
            family = _find_item_by_id(dead_ends.get("families", []), family_id)
            if family is not None:
                text_parts.append(str(family.get("claim", "")))
    replacement_text = " ".join(text_parts).lower()
    return any(keyword in replacement_text for keyword in keywords)


def _validate_anchor_lock(
    dead_ends: dict[str, list[dict[str, object]]],
    previous_active: dict[str, list[dict[str, object]]],
    state: dict[str, object],
) -> list[str]:
    anchor_lock = state.get("anchor_lock", {})
    if not isinstance(anchor_lock, dict) or not anchor_lock.get("active"):
        return []
    locked_basin_id = str(anchor_lock.get("locked_basin_id", "") or "")
    locked_hash = str(anchor_lock.get("locked_basin_hash", "") or "")
    replacement_theory_type = str(anchor_lock.get("replacement_theory_type", "") or "")
    if not locked_basin_id or not locked_hash:
        return []

    locked_basin = _find_item_by_id(dead_ends.get("basins", []), locked_basin_id)
    if locked_basin is None:
        return []

    replacement_basins = [
        basin
        for basin in dead_ends.get("basins", [])
        if str(basin.get("id", "")) != locked_basin_id and str(basin.get("status", "ACTIVE")) == "ACTIVE"
    ]
    locked_content = _anchor_lock_content_snippet(previous_active, locked_basin_id)

    if str(locked_basin.get("status", "ACTIVE")) == "SUPERSEDED":
        if not replacement_basins:
            return [
                "ANCHOR_LOCK_VIOLATION: "
                f"Locked basin {locked_basin_id} superseded without replacement. "
                "Assembly Gap prevented. Supersession requires concurrent replacement basin registration. "
                f"Locked content: {locked_content}"
            ]
        if not _replacement_matches_theory_type(dead_ends, replacement_basins, replacement_theory_type):
            return [
                "ANCHOR_LOCK_VIOLATION: "
                f'Replacement basin does not match designated replacement theory type "{replacement_theory_type}". '
                "Supersession rejected. Original locked basin restored. "
                f"Locked content: {locked_content}"
            ]
        return []

    current_hash = compute_basin_lock_hash_from_dead_ends(dead_ends, locked_basin_id)
    if current_hash != locked_hash:
        return [
            "ANCHOR_LOCK_VIOLATION: "
            f"Locked basin {locked_basin_id} content modified without supersession-with-replacement. "
            "Hash mismatch detected. Revert to locked content. "
            f"Locked content: {locked_content}"
        ]
    return []


def validate_dead_ends(
    dead_ends: dict[str, list[dict[str, object]]],
    previous_active: dict[str, list[dict[str, object]]],
    state: dict[str, object],
) -> list[str]:
    errors: list[str] = []
    basins = dead_ends.get("basins", [])
    families = dead_ends.get("families", [])
    locals_ = dead_ends.get("locals", [])

    if len(basins) > MAX_BASINS:
        errors.append(f"Too many basins ({len(basins)} > {MAX_BASINS}).")
    if len(families) > MAX_FAMILIES:
        errors.append(f"Too many families ({len(families)} > {MAX_FAMILIES}).")
    if len(locals_) > MAX_LOCALS:
        errors.append(f"Too many locals ({len(locals_)} > {MAX_LOCALS}).")

    current_family_ids = _collect_ids(families)
    seen_ids: set[str] = set()
    tracked_arrays: list[str] = []

    for basin in basins:
        basin_id = str(basin.get("id", ""))
        claim = str(basin.get("claim", basin.get("paradigm_banned", "")))
        status = str(basin.get("status", ""))
        cited = basin.get("cited_families", [])
        if not basin_id:
            errors.append("Basin entry missing id.")
        elif basin_id in seen_ids:
            errors.append(f"Duplicate basin id `{basin_id}`.")
        seen_ids.add(basin_id)
        if status not in STATUS_VALUES:
            errors.append(f"Basin `{basin_id}` has invalid status `{status}`.")
        if not claim:
            errors.append(f"Basin `{basin_id}` is missing claim.")
        if _word_count(claim) > MAX_BASIN_WORDS:
            errors.append(f"Basin `{basin_id}` exceeds {MAX_BASIN_WORDS} words.")
        if any(char in FORBIDDEN_BASIN_CHARS for char in claim):
            errors.append(f"Basin `{basin_id}` violates the syntax firewall.")
        normalized_cited = _normalize_id_list(cited)
        if not isinstance(cited, list) or len(normalized_cited) < 2:
            errors.append(f"Basin `{basin_id}` must cite at least 2 family ids.")
        else:
            missing = [family_id for family_id in normalized_cited if family_id not in current_family_ids]
            if missing:
                errors.append(f"Basin `{basin_id}` cites unknown family ids: {', '.join(missing)}.")

    for family in families:
        family_id = str(family.get("id", ""))
        claim = str(family.get("claim", family.get("mechanism_banned", "")))
        status = str(family.get("status", ""))
        arrays = _family_arrays(family)
        if not family_id:
            errors.append("Family entry missing id.")
        elif family_id in seen_ids:
            errors.append(f"Duplicate family id `{family_id}`.")
        seen_ids.add(family_id)
        if status not in STATUS_VALUES:
            errors.append(f"Family `{family_id}` has invalid status `{status}`.")
        if not claim:
            errors.append(f"Family `{family_id}` is missing claim.")
        if _word_count(claim) > MAX_FAMILY_WORDS:
            errors.append(f"Family `{family_id}` exceeds {MAX_FAMILY_WORDS} words.")
        if len(arrays) < 2:
            errors.append(f"Family `{family_id}` must cite at least 2 falsifying arrays.")
        family_signatures = [array_signature(arr) for arr in arrays]
        if len(set(family_signatures)) != len(family_signatures):
            errors.append(f"Family `{family_id}` repeats the same falsifying array.")
        tracked_arrays.extend(family_signatures)

    for index, local in enumerate(locals_, start=1):
        hypothesis = str(local.get("failing_hypothesis", ""))
        local_label = f"L{index}"
        if not hypothesis:
            errors.append(f"Local `{local_label}` is missing failing_hypothesis.")
        if _word_count(hypothesis) > MAX_LOCAL_HYPOTHESIS_WORDS:
            errors.append(f"Local `{local_label}` exceeds {MAX_LOCAL_HYPOTHESIS_WORDS} words.")
        arr = _local_array(local)
        if arr is None:
            errors.append(f"Local `{local_label}` must include one falsifying_array of integers.")
        else:
            tracked_arrays.append(array_signature(arr))

    if len(set(tracked_arrays)) != len(tracked_arrays):
        errors.append("Tracked falsifying arrays must all be distinct across families and locals.")

    for tier in ("basins", "families"):
        previous_items = previous_active.get(tier, [])
        current_ids = _collect_ids(dead_ends.get(tier, []))
        for item in previous_items:
            if str(item.get("status", "ACTIVE")) not in ACTIVEISH_STATUS:
                continue
            item_id = str(item.get("id", ""))
            if item_id and item_id not in current_ids:
                errors.append(
                    f"[LINTER ERROR: CRITICAL MEMORY LOSS] {tier[:-1].capitalize()} ID `{item_id}` illegally dropped."
                )

    if not errors:
        errors.extend(_validate_anchor_lock(dead_ends, previous_active, state))

    return errors


def merge_state(
    state: dict[str, object],
    dead_ends: dict[str, list[dict[str, object]]],
    cycle: int,
) -> dict[str, object]:
    merged = copy.deepcopy(state)
    merged["active"] = dead_ends
    registry = merged.setdefault("registry", {"basins": {}, "families": {}, "arrays": {}})
    assert isinstance(registry, dict)

    for tier in ("basins", "families"):
        tier_registry = registry.setdefault(tier, {})
        assert isinstance(tier_registry, dict)
        for item in dead_ends.get(tier, []):
            item_id = str(item.get("id", ""))
            if not item_id:
                continue
            prior = tier_registry.get(item_id, {})
            if not isinstance(prior, dict):
                prior = {}
            tier_registry[item_id] = {
                "item": item,
                "first_seen_cycle": prior.get("first_seen_cycle", cycle),
                "last_seen_cycle": cycle,
                "seen_count": int(prior.get("seen_count", 0)) + 1,
            }

    arrays_registry = registry.setdefault("arrays", {})
    assert isinstance(arrays_registry, dict)
    for signature in tracked_array_signatures(dead_ends):
        prior = arrays_registry.get(signature, {})
        if not isinstance(prior, dict):
            prior = {}
        arrays_registry[signature] = {
            "array": json.loads(signature),
            "first_seen_cycle": prior.get("first_seen_cycle", cycle),
            "last_seen_cycle": cycle,
            "seen_count": int(prior.get("seen_count", 0)) + 1,
        }

    anchor_lock = merged.setdefault("anchor_lock", blank_anchor_lock())
    if not isinstance(anchor_lock, dict):
        anchor_lock = blank_anchor_lock()
        merged["anchor_lock"] = anchor_lock
    if anchor_lock.get("active"):
        locked_basin_id = str(anchor_lock.get("locked_basin_id", "") or "")
        replacement_theory_type = str(anchor_lock.get("replacement_theory_type", "") or "")
        locked_basin = _find_item_by_id(dead_ends.get("basins", []), locked_basin_id) if locked_basin_id else None
        replacement_basins = [
            basin
            for basin in dead_ends.get("basins", [])
            if str(basin.get("id", "")) != locked_basin_id and str(basin.get("status", "ACTIVE")) == "ACTIVE"
        ]
        if (
            locked_basin is not None
            and str(locked_basin.get("status", "ACTIVE")) == "SUPERSEDED"
            and replacement_basins
            and _replacement_matches_theory_type(dead_ends, replacement_basins, replacement_theory_type)
        ):
            anchor_lock["active"] = False
            anchor_lock["lock_cleared_cycle"] = cycle

    return merged


def render_dead_ends_md(dead_ends: dict[str, list[dict[str, object]]]) -> str:
    lines = ["# DEAD ENDS", ""]
    basin_items = dead_ends.get("basins", [])
    family_items = dead_ends.get("families", [])
    local_items = dead_ends.get("locals", [])

    lines.append("## Basin")
    if basin_items:
        for basin in basin_items:
            cited = ",".join(str(item) for item in basin.get("cited_families", []))
            basin_id = str(basin.get("id", "?"))
            status = str(basin.get("status", "?"))
            claim = str(basin.get("claim", basin.get("paradigm_banned", "?")))
            lines.append(f"- [{basin_id}|{status}] {claim} -> cites {cited or '?'}")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## Family")
    if family_items:
        for family in family_items:
            family_id = str(family.get("id", "?"))
            status = str(family.get("status", "?"))
            claim = str(family.get("claim", family.get("mechanism_banned", "?")))
            arrays = _family_arrays(family)
            preview = "; ".join(array_signature(arr) for arr in arrays[:2])
            lines.append(f"- [{family_id}|{status}] {claim} -> arrays {preview or '?'}")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## Local")
    if local_items:
        for index, local in enumerate(local_items, start=1):
            hypothesis = str(local.get("failing_hypothesis", local.get("claim", "?")))
            arr = _local_array(local)
            rendered = array_signature(arr) if arr is not None else "?"
            lines.append(f"- [L{index}] {hypothesis} -> {rendered}")
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def history_summary(state: dict[str, object]) -> str:
    registry = state.get("registry", {})
    if not isinstance(registry, dict):
        return "No historical dead-end ids yet."
    parts: list[str] = []
    for tier in ("basins", "families"):
        tier_map = registry.get(tier, {})
        if isinstance(tier_map, dict) and tier_map:
            parts.append(f"{tier}: {', '.join(sorted(tier_map.keys()))}")
    arrays_map = registry.get("arrays", {})
    if isinstance(arrays_map, dict) and arrays_map:
        parts.append(f"arrays: {len(arrays_map)}")
    return " | ".join(parts) if parts else "No historical dead-end ids yet."


def detect_work_event(
    previous_active: dict[str, list[dict[str, object]]],
    current_active: dict[str, list[dict[str, object]]],
) -> bool:
    """Return True if a structurally meaningful change occurred in dead-end state.

    Triggers on:
      - New basin/family ID appeared
      - Existing basin/family was superseded (status ACTIVE → SUPERSEDED)
      - Existing basin/family was fossilized (present before, absent now)
    Does NOT trigger on local changes alone (too noisy).
    """
    prev_basin_ids = _collect_ids(previous_active.get("basins", []))
    curr_basin_ids = _collect_ids(current_active.get("basins", []))
    prev_family_ids = _collect_ids(previous_active.get("families", []))
    curr_family_ids = _collect_ids(current_active.get("families", []))

    # New basin or family appeared
    if curr_basin_ids - prev_basin_ids or curr_family_ids - prev_family_ids:
        return True

    # Basin or family was fossilized (disappeared from active surface entirely)
    if prev_basin_ids - curr_basin_ids or prev_family_ids - curr_family_ids:
        return True

    # Basin or family was superseded (status changed from ACTIVE to SUPERSEDED)
    for tier_key in ("basins", "families"):
        prev_items = {str(item.get("id", "")): item for item in previous_active.get(tier_key, []) if item.get("id")}
        curr_items = {str(item.get("id", "")): item for item in current_active.get(tier_key, []) if item.get("id")}
        for item_id in prev_items:
            if item_id in curr_items:
                prev_status = str(prev_items[item_id].get("status", "ACTIVE"))
                curr_status = str(curr_items[item_id].get("status", "ACTIVE"))
                if prev_status == "ACTIVE" and curr_status == "SUPERSEDED":
                    return True

    return False


SUPERSEDED_LOG_FILE = "superseded_theories.jsonl"


def compress_dead_ends_for_prompt(
    dead_ends_json: str,
    *,
    max_entries: int | None = None,
) -> tuple[str, int, int, int]:
    """Compress SUPERSEDED theories to single-line summaries for prompt injection.

    ACTIVE entries remain fully expanded. SUPERSEDED basins/families are reduced
    to a one-line summary. Locals (no status) are always fully rendered unless
    prompt thinning requires them to be dropped.

    Args:
        dead_ends_json: Raw JSON string of the dead-ends structure.
        max_entries: If set, limit total rendered entries. Thinning is priority
            ordered: archived summaries drop first, then locals, then active
            families, then active basins last. Within each tier, preserve the
            most recent (last in list). Minimum 3.

    Returns:
        (compressed_text, active_count, archived_count, estimated_tokens_saved)
    """
    try:
        dead_ends = json.loads(dead_ends_json) if dead_ends_json else {}
    except json.JSONDecodeError:
        dead_ends = {}

    active_basins = []
    archived_basins = []
    for basin in dead_ends.get("basins", []):
        if str(basin.get("status", "ACTIVE")) == "SUPERSEDED":
            archived_basins.append(basin)
        else:
            active_basins.append(basin)

    active_families = []
    archived_families = []
    for family in dead_ends.get("families", []):
        if str(family.get("status", "ACTIVE")) == "SUPERSEDED":
            archived_families.append(family)
        else:
            active_families.append(family)

    locals_ = dead_ends.get("locals", [])

    # Graveyard thinning: protect the live hierarchy and drop expendable material first.
    if max_entries is not None:
        cap = max(3, max_entries)
        rendered_count = (
            len(active_basins)
            + len(active_families)
            + len(locals_)
            + len(archived_basins)
            + len(archived_families)
        )
        overflow = rendered_count - cap

        def _drop_oldest(items: list[dict], count: int) -> tuple[list[dict], int]:
            if count <= 0 or not items:
                return items, count
            drop = min(len(items), count)
            return items[drop:], count - drop

        if overflow > 0:
            archived_basins, overflow = _drop_oldest(archived_basins, overflow)
        if overflow > 0:
            archived_families, overflow = _drop_oldest(archived_families, overflow)
        if overflow > 0:
            locals_, overflow = _drop_oldest(locals_, overflow)
        if overflow > 0:
            active_families, overflow = _drop_oldest(active_families, overflow)
        if overflow > 0:
            active_basins, overflow = _drop_oldest(active_basins, overflow)

    active_count = len(active_basins) + len(active_families)
    archived_count = len(archived_basins) + len(archived_families)

    # Build the active-only JSON (full detail)
    active_de = {
        "basins": active_basins,
        "families": active_families,
        "locals": locals_,
    }
    active_json = json.dumps(active_de, indent=2)

    # Build archived summaries (one line each)
    archived_lines = []
    for basin in archived_basins:
        bid = str(basin.get("id", "?"))
        claim = str(basin.get("claim", "?"))
        archived_lines.append(f"[SUPERSEDED] basin {bid}: {claim}")
    for family in archived_families:
        fid = str(family.get("id", "?"))
        claim = str(family.get("claim", "?"))
        archived_lines.append(f"[SUPERSEDED] family {fid}: {claim}")

    # Estimate tokens saved
    original_len = len(dead_ends_json) if dead_ends_json else 0
    compressed_len = len(active_json) + sum(len(line) for line in archived_lines)
    tokens_saved = max(0, (original_len - compressed_len) // 4)

    # Assemble
    header = f"[ACTIVE_THEORIES: {active_count} | ARCHIVED: {archived_count} | TOKENS_SAVED: ~{tokens_saved}]"
    parts = [header, active_json]
    if archived_lines:
        parts.append("")
        parts.append("# Archived (superseded, compressed):")
        parts.extend(archived_lines)

    compressed_text = "\n".join(parts)
    return compressed_text, active_count, archived_count, tokens_saved


def log_superseded_theories(dead_ends: dict, log_path: str) -> None:
    """Append full SUPERSEDED entries to a JSONL file for post-run analysis."""
    from datetime import datetime, timezone
    superseded = []
    for basin in dead_ends.get("basins", []):
        if str(basin.get("status", "ACTIVE")) == "SUPERSEDED":
            superseded.append({"tier": "basin", **basin})
    for family in dead_ends.get("families", []):
        if str(family.get("status", "ACTIVE")) == "SUPERSEDED":
            superseded.append({"tier": "family", **family})
    if superseded:
        with open(log_path, "a", encoding="utf-8", newline="\n") as f:
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "entries": superseded,
            }
            f.write(json.dumps(record) + "\n")


def dead_end_metrics(
    previous_active: dict[str, list[dict[str, object]]],
    current_active: dict[str, list[dict[str, object]]],
    state: dict[str, object],
) -> dict[str, object]:
    previous_basin_ids = _collect_ids(previous_active.get("basins", []))
    current_basin_ids = _collect_ids(current_active.get("basins", []))
    previous_family_ids = _collect_ids(previous_active.get("families", []))
    current_family_ids = _collect_ids(current_active.get("families", []))
    current_locals = current_active.get("locals", [])

    promotions = len(current_basin_ids - previous_basin_ids) + len(current_family_ids - previous_family_ids)

    registry = state.get("registry", {})
    total_historical_arrays = 0
    basin_tenures: list[int] = []
    if isinstance(registry, dict):
        arrays_registry = registry.get("arrays", {})
        if isinstance(arrays_registry, dict):
            total_historical_arrays = len(arrays_registry)
        basins_registry = registry.get("basins", {})
        if isinstance(basins_registry, dict):
            for basin_id in current_basin_ids:
                record = basins_registry.get(basin_id, {})
                if isinstance(record, dict):
                    first_seen = int(record.get("first_seen_cycle", 0))
                    last_seen = int(record.get("last_seen_cycle", 0))
                    if first_seen and last_seen:
                        basin_tenures.append(last_seen - first_seen + 1)

    family_retention = 1.0 if not previous_family_ids else len(previous_family_ids & current_family_ids) / len(previous_family_ids)
    basin_retention = 1.0 if not previous_basin_ids else len(previous_basin_ids & current_basin_ids) / len(previous_basin_ids)
    compression_ratio = 0.0
    active_compression_base = len(current_locals) + len(current_active.get("families", []))
    if active_compression_base > 0:
        compression_ratio = total_historical_arrays / active_compression_base

    return {
        "dead_ends_count": len(current_active.get("basins", [])) + len(current_active.get("families", [])) + len(current_locals),
        "dead_end_basin_count": len(current_active.get("basins", [])),
        "dead_end_family_count": len(current_active.get("families", [])),
        "dead_end_local_count": len(current_locals),
        "dead_end_family_retention": round(family_retention, 4),
        "dead_end_basin_retention": round(basin_retention, 4),
        "dead_end_ontology_count": len(current_active.get("basins", [])),
        "ontology_migration_rate": promotions,
        "compression_ratio": round(compression_ratio, 4),
        "basin_tenure": round(sum(basin_tenures) / len(basin_tenures), 4) if basin_tenures else 0.0,
    }
