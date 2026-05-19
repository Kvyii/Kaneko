from __future__ import annotations

import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker


def generate_advantage_graph(
    gold_adv: list[int],
    xp_adv: list[int] | None = None,
    *,
    is_radiant: bool = True,
) -> io.BytesIO:
    """Generate a gold/XP advantage graph and return it as a PNG buffer.

    Values are from Radiant's perspective; flipped for Dire players.
    Each index represents one minute of game time.
    """
    minutes = list(range(len(gold_adv)))
    gold = gold_adv if is_radiant else [-v for v in gold_adv]
    xp = None
    if xp_adv:
        xp = xp_adv if is_radiant else [-v for v in xp_adv]

    fig, ax = plt.subplots(figsize=(7, 3), dpi=100)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    # Symmetric Y axis
    all_values = list(gold) + (list(xp) if xp else [])
    y_max = max(abs(v) for v in all_values) if all_values else 1000
    ax.set_ylim(-y_max, y_max)

    # Gold line
    ax.plot(minutes, gold, color="#FFD700", linewidth=2, label="Gold")

    # XP line
    if xp:
        ax.plot(minutes, xp, color="#2ECC71", linewidth=2, linestyle="--", label="EXP")

    ax.axhline(0, color="#666666", linewidth=0.8)

    # Legend — no box, large text, colors match lines
    legend = ax.legend(loc="upper left", fontsize=14, frameon=False)
    for text in legend.get_texts():
        label = text.get_text()
        text.set_color("#FFD700" if label == "Gold" else "#2ECC71")

    # Clean axis labels — large, no spines
    ax.set_xlabel("Minutes", color="#CCCCCC", fontsize=13)
    ax.set_ylabel("Advantage", color="#CCCCCC", fontsize=13)
    ax.tick_params(colors="#AAAAAA", labelsize=12, length=0)
    ax.yaxis.set_major_formatter(
        ticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}k" if abs(v) >= 1000 else f"{v:.0f}")
    )
    for spine in ax.spines.values():
        spine.set_visible(False)

    # White border around the plot area
    ax.patch.set_edgecolor("white")
    ax.patch.set_linewidth(2)
    ax.patch.set_alpha(0)

    fig.tight_layout(pad=0.3)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True)
    plt.close(fig)
    buf.seek(0)
    return buf
