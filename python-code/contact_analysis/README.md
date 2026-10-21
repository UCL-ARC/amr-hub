# Contact analysis experiments

Scripts for comparing agent movement strategies (`fixed` vs `deadline_paced`,
stochastic vs non-stochastic) by contact pair type. Run from `python-code/`.

1. Run the seeded experiments and save raw per-run metrics:

   ```bash
   uv run python contact_analysis/run_experiments.py --replicates 30 --step-seconds 1 --workers 16
   ```

   This writes `contact_analysis/results/contact_pair_types.csv`.

2. Plot figures into `docs/` (stacked percentage bars by pair type, plus
   absolute metrics with confidence intervals and episode counts/lengths):

   ```bash
   uv run python contact_analysis/plot_contact_types.py
   uv run python contact_analysis/plot_contact_summary.py
   ```

Results use only the synthetic fixture in `tests/inputs/`.
