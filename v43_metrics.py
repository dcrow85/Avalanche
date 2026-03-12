#!/usr/bin/env python3
"""Deterministic telemetry and oracle helpers for Avalanche V4.3."""
from __future__ import annotations

import ast
import collections
import math
import random
import re
from typing import Callable

try:
    from nltk.stem import PorterStemmer as _NltkPorterStemmer  # type: ignore
except ImportError:
    _NltkPorterStemmer = None


STOPWORDS = {
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "also",
    "am",
    "an",
    "and",
    "any",
    "are",
    "array",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "could",
    "current",
    "did",
    "do",
    "does",
    "doing",
    "down",
    "during",
    "each",
    "element",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "hypothesis",
    "i",
    "if",
    "in",
    "index",
    "input",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "just",
    "list",
    "me",
    "more",
    "most",
    "my",
    "myself",
    "negative",
    "no",
    "nor",
    "not",
    "number",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "our",
    "ours",
    "ourselves",
    "out",
    "output",
    "over",
    "own",
    "positive",
    "return",
    "rule",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "theory",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "value",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "will",
    "with",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
}

TOKEN_RE = re.compile(r"\b[a-z]{3,}\b")
DEFAULT_PINK_WINDOW = 8
TARGET_AST_NODES = (
    ast.If,
    ast.For,
    ast.While,
    ast.BoolOp,
    ast.IfExp,
    ast.ListComp,
    ast.DictComp,
    ast.SetComp,
    ast.GeneratorExp,
)
ONTOLOGY_KEYWORDS = {
    "anchor",
    "block",
    "descent",
    "equality",
    "global",
    "index",
    "local",
    "minimum",
    "monotone",
    "peak",
    "penultimate",
    "position",
    "prefix",
    "rebound",
    "run",
    "scan",
    "segment",
    "shape",
    "suffix",
    "valley",
}


class _FallbackStemmer:
    """Small deterministic fallback when nltk is unavailable."""

    SUFFIXES = (
        "ization",
        "ational",
        "fulness",
        "ousness",
        "iveness",
        "tional",
        "biliti",
        "lessli",
        "entli",
        "ation",
        "alism",
        "aliti",
        "ousli",
        "iviti",
        "fulli",
        "enci",
        "anci",
        "izer",
        "ator",
        "alli",
        "bli",
        "ogi",
        "li",
        "ing",
        "edly",
        "edly",
        "ed",
        "ies",
        "ied",
        "ly",
        "es",
        "s",
    )

    def stem(self, word: str) -> str:
        if len(word) <= 4:
            return word
        for suffix in self.SUFFIXES:
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                if suffix in {"ies", "ied"}:
                    return word[:-3] + "y"
                return word[: -len(suffix)]
        return word


_STEMMER = _NltkPorterStemmer() if _NltkPorterStemmer else _FallbackStemmer()


def semantic_token_set(text: str) -> set[str]:
    """Tokenize, normalize, stopword-filter, and stem opinions text."""
    tokens = TOKEN_RE.findall(text.lower())
    processed = set()
    for token in tokens:
        if token in STOPWORDS:
            continue
        stem = _STEMMER.stem(token)
        if stem and stem not in STOPWORDS:
            processed.add(stem)
    return processed


def semantic_distance(previous_text: str, current_text: str) -> float:
    """Jaccard distance of processed opinion tokens."""
    left = semantic_token_set(previous_text or "")
    right = semantic_token_set(current_text or "")
    union = left | right
    if not union:
        return 0.0
    return 1.0 - (len(left & right) / len(union))


def solver_ast_complexity(code: str) -> int:
    """Count branching/looping constructs in solver code."""
    try:
        tree = ast.parse(code or "")
    except SyntaxError:
        return 0
    return sum(1 for node in ast.walk(tree) if isinstance(node, TARGET_AST_NODES))


def classify_turbulence(d_sem: float, delta_c: int) -> str:
    """Classify cycle dynamics using the V4.3 rubric."""
    if d_sem < 0.40:
        if delta_c <= 0:
            return "STABLE_PATCHING"
        return "EPICYCLE_ACCUMULATION"
    if delta_c >= 0:
        return "ONTOLOGY_CHANGE"
    return "PRODUCTIVE_TURBULENCE"


def text_signal_metrics(text: str) -> dict[str, float | int]:
    """Compact character/line spectrum for prose telemetry."""
    raw = text or ""
    char_count = len(raw)
    lines = raw.splitlines() or [raw]
    line_lengths = [len(line) for line in lines] or [0]
    avg_line_length = sum(line_lengths) / len(line_lengths)
    line_var = sum((length - avg_line_length) ** 2 for length in line_lengths) / len(line_lengths)
    line_std = math.sqrt(line_var)

    counts = collections.Counter(raw)
    entropy = 0.0
    if char_count > 0:
        for count in counts.values():
            p = count / char_count
            entropy -= p * math.log2(p)

    symbol_count = sum(1 for ch in raw if not ch.isalnum() and not ch.isspace())
    uppercase_count = sum(1 for ch in raw if ch.isalpha() and ch.isupper())
    digit_count = sum(1 for ch in raw if ch.isdigit())

    return {
        "opinions_char_count": char_count,
        "opinions_line_count": len(lines),
        "opinions_avg_line_length": round(avg_line_length, 4),
        "opinions_line_length_std": round(line_std, 4),
        "opinions_char_entropy": round(entropy, 4),
        "opinions_symbol_density": round(symbol_count / max(1, char_count), 4),
        "opinions_uppercase_density": round(uppercase_count / max(1, char_count), 4),
        "opinions_digit_density": round(digit_count / max(1, char_count), 4),
    }


def _coerce_numeric_series(series: list[object]) -> list[float]:
    values: list[float] = []
    for item in series:
        if isinstance(item, bool):
            continue
        if isinstance(item, (int, float)):
            values.append(float(item))
    return values


def _power_spectrum(series: list[float]) -> tuple[list[float], list[float]]:
    n = len(series)
    if n < 4:
        return [], []
    mean = sum(series) / n
    centered = [value - mean for value in series]
    frequencies: list[float] = []
    powers: list[float] = []
    for k in range(1, (n // 2) + 1):
        real = 0.0
        imag = 0.0
        for idx, value in enumerate(centered):
            angle = 2.0 * math.pi * k * idx / n
            real += value * math.cos(angle)
            imag -= value * math.sin(angle)
        power = (real * real + imag * imag) / max(1, n)
        frequencies.append(k / n)
        powers.append(power)
    return frequencies, powers


def _log_slope(xs: list[float], ys: list[float]) -> float:
    pairs = [
        (math.log10(x), math.log10(y))
        for x, y in zip(xs, ys)
        if x > 0 and y > 0
    ]
    if len(pairs) < 2:
        return 0.0
    mean_x = sum(x for x, _ in pairs) / len(pairs)
    mean_y = sum(y for _, y in pairs) / len(pairs)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denominator = sum((x - mean_x) ** 2 for x, _ in pairs)
    if denominator == 0:
        return 0.0
    return numerator / denominator


def spectral_series_metrics(series: list[object], prefix: str) -> dict[str, float | int]:
    """Compact spectrum over a cycle-indexed numeric series."""
    values = _coerce_numeric_series(series)
    metrics: dict[str, float | int] = {
        f"{prefix}_sample_count": len(values),
        f"{prefix}_dominant_period": 0.0,
        f"{prefix}_dominant_power_ratio": 0.0,
        f"{prefix}_spectral_entropy": 0.0,
        f"{prefix}_low_high_power_ratio": 0.0,
        f"{prefix}_pink_beta": 0.0,
        f"{prefix}_pink_distance": 1.0,
        f"{prefix}_pink_closeness": 0.0,
    }
    if len(values) < 4:
        return metrics

    freqs, powers = _power_spectrum(values)
    total_power = sum(powers)
    if total_power <= 0:
        return metrics

    dominant_index = max(range(len(powers)), key=lambda idx: powers[idx])
    dominant_frequency = freqs[dominant_index]
    dominant_period = 1.0 / dominant_frequency if dominant_frequency > 0 else 0.0
    dominant_power_ratio = powers[dominant_index] / total_power

    positive_powers = [power / total_power for power in powers if power > 0]
    if len(positive_powers) > 1:
        entropy = -sum(prob * math.log2(prob) for prob in positive_powers) / math.log2(len(positive_powers))
    else:
        entropy = 0.0

    low_cut = max(1, len(powers) // 3)
    low_power = sum(powers[:low_cut])
    high_power = sum(powers[low_cut:])
    low_high_ratio = low_power / max(high_power, 1e-9)

    beta = -_log_slope(freqs, powers)
    pink_distance = abs(beta - 1.0)
    pink_closeness = max(0.0, 1.0 - pink_distance)

    metrics.update(
        {
            f"{prefix}_dominant_period": round(dominant_period, 4),
            f"{prefix}_dominant_power_ratio": round(dominant_power_ratio, 4),
            f"{prefix}_spectral_entropy": round(entropy, 4),
            f"{prefix}_low_high_power_ratio": round(low_high_ratio, 4),
            f"{prefix}_pink_beta": round(beta, 4),
            f"{prefix}_pink_distance": round(pink_distance, 4),
            f"{prefix}_pink_closeness": round(pink_closeness, 4),
        }
    )
    return metrics


def rolling_pink_metrics(
    series: list[object],
    prefix: str,
    *,
    window: int = DEFAULT_PINK_WINDOW,
) -> dict[str, float | int]:
    """Trailing-window spectral probe for pink-noise style behavior."""
    values = _coerce_numeric_series(series)
    trailing = values[-window:] if window > 0 else values
    metrics = spectral_series_metrics(trailing, prefix)
    metrics[f"{prefix}_pink_window"] = min(window, len(values)) if window > 0 else len(values)
    return metrics


def _normalize_family_id(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", (text or "").strip().lower()).strip("_")
    return normalized or "dead_end"


def _normalize_tags(raw_tags: str) -> list[str]:
    tags = []
    for tag in (raw_tags or "").split(","):
        normalized = _normalize_family_id(tag)
        if normalized and normalized != "dead_end":
            tags.append(normalized)
    return sorted(set(tags))


def _infer_ontology_tags(claim: str) -> list[str]:
    lowered = (claim or "").lower()
    found = [tag for tag in ONTOLOGY_KEYWORDS if re.search(rf"\b{re.escape(tag)}\b", lowered)]
    return sorted(found)


def parse_dead_end_entries(dead_ends_text: str) -> list[dict[str, object]]:
    """Parse structured or legacy dead-end lines into stable family entries."""
    entries: list[dict[str, object]] = []
    for raw_line in (dead_ends_text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "->" not in line:
            continue
        trimmed = re.sub(r"^(?:[-*]\s*)", "", line)
        left, right = trimmed.split("->", 1)
        left = left.strip()
        falsifier = right.strip()
        header = ""
        claim = left
        family_source = claim
        tags: list[str] = []
        structured = False

        if left.startswith("[") and "]" in left:
            header, _, remainder = left[1:].partition("]")
            claim = remainder.strip() or header.strip()
            structured = "|" in header
            family_part, _, tag_part = header.partition("|")
            if family_part.strip():
                family_source = family_part.strip()
            tags = _normalize_tags(tag_part)

        entry = {
            "family_id": _normalize_family_id(family_source),
            "claim": claim,
            "falsifier": falsifier,
            "ontology_tags": tags or _infer_ontology_tags(claim),
            "structured": structured,
            "raw_line": line,
        }
        entries.append(entry)
    return entries


def dead_ends_count(dead_ends_text: str) -> int:
    """Count discrete falsification entries in dead-ends.md."""
    return len(parse_dead_end_entries(dead_ends_text))


def dead_end_family_count(dead_ends_text: str) -> int:
    """Count distinct dead-end families tracked in dead-ends.md."""
    return len({entry["family_id"] for entry in parse_dead_end_entries(dead_ends_text)})


def dead_end_metrics(previous_text: str, current_text: str) -> dict[str, object]:
    """Summarize family retention, churn, and ontology breadth across cycles."""
    previous_entries = parse_dead_end_entries(previous_text)
    current_entries = parse_dead_end_entries(current_text)
    previous_families = {entry["family_id"] for entry in previous_entries}
    current_families = {entry["family_id"] for entry in current_entries}
    retained = previous_families & current_families
    new_families = current_families - previous_families
    lost_families = previous_families - current_families
    retention = 1.0 if not previous_families else len(retained) / len(previous_families)
    ontology_tags = {
        tag
        for entry in current_entries
        for tag in entry["ontology_tags"]  # type: ignore[union-attr]
    }
    structured_count = sum(1 for entry in current_entries if entry["structured"])

    return {
        "dead_ends_count": len(current_entries),
        "dead_end_family_count": len(current_families),
        "dead_end_retained_family_count": len(retained),
        "dead_end_new_family_count": len(new_families),
        "dead_end_lost_family_count": len(lost_families),
        "dead_end_family_retention": round(retention, 4),
        "dead_end_ontology_count": len(ontology_tags),
        "dead_end_structured_count": structured_count,
    }


def generate_random_array(
    rng: random.Random,
    min_len: int = 5,
    max_len: int = 8,
    min_value: int = 1,
    max_value: int = 9,
) -> list[int]:
    """Generate a random C9-style input array."""
    return [rng.randint(min_value, max_value) for _ in range(rng.randint(min_len, max_len))]


def blandness_score(arr: list[int]) -> int:
    """Higher is blander and less visually suggestive."""
    duplicate_penalty = (len(arr) - len(set(arr))) * 10
    contiguous_penalty = sum(5 for i in range(len(arr) - 1) if abs(arr[i] - arr[i + 1]) == 1)
    return -(duplicate_penalty + contiguous_penalty)


def euclidean_distance(left: list[int], right: list[int]) -> float:
    """Distance helper for diverse counterexample selection."""
    max_len = max(len(left), len(right))
    left_pad = left + [0] * (max_len - len(left))
    right_pad = right + [0] * (max_len - len(right))
    return math.dist(left_pad, right_pad)


def select_adversarial_pairs(
    solver: Callable[[list[int]], list[int]],
    true_law: Callable[[list[int]], list[int]],
    rng: random.Random,
    pool_size: int = 1000,
    top_k: int = 50,
    desired: int = 4,
) -> list[dict[str, list[int]]]:
    """Select counterexamples maximizing falsification and blandness."""
    falsifying: list[list[int]] = []
    for _ in range(pool_size):
        arr = generate_random_array(rng)
        try:
            got = solver(arr.copy())
        except Exception:
            got = None
        expected = true_law(arr)
        if got != expected:
            falsifying.append(arr)

    if not falsifying:
        return []

    scored = sorted(
        ((blandness_score(arr), arr) for arr in falsifying),
        key=lambda item: item[0],
        reverse=True,
    )
    candidates = [arr for _, arr in scored[: max(desired, min(top_k, len(scored)))]]
    selected = [candidates.pop(0)]

    while candidates and len(selected) < desired:
        best = max(candidates, key=lambda cand: min(euclidean_distance(cand, seen) for seen in selected))
        selected.append(best)
        candidates.remove(best)

    return [{"input": arr, "expected": true_law(arr)} for arr in selected]
