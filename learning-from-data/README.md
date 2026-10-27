# Learning from data

Analysis scripts run inside the TRE. Images are built outside, exported with
`docker save`, and imported through the airlock. Mount the data folder
read-only at `/data` and an output folder at `/outputs`. Refer to docker run scripts saved in the shared folders and ask Kieran.

## Analyses (one script per Docker image)

| Folder                  | What it does                                                       | Input                      |
| ----------------------- | ------------------------------------------------------------------ | -------------------------- |
| `activity_exploration/` | Shift summaries, class and location transitions                    | `canonical_events.parquet` |
| `sequence_clustering/`  | Trigram features per shift, k-means for k = 2–6, Calinski–Harabasz | `canonical_events.parquet` |
| `learnability/`         | Held-out next class / next location / next room change             | `canonical_events.parquet` |
| `rollout_analysis/`     | Free-running class rollouts by seed length and context             | `canonical_events.parquet` |
| `door_matching/`        | Door codes parsed from door names                                  | `doors.csv`                |

The table is `/data/canonical_events.parquet` with `shift_id`, `event_time`,
`iclass` and optional `resolved_location`, `role`, `roster_unit`;
`door_matching` reads `/data/doors.csv` with `door_key`, `door_name`.

The canonical dataset from `legacy/amr_hub_learnability_bundle/` names the
class column `interaction_class` and leaves out `event_time` unless run with
`--include-timestamps`, so rename the column and include timestamps before
using it here.

```bash
docker build -t <name> <folder>/
docker run --rm -v "$PWD/data:/data:ro" -v "$PWD/outputs:/outputs" <name>
```

The notebooks `AMR_HUB_Free_Running_Rollout.ipynb` (reads
`learnability_analysis/canonical_events.parquet`) and
`AMR_HUB_Advanced_RISE_Demo.ipynb` (shows the advanced-demo figures) run in
JupyterLab. Notebooks are generally used more for exploratory analysis and visualisation purposes.

## Legacy

`legacy/` holds the original TRE scripts that read the database directly, and I might have more files in the TRE itself as there were iterations of the Docker and earlier code:

| Folder                                  | Input                                      | Output folder                                               |
| --------------------------------------- | ------------------------------------------ | ----------------------------------------------------------- |
| `legacy/amr_hub_progress_report/`       | database                                   | `progress_report/`, `ws_crosswalk.csv`                      |
| `legacy/amr_hub_door_jupyter_existing/` | database                                   | `door_exploration/`                                         |
| `legacy/amr_hub_activity_exploration/`  | database                                   | `activity_exploration/`                                     |
| `legacy/amr_hub_learnability_bundle/`   | database                                   | `learnability_analysis/` (incl. `canonical_events.parquet`) |
| `legacy/amr_hub_advanced_demo/`         | `canonical_events.parquet`                 | `advanced_demo_analysis/`                                   |
| `legacy/amr_hub_cluster_meeting/`       | trigram outputs in `activity_exploration/` | `cluster_meeting/`                                          |

Run order: progress report → activity exploration and learnability → advanced
demo and rollout notebook. Each folder's README or script `--help` lists its
options. The canonical dataset used above is produced by
`legacy/amr_hub_learnability_bundle/`.

## Testing with synthetic data

`python-code/data_analysis/make_synthetic_db.py` (on `main`) writes a synthetic
DuckDB file in the same schema as the TRE extract (`Data.StaffLocationEvent`
and the `Ref.*` tables). It can be used to check that the images run before
they go through the airlock. The results say nothing about real staff
behaviour; the generator follows its own fixed rules.

```bash
cd python-code
uv run python data_analysis/make_synthetic_db.py --out ../synthetic/synthetic_amr.duckdb
cd ..
docker run --rm -v "$PWD/synthetic:/data:ro" -v "$PWD/outputs:/outputs" \
  --entrypoint /app/run_progress_report.sh amr-bc-jupyter-report
docker run --rm -v "$PWD/synthetic:/data:ro" -v "$PWD/outputs:/outputs" \
  amr-learnability:latest
```

Options: `--n-staff`, `--n-days`, `--seed`, and `--noisy-fraction` (share of
staff with random room order instead of a fixed rotation).

The legacy progress report and learnability scripts run on it without changes.
Things to expect:

- The synthetic door names ("Corridor - Bay1") have no door code, so no door
  points are built and door events stay unresolved.
- The mobile workstation cart is meant to stay unresolved in the workstation
  crosswalk; only the fixed bay workstation gets placed.
- The scripts in the top-level folders read `canonical_events.parquet`, not the
  database. Run the learnability bundle with `--include-timestamps` first and
  rename `interaction_class` to `iclass` before using them.

Keep `synthetic/` and `outputs/` out of git.
