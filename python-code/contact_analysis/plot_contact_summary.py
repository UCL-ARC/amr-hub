"""
Plot absolute contact and episode metrics from ``run_experiments.py`` output.

Produces two figures in the output directory:

* ``contact-summary.png``: per-case means with 95% Student-t confidence
  intervals for contact observations, number of episodes, mean episode length
  and longest episode.
* ``contact-episodes-by-type.png``: per-case means split by pair type for the
  number of episodes, total contact duration and mean episode length.

Run from ``python-code/``::

    uv run python contact_analysis/plot_contact_summary.py
"""

import argparse
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from plot_contact_types import (
    CASE_ORDER,
    COLOURS,
    LABELS,
    PAIR_TYPES,
    case_label,
    load,
)
from scipy import stats

CASE_COLOURS = ["#1b6ca8", "#6fa8d6", "#e08a1e", "#f0c080"]


def case_rows(
    rows: list[dict[str, str]], strategy: str, stochastic: int
) -> list[dict[str, str]]:
    """Return the rows belonging to one case."""
    return [
        r
        for r in rows
        if r["strategy"] == strategy and int(r["stochastic"]) == stochastic
    ]


def per_run(
    rows: list[dict[str, str]], strategy: str, stochastic: int, prefix: str
) -> npt.NDArray[np.float64]:
    """Return per-run values (runs, types) for one metric prefix."""
    return np.array(
        [
            [float(r[f"{prefix}_{t}"]) for t in PAIR_TYPES]
            for r in case_rows(rows, strategy, stochastic)
        ]
    )


def mean_ci(values: npt.NDArray[np.float64]) -> tuple[float, float]:
    """Return the mean and 95% t-interval half-width of a 1D sample."""
    n = len(values)
    mean = float(values.mean())
    if n < 2 or values.std(ddof=1) == 0:
        return mean, 0.0
    sem = values.std(ddof=1) / np.sqrt(n)
    return mean, float(stats.t.ppf(0.975, n - 1) * sem)


def overall_metrics(
    rows: list[dict[str, str]], strategy: str, stochastic: int
) -> dict[str, npt.NDArray[np.float64]]:
    """Return per-run overall metrics (summed or pooled over pair types)."""
    obs = per_run(rows, strategy, stochastic, "observations").sum(axis=1)
    episodes = per_run(rows, strategy, stochastic, "episodes").sum(axis=1)
    duration = per_run(rows, strategy, stochastic, "duration_s").sum(axis=1)
    longest = per_run(rows, strategy, stochastic, "longest_episode_s").max(axis=1)
    mean_len = np.divide(
        duration, episodes, out=np.zeros_like(duration), where=episodes > 0
    )
    return {
        "Contact observations (per run)": obs,
        "Number of contact episodes (per run)": episodes,
        "Mean episode length (s)": mean_len,
        "Longest episode (s)": longest,
    }


def summary_figure(rows: list[dict[str, str]], output: Path) -> None:
    """Draw mean +/- 95% CI bars for the overall metrics."""
    metrics = [overall_metrics(rows, *case) for case in CASE_ORDER]
    names = list(metrics[0])
    fig, axes = plt.subplots(1, len(names), figsize=(16, 4.5))
    for ax, name in zip(axes, names, strict=True):
        stats_ = [mean_ci(m[name]) for m in metrics]
        means = [s[0] for s in stats_]
        errors = [s[1] for s in stats_]
        ax.barh(
            range(len(CASE_ORDER)),
            means,
            xerr=errors,
            color=CASE_COLOURS,
            capsize=4,
        )
        for i, mean in enumerate(means):
            ax.text(mean, i, f" {mean:,.1f}", va="center", fontsize=8)
        ax.set_yticks(
            range(len(CASE_ORDER)),
            [case_label(*c).replace("\n", " / ") for c in CASE_ORDER]
            if ax is axes[0]
            else [],
        )
        ax.invert_yaxis()
        ax.set_title(name, fontsize=10)
        ax.set_xlim(0, max(m + e for m, e in zip(means, errors, strict=True)) * 1.3)
    fig.suptitle("Contact metrics by case (mean, 95% CI)")
    fig.tight_layout()
    fig.savefig(output, dpi=150)
    plt.close(fig)


def stacked_absolute(
    ax: plt.Axes, rows: list[dict[str, str]], prefix: str, title: str, ylabel: str
) -> None:
    """Draw stacked mean-per-run bars by pair type for one metric."""
    means = np.array([per_run(rows, *case, prefix).mean(axis=0) for case in CASE_ORDER])
    bottom = np.zeros(len(CASE_ORDER))
    for j, t in enumerate(PAIR_TYPES):
        ax.bar(
            range(len(CASE_ORDER)),
            means[:, j],
            bottom=bottom,
            label=LABELS[t],
            color=COLOURS[t],
        )
        bottom += means[:, j]
    for i, total in enumerate(bottom):
        ax.text(i, total, f"{total:,.1f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(
        range(len(CASE_ORDER)), [case_label(*c) for c in CASE_ORDER], fontsize=8
    )
    ax.set_ylim(0, bottom.max() * 1.1)
    ax.set_title(title, fontsize=10)
    ax.set_ylabel(ylabel)


def episodes_figure(rows: list[dict[str, str]], output: Path) -> None:
    """Draw episode count, total duration and mean episode length by type."""
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    stacked_absolute(
        axes[0], rows, "episodes", "Number of episodes per run", "Episodes"
    )
    stacked_absolute(
        axes[1], rows, "duration_s", "Total contact duration per run", "Seconds"
    )

    width = 0.25
    for j, t in enumerate(PAIR_TYPES):
        heights = []
        for case in CASE_ORDER:
            episodes = per_run(rows, *case, "episodes")[:, j].sum()
            duration = per_run(rows, *case, "duration_s")[:, j].sum()
            heights.append(duration / episodes if episodes else 0.0)
        axes[2].bar(
            np.arange(len(CASE_ORDER)) + (j - 1) * width,
            heights,
            width,
            label=LABELS[t],
            color=COLOURS[t],
        )
    axes[2].set_xticks(
        range(len(CASE_ORDER)), [case_label(*c) for c in CASE_ORDER], fontsize=8
    )
    axes[2].set_title("Mean episode length by pair type", fontsize=10)
    axes[2].set_ylabel("Seconds")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(output, dpi=150)
    plt.close(fig)


def main() -> None:
    """Generate both figures."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("contact_analysis/results/contact_pair_types.csv"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("../docs"))
    args = parser.parse_args()

    rows = load(args.input)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_figure(rows, args.output_dir / "contact-summary.png")
    episodes_figure(rows, args.output_dir / "contact-episodes-by-type.png")


if __name__ == "__main__":
    main()
