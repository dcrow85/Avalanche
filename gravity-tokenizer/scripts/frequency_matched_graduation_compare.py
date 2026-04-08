from __future__ import annotations

import argparse
import glob
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np

from classification_compat import is_quiescent_classification, normalize_classification, normalize_phase_space_snapshot

SHARD_MAGIC = 20240520
SHARD_VERSION = 1
HEADER_INTS = 256
HEADER_BYTES = HEADER_INTS * np.dtype("<i4").itemsize
DEFAULT_VOCAB_SIZE = 1024


@dataclass(frozen=True)
class Band:
    label: str
    min_count: int
    max_count: int | None


BANDS = [
    Band(label=">=1M", min_count=1_000_000, max_count=None),
    Band(label="100k-1M", min_count=100_000, max_count=1_000_000),
    Band(label="10k-100k", min_count=10_000, max_count=100_000),
    Band(label="1k-10k", min_count=1_000, max_count=10_000),
    Band(label="<1k", min_count=0, max_count=1_000),
]


def load_shard_counts(dataset_dir: Path, vocab_size: int = DEFAULT_VOCAB_SIZE) -> np.ndarray:
    counts = np.zeros(vocab_size, dtype=np.int64)
    shard_paths = sorted(dataset_dir.glob("fineweb_train_*.bin"))
    if not shard_paths:
        raise FileNotFoundError(f"No training shards found under {dataset_dir}")

    for shard_path in shard_paths:
        header = np.fromfile(shard_path, dtype="<i4", count=HEADER_INTS)
        if (
            header.size != HEADER_INTS
            or int(header[0]) != SHARD_MAGIC
            or int(header[1]) != SHARD_VERSION
        ):
            raise ValueError(f"Unexpected shard header for {shard_path}")
        num_tokens = int(header[2])
        tokens = np.fromfile(
            shard_path,
            dtype="<u2",
            count=num_tokens,
            offset=HEADER_BYTES,
        )
        bincount = np.bincount(tokens, minlength=vocab_size)
        if bincount.shape[0] > counts.shape[0]:
            counts = np.pad(counts, (0, bincount.shape[0] - counts.shape[0]))
        counts[: bincount.shape[0]] += bincount
    return counts


def load_phase_rows(path: Path) -> dict[int, dict[str, Any]]:
    payload = normalize_phase_space_snapshot(json.loads(path.read_text(encoding="utf-8")))
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError(f"Expected 'rows' list in {path}")
    return {int(row["token_id"]): row for row in rows}


def gravity_entries(gravity_paths: list[Path], counts: np.ndarray) -> list[dict[str, Any]]:
    per_seed = [load_phase_rows(path) for path in gravity_paths]
    base = per_seed[0]
    entries: list[dict[str, Any]] = []
    for token_id in sorted(base):
        classes = [normalize_classification(rows[token_id]["classification"]) for rows in per_seed]
        graduated_flags = [is_quiescent_classification(cls) for cls in classes]
        entries.append(
            {
                "token_id": token_id,
                "piece": base[token_id]["piece"],
                "readable": base[token_id]["readable"],
                "count": int(counts[token_id]),
                "is_static": bool(base[token_id]["is_static_core"]),
                "seed_classes": classes,
                "seed_graduated_flags": graduated_flags,
                "graduated_votes": int(sum(graduated_flags)),
                "graduated_majority": int(sum(graduated_flags) >= (len(per_seed) // 2 + 1)),
                "graduated_mean": float(mean(1.0 if flag else 0.0 for flag in graduated_flags)),
            }
        )
    return entries


def single_seed_entries(path: Path, counts: np.ndarray) -> list[dict[str, Any]]:
    rows = load_phase_rows(path)
    entries: list[dict[str, Any]] = []
    for token_id in sorted(rows):
        row = rows[token_id]
        entries.append(
            {
                "token_id": token_id,
                "piece": row["piece"],
                "readable": row["readable"],
                "count": int(counts[token_id]),
                "is_static": bool(row["is_static_core"]),
                "classification": normalize_classification(row["classification"]),
                "graduated": int(is_quiescent_classification(row["classification"])),
            }
        )
    return entries


def top_k_summary(
    entries: list[dict[str, Any]],
    *,
    k: int,
    graduated_key: str,
    nonstatic_only: bool,
) -> dict[str, Any]:
    subset = [entry for entry in entries if not nonstatic_only or not entry["is_static"]]
    ordered = sorted(subset, key=lambda entry: (-entry["count"], entry["token_id"]))
    top = ordered[:k]
    graduated_total = sum(float(entry[graduated_key]) for entry in top)
    return {
        "k": k,
        "n": len(top),
        "graduated_total": graduated_total,
        "graduated_rate": (graduated_total / len(top)) if top else 0.0,
        "count_max": int(top[0]["count"]) if top else 0,
        "count_min": int(top[-1]["count"]) if top else 0,
        "nonstatic_only": nonstatic_only,
        "top_examples": [
            {
                "token_id": int(entry["token_id"]),
                "readable": entry["readable"],
                "count": int(entry["count"]),
                "graduated_signal": float(entry[graduated_key]),
            }
            for entry in top[:10]
        ],
    }


def band_summary(
    entries: list[dict[str, Any]],
    *,
    graduated_key: str,
    nonstatic_only: bool,
) -> list[dict[str, Any]]:
    subset = [entry for entry in entries if not nonstatic_only or not entry["is_static"]]
    rows: list[dict[str, Any]] = []
    for band in BANDS:
        band_entries = [
            entry
            for entry in subset
            if entry["count"] >= band.min_count
            and (band.max_count is None or entry["count"] < band.max_count)
        ]
        graduated_total = sum(float(entry[graduated_key]) for entry in band_entries)
        rows.append(
            {
                "label": band.label,
                "n": len(band_entries),
                "graduated_total": graduated_total,
                "graduated_rate": (graduated_total / len(band_entries)) if band_entries else 0.0,
                "count_max": int(max((entry["count"] for entry in band_entries), default=0)),
                "count_min": int(min((entry["count"] for entry in band_entries), default=0)),
            }
        )
    return rows


def decile_summary(
    entries: list[dict[str, Any]],
    *,
    graduated_key: str,
    nonstatic_only: bool,
) -> list[dict[str, Any]]:
    subset = [entry for entry in entries if not nonstatic_only or not entry["is_static"]]
    ordered = sorted(subset, key=lambda entry: (-entry["count"], entry["token_id"]))
    chunks = np.array_split(np.array(ordered, dtype=object), 10)
    rows: list[dict[str, Any]] = []
    for idx, chunk in enumerate(chunks, start=1):
        items = list(chunk)
        graduated_total = sum(float(entry[graduated_key]) for entry in items)
        rows.append(
            {
                "decile": idx,
                "n": len(items),
                "graduated_total": graduated_total,
                "graduated_rate": (graduated_total / len(items)) if items else 0.0,
                "count_max": int(items[0]["count"]) if items else 0,
                "count_min": int(items[-1]["count"]) if items else 0,
            }
        )
    return rows


def whole_vocab_summary(
    entries: list[dict[str, Any]],
    *,
    graduated_key: str,
    nonstatic_only: bool,
) -> dict[str, Any]:
    subset = [entry for entry in entries if not nonstatic_only or not entry["is_static"]]
    graduated_total = sum(float(entry[graduated_key]) for entry in subset)
    return {
        "n": len(subset),
        "graduated_total": graduated_total,
        "graduated_rate": (graduated_total / len(subset)) if subset else 0.0,
        "nonstatic_only": nonstatic_only,
    }


def absolute_range_match(
    source_topk: dict[str, Any],
    target_entries: list[dict[str, Any]],
    *,
    graduated_key: str,
    nonstatic_only: bool,
) -> dict[str, Any]:
    subset = [entry for entry in target_entries if not nonstatic_only or not entry["is_static"]]
    lo = int(source_topk["count_min"])
    hi = int(source_topk["count_max"])
    matched = [entry for entry in subset if lo <= entry["count"] <= hi]
    graduated_total = sum(float(entry[graduated_key]) for entry in matched)
    return {
        "range_min": lo,
        "range_max": hi,
        "n": len(matched),
        "graduated_total": graduated_total,
        "graduated_rate": (graduated_total / len(matched)) if matched else 0.0,
    }


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def build_markdown(summary: dict[str, Any]) -> str:
    gravity = summary["gravity"]
    bpe = summary["bpe"]
    top100_g = gravity["top_k"]["100_nonstatic"]
    top100_b = bpe["top_k"]["100_nonstatic"]
    match100 = summary["matched_ranges"]["gravity_top100_band_vs_bpe"]

    lines = [
        "# Frequency-Matched Graduation Comparison",
        "",
        "This compares gravity `beta=1.0_with_space` against standard BPE at step `2000` using realized token counts from the local training shards, not score-side metadata.",
        "",
        "## Headline",
        "",
        f"- Whole-vocab graduation remains far apart: gravity `{gravity['whole_vocab']['graduated_total']:.2f}/{gravity['whole_vocab']['n']}` vs BPE `{bpe['whole_vocab']['graduated_total']:.2f}/{bpe['whole_vocab']['n']}`.",
        f"- Among the top-100 most frequent non-static tokens, the gap shrinks: gravity `{top100_g['graduated_total']:.2f}/{top100_g['n']}` vs BPE `{top100_b['graduated_total']:.2f}/{top100_b['n']}`.",
        f"- Inside the same absolute frequency band as gravity's top-100 (`{match100['range_min']:,}` to `{match100['range_max']:,}` occurrences), BPE graduates `{match100['graduated_total']:.2f}/{match100['n']}` tokens.",
        "- Current read: the raw whole-vocab gap is real, but a large fraction of it comes from vocabulary composition. Gravity allocates many more slots to low-frequency tokens that almost never graduate for either tokenizer family by step 2000.",
        "",
        "## Whole Vocab",
        "",
        render_table(
            ["Condition", "Graduated", "Total", "Rate"],
            [
                [
                    "Gravity (mean across 3 seeds)",
                    f"{gravity['whole_vocab']['graduated_total']:.2f}",
                    str(gravity["whole_vocab"]["n"]),
                    f"{100.0 * gravity['whole_vocab']['graduated_rate']:.2f}%",
                ],
                [
                    "BPE (seed 1337)",
                    f"{bpe['whole_vocab']['graduated_total']:.2f}",
                    str(bpe["whole_vocab"]["n"]),
                    f"{100.0 * bpe['whole_vocab']['graduated_rate']:.2f}%",
                ],
            ],
        ),
        "",
        "## Top-K Frequent Non-Static Tokens",
        "",
        render_table(
            ["K", "Gravity Graduated", "Gravity Rate", "BPE Graduated", "BPE Rate"],
            [
                [
                    k.split("_")[0],
                    f"{gravity['top_k'][k]['graduated_total']:.2f}",
                    f"{100.0 * gravity['top_k'][k]['graduated_rate']:.2f}%",
                    f"{bpe['top_k'][k]['graduated_total']:.2f}",
                    f"{100.0 * bpe['top_k'][k]['graduated_rate']:.2f}%",
                ]
                for k in ["25_nonstatic", "50_nonstatic", "100_nonstatic", "200_nonstatic"]
            ],
        ),
        "",
        "## Absolute Frequency Bands (Non-Static)",
        "",
        render_table(
            [
                "Band",
                "Gravity N",
                "Gravity Graduated",
                "Gravity Rate",
                "BPE N",
                "BPE Graduated",
                "BPE Rate",
            ],
            [
                [
                    g_row["label"],
                    str(g_row["n"]),
                    f"{g_row['graduated_total']:.2f}",
                    f"{100.0 * g_row['graduated_rate']:.2f}%",
                    str(b_row["n"]),
                    f"{b_row['graduated_total']:.2f}",
                    f"{100.0 * b_row['graduated_rate']:.2f}%",
                ]
                for g_row, b_row in zip(gravity["bands_nonstatic"], bpe["bands_nonstatic"], strict=True)
            ],
        ),
        "",
        "## Within-Vocab Frequency Deciles (Non-Static)",
        "",
        render_table(
            [
                "Decile",
                "Gravity N",
                "Gravity Graduated",
                "Gravity Rate",
                "BPE N",
                "BPE Graduated",
                "BPE Rate",
            ],
            [
                [
                    str(g_row["decile"]),
                    str(g_row["n"]),
                    f"{g_row['graduated_total']:.2f}",
                    f"{100.0 * g_row['graduated_rate']:.2f}%",
                    str(b_row["n"]),
                    f"{b_row['graduated_total']:.2f}",
                    f"{100.0 * b_row['graduated_rate']:.2f}%",
                ]
                for g_row, b_row in zip(gravity["deciles_nonstatic"], bpe["deciles_nonstatic"], strict=True)
            ],
        ),
        "",
        "## Interpretation",
        "",
        "- If we compare whole vocabularies, gravity under-graduates massively.",
        "- If we compare tokens inside the same absolute frequency bands (`>=1M`, `100k-1M`), gravity and BPE look much closer.",
        "- The main structural difference is allocation: gravity spends far more of its vocabulary budget in the `10k-100k` band, where graduation is near-zero by step 2000.",
        "- That means the current gravity failure is at least partly a composition/accessibility problem, not only a per-token suppression problem within matched frequency bands.",
        "",
    ]
    return "\n".join(line for line in lines if line is not None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Frequency-matched gravity vs BPE graduation comparison")
    parser.add_argument(
        "--gravity-dataset-dir",
        type=Path,
        default=Path(r"C:\Avalanche\gravity-tokenizer\parameter-golf\data\datasets\fineweb_gravity_beta_1.0"),
    )
    parser.add_argument(
        "--bpe-dataset-dir",
        type=Path,
        default=Path(r"C:\Avalanche\gravity-tokenizer\parameter-golf\data\datasets\fineweb10B_sp1024"),
    )
    parser.add_argument(
        "--gravity-phase-glob",
        type=str,
        default=r"C:\Avalanche\gravity-tokenizer\parameter-golf\logs\determinism\determinism_seed_*_phase_space_step_02000.json",
    )
    parser.add_argument(
        "--bpe-phase-path",
        type=Path,
        default=Path(r"C:\Avalanche\gravity-tokenizer\parameter-golf\logs\bpe_cooling\bpe_4k_constant_control_v1_phase_space_step_02000.json"),
    )
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=Path(r"C:\Avalanche\gravity-tokenizer\parameter-golf\logs\frequency_matched_graduation_v1"),
    )
    args = parser.parse_args()

    gravity_phase_paths = sorted(Path(path) for path in glob.glob(args.gravity_phase_glob))
    if not gravity_phase_paths:
        raise FileNotFoundError(f"No gravity phase-space files matched {args.gravity_phase_glob}")

    gravity_counts = load_shard_counts(args.gravity_dataset_dir)
    bpe_counts = load_shard_counts(args.bpe_dataset_dir)

    gravity = gravity_entries(gravity_phase_paths, gravity_counts)
    bpe = single_seed_entries(args.bpe_phase_path, bpe_counts)

    gravity_summary = {
        "whole_vocab": whole_vocab_summary(gravity, graduated_key="graduated_mean", nonstatic_only=False),
        "whole_vocab_nonstatic": whole_vocab_summary(gravity, graduated_key="graduated_mean", nonstatic_only=True),
        "top_k": {
            "25_nonstatic": top_k_summary(gravity, k=25, graduated_key="graduated_mean", nonstatic_only=True),
            "50_nonstatic": top_k_summary(gravity, k=50, graduated_key="graduated_mean", nonstatic_only=True),
            "100_nonstatic": top_k_summary(gravity, k=100, graduated_key="graduated_mean", nonstatic_only=True),
            "200_nonstatic": top_k_summary(gravity, k=200, graduated_key="graduated_mean", nonstatic_only=True),
        },
        "bands_nonstatic": band_summary(gravity, graduated_key="graduated_mean", nonstatic_only=True),
        "deciles_nonstatic": decile_summary(gravity, graduated_key="graduated_mean", nonstatic_only=True),
    }
    bpe_summary = {
        "whole_vocab": whole_vocab_summary(bpe, graduated_key="graduated", nonstatic_only=False),
        "whole_vocab_nonstatic": whole_vocab_summary(bpe, graduated_key="graduated", nonstatic_only=True),
        "top_k": {
            "25_nonstatic": top_k_summary(bpe, k=25, graduated_key="graduated", nonstatic_only=True),
            "50_nonstatic": top_k_summary(bpe, k=50, graduated_key="graduated", nonstatic_only=True),
            "100_nonstatic": top_k_summary(bpe, k=100, graduated_key="graduated", nonstatic_only=True),
            "200_nonstatic": top_k_summary(bpe, k=200, graduated_key="graduated", nonstatic_only=True),
        },
        "bands_nonstatic": band_summary(bpe, graduated_key="graduated", nonstatic_only=True),
        "deciles_nonstatic": decile_summary(bpe, graduated_key="graduated", nonstatic_only=True),
    }

    matched_ranges = {
        "gravity_top100_band_vs_bpe": absolute_range_match(
            gravity_summary["top_k"]["100_nonstatic"],
            bpe,
            graduated_key="graduated",
            nonstatic_only=True,
        )
    }

    summary = {
        "meta": {
            "gravity_dataset_dir": str(args.gravity_dataset_dir),
            "bpe_dataset_dir": str(args.bpe_dataset_dir),
            "gravity_phase_paths": [str(path) for path in gravity_phase_paths],
            "bpe_phase_path": str(args.bpe_phase_path),
            "comparison_step": 2000,
        },
        "gravity": gravity_summary,
        "bpe": bpe_summary,
        "matched_ranges": matched_ranges,
    }

    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = args.output_prefix.with_suffix(".summary.json")
    md_path = args.output_prefix.with_suffix(".md")
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(summary), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
