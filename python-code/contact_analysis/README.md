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

## Generating extra HCWs

`generate_extra_hcws.py` adds synthetic healthcare workers (ids after the
existing ones) over the same time window as the base timeseries. Each does
workstation work, patient rounds on the existing patients, and occasional WC
and restaurant visits. The input is untouched; it writes
`<output-stem>.csv` and `<output-stem>.duckdb` (schema v1).

```bash
uv run python contact_analysis/generate_extra_hcws.py --n-extra-hcws 4 --seed 0
```

Point `location_data.path` in a config at the new DuckDB file to use it. The
route table assumes the `tests/inputs/buildings.yml` layout, and the Staff Room
has only three workstations, so extra HCWs fall back to random points in the
room (logged as errors by the simulation).

## Sweeping the number of HCWs

`run_hcw_sweep.py` generates the location timeseries and runs the experiments for
each total HCW count (2 uses the original fixture). It skips counts whose
`results/contact_pair_types_<N>hcw.csv` already exists, so an interrupted sweep
can be resumed (`--force` re-runs). `plot_hcw_sweep.py` then plots each metric
against HCW count and writes `results/hcw_sweep_summary.csv`.

```bash
uv run python contact_analysis/run_hcw_sweep.py --hcw-counts 2 4 8 16 24 32 --replicates 30
uv run python contact_analysis/plot_hcw_sweep.py
```

Run time grows quickly with HCW count (32 HCWs took about an hour for 120 runs);
use `--replicates 10` for a faster pass. The generated inputs are written to
`tests/inputs/location_timeseries_<N>hcw.{csv,duckdb}`.
