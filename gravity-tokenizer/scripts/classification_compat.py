"""Compatibility helpers for phase-space class labels."""
from __future__ import annotations

from typing import Any

QUIESCENT_CLASS = "QUIESCENT"
QUIESCENT_ALIASES = frozenset({"GRADUATED", QUIESCENT_CLASS})


def normalize_classification(classification: str | None) -> str:
    if classification in QUIESCENT_ALIASES:
        return QUIESCENT_CLASS
    return str(classification or "")


def is_quiescent_classification(classification: str | None) -> bool:
    return normalize_classification(classification) == QUIESCENT_CLASS


def remap_class_counts(class_counts: dict[str, Any] | None) -> dict[str, Any]:
    counts = dict(class_counts or {})
    quiet_count = int(counts.pop("GRADUATED", 0)) + int(counts.get(QUIESCENT_CLASS, 0))
    if quiet_count:
        counts[QUIESCENT_CLASS] = quiet_count
    return counts


def normalize_phase_space_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                row["classification"] = normalize_classification(row.get("classification"))
    if "class_counts" in payload:
        payload["class_counts"] = remap_class_counts(payload.get("class_counts"))
    return payload
