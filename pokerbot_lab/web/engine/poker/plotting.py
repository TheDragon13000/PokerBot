"""Bankroll-over-time charting with matplotlib."""

from typing import Optional

from poker.stats import Stats


def plot_bankrolls(stats: Stats, outfile: Optional[str] = "bankrolls.png",
                   show: bool = False) -> None:
    """Plot cumulative net chips vs hand number, one line per bot.

    Saves a PNG to `outfile` (if given) and optionally shows the window.
    Import is local so the rest of the package works without matplotlib installed.
    """
    import matplotlib
    if not show:
        matplotlib.use("Agg")  # headless: render to file without a display
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))
    for b in stats.seats:
        ax.plot(range(1, len(b.bankroll) + 1), b.bankroll, label=b.name)

    ax.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Hand number")
    ax.set_ylabel("Cumulative net chips")
    ax.set_title("Bankroll over time")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if outfile:
        fig.savefig(outfile, dpi=120)
        print(f"Saved chart to {outfile}")
    if show:
        plt.show()
    plt.close(fig)
