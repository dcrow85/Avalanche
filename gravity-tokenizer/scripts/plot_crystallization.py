"""
Visualize crystallization curves from crystallization_curves.json.

Generates three figures:
1. Showcase panel — 8 interesting chains with CI bands and jump annotations
2. Delta-leverage heatmap — all 50 chains side by side
3. Jump distribution — histogram + top 15 largest crystallization jumps

Usage:
    python scripts/plot_crystallization.py [--input data/crystallization_curves.json]
"""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np


def load_data(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_normal_chain(info: dict) -> list[dict]:
    return [e for e in info["chain"] if e["type"] == "normal"]


def plot_showcase(data: dict, output_dir: Path):
    """Figure 1: Panel of 8 interesting chains."""
    showcase = ["contin", "partic", "accom", "Thank", "doesn", "signific", "between", "continu"]
    # Filter to those present
    showcase = [s for s in showcase if s in data]

    fig, axes = plt.subplots(2, 4, figsize=(18, 8), sharey=True)
    fig.suptitle("Crystallization Curves \u2014 Leverage vs Merge Step",
                 fontsize=16, fontweight="bold", y=0.98)

    for idx, ax in enumerate(axes.flat):
        if idx >= len(showcase):
            ax.set_visible(False)
            continue

        target = showcase[idx]
        normal = get_normal_chain(data[target])

        steps = list(range(len(normal)))
        leverages = [e["leverage"] if e["leverage"] is not None else 0 for e in normal]
        labels = [e["readable"] for e in normal]
        ci_lo = [e.get("leverage_ci_low") or 0 for e in normal]
        ci_hi = [e.get("leverage_ci_high") or 0 for e in normal]

        # CI band + line
        ax.fill_between(steps, ci_lo, ci_hi, alpha=0.15, color="#2196F3")
        ax.plot(steps, leverages, "o-", color="#1565C0", linewidth=2, markersize=7, zorder=5)

        # Find biggest jump
        max_delta = 0
        max_idx = 0
        for i in range(1, len(leverages)):
            delta = leverages[i] - leverages[i - 1]
            if delta > max_delta:
                max_delta = delta
                max_idx = i

        if max_delta > 0.2:
            ax.annotate(
                f"+{max_delta:.2f}",
                xy=(max_idx, leverages[max_idx]),
                xytext=(max_idx - 0.3, leverages[max_idx] + 0.08),
                fontsize=9, fontweight="bold", color="#C62828",
                arrowprops=dict(arrowstyle="->", color="#C62828", lw=1.5),
            )

        # Label points
        for i, (s, l, lev) in enumerate(zip(steps, labels, leverages)):
            offset = -12 if i % 2 == 0 else 10
            ax.annotate(l, (s, lev), textcoords="offset points",
                        xytext=(0, offset), ha="center", fontsize=7.5,
                        fontstyle="italic", color="#424242")

        ax.set_title(f'"{target}"', fontsize=12, fontweight="bold")
        ax.set_xlabel("Merge step", fontsize=9)
        if idx % 4 == 0:
            ax.set_ylabel("Ablation leverage", fontsize=10)
        ax.set_ylim(-0.05, 1.75)
        ax.axhline(y=0, color="grey", linewidth=0.5, linestyle="--")
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out = output_dir / "crystallization_showcase.png"
    plt.savefig(out, dpi=180, bbox_inches="tight", facecolor="white", edgecolor="none")
    print(f"Saved: {out}")
    plt.close()


def plot_heatmap(data: dict, output_dir: Path):
    """Figure 2: Delta-leverage heatmap for all chains."""
    sorted_targets = sorted(
        data.keys(),
        key=lambda t: max(
            (e["leverage"] or 0) for e in data[t]["chain"] if e["type"] == "normal"
        ),
        reverse=True,
    )

    labels_y = []
    all_deltas = []
    all_labels_x = []
    max_steps = 0

    for target in sorted_targets:
        normal = get_normal_chain(data[target])
        leverages = [e["leverage"] if e["leverage"] is not None else 0 for e in normal]

        deltas = [leverages[0]]
        for i in range(1, len(leverages)):
            deltas.append(leverages[i] - leverages[i - 1])

        all_deltas.append(deltas)
        all_labels_x.append([e["readable"] for e in normal])
        labels_y.append(target)
        max_steps = max(max_steps, len(deltas))

    # Pad to uniform width
    matrix = np.full((len(all_deltas), max_steps), np.nan)
    for i, deltas in enumerate(all_deltas):
        for j, d in enumerate(deltas):
            matrix[i, j] = d

    fig, ax = plt.subplots(figsize=(14, 16))

    cmap = plt.cm.RdYlBu_r.copy()
    cmap.set_bad("white")

    im = ax.imshow(matrix, aspect="auto", cmap=cmap, vmin=-0.5, vmax=1.1,
                   interpolation="nearest")

    ax.set_yticks(range(len(labels_y)))
    ax.set_yticklabels(labels_y, fontsize=7.5, fontfamily="monospace")
    ax.set_xlabel("Merge step in chain", fontsize=11)
    ax.set_title(
        "Delta-Leverage Heatmap \u2014 All 50 Chains\n"
        "(red = leverage jump, blue = leverage drop)",
        fontsize=13, fontweight="bold",
    )

    # Annotate cells
    for i in range(len(all_labels_x)):
        for j in range(len(all_labels_x[i])):
            val = matrix[i, j]
            if not np.isnan(val):
                color = "white" if abs(val) > 0.6 else "black"
                weight = "bold" if val > 0.5 else "normal"
                ax.text(j, i, all_labels_x[i][j], ha="center", va="center",
                        fontsize=5, color=color, fontweight=weight)

    cbar = plt.colorbar(im, ax=ax, shrink=0.6, pad=0.02)
    cbar.set_label("Delta leverage (step-to-step change)", fontsize=10)

    plt.tight_layout()
    out = output_dir / "crystallization_heatmap.png"
    plt.savefig(out, dpi=180, bbox_inches="tight", facecolor="white", edgecolor="none")
    print(f"Saved: {out}")
    plt.close()


def plot_jumps(data: dict, output_dir: Path):
    """Figure 3: Jump distribution + top 15."""
    sorted_targets = sorted(data.keys())

    all_jumps = []
    jump_labels = []
    for target in sorted_targets:
        normal = get_normal_chain(data[target])
        leverages = [e["leverage"] if e["leverage"] is not None else 0 for e in normal]
        readables = [e["readable"] for e in normal]
        for i in range(1, len(leverages)):
            delta = leverages[i] - leverages[i - 1]
            all_jumps.append(delta)
            jump_labels.append(f"{readables[i-1]}->{readables[i]}")

    all_jumps = np.array(all_jumps)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Left: histogram
    ax1.hist(all_jumps, bins=40, color="#1565C0", alpha=0.8,
             edgecolor="white", linewidth=0.5)
    ax1.axvline(x=0, color="red", linewidth=1, linestyle="--")
    ax1.set_xlabel("Delta leverage (step-to-step)", fontsize=11)
    ax1.set_ylabel("Count", fontsize=11)
    ax1.set_title("Distribution of Leverage Jumps\nAcross All Merge Steps",
                   fontsize=12, fontweight="bold")
    pos_count = int((all_jumps > 0).sum())
    stats_text = (f"Mean: {np.mean(all_jumps):.3f}\n"
                  f"Std: {np.std(all_jumps):.3f}\n"
                  f"Positive: {pos_count}/{len(all_jumps)}")
    ax1.annotate(stats_text, xy=(0.72, 0.85), xycoords="axes fraction",
                 fontsize=9, bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    # Right: top 15 jumps
    top_idx = np.argsort(all_jumps)[-15:][::-1]
    top_vals = all_jumps[top_idx]
    top_labels_list = [jump_labels[i] for i in top_idx]

    ax2.barh(range(len(top_vals)), top_vals, color="#C62828", alpha=0.85,
             edgecolor="white")
    ax2.set_yticks(range(len(top_vals)))
    ax2.set_yticklabels(top_labels_list, fontsize=8, fontfamily="monospace")
    ax2.set_xlabel("Delta leverage", fontsize=11)
    ax2.set_title("Top 15 Crystallization Jumps", fontsize=12, fontweight="bold")
    ax2.invert_yaxis()
    ax2.grid(True, axis="x", alpha=0.3)

    for i, v in enumerate(top_vals):
        ax2.text(v + 0.01, i, f"+{v:.3f}", va="center", fontsize=8, fontweight="bold")

    plt.tight_layout()
    out = output_dir / "crystallization_jumps.png"
    plt.savefig(out, dpi=180, bbox_inches="tight", facecolor="white", edgecolor="none")
    print(f"Saved: {out}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Plot crystallization curves")
    parser.add_argument("--input", type=str, default="data/crystallization_curves.json")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory for PNGs (default: same as input)")
    args = parser.parse_args()

    data = load_data(args.input)
    output_dir = Path(args.output_dir) if args.output_dir else Path(args.input).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loaded {len(data)} chains from {args.input}")
    plot_showcase(data, output_dir)
    plot_heatmap(data, output_dir)
    plot_jumps(data, output_dir)
    print("Done.")


if __name__ == "__main__":
    main()
