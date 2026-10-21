# AMR-HUB JupyterLab and progress report

The database is attached read-only as catalog `output`, which stored views
refer to. Outputs go to `/outputs/progress_report`.

## Build (outside the TRE)

```bash
docker build --platform linux/amd64 -t amr-bc-jupyter-report .
docker save -o amr-bc-jupyter-report.tar amr-bc-jupyter-report
```

Inside the TRE, after the airlock:

```bash
docker load -i amr-bc-jupyter-report.tar
```

## Progress report

```bash
docker run --rm \
  -v /path/to/dbdir:/data:ro \
  -v /path/to/out:/outputs \
  --entrypoint /app/run_progress_report.sh \
  amr-bc-jupyter-report [--db my_database.duckdb] [--refresh-crosswalk]
```

`--db` is needed only if `/data` has more than one `.db`/`.duckdb` file.
`/outputs/ws_crosswalk.csv` is reused if present; `--refresh-crosswalk`
regenerates it.

Outputs: `01_overall_summary.png` to `09_example_sequence.png`, the matching
CSVs and `REPORT_INDEX.txt`.

## JupyterLab

```bash
docker run --rm \
  -p 127.0.0.1:8888:8888 \
  -v /path/to/dbdir:/data:ro \
  -v /path/to/out:/outputs \
  amr-bc-jupyter-report
```

The progress report can also be run from a JupyterLab terminal with
`/app/run_progress_report.sh`.
