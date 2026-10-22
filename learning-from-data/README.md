# Learning from data

Analysis scripts run inside the TRE. Images are built outside, exported with
`docker save`, and imported through the airlock. Mount the data folder
read-only at `/data` and an output folder at `/outputs`.

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
JupyterLab.

## Legacy

`legacy/` holds the original TRE scripts that read the database directly:

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
