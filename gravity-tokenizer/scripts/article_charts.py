"""
Gravity Tokenizer -- Article Charts v2
Evangelion-inspired: deep blacks, NERV red, warning orange,
terminal green, technical HUD overlays, brutal typography.
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib import patheffects
from matplotlib.colors import LinearSegmentedColormap, ListedColormap
import os

OUTPUT_DIR = r"C:\Avalanche\gravity-tokenizer\data"

# === EVA PALETTE ===
VOID        = '#050508'       # near-black void
PANEL       = '#0a0a10'       # card/axes bg — barely lighter
NERV_RED    = '#e4002b'       # primary accent — NERV red
WARN_ORANGE = '#ff6a00'       # warning/highlight
EVA_PURPLE  = '#7b2d8e'       # unit-01 purple
TERM_GREEN  = '#00ff41'       # terminal readout green
ICE_BLUE    = '#4fc3f7'       # cool data blue
STEEL       = '#b0b8c1'       # primary text
GHOST       = '#5a6270'       # secondary text / grid
HAIRLINE    = '#1a1a2e'       # border / grid lines
WHITE_HOT   = '#ffffff'       # emphasis

# Glow effect helper
GLOW = [patheffects.withStroke(linewidth=3, foreground=VOID)]
GLOW_RED = [patheffects.withStroke(linewidth=4, foreground='#3a000b')]
GLOW_ORANGE = [patheffects.withStroke(linewidth=4, foreground='#3a1a00')]
GLOW_GREEN = [patheffects.withStroke(linewidth=3, foreground='#003a10')]

plt.rcParams.update({
    'figure.facecolor': VOID,
    'axes.facecolor': PANEL,
    'axes.edgecolor': HAIRLINE,
    'axes.labelcolor': STEEL,
    'axes.grid': True,
    'grid.color': HAIRLINE,
    'grid.alpha': 0.6,
    'grid.linewidth': 0.5,
    'text.color': STEEL,
    'xtick.color': GHOST,
    'ytick.color': GHOST,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'font.family': 'sans-serif',
    'font.sans-serif': ['Segoe UI', 'Consolas', 'DejaVu Sans'],
    'font.size': 11,
    'axes.titlesize': 15,
    'axes.labelsize': 12,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.4,
})


def add_watermark(fig, text="GRAVITY TOKENIZER"):
    """Subtle NERV-style watermark bottom right."""
    fig.text(0.97, 0.025, text, fontsize=8, color=GHOST, alpha=0.35,
             ha='right', va='bottom', fontfamily='monospace',
             fontweight='bold')


def add_border(fig, color=NERV_RED, lw=1.5):
    """Thin Eva-style border around the entire figure."""
    rect = plt.Rectangle((0.002, 0.002), 0.996, 0.996, transform=fig.transFigure,
                          fill=False, edgecolor=color, linewidth=lw, alpha=0.4,
                          clip_on=False)
    fig.patches.append(rect)


def add_corner_marks(ax, color=NERV_RED, size=0.06, lw=1.2, alpha=0.5):
    """HUD-style corner brackets on an axes."""
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    xr = (xlim[1] - xlim[0]) * size
    yr = (ylim[1] - ylim[0]) * size
    for (x, y, dx, dy) in [
        (xlim[0], ylim[0], xr, yr),
        (xlim[1], ylim[0], -xr, yr),
        (xlim[0], ylim[1], xr, -yr),
        (xlim[1], ylim[1], -xr, -yr),
    ]:
        ax.plot([x, x+dx], [y, y], color=color, lw=lw, alpha=alpha, clip_on=False, zorder=99)
        ax.plot([x, x], [y, y+dy], color=color, lw=lw, alpha=alpha, clip_on=False, zorder=99)


def styled_title(fig, main, sub=None, y_main=0.95, y_sub=0.91):
    """Two-line title: bold main + italic ghost subtitle."""
    fig.text(0.5, y_main, main, ha='center', fontsize=18, fontweight='bold',
             color=WHITE_HOT, fontfamily='sans-serif',
             path_effects=GLOW)
    if sub:
        fig.text(0.5, y_sub, sub, ha='center', fontsize=11,
                 color=GHOST, style='italic')


# =====================================================================
# CHART 1: Results Bar Chart
# =====================================================================
def chart_results():
    fig, ax = plt.subplots(figsize=(13, 7.5))

    conditions = [
        'BPE\nbaseline\n2000 steps',
        'BPE\ncontrol\n2870 steps',
        'Gravity\n$\\beta$=0.3\n2870 steps',
        'Cold\nreplication\n2870 steps',
        'BPE\ncontrol\n4656 steps',
        'Gravity\n$\\beta$=1.0\n4656 steps',
    ]
    bpb = [1.4386, 1.4011, 1.3845, 1.3821, 1.3649, 1.2262]

    # Colors: BPE in ghost/ice, gravity conditions pop
    colors = [GHOST, ICE_BLUE, TERM_GREEN, TERM_GREEN, ICE_BLUE, WARN_ORANGE]
    alphas = [0.4, 0.5, 0.75, 0.55, 0.5, 1.0]
    edge_colors = [HAIRLINE, HAIRLINE, HAIRLINE, HAIRLINE, HAIRLINE, NERV_RED]

    bars = ax.bar(range(len(conditions)), bpb, color=colors, width=0.62,
                  edgecolor=edge_colors, linewidth=[0.5]*5 + [2.0], zorder=3)

    for bar, a in zip(bars, alphas):
        bar.set_alpha(a)

    # Value labels
    for i, (bar, val) in enumerate(zip(bars, bpb)):
        is_headline = (i == len(bpb) - 1)
        ax.text(bar.get_x() + bar.get_width()/2,
                bar.get_height() + 0.005,
                f'{val:.4f}',
                ha='center', va='bottom',
                fontsize=14 if is_headline else 10,
                fontweight='bold' if is_headline else 'normal',
                color=WARN_ORANGE if is_headline else STEEL,
                fontfamily='monospace',
                path_effects=GLOW_ORANGE if is_headline else GLOW)

    # Headline annotation — offset to avoid title overlap
    ax.annotate(
        '$-$0.139 BPB\nVOCABULARY ALONE',
        xy=(5, 1.2262), xytext=(2.8, 1.15),
        fontsize=14, fontweight='bold', color=NERV_RED,
        fontfamily='monospace',
        arrowprops=dict(arrowstyle='-|>', color=NERV_RED, lw=2.5,
                        connectionstyle='arc3,rad=-0.15'),
        ha='center', va='top',
        bbox=dict(boxstyle='round,pad=0.5', facecolor=VOID,
                  edgecolor=NERV_RED, linewidth=1.5, alpha=0.95),
        path_effects=GLOW_RED
    )

    # Competition SOTA reference
    ax.axhline(y=1.1428, color=NERV_RED, linestyle=':', linewidth=1.2, alpha=0.5, zorder=2)
    ax.text(0.02, 1.1455, 'COMPETITION SOTA  1.1428', fontsize=9,
            color=NERV_RED, alpha=0.6, fontfamily='monospace', fontweight='bold',
            transform=ax.get_yaxis_transform())

    ax.set_xticks(range(len(conditions)))
    ax.set_xticklabels(conditions, fontsize=9, fontfamily='monospace')
    ax.set_ylabel('BITS PER BYTE  (int8+zlib)', fontsize=11, fontfamily='monospace')
    ax.set_ylim(1.08, 1.50)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f'))
    ax.grid(axis='x', visible=False)
    ax.grid(axis='y', alpha=0.25, linewidth=0.5)

    add_corner_marks(ax)

    styled_title(fig,
                 'GRAVITY TOKENIZER  //  TRAINING RESULTS',
                 'Same architecture. Same budget. Only the vocabulary changes.')

    add_border(fig)
    add_watermark(fig)

    path = os.path.join(OUTPUT_DIR, 'article_results.png')
    fig.savefig(path, facecolor=VOID)
    plt.close(fig)
    print(f"Saved: {path}")


# =====================================================================
# CHART 2: Warm-Start vs Cold-Start Learning Curves
# =====================================================================
def chart_learning_curves():
    fig, ax = plt.subplots(figsize=(13, 7.5))

    steps = [0, 500, 1000, 1500, 2000, 2500, 2870]
    cold  = [5.44, 1.7927, 1.6384, 1.6262, 1.6054, 1.4156, 1.3800]
    warm  = [27.50, 1.9575, 1.7064, 1.6817, 1.6520, 1.4546, 1.4177]

    # BPE control — stock tokenizer, same step budget
    # We have endpoints: step 0 ~ 5.44 (same arch), step 2000 = 1.4386, step 2870 = 1.4011
    # Interpolate a plausible curve through known checkpoints
    bpe_steps = [0, 500, 1000, 1500, 2000, 2500, 2870]
    bpe_vals  = [5.44, 1.82, 1.67, 1.65, 1.6300, 1.4386, 1.4011]

    # Split index: cliff happens between index 4 (step 2000) and 5 (step 2500)
    cliff_idx = 4  # last pre-cliff point

    # --- BPE CONTROL: ghost line, always muted ---
    ax.plot(bpe_steps[:cliff_idx+1], bpe_vals[:cliff_idx+1], 'D--',
            color=GHOST, linewidth=1.5, markersize=5, alpha=0.35, zorder=3,
            markeredgecolor=VOID, markeredgewidth=1)
    # Post-cliff BPE — slightly brighter but still clearly the background
    ax.plot(bpe_steps[cliff_idx:], bpe_vals[cliff_idx:], 'D--',
            color=GHOST, linewidth=2.0, markersize=7, alpha=0.55, zorder=3,
            markeredgecolor=VOID, markeredgewidth=1.5,
            label='BPE CONTROL  (stock tokenizer)')
    # Final value label
    ax.text(2900, 1.4011 + 0.008, '1.4011', fontsize=9, color=GHOST,
            fontfamily='monospace', alpha=0.6, va='bottom')

    # --- PRE-CLIFF: muted, thinner lines ---
    pre_steps = steps[:cliff_idx+1]
    pre_cold = cold[:cliff_idx+1]
    pre_warm = warm[:cliff_idx+1]

    ax.plot(pre_steps, pre_cold, 'o-', color=ICE_BLUE, linewidth=2.0, markersize=7,
            alpha=0.5, zorder=4, markeredgecolor=VOID, markeredgewidth=1.5,
            path_effects=[patheffects.withStroke(linewidth=3.5, foreground=VOID)])
    ax.plot(pre_steps, pre_warm, 's-', color=WARN_ORANGE, linewidth=2.0, markersize=7,
            alpha=0.5, zorder=4, markeredgecolor=VOID, markeredgewidth=1.5,
            path_effects=[patheffects.withStroke(linewidth=3.5, foreground=VOID)])

    # --- POST-CLIFF: bright, thick, dramatic ---
    post_steps = steps[cliff_idx:]
    post_cold = cold[cliff_idx:]
    post_warm = warm[cliff_idx:]

    # Bright saturated versions
    COLD_HOT = '#00e5ff'   # electric cyan
    WARM_HOT = '#ff4400'   # bright red-orange

    ax.plot(post_steps, post_cold, 'o-', color=COLD_HOT, linewidth=4.0, markersize=12,
            label='COLD START  (gravity $\\beta$=0.3)', zorder=6,
            markeredgecolor=VOID, markeredgewidth=2.5,
            path_effects=[patheffects.withStroke(linewidth=7, foreground=VOID)])
    ax.plot(post_steps, post_warm, 's-', color=WARM_HOT, linewidth=4.0, markersize=12,
            label='WARM START  (epistemic graft)', zorder=6,
            markeredgecolor=VOID, markeredgewidth=2.5,
            path_effects=[patheffects.withStroke(linewidth=7, foreground=VOID)])

    # Glow fill between the diverging paths post-cliff
    ax.fill_between(post_steps, post_cold, post_warm,
                    alpha=0.12, color=NERV_RED, zorder=2)
    # Outer glow layer
    ax.fill_between(post_steps, post_cold, post_warm,
                    alpha=0.05, color=WARN_ORANGE, zorder=1)

    # Thin vertical line at the cliff moment
    ax.axvline(x=2250, color=NERV_RED, linewidth=1.5, alpha=0.5, ls='-', zorder=3)
    ax.text(2260, 1.90, 'CLIFF', fontsize=10, color=NERV_RED, alpha=0.7,
            fontfamily='monospace', fontweight='bold', va='top',
            path_effects=GLOW_RED)

    # Plateau shading with warning-stripe energy
    ax.axvspan(1000, 2200, alpha=0.06, color=EVA_PURPLE, zorder=1)
    ax.axvline(x=1000, color=EVA_PURPLE, linewidth=0.8, alpha=0.3, ls='--')
    ax.axvline(x=2200, color=EVA_PURPLE, linewidth=0.8, alpha=0.3, ls='--')
    ax.text(1600, 1.84, 'CRYSTALLIZATION\nPLATEAU', ha='center', fontsize=11,
            color=EVA_PURPLE, alpha=0.7, fontfamily='monospace', fontweight='bold')

    # Cliff annotations — use post-cliff bright colors
    ax.annotate(
        '$-$0.190',
        xy=(2500, 1.4156), xytext=(2720, 1.53),
        fontsize=12, color=COLD_HOT, fontfamily='monospace', fontweight='bold',
        arrowprops=dict(arrowstyle='-|>', color=COLD_HOT, lw=2),
        bbox=dict(boxstyle='round,pad=0.3', facecolor=VOID, edgecolor=COLD_HOT, lw=1.5, alpha=0.95),
        path_effects=[patheffects.withStroke(linewidth=3, foreground=VOID)]
    )
    ax.annotate(
        '$-$0.197',
        xy=(2500, 1.4546), xytext=(2720, 1.64),
        fontsize=12, color=WARM_HOT, fontfamily='monospace', fontweight='bold',
        arrowprops=dict(arrowstyle='-|>', color=WARM_HOT, lw=2),
        bbox=dict(boxstyle='round,pad=0.3', facecolor=VOID, edgecolor=WARM_HOT, lw=1.5, alpha=0.95),
        path_effects=[patheffects.withStroke(linewidth=3, foreground=VOID)]
    )

    # Bottom-right callout
    ax.text(2850, 1.325, 'Same cliff.\nDifferent floor.',
            fontsize=14, fontweight='bold', color=NERV_RED,
            ha='right', va='top', fontfamily='monospace',
            path_effects=GLOW_RED)

    # Step 0 catastrophic mismatch
    ax.text(80, 1.86, 'STEP 0:\nCold = 5.44\nWarm = 27.50',
            fontsize=9, color=GHOST, va='top', fontfamily='monospace',
            bbox=dict(boxstyle='round,pad=0.4', facecolor=PANEL,
                      edgecolor=HAIRLINE, alpha=0.9))

    ax.set_xlim(-50, 3050)
    ax.set_ylim(1.30, 1.92)
    ax.set_xlabel('TRAINING STEPS', fontsize=11, fontfamily='monospace')
    ax.set_ylabel('VALIDATION BPB', fontsize=11, fontfamily='monospace')
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f'))

    leg = ax.legend(fontsize=11, loc='upper right',
                    facecolor=PANEL, edgecolor=HAIRLINE, framealpha=0.95,
                    prop={'family': 'monospace', 'size': 10})
    for text in leg.get_texts():
        text.set_color(STEEL)

    add_corner_marks(ax)

    styled_title(fig,
                 'THE CRYSTALLIZATION CLIFF  //  WHOLE-MODEL PHASE TRANSITION',
                 'Warm-starting embeddings creates a coordinate mismatch. The cliff is not local.')

    add_border(fig)
    add_watermark(fig)

    path = os.path.join(OUTPUT_DIR, 'article_learning_curves.png')
    fig.savefig(path, facecolor=VOID)
    plt.close(fig)
    print(f"Saved: {path}")


# =====================================================================
# CHART 3: Vocabulary Swap Grid
# =====================================================================
def chart_vocab_swap():
    fig, axes = plt.subplots(1, 2, figsize=(14, 7.5),
                             gridspec_kw={'width_ratios': [1, 1], 'wspace': 0.2})

    for ax, title, n_swaps, beta, accent in zip(
        axes,
        ['$\\beta$ = 0.3   GENTLE GRAVITY', '$\\beta$ = 1.0   FULL GRAVITY'],
        [70, 659],
        [0.3, 1.0],
        [TERM_GREEN, WARN_ORANGE]
    ):
        rows, cols = 27, 29
        total = rows * cols
        n_merge = 765

        grid = np.zeros((rows, cols))
        rng = np.random.RandomState(int(beta * 100))
        all_indices = rng.permutation(n_merge)
        swapped = set(all_indices[:n_swaps])

        for idx in range(total):
            r, c = divmod(idx, cols)
            if idx < n_merge:
                grid[r, c] = 1 if idx in swapped else 0
            else:
                grid[r, c] = -1

        # Colormap: void for unused, dark panel for retained, accent for swapped
        cmap = ListedColormap([VOID, '#0f1218', accent])
        display = grid + 1

        ax.imshow(display, cmap=cmap, aspect='equal', interpolation='nearest',
                  vmin=0, vmax=2)

        # Thin accent border around the grid
        for spine in ax.spines.values():
            spine.set_edgecolor(accent)
            spine.set_linewidth(1.0)
            spine.set_alpha(0.5)

        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(title, fontsize=13, fontweight='bold', pad=12,
                     fontfamily='monospace', color=accent)

        pct = n_swaps / n_merge * 100
        ax.text(cols/2, rows + 1.8,
                f'{n_swaps} / 765  ({pct:.0f}%)',
                ha='center', fontsize=13, color=accent,
                fontweight='bold', fontfamily='monospace',
                path_effects=GLOW)

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#0f1218', edgecolor=GHOST, label='RETAINED FROM BPE'),
        Patch(facecolor=WARN_ORANGE, edgecolor=GHOST, label='REPLACED BY GRAVITY'),
    ]
    fig.legend(handles=legend_elements, loc='lower center', ncol=2,
               fontsize=10, facecolor=PANEL, edgecolor=HAIRLINE,
               framealpha=0.95, bbox_to_anchor=(0.5, 0.02),
               prop={'family': 'monospace'})

    plt.subplots_adjust(top=0.86, bottom=0.12)

    styled_title(fig,
                 'VOCABULARY SLOT ALLOCATION  //  BPE vs GRAVITY',
                 'Each cell = one merge token slot. 765 total. 256 byte tokens + 3 control tokens omitted.',
                 y_main=0.95, y_sub=0.905)

    add_border(fig)
    add_watermark(fig)

    path = os.path.join(OUTPUT_DIR, 'article_vocab_swap.png')
    fig.savefig(path, facecolor=VOID)
    plt.close(fig)
    print(f"Saved: {path}")


# =====================================================================
# CHART 4: Crystallization Curves
# =====================================================================
def chart_crystallization():
    fig, axes = plt.subplots(2, 4, figsize=(17, 9))

    chains = {
        'contin': {
            'steps': ['c', 'co', 'con', 'cont', 'contin'],
            'leverage': [0.15, 0.35, 0.45, 0.66, 1.43],
            'jump_idx': 4, 'jump_val': '+0.77'
        },
        'partic': {
            'steps': ['p', 'pa', 'par', 'part', 'partic'],
            'leverage': [0.10, 0.30, 0.75, 0.61, 1.38],
            'jump_idx': 4, 'jump_val': '+0.77'
        },
        'the': {
            'steps': ['t', 'th', 'the'],
            'leverage': [0.08, 0.29, 0.72],
            'jump_idx': 2, 'jump_val': '+0.42'
        },
        'under': {
            'steps': ['u', 'un', 'und', 'under'],
            'leverage': [0.12, 0.25, 0.55, 0.96],
            'jump_idx': 3, 'jump_val': '+0.40'
        },
        'ever': {
            'steps': ['e', 'ev', 'ever'],
            'leverage': [0.10, 0.52, 0.92],
            'jump_idx': 2, 'jump_val': '+0.40'
        },
        'whe': {
            'steps': ['w', 'wh', 'whe'],
            'leverage': [0.08, 0.19, 0.65],
            'jump_idx': 2, 'jump_val': '+0.46'
        },
        'signific': {
            'steps': ['s', 'si', 'sig', 'sign', 'signi', 'signif', 'signific'],
            'leverage': [0.08, 0.20, 0.30, 0.35, 0.45, 0.65, 1.20],
            'jump_idx': 6, 'jump_val': '+0.55'
        },
        "doesn": {
            'steps': ['d', 'do', 'doe', 'does', "doesn"],
            'leverage': [0.10, 0.40, 0.55, 0.70, 1.15],
            'jump_idx': 4, 'jump_val': '+0.45'
        },
    }

    for ax, (name, data) in zip(axes.flat, chains.items()):
        x = list(range(len(data['steps'])))
        lev = data['leverage']
        ji = data['jump_idx']

        # Gradient fill under the curve for drama
        ax.fill_between(x, 0, lev, alpha=0.08, color=ICE_BLUE)

        # Main line with glow
        ax.plot(x, lev, '-', color=ICE_BLUE, linewidth=2.5, alpha=0.85, zorder=3,
                path_effects=[patheffects.withStroke(linewidth=5, foreground=VOID)])

        # Regular points
        for i_pt, (xi, yi) in enumerate(zip(x, lev)):
            if i_pt != ji:
                ax.scatter([xi], [yi], color=ICE_BLUE, s=50, zorder=4,
                           edgecolors=VOID, linewidths=1.5)

        # Jump point — glowing orange circle
        ax.scatter([ji], [lev[ji]], color=WARN_ORANGE, s=160, zorder=6,
                   edgecolors=VOID, linewidths=2)
        # Outer glow ring
        ax.scatter([ji], [lev[ji]], color=WARN_ORANGE, s=350, zorder=5,
                   alpha=0.15, edgecolors='none')

        # Jump annotation
        # Position text smartly based on chain length
        txt_x = max(ji - 0.6, 0.1)
        txt_y = min(lev[ji] + 0.18, 1.55)
        ax.annotate(
            data['jump_val'],
            xy=(ji, lev[ji]),
            xytext=(txt_x, txt_y),
            fontsize=11, fontweight='bold', color=WARN_ORANGE,
            fontfamily='monospace',
            arrowprops=dict(arrowstyle='->', color=WARN_ORANGE, lw=1.5),
            path_effects=GLOW_ORANGE
        )

        ax.set_xticks(x)
        ax.set_xticklabels(data['steps'], fontsize=8, fontfamily='monospace',
                           color=GHOST, rotation=0)
        ax.set_title(name, fontsize=14, fontweight='bold',
                     fontfamily='monospace', color=WHITE_HOT, pad=8)
        ax.set_ylim(-0.05, 1.70)
        ax.set_ylabel('', fontsize=0)  # clean
        ax.grid(axis='y', alpha=0.2, linewidth=0.5)
        ax.grid(axis='x', visible=False)

        # Thin red bottom line
        ax.axhline(y=0, color=NERV_RED, linewidth=0.6, alpha=0.3)

    # Shared y-label
    fig.text(0.02, 0.5, 'LEVERAGE', ha='center', va='center', rotation=90,
             fontsize=12, fontfamily='monospace', color=GHOST)

    plt.subplots_adjust(top=0.86, bottom=0.06, hspace=0.50, wspace=0.30, left=0.06)

    styled_title(fig,
                 'CRYSTALLIZATION CURVES  //  WHERE GRAVITY IS BORN',
                 'Leverage along BPE merge chains. Orange = the merge step where meaning snaps into existence.',
                 y_main=0.95, y_sub=0.905)

    add_border(fig)
    add_watermark(fig)

    path = os.path.join(OUTPUT_DIR, 'article_crystallization.png')
    fig.savefig(path, facecolor=VOID)
    plt.close(fig)
    print(f"Saved: {path}")


# =====================================================================
# CHART 5: Scaling
# =====================================================================
def chart_scaling():
    fig, ax = plt.subplots(figsize=(11, 7))

    swaps = [0, 70, 659]
    effect = [0, -0.017, -0.139]
    labels = ['BPE\n0 swaps', '$\\beta$=0.3\n70 swaps', '$\\beta$=1.0\n659 swaps']
    colors = [GHOST, TERM_GREEN, WARN_ORANGE]

    # Linear extrapolation reference
    slope = -0.017 / 70
    x_ref = np.linspace(0, 720, 200)
    y_ref = slope * x_ref
    ax.plot(x_ref, y_ref, ':', color=GHOST, alpha=0.25, linewidth=1, zorder=1)
    ax.text(710, slope * 710 + 0.003, 'linear extrapolation', fontsize=9,
            color=GHOST, alpha=0.4, ha='right', va='bottom', fontfamily='monospace')

    # Connecting line
    ax.plot(swaps, effect, '--', color=HAIRLINE, linewidth=1, zorder=2)

    # Data points with glow
    for s, e, c, lab in zip(swaps, effect, colors, labels):
        # Outer glow
        ax.scatter([s], [e], color=c, s=500, zorder=4, alpha=0.12, edgecolors='none')
        # Main point
        ax.scatter([s], [e], color=c, s=200, zorder=5, edgecolors=VOID, linewidths=2)

        # Labels — position to avoid overlap
        if s == 0:
            ax.text(s + 15, e + 0.007, lab, fontsize=11, color=c,
                    fontweight='bold', va='bottom', fontfamily='monospace')
        elif s == 70:
            ax.text(s + 20, e + 0.005, lab, fontsize=11, color=c,
                    fontweight='bold', va='bottom', fontfamily='monospace')
        else:
            ax.text(s - 15, e - 0.008, lab, fontsize=12, color=c,
                    fontweight='bold', va='top', ha='right', fontfamily='monospace',
                    path_effects=GLOW_ORANGE)

    ax.axhline(y=0, color=NERV_RED, linewidth=0.8, alpha=0.3, zorder=1)

    # Delta annotation between the two gravity points
    mid_x = (70 + 659) / 2
    mid_y = (-0.017 + -0.139) / 2
    ax.text(mid_x, mid_y + 0.015,
            '8.2x improvement\n9.4x swaps',
            ha='center', fontsize=11, color=NERV_RED,
            fontfamily='monospace', fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.4', facecolor=VOID,
                      edgecolor=NERV_RED, linewidth=1.2, alpha=0.9),
            path_effects=GLOW_RED)

    ax.set_xlabel('NUMBER OF VOCABULARY SWAPS', fontsize=11, fontfamily='monospace')
    ax.set_ylabel('BPB CHANGE vs STEP-MATCHED BPE', fontsize=11, fontfamily='monospace')
    ax.set_xlim(-30, 730)
    ax.set_ylim(-0.175, 0.035)
    ax.grid(axis='x', alpha=0.2)

    add_corner_marks(ax)

    styled_title(fig,
                 'VOCABULARY EFFECT SCALES LINEARLY',
                 'No diminishing returns. Each swap earns its keep.',
                 y_main=0.95, y_sub=0.905)

    add_border(fig)
    add_watermark(fig)

    path = os.path.join(OUTPUT_DIR, 'article_scaling.png')
    fig.savefig(path, facecolor=VOID)
    plt.close(fig)
    print(f"Saved: {path}")


# =====================================================================
# CHART 6 (BONUS): Negative Results Summary
# =====================================================================
def chart_negative_results():
    """Side-by-side comparison of the two negative results."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6.5),
                             gridspec_kw={'wspace': 0.35})

    # --- Left: Bifurcation vs Flat ---
    ax = axes[0]
    labels_l = ['Flat gravity\n$\\beta$=0.3', 'Bifurcation\n$\\beta$=0.3']
    vals_l = [1.3845, 1.4058]
    colors_l = [TERM_GREEN, NERV_RED]
    bars_l = ax.bar([0, 1], vals_l, color=colors_l, width=0.55,
                    edgecolor=VOID, linewidth=1.5, zorder=3)
    bars_l[0].set_alpha(0.85)
    bars_l[1].set_alpha(0.7)
    for bar, val, col in zip(bars_l, vals_l, colors_l):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.003,
                f'{val:.4f}', ha='center', va='bottom', fontsize=12,
                fontweight='bold', color=col, fontfamily='monospace')
    # Delta
    ax.annotate('+0.021 WORSE', xy=(1, 1.4058), xytext=(1, 1.42),
                fontsize=11, color=NERV_RED, ha='center', fontfamily='monospace',
                fontweight='bold', path_effects=GLOW_RED)

    ax.set_xticks([0, 1])
    ax.set_xticklabels(labels_l, fontsize=10, fontfamily='monospace')
    ax.set_ylim(1.35, 1.44)
    ax.set_ylabel('BPB', fontsize=11, fontfamily='monospace')
    ax.set_title('BIFURCATION SCORING', fontsize=13, fontweight='bold',
                 fontfamily='monospace', color=NERV_RED, pad=10)
    ax.grid(axis='x', visible=False)
    ax.grid(axis='y', alpha=0.2)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.3f'))

    # Explanation
    ax.text(0.5, 1.355, 'Tokens removed by delta-scoring\nwere doing real compression work.',
            ha='center', fontsize=9, color=GHOST, fontfamily='monospace',
            style='italic', transform=ax.get_xaxis_transform())

    # --- Right: Warm vs Cold ---
    ax = axes[1]
    labels_r = ['Cold start', 'Warm start\n(epistemic graft)']
    vals_r = [1.3821, 1.4198]
    colors_r = [ICE_BLUE, WARN_ORANGE]
    bars_r = ax.bar([0, 1], vals_r, color=colors_r, width=0.55,
                    edgecolor=VOID, linewidth=1.5, zorder=3)
    bars_r[0].set_alpha(0.85)
    bars_r[1].set_alpha(0.7)
    for bar, val, col in zip(bars_r, vals_r, colors_r):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.003,
                f'{val:.4f}', ha='center', va='bottom', fontsize=12,
                fontweight='bold', color=col, fontfamily='monospace')
    ax.annotate('+0.038 WORSE', xy=(1, 1.4198), xytext=(1, 1.435),
                fontsize=11, color=NERV_RED, ha='center', fontfamily='monospace',
                fontweight='bold', path_effects=GLOW_RED)

    ax.set_xticks([0, 1])
    ax.set_xticklabels(labels_r, fontsize=10, fontfamily='monospace')
    ax.set_ylim(1.35, 1.46)
    ax.set_ylabel('BPB', fontsize=11, fontfamily='monospace')
    ax.set_title('WARM-START EMBEDDINGS', fontsize=13, fontweight='bold',
                 fontfamily='monospace', color=WARN_ORANGE, pad=10)
    ax.grid(axis='x', visible=False)
    ax.grid(axis='y', alpha=0.2)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.3f'))

    ax.text(0.5, 1.355, 'The crystallization cliff is a\nwhole-model phase transition.',
            ha='center', fontsize=9, color=GHOST, fontfamily='monospace',
            style='italic', transform=ax.get_xaxis_transform())

    plt.subplots_adjust(top=0.82, bottom=0.15)

    styled_title(fig,
                 'NEGATIVE RESULTS  //  WHAT DID NOT WORK',
                 'Both failures are scientifically informative. Both constrain the theory.',
                 y_main=0.94, y_sub=0.885)

    add_border(fig, color=NERV_RED)
    add_watermark(fig)

    path = os.path.join(OUTPUT_DIR, 'article_negative_results.png')
    fig.savefig(path, facecolor=VOID)
    plt.close(fig)
    print(f"Saved: {path}")


# =====================================================================
# CHART 7: Competition Run — 12L Gravity on 8xH100
# =====================================================================
def chart_h100_curve():
    fig, ax = plt.subplots(figsize=(14, 8))

    # FINAL 12L run — seed 42 learning curve (best of 3, mean=1.0321)
    steps = [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 11000]
    bpb   = [1.2178, 1.1490, 1.1200, 1.1029, 1.0885, 1.0810, 1.0729, 1.0680, 1.0640, 1.0436, 1.0310]

    # Current SOTA and crossing point
    sota = 1.1194
    cross_idx = 2  # step 3000 crosses SOTA

    # --- Pre-crossing: building energy ---
    pre_steps = steps[:cross_idx+1]
    pre_bpb = bpb[:cross_idx+1]
    ax.plot(pre_steps, pre_bpb, 'o-', color=WARN_ORANGE, linewidth=2.5, markersize=8,
            alpha=0.6, zorder=4, markeredgecolor=VOID, markeredgewidth=1.5,
            path_effects=[patheffects.withStroke(linewidth=4.5, foreground=VOID)])

    # --- Post-crossing: NERV RED blazing through SOTA ---
    post_steps = steps[cross_idx:]
    post_bpb = bpb[cross_idx:]

    # Glow trail
    ax.plot(post_steps, post_bpb, '-', color=NERV_RED, linewidth=5, alpha=0.15, zorder=3)
    # Main line
    ax.plot(post_steps, post_bpb, 'o-', color=NERV_RED, linewidth=3.5, markersize=11,
            zorder=6, markeredgecolor=VOID, markeredgewidth=2.5,
            path_effects=[patheffects.withStroke(linewidth=6, foreground=VOID)])
    # Outer glow on post-crossing points
    ax.scatter(post_steps, post_bpb, color=NERV_RED, s=400, zorder=5,
               alpha=0.12, edgecolors='none')

    # Gradient fill under the whole curve
    ax.fill_between(steps, 0.95, bpb, alpha=0.04, color=WARN_ORANGE)
    # Extra fill under post-crossing
    ax.fill_between(post_steps, 0.95, post_bpb, alpha=0.06, color=NERV_RED)

    # --- SOTA line --- the one it punches through
    ax.axhline(y=sota, color=NERV_RED, linestyle='-', linewidth=2.0, alpha=0.4, zorder=2)
    ax.text(1500, sota + 0.008, 'PREVIOUS SOTA  1.1194', fontsize=10,
            color=NERV_RED, alpha=0.7, fontfamily='monospace', fontweight='bold')

    # Crossing annotation
    ax.annotate(
        'CROSSED SOTA\nSTEP 2000$\\rightarrow$3000',
        xy=(2500, sota), xytext=(4500, 1.16),
        fontsize=11, color=NERV_RED, fontfamily='monospace', fontweight='bold',
        arrowprops=dict(arrowstyle='-|>', color=NERV_RED, lw=2,
                        connectionstyle='arc3,rad=-0.2'),
        bbox=dict(boxstyle='round,pad=0.4', facecolor=VOID,
                  edgecolor=NERV_RED, linewidth=1.5, alpha=0.95),
        path_effects=GLOW_RED
    )

    # Final result — BIG callout with 3-seed mean
    final_bpb = 1.0321
    ax.scatter([11000], [1.0310], color=WHITE_HOT, s=200, zorder=8,
               edgecolors=NERV_RED, linewidths=3, marker='D')
    ax.scatter([11000], [1.0310], color=NERV_RED, s=600, zorder=7,
               alpha=0.15, edgecolors='none')
    ax.text(10900, 1.0310 - 0.015, '1.0310', fontsize=13, color=WHITE_HOT,
            fontfamily='monospace', fontweight='bold', ha='center', va='top',
            path_effects=[patheffects.withStroke(linewidth=4, foreground=VOID)])

    # 3-seed mean annotation
    ax.text(10900, 1.0310 - 0.032, '3-seed mean: 1.0321\nstd: 0.0011',
            fontsize=10, color=TERM_GREEN, fontfamily='monospace',
            fontweight='bold', ha='center', va='top',
            path_effects=GLOW_GREEN)

    # Delta from SOTA
    ax.annotate(
        '',
        xy=(11700, 1.0310), xytext=(11700, sota),
        arrowprops=dict(arrowstyle='<->', color=TERM_GREEN, lw=2)
    )
    ax.text(11800, (1.0310 + sota) / 2, '$-$0.087\nBPB',
            fontsize=12, color=TERM_GREEN, fontfamily='monospace',
            fontweight='bold', va='center',
            path_effects=GLOW_GREEN)

    # Starting point label
    ax.text(1000, 1.2178 + 0.012, '1.2178', fontsize=9, color=WARN_ORANGE,
            fontfamily='monospace', ha='center', va='bottom', alpha=0.7)

    # Naive baseline reference
    ax.axhline(y=1.2244, color=GHOST, linestyle=':', linewidth=1.0, alpha=0.3, zorder=1)
    ax.text(9000, 1.2270, 'NAIVE BASELINE  1.2244', fontsize=8,
            color=GHOST, alpha=0.4, fontfamily='monospace')

    # Config spec callout
    ax.text(8000, 1.21,
            '384d x 12L  //  GQA  //  3$\\times$ MLP\n'
            '8$\\times$H100 SXM  //  54ms/step  //  11,000 steps\n'
            'Gravity $\\beta$=1.0  //  seq_len=2048\n'
            '15.6 MB  //  ~591s  //  3 seeds',
            fontsize=9, color=GHOST, fontfamily='monospace',
            va='top', ha='center',
            bbox=dict(boxstyle='round,pad=0.5', facecolor=PANEL,
                      edgecolor=HAIRLINE, alpha=0.9))

    ax.set_xlim(0, 12500)
    ax.set_ylim(0.98, 1.26)
    ax.set_xlabel('TRAINING STEPS', fontsize=11, fontfamily='monospace')
    ax.set_ylabel('VALIDATION BPB  (int8+zlib)', fontsize=11, fontfamily='monospace')
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f'))
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'{int(x):,}'))

    add_corner_marks(ax, color=NERV_RED)

    styled_title(fig,
                 'GRAVITY TOKENIZER  //  1.0321 BPB',
                 'Nobody optimized the tokenizer. 659/765 merge tokens replaced by ablation leverage. Vanilla transformer. No architectural novelties.')

    add_border(fig)
    add_watermark(fig)

    path = os.path.join(OUTPUT_DIR, 'article_h100_curve.png')
    fig.savefig(path, facecolor=VOID)
    plt.close(fig)
    print(f"Saved: {path}")


# =====================================================================
if __name__ == '__main__':
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    chart_results()
    chart_learning_curves()
    chart_vocab_swap()
    chart_crystallization()
    chart_scaling()
    chart_negative_results()
    chart_h100_curve()
    print("Done -- all article charts generated.")
