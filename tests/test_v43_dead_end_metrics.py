"""Regression tests for V4.3 dead-end family parsing and retention metrics."""

import v43_metrics


def test_parse_structured_dead_end_lines():
    text = (
        "# DEAD ENDS\n\n"
        "- [peak_gate|peak,equality] strict d<a gate -> [6,2,2,4,3]\n"
        "- [valley_split|valley,shape] valley always flips b,c -> [6,9,9,4,6,4,9]\n"
    )

    entries = v43_metrics.parse_dead_end_entries(text)

    assert [entry["family_id"] for entry in entries] == ["peak_gate", "valley_split"]
    assert entries[0]["ontology_tags"] == ["equality", "peak"]
    assert entries[1]["ontology_tags"] == ["shape", "valley"]


def test_parse_legacy_dead_end_lines_still_counts_families():
    text = (
        "# DEAD ENDS\n\n"
        "Global-prefix logic -> falsified by [5,3,8,6,2].\n"
        "Peak logic requiring only strict d<a -> falsified by [6,2,2,4,3].\n"
    )

    assert v43_metrics.dead_ends_count(text) == 2
    assert v43_metrics.dead_end_family_count(text) == 2


def test_parse_header_only_dead_end_line_preserves_family_id():
    text = "[one-contiguous-valley-tail-block] -> Falsified by `[2,1,3,9,8] -> [2,1,3,-9,8]`."

    entries = v43_metrics.parse_dead_end_entries(text)

    assert len(entries) == 1
    assert entries[0]["family_id"] == "one_contiguous_valley_tail_block"
    assert entries[0]["claim"] == "one-contiguous-valley-tail-block"


def test_dead_end_metrics_reports_retention_and_churn():
    previous = (
        "# DEAD ENDS\n\n"
        "- [peak_gate|peak,equality] strict d<a gate -> [6,2,2,4,3]\n"
        "- [global_prefix|prefix,global] global prefix rule -> [5,3,8,6,2]\n"
    )
    current = (
        "# DEAD ENDS\n\n"
        "- [peak_gate|peak,equality] strict d<a gate -> [6,2,2,4,3]\n"
        "- [valley_split|valley,shape] valley always flips b,c -> [6,9,9,4,6,4,9]\n"
    )

    metrics = v43_metrics.dead_end_metrics(previous, current)

    assert metrics["dead_ends_count"] == 2
    assert metrics["dead_end_family_count"] == 2
    assert metrics["dead_end_retained_family_count"] == 1
    assert metrics["dead_end_new_family_count"] == 1
    assert metrics["dead_end_lost_family_count"] == 1
    assert metrics["dead_end_family_retention"] == 0.5
    assert metrics["dead_end_ontology_count"] == 4
    assert metrics["dead_end_structured_count"] == 2
