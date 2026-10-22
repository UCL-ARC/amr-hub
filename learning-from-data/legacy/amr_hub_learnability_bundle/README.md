# AMR-HUB canonical sequence and learnability

Builds the canonical rostered event table and runs held-out learnability tests
(whole-shift split). Writes to `/outputs/learnability_analysis/`. Uses
`/outputs/ws_crosswalk.csv` from the progress report if it exists.

## Build

```bash
docker build -t amr-learnability:latest .
```

Offline, on top of the activity-exploration image:

```bash
docker build \
  -f Dockerfile.reuse \
  --build-arg BASE_IMAGE=amr-activity-exploration:latest \
  -t amr-learnability:latest .
```

## Run

```bash
docker run --rm \
  -v "$HOME/amr_data:/data:ro" \
  -v "$HOME/amr_outputs:/outputs" \
  amr-learnability:latest
```

Add `--db FILE` if `/data` has more than one database. Other options: `--seed`
(default `20260813`), `--train-fraction`, `--min-group-shifts`,
`--min-group-test-pairs`, `--include-timestamps`.

## Outputs

- `LEARNABILITY_REPORT.md`, `REPORT_INDEX.txt`
- `canonical_events.parquet`: event-level sequence with pseudonymous staff and
  shift IDs; no absolute timestamps unless `--include-timestamps`
- `canonical_events_sample.csv`: first 5,000 rows
- `canonical_shift_summary.csv`: one row per shift
- `spatial_location_map_used.csv`, `quality_summary.csv`
- `pooled_learnability.csv`, `subgroup_learnability.csv`, `entropy_summary.csv`
- `01`–`05` SVG figures
