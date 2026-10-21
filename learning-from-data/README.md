# Learning from data

Analysis scripts run inside the TRE. Images are built outside, exported with
`docker save`, and imported through the airlock. Mount the database folder
read-only at `/data` and an output folder at `/outputs`.

## Analyses

| Folder                               | Input                                      | Output folder                                               |
| ------------------------------------ | ------------------------------------------ | ----------------------------------------------------------- |
| `amr_hub_progress_report/`           | database                                   | `progress_report/`, `ws_crosswalk.csv`                      |
| `amr_hub_door_jupyter_existing/`     | database                                   | `door_exploration/`                                         |
| `amr_hub_activity_exploration/`      | database                                   | `activity_exploration/`                                     |
| `amr_hub_learnability_bundle/`       | database                                   | `learnability_analysis/` (incl. `canonical_events.parquet`) |
| `amr_hub_advanced_demo/`             | `canonical_events.parquet`                 | `advanced_demo_analysis/`                                   |
| `amr_hub_cluster_meeting/`           | trigram outputs in `activity_exploration/` | `cluster_meeting/`                                          |
| `AMR_HUB_Free_Running_Rollout.ipynb` | `canonical_events.parquet`                 | `learnability_analysis/rollout_inspection/`                 |
| `AMR_HUB_Advanced_RISE_Demo.ipynb`   | `advanced_demo_analysis/` figures          | none                                                        |

Run order: progress report → activity exploration and learnability → advanced
demo and rollout notebook. Each folder's README or script `--help` lists its
options.

## Simplified examples

`activity_exploration/`, `sequence_clustering/`, `learnability/`,
`rollout_analysis/` and `door_matching/` are short standalone versions that
read a prepared table (`/data/canonical_events.parquet` with `shift_id`,
`event_time`, `iclass`, optional `resolved_location`, `role`, `roster_unit`;
or `/data/doors.csv` with `door_key`, `door_name`).

```bash
docker build -t <name> <folder>/
docker run --rm -v "$PWD/data:/data:ro" -v "$PWD/outputs:/outputs" <name>
```
