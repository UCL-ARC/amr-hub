"""
Plot contact metrics against the number of HCWs.

Reads every ``contact_pair_types_<N>hcw.csv`` in the results directory (written
by ``run_hcw_sweep.py``) and draws one line per movement-strategy case with 95%
Student-t error bars. Also writes a tidy summary CSV. Run from ``python-code/``::

    uv run python contact_analysis/plot_hcw_sweep.py
"""

import argparse
import csv
import re
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
from plot_contact_summary import mean_ci, overall_metrics
from plot_contact_types import CASE_ORDER, case_label, load, mean_percentages

FILENAME = re.compile(r"contact_pair_types_(\d+)hcw\.csv")
CASE_COLOURS = ["#1b6ca8", "#6fa8d6", "#e08a1e", "#f0c080"]
CASE_STYLES = ["-", "--", "-", "--"]
SHARE_NAME = "HCW-HCW share of observations (%)"
LOG_METRICS = {"Contact observations (per run)", "Number of contact episodes (per run)"}


def find_results(results_dir: Path) -> dict[int, Path]:
    """Map HCW count to results file for every matching CSV."""
    found: dict[int, Path] = {}
    for path in results_dir.glob("contact_pair_types_*hcw.csv"):
        match = FILENAME.fullmatch(path.name)
        if match:
            found[int(match.group(1))] = path
    return dict(sorted(found.items()))


def summarise(
    results: dict[int, Path],
) -> dict[str, dict[tuple[str, int], list[tuple[int, float, float]]]]:
    """Return ``metric -> case -> [(n_hcw, mean, ci_half_width)]``."""
    summary: dict[str, dict[tuple[str, int], list[tuple[int, float, float]]]] = {}
    for n_hcw, path in results.items():
        rows = load(path)
        shares = mean_percentages(rows, "observations")
        for i, case in enumerate(CASE_ORDER):
            metrics = overall_metrics(rows, *case)
            for name, values in metrics.items():
                mean, half = mean_ci(values)
                summary.setdefault(name, {}).setdefault(case, []).append(
                    (n_hcw, mean, half)
                )
            summary.setdefault(SHARE_NAME, {}).setdefault(case, []).append(
                (n_hcw, float(shares[i, 0]), 0.0)
            )
    return summary


def write_summary_csv(
    summary: dict[str, dict[tuple[str, int], list[tuple[int, float, float]]]],
    output: Path,
) -> None:
    """Write the sweep summary as a tidy CSV."""
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "strategy", "stochastic", "n_hcw", "mean", "ci95"])
        for name, cases in summary.items():
            for (strategy, stochastic), points in cases.items():
                writer.writerows(
                    [name, strategy, stochastic, n, f"{m:.4f}", f"{h:.4f}"]
                    for n, m, h in points
                )


def plot(
    summary: dict[str, dict[tuple[str, int], list[tuple[int, float, float]]]],
    output: Path,
) -> None:
    """Draw one panel per metric, one line per case."""
    names = list(summary)
    fig, axes = plt.subplots(2, 3, figsize=(16, 8))
    for ax, name in zip(axes.flat, names, strict=False):
        for case, colour, style in zip(
            CASE_ORDER, CASE_COLOURS, CASE_STYLES, strict=True
        ):
            points = summary[name][case]
            ax.errorbar(
                [p[0] for p in points],
                [p[1] for p in points],
                yerr=[p[2] for p in points],
                color=colour,
                linestyle=style,
                marker="o",
                capsize=3,
                label=case_label(*case).replace("\n", " / "),
            )
        if name in LOG_METRICS:
            ax.set_yscale("log")
        ax.set_xscale("log", base=2)
        counts = sorted({p[0] for p in summary[name][CASE_ORDER[0]]})
        ax.set_xticks(counts, [str(c) for c in counts])
        ax.set_xlabel("Number of HCWs")
        ax.set_title(name, fontsize=10)
    for ax in axes.flat[len(names) :]:
        ax.axis("off")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False)
    fig.suptitle("Contact metrics vs number of HCWs (mean, 95% CI)")
    fig.tight_layout(rect=(0, 0.05, 1, 0.96))
    fig.savefig(output, dpi=150)
    plt.close(fig)


def main() -> None:
    """Generate the sweep figure and summary CSV."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir", type=Path, default=Path("contact_analysis/results")
    )
    parser.add_argument("--output-dir", type=Path, default=Path("../docs"))
    args = parser.parse_args()

    results = find_results(args.results_dir)
    if len(results) < 2:
        msg = f"Need at least two contact_pair_types_<N>hcw.csv in {args.results_dir}."
        raise SystemExit(msg)
    summary = summarise(results)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    plot(summary, args.output_dir / "contact-hcw-sweep.png")
    write_summary_csv(summary, args.results_dir / "hcw_sweep_summary.csv")
    print(f"Plotted HCW counts: {list(results)}")  # noqa: T201


if __name__ == "__main__":
    main()
