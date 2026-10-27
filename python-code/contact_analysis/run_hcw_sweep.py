"""
Run the contact experiments for a range of HCW counts.

For each requested total HCW count this generates the location timeseries (via
``generate_extra_hcws.py``) and runs the 2x2 movement-strategy experiment (via
``run_experiments.py``). Counts whose results file already exists are skipped
unless ``--force`` is given, so an interrupted sweep can be resumed. Run from
``python-code/``::

    uv run python contact_analysis/run_hcw_sweep.py --hcw-counts 2 4 8 16 24 32
"""

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent
BASE_HCWS = 2
DEFAULT_COUNTS = (2, 4, 8, 16, 24, 32)


def run(command: list[str]) -> None:
    """Run a subprocess command, raising if it fails."""
    print("+", " ".join(command), flush=True)  # noqa: T201
    subprocess.run(command, check=True)  # noqa: S603


def main() -> None:
    """Generate inputs and run experiments for each HCW count."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hcw-counts", type=int, nargs="+", default=list(DEFAULT_COUNTS)
    )
    parser.add_argument("--replicates", type=int, default=30)
    parser.add_argument("--step-seconds", type=int, default=1)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--seed", type=int, default=0, help="Generator seed.")
    parser.add_argument("--inputs-dir", type=Path, default=Path("tests/inputs"))
    parser.add_argument(
        "--results-dir", type=Path, default=Path("contact_analysis/results")
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-run counts with existing results."
    )
    args = parser.parse_args()

    for count in sorted(set(args.hcw_counts)):
        if count < BASE_HCWS:
            msg = f"HCW count must be at least {BASE_HCWS}, got {count}."
            raise SystemExit(msg)
        results = args.results_dir / f"contact_pair_types_{count}hcw.csv"
        if results.exists() and not args.force:
            print(f"Skipping {count} HCWs: {results} exists")  # noqa: T201
            continue

        experiment = [
            sys.executable,
            str(SCRIPTS / "run_experiments.py"),
            "--replicates",
            str(args.replicates),
            "--step-seconds",
            str(args.step_seconds),
            "--workers",
            str(args.workers),
            "--output",
            str(results),
        ]
        if count > BASE_HCWS:
            stem = args.inputs_dir / f"location_timeseries_{count}hcw"
            run(
                [
                    sys.executable,
                    str(SCRIPTS / "generate_extra_hcws.py"),
                    "--n-extra-hcws",
                    str(count - BASE_HCWS),
                    "--seed",
                    str(args.seed),
                    "--output-stem",
                    str(stem),
                ]
            )
            experiment += ["--location-path", str(stem.with_suffix(".duckdb"))]
        run(experiment)


if __name__ == "__main__":
    main()
