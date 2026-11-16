"""Regenerate report staffing figures from the archived stochasticity summary."""

from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

PANELS = (
    ("duration_s", "Pair-contact duration (s)"),
    ("episodes", "Contact episodes"),
    ("mean_episode_s", "Mean episode (s)"),
    ("longest_episode_s", "Longest episode (s)"),
    ("share_observations_hcw_hcw", "HCW-HCW observation share (%)"),
)


def figures(summary: pd.DataFrame, output: Path) -> None:
    """
    Plot staffing metrics, omitting the redundant observation-count panel.

    Parameters
    ----------
    summary : pandas.DataFrame
        Archived means and confidence intervals, grouped by strategy,
        stochasticity, staffing count, and metric.
    output : pathlib.Path
        Directory in which to write the two staffing figures.

    """
    output.mkdir(parents=True, exist_ok=True)
    y_limits: dict[str, tuple[float, float]] = {}
    for metric, _ in PANELS:
        points = summary[summary.metric == metric]
        lower = (points["mean"] - points.ci95).min()
        upper = (points["mean"] + points.ci95).max()
        if metric == "duration_s":
            lower = max(lower, points["mean"].min() / 2)
            y_limits[metric] = (lower / 1.1, upper * 1.1)
        else:
            padding = (upper - lower) * 0.05
            y_limits[metric] = (max(0, lower - padding), upper + padding)

    for strategy in ("fixed", "deadline_paced"):
        selected = summary[summary.strategy == strategy]
        counts = sorted(selected.n_hcw.unique())
        levels = sorted(selected.stochasticity.unique())
        fig, axes = plt.subplots(2, 3, figsize=(16, 8))
        for ax, (metric, label) in zip(axes.flat, PANELS, strict=False):
            for level in levels:
                points = selected[
                    (selected.metric == metric) & (selected.stochasticity == level)
                ].sort_values("n_hcw")
                ax.errorbar(
                    points.n_hcw,
                    points["mean"],
                    yerr=points.ci95,
                    marker="o",
                    capsize=3,
                    label=f"{level:g}",
                )
            if metric == "duration_s":
                ax.set_yscale("log")
                ax.set_ylabel("Pair-contact seconds (log scale)")
            ax.set_ylim(y_limits[metric])
            ax.set_title(label)
            ax.set_xticks(counts)
            ax.set_xlabel("HCWs")
        axes.flat[-1].set_axis_off()
        handles, labels = axes.flat[0].get_legend_handles_labels()
        axes.flat[-1].legend(handles, labels, title="Stochasticity", loc="center")
        fig.suptitle(f"{strategy}: mean and 95% Student-t CI")
        fig.tight_layout()
        fig.savefig(output / f"staffing-{strategy}.png", dpi=150)
        plt.close(fig)


if __name__ == "__main__":
    report_assets = Path(__file__).resolve().parents[2] / "docs/contact-stochasticity"
    figures(pd.read_csv(report_assets / "data/summary.csv"), report_assets)
