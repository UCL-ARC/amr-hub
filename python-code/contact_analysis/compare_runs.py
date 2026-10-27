"""
Compare contact metrics between two ``run_experiments.py`` result files.

Prints a markdown table of mean and 95% Student-t interval per case for contact
observations, episodes, mean episode length, longest episode, and pair-type
shares. Run from ``python-code/``::

    uv run python contact_analysis/compare_runs.py BASE.csv OTHER.csv
"""

import argparse
from pathlib import Path

import numpy as np
import numpy.typing as npt
from plot_contact_summary import mean_ci, overall_metrics
from plot_contact_types import (
    CASE_ORDER,
    PAIR_TYPES,
    case_label,
    load,
    mean_percentages,
)


def fmt(values: npt.NDArray[np.float64]) -> str:
    """Format a sample as ``mean [lo, hi]``."""
    mean, half = mean_ci(values)
    return f"{mean:,.1f} [{mean - half:,.1f}, {mean + half:,.1f}]"


def main() -> None:
    """Print comparison tables for both result files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("other", type=Path)
    args = parser.parse_args()

    for path in (args.base, args.other):
        rows = load(path)
        print(f"\n### {path.name}\n")  # noqa: T201
        names = list(overall_metrics(rows, *CASE_ORDER[0]))
        print("| Case | " + " | ".join(names) + " |")  # noqa: T201
        print("|---|" + "---:|" * len(names))  # noqa: T201
        for case in CASE_ORDER:
            metrics = overall_metrics(rows, *case)
            cells = " | ".join(fmt(metrics[n]) for n in names)
            print(f"| {case_label(*case).replace(chr(10), ' / ')} | {cells} |")  # noqa: T201
        shares = mean_percentages(rows, "observations")
        print("\n| Case | " + " | ".join(PAIR_TYPES) + " |")  # noqa: T201
        print("|---|" + "---:|" * len(PAIR_TYPES))  # noqa: T201
        for case, values in zip(CASE_ORDER, shares, strict=True):
            cells = " | ".join(f"{v:.1f}%" for v in values)
            print(f"| {case_label(*case).replace(chr(10), ' / ')} | {cells} |")  # noqa: T201


if __name__ == "__main__":
    main()
