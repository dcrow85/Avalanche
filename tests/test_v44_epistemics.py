"""Regression tests for Avalanche V4.4 epistemic state helpers."""

import v44_epistemics


def valid_dead_ends():
    return {
        "basins": [
            {
                "id": "B1",
                "status": "ACTIVE",
                "claim": "local topology and extrema anchors",
                "cited_families": ["F1", "F2"],
            }
        ],
        "families": [
            {
                "id": "F1",
                "status": "ACTIVE",
                "claim": "Anchor on global minimum and mutate neighbors",
                "falsifying_arrays": [[2, 1, 3], [4, 1, 3, 2]],
            },
            {
                "id": "F2",
                "status": "ACTIVE",
                "claim": "Flip alternating runs after a rebound",
                "falsifying_arrays": [[3, 1, 2], [5, 2, 4, 1]],
            },
        ],
        "locals": [
            {"failing_hypothesis": "flip even prefix sums", "falsifying_array": [1, 2, 6]},
            {"failing_hypothesis": "alternate on runs", "falsifying_array": [6, 2, 1, 4]},
        ],
    }


def test_validate_dead_ends_accepts_valid_pyramid():
    previous_state = v44_epistemics.blank_state()
    errors = v44_epistemics.validate_dead_ends(valid_dead_ends(), previous_state["active"], previous_state)
    assert errors == []


def test_validate_dead_ends_rejects_dropped_active_basin():
    previous_state = v44_epistemics.blank_state()
    previous_state = v44_epistemics.merge_state(previous_state, valid_dead_ends(), cycle=3)
    current = valid_dead_ends()
    current["basins"] = []

    errors = v44_epistemics.validate_dead_ends(current, previous_state["active"], previous_state)

    assert any("CRITICAL MEMORY LOSS" in error for error in errors)


def test_validate_dead_ends_rejects_invalid_status():
    payload = valid_dead_ends()
    payload["basins"][0]["status"] = "WEAKENED"

    errors = v44_epistemics.validate_dead_ends(payload, v44_epistemics.blank_dead_ends(), v44_epistemics.blank_state())

    assert any("invalid status" in error for error in errors)


def test_validate_dead_ends_rejects_duplicate_tracked_arrays():
    payload = valid_dead_ends()
    payload["locals"][0]["falsifying_array"] = [2, 1, 3]

    errors = v44_epistemics.validate_dead_ends(payload, v44_epistemics.blank_dead_ends(), v44_epistemics.blank_state())

    assert any("must all be distinct" in error for error in errors)


def test_validate_dead_ends_requires_empirical_span_per_family():
    payload = valid_dead_ends()
    payload["families"][0]["falsifying_arrays"] = [[9, 9, 2, 3, 7, 4, 5, 1]]

    errors = v44_epistemics.validate_dead_ends(payload, v44_epistemics.blank_dead_ends(), v44_epistemics.blank_state())

    assert any("at least 2 falsifying arrays" in error for error in errors)


def test_merge_state_and_metrics_track_history():
    state = v44_epistemics.blank_state()
    first = valid_dead_ends()
    state = v44_epistemics.merge_state(state, first, cycle=2)

    second = valid_dead_ends()
    second["locals"] = [
        {"failing_hypothesis": "new parity rule", "falsifying_array": [4, 1, 7]}
    ]
    second["families"][0]["falsifying_arrays"] = [[2, 1, 3], [4, 1, 7]]
    second["families"][1]["falsifying_arrays"] = [[3, 1, 2], [5, 2, 4, 1]]
    state = v44_epistemics.merge_state(state, second, cycle=3)

    metrics = v44_epistemics.dead_end_metrics(first, second, state)

    assert metrics["dead_end_basin_count"] == 1
    assert metrics["dead_end_family_count"] == 2
    assert metrics["dead_end_local_count"] == 1
    assert metrics["compression_ratio"] > 0
    assert metrics["basin_tenure"] >= 2
