#!/usr/bin/env python3
"""Structured dead-end state helpers for Avalanche V4.4.1."""
from __future__ import annotations

import copy
import json
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


def blank_dead_ends() -> dict[str, list[dict[str, object]]]:
    return {"basins": [], "families": [], "locals": []}


def blank_state() -> dict[str, object]:
    return {
        "active": blank_dead_ends(),
        "registry": {"basins": {}, "families": {}, "arrays": {}},
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
