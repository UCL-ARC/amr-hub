"""
Plot stacked bars of contact pair types from ``run_experiments.py`` output.

Produces two figures: share of contact observations and share of contact
duration attributable to HCW-HCW, HCW-patient and patient-patient pairs. Also
prints a markdown table of mean percentages. Run from ``python-code/``::

    uv run python contact_analysis/plot_contact_types.py
"""

import argparse
import csv
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PAIR_TYPES = ("hcw_hcw", "hcw_patient", "patient_patient")
LABELS = {
    "hcw_hcw": "HCW-HCW",
    "hcw_patient": "HCW-patient",
    "patient_patient": "Patient-patient",
}
COLOURS = {"hcw_hcw": "#1b6ca8", "hcw_patient": "#e08a1e", "patient_patient": "#4c9a5b"}
CASE_ORDER = [
    ("fixed", 1),
    ("fixed", 0),
    ("deadline_paced", 1),
    ("deadline_paced", 0),
]


def case_label(strategy: str, stochastic: int) -> str:
    """Return a two-line axis label for a case."""
    noise = "stochastic" if stochastic else "non-stochastic"
    return f"{strategy}\n{noise}"


def load(path: Path) -> list[dict[str, str]]:
    """Read the raw per-run CSV."""
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def mean_percentages(rows: list[dict[str, str]], prefix: str) -> np.ndarray:
    """Return mean per-run percentage by pair type, shape (cases, types)."""
    result = np.zeros((len(CASE_ORDER), len(PAIR_TYPES)))
    for i, (strategy, stochastic) in enumerate(CASE_ORDER):
        selected = [
            r
            for r in rows
            if r["strategy"] == strategy and int(r["stochastic"]) == stochastic
        ]
        values = np.array(
            [[float(r[f"{prefix}_{t}"]) for t in PAIR_TYPES] for r in selected]
        )
        totals = values.sum(axis=1, keepdims=True)
        shares = np.divide(values, totals, out=np.zeros_like(values), where=totals > 0)
        result[i] = 100 * shares.mean(axis=0)
    return result


def stacked_bar(percentages: np.ndarray, title: str, output: Path) -> None:
    """Draw and save one stacked percentage bar chart."""
    fig, ax = plt.subplots(figsize=(8, 5))
    positions = np.arange(len(CASE_ORDER))
    bottom = np.zeros(len(CASE_ORDER))
    for j, t in enumerate(PAIR_TYPES):
        ax.bar(
            positions,
            percentages[:, j],
            bottom=bottom,
            label=LABELS[t],
            color=COLOURS[t],
        )
        for i, value in enumerate(percentages[:, j]):
            if value >= 4:
                ax.text(
                    i,
                    bottom[i] + value / 2,
                    f"{value:.1f}%",
                    ha="center",
                    va="center",
                    color="white",
                    fontsize=9,
                )
        bottom += percentages[:, j]
    ax.set_xticks(positions, [case_label(*c) for c in CASE_ORDER])
    ax.set_ylim(0, 100)
    ax.set_ylabel("Share of total (%)")
    ax.set_title(title)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=3, frameon=False)
    fig.tight_layout()
    fig.savefig(output, dpi=150)
    plt.close(fig)


def main() -> None:
    """Generate both figures and print the summary tables."""
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
    figures = (
        (
            "observations",
            "Contact observations by pair type",
            "contact-counts-by-type.png",
        ),
        ("duration_s", "Contact duration by pair type", "contact-duration-by-type.png"),
    )
    for prefix, title, filename in figures:
        percentages = mean_percentages(rows, prefix)
        stacked_bar(percentages, title, args.output_dir / filename)
        print(f"\n{title} (mean % per run)\n")  # noqa: T201
        print("| Case | HCW-HCW | HCW-patient | Patient-patient |")  # noqa: T201
        print("|---|---|---|---|")  # noqa: T201
        for (strategy, stochastic), values in zip(CASE_ORDER, percentages, strict=True):
            label = case_label(strategy, stochastic).replace("\n", " / ")
            cells = " | ".join(f"{v:.1f}%" for v in values)
            print(f"| {label} | {cells} |")  # noqa: T201


if __name__ == "__main__":
    main()
